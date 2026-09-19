import sys
import json
import requests
import subprocess
import os

sys.stdout.reconfigure(encoding='utf-8')

with open('scratch/dick_songs.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

all_songs = []
for art in d.get('data', []):
    for alb in art.get('albums', []):
        for s in alb.get('songs', []):
            all_songs.append({
                'id': s.get('id'),
                'album': alb.get('title'),
                'title': s.get('title'),
                'path': s.get('path'),
                'lrc': s.get('lrc_path')
            })

print(f"Total 迪克牛仔 tracks in catalog: {len(all_songs)}")

def get_current_duration(url):
    if not url: return None
    try:
        res = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            url
        ], capture_output=True, text=True, timeout=10)
        out = res.stdout.strip()
        for line in out.splitlines():
            if line.startswith('duration='):
                return float(line.split('=')[1])
    except Exception:
        pass
    return None

def find_kuwo_dick_cowboy(title, album):
    url = f"http://search.kuwo.cn/r.s?client=kt&all=迪克牛仔+{title}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=10"
    try:
        r = requests.get(url, timeout=5)
        d = json.loads(r.text.replace("'", '"'))
        for item in d.get('abslist', []):
            art = item.get('ARTIST', '')
            alb = item.get('ALBUM', '')
            dur = int(item.get('DURATION', 0))
            rid = item.get('DC_TARGETID', '')
            # Match 迪克牛仔
            if '迪克牛仔' in art:
                # Prefer same album or any 迪克牛仔 studio version
                is_live = 'live' in alb.lower() or '演唱会' in alb or 'live' in item.get('SONGNAME', '').lower()
                return {
                    'rid': rid,
                    'artist': art,
                    'album': alb,
                    'title': item.get('SONGNAME'),
                    'duration': dur,
                    'is_live': is_live
                }
    except Exception as e:
        pass
    return None

report = []
for idx, s in enumerate(all_songs, 1):
    sid = s['id']
    alb = s['album']
    tit = s['title']
    path = s['path']
    print(f"[{idx}/{len(all_songs)}] Auditing 《{alb}》 - 《{tit}》 (ID: {sid})...")
    kw_match = find_kuwo_dick_cowboy(tit, alb)
    report.append({
        'id': sid,
        'album': alb,
        'title': tit,
        'current_path': path,
        'kuwo_match': kw_match
    })

with open('scratch/dick_cowboy_audit_report.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\nAudit finished! Saved to scratch/dick_cowboy_audit_report.json")
