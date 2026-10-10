import os
import sys
import json
import sqlite3
import requests
import hashlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect(r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\database\catalog_sync.db')
cur = conn.cursor()

cur.execute('''
    SELECT s.album_id, a.title, art.name, t.file_size, s.id, s.title, s.file_path, s.lrc_path
    FROM songs s
    JOIN albums a ON s.album_id = a.id
    JOIN artists art ON a.artist_id = art.id
    JOIN tracks_sync_state t ON s.id = t.song_id
    WHERE (s.album_id, t.file_size) IN (
        SELECT s2.album_id, t2.file_size
        FROM songs s2
        JOIN tracks_sync_state t2 ON s2.id = t2.song_id
        WHERE t2.file_size > 1000000
        GROUP BY s2.album_id, t2.file_size
        HAVING COUNT(*) > 1
    )
    ORDER BY s.album_id, t.file_size, s.id
''')

rows = cur.fetchall()
groups = defaultdict(list)
for r in rows:
    key = (r[0], r[1], r[2], r[3])  # (album_id, album_title, artist_name, file_size)
    groups[key].append({
        'id': r[4],
        'title': r[5],
        'file_path': r[6],
        'lrc_path': r[7]
    })

print(f"Total candidate groups: {len(groups)}, total songs: {len(rows)}", flush=True)

def check_single_song(s):
    url = s['file_path']
    if not url or not url.startswith('http'):
        return None, None
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Range': 'bytes=0-4096'}, timeout=7)
        if resp.status_code in [200, 206]:
            etag = resp.headers.get('ETag', '').strip('"')
            h = hashlib.md5(resp.content).hexdigest()
            return etag, h
    except Exception:
        pass
    return None, None

def audit_group(item):
    grp_key, song_list = item
    album_id, album_title, artist_name, file_size = grp_key
    
    chunk_hashes = []
    enriched_songs = []
    
    for s in song_list:
        etag, h = check_single_song(s)
        s_copy = dict(s)
        s_copy['etag'] = etag
        s_copy['chunk_hash'] = h
        enriched_songs.append(s_copy)
        if h:
            chunk_hashes.append(h)
            
    if len(chunk_hashes) < len(song_list):
        return 'unreachable', grp_key, enriched_songs
    elif len(set(chunk_hashes)) == 1:
        return 'identical', grp_key, enriched_songs
    else:
        return 'different', grp_key, enriched_songs

identical_hash_groups = []
different_hash_groups = []
unreachable_groups = []

items = list(groups.items())
completed = 0

with ThreadPoolExecutor(max_workers=16) as pool:
    futures = {pool.submit(audit_group, item): item for item in items}
    for fut in as_completed(futures):
        completed += 1
        res_type, grp_key, s_list = fut.result()
        if res_type == 'identical':
            identical_hash_groups.append({
                'group_key': grp_key,
                'songs': s_list,
                'hash': s_list[0]['chunk_hash']
            })
        elif res_type == 'different':
            different_hash_groups.append({
                'group_key': grp_key,
                'songs': s_list
            })
        else:
            unreachable_groups.append({
                'group_key': grp_key,
                'songs': s_list
            })
        if completed % 30 == 0 or completed == len(items):
            print(f"Progress: {completed}/{len(items)} groups processed...", flush=True)

print("\n" + "=" * 60, flush=True)
print(f"Stage 1 Analysis Complete:", flush=True)
print(f"  🔴 Identical Hash Groups (100% same audio duplicate): {len(identical_hash_groups)} groups, {sum(len(g['songs']) for g in identical_hash_groups)} songs", flush=True)
print(f"  🟢 Different Hash Groups (independent audio files): {len(different_hash_groups)} groups, {sum(len(g['songs']) for g in different_hash_groups)} songs", flush=True)
print(f"  ⚪ Unreachable / Error Groups: {len(unreachable_groups)} groups", flush=True)
print("=" * 60, flush=True)

out_file = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts\stage1_audit_result.json'
with open(out_file, 'w', encoding='utf-8') as f:
    json.dump({
        'identical_hash_groups': identical_hash_groups,
        'different_hash_groups': different_hash_groups,
        'unreachable_groups': unreachable_groups
    }, f, ensure_ascii=False, indent=2)

print(f"Saved results to {out_file}", flush=True)
