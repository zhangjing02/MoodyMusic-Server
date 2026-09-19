#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 汪峰遗漏 2 首曲目精准补采与点亮脚本
18290: 那年我五岁 (YouTube ID: 2DgF4Hl3FhQ)
18361: 多么完美的生活 (YouTube ID: iyb-pd0JwOU)
"""

import os, json, subprocess, requests, boto3

PROXY = 'http://127.0.0.1:7897'
API_BASE = 'https://m-api.changgepd.ccwu.cc'

with open('r2_config.json') as f:
    cfg = json.load(f)['buckets']['account_08']

s3 = boto3.client(
    's3',
    endpoint_url=cfg['endpoint_url'],
    aws_access_key_id=cfg['access_key_id'],
    aws_secret_access_key=cfg['secret_access_key'],
    region_name='auto'
)

tracks = [
    {
        'id': 18290,
        'title': '那年我五岁',
        'album': '果岭里29号',
        'yt_id': '2DgF4Hl3FhQ',
        'lrc_query': '汪峰 那年我五岁'
    },
    {
        'id': 18361,
        'title': '多么完美的生活',
        'album': '生无所求',
        'yt_id': 'iyb-pd0JwOU',
        'lrc_query': '汪峰 多么完美的生活'
    }
]

updates = []

for t in tracks:
    sid = t['id']
    title = t['title']
    album = t['album']
    yt_id = t['yt_id']
    
    print(f"Downloading {title} ({yt_id})...")
    temp_raw = f"/tmp/wf_{sid}_raw"
    out_mp3 = f"/tmp/wf_{sid}.mp3"
    
    cmd_dl = [
        'yt-dlp', '--proxy', PROXY,
        '-x', '--audio-format', 'mp3',
        '--audio-quality', '0',
        '-o', f'{temp_raw}.%(ext)s',
        f'https://www.youtube.com/watch?v={yt_id}'
    ]
    subprocess.run(cmd_dl, check=True)
    
    cmd_ffmpeg = [
        'ffmpeg', '-y', '-i', f'{temp_raw}.mp3',
        '-vn', '-af', 'loudnorm=I=-14:TP=-1.0:LRA=11',
        '-c:a', 'libmp3lame', '-b:a', '192k', '-ar', '44100',
        '-metadata', f'title={title}', '-metadata', 'artist=汪峰', '-metadata', f'album={album}',
        out_mp3
    ]
    subprocess.run(cmd_ffmpeg, check=True)
    
    r2_audio_key = f"music/汪峰/{album}/s_{sid}.mp3"
    s3.upload_file(out_mp3, cfg['name'], r2_audio_key, ExtraArgs={'ContentType': 'audio/mpeg'})
    print(f"Uploaded {r2_audio_key}")
    
    # 歌词
    lrc_content = None
    try:
        from syncedlyrics import search as search_lrc
        lrc_content = search_lrc(t['lrc_query'], allow_plain_format=False)
    except Exception:
        pass
        
    r2_lrc_key = None
    if lrc_content:
        lrc_file = f"/tmp/wf_{sid}.lrc"
        with open(lrc_file, 'w', encoding='utf-8') as f:
            f.write(lrc_content)
        r2_lrc_key = f"lyrics/汪峰/{album}/s_{sid}.lrc"
        s3.upload_file(lrc_file, cfg['name'], r2_lrc_key, ExtraArgs={'ContentType': 'text/plain; charset=utf-8'})
        print(f"Uploaded {r2_lrc_key}")
        
    updates.append({
        'id': sid,
        'file_path': r2_audio_key,
        'lrc_path': r2_lrc_key
    })

print(f"Lighting {len(updates)} tracks in D1...")
r = requests.post(f"{API_BASE}/api/admin/songs/batch-light", json={'updates': updates}, timeout=10)
print("D1 Response:", r.status_code, r.text)
