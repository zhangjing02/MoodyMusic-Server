#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
郑智化全专（9 张大碟，87 首曲目）音源真实性地毯式审核脚本
"""
import sys
import json
import os
import subprocess
import requests

sys.stdout.reconfigure(encoding='utf-8')

WORKSPACE = r"e:\Workspace\AI-Project\MoodyMusic-Workspace"
BASE_DIR = os.path.join(WORKSPACE, "backend")

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

with open('scratch/zheng_songs.json', 'r', encoding='utf-8') as f:
    zheng_json = json.load(f)

all_tracks = []
for art in zheng_json.get('data', []):
    for alb in art.get('albums', []):
        alb_title = alb.get('title')
        for s in alb.get('songs', []):
            all_tracks.append({
                'id': s.get('id'),
                'album': alb_title,
                'title': s.get('title'),
                'track_index': s.get('TrackIndex'),
                'path': s.get('path'),
                'lrc_path': s.get('lrc_path')
            })

print(f"待审核郑智化曲目: {len(all_tracks)} 首 (涵盖 9 张大碟)")

def get_current_info(url):
    if not url: return None, {}
    try:
        res = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration,tags',
            url
        ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=12)
        dur = 0
        tags = {}
        for line in res.stdout.splitlines():
            if line.startswith('duration='):
                dur = float(line.split('=')[1])
            elif '=' in line:
                k, v = line.split('=', 1)
                tags[k.upper()] = v
        return dur, tags
    except:
        return None, {}

def get_official_zheng_info(title, album):
    url_kw = f"http://search.kuwo.cn/r.s?client=kt&all=郑智化+{title}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=10"
    try:
        r = requests.get(url_kw, timeout=5)
        d = json.loads(r.text.replace("'", '"'))
        for item in d.get('abslist', []):
            art = item.get('ARTIST', '')
            alb = item.get('ALBUM', '')
            dur = int(item.get('DURATION', 0))
            rid = item.get('DC_TARGETID', '')
            if '郑智化' in art:
                return {'source': 'kuwo', 'rid': rid, 'artist': art, 'album': alb, 'duration': dur}
    except:
        pass

    url_ne = f"https://music.163.com/api/search/get/web?s=郑智化+{title}&type=1&limit=5"
    try:
        r = requests.get(url_ne, headers=HEADERS, timeout=5)
        for s in r.json().get('result', {}).get('songs', []):
            s_art = s.get('artists', [{}])[0].get('name', '')
            if '郑智化' in s_art:
                return {'source': 'netease', 'id': s.get('id'), 'artist': s_art, 'album': s.get('album', {}).get('name'), 'duration': s.get('duration') // 1000}
    except:
        pass
    return None

audit_results = []
print("开始审核郑智化所有曲目音频与元数据...")
for idx, t in enumerate(all_tracks, 1):
    sid = t['id']
    alb = t['album']
    tit = t['title']
    path = t['path']
    print(f"[{idx}/{len(all_tracks)}] 审核 《{alb}》 - 《{tit}》...", end="", flush=True)
    cur_dur, cur_tags = get_current_info(path)
    off_info = get_official_zheng_info(tit, alb)
    
    is_mismatch = False
    reason = "正常"
    if cur_dur is None or cur_dur < 30:
        is_mismatch = True
        reason = "无法播放或缺失"
    elif off_info and abs(cur_dur - off_info['duration']) > 15:
        is_mismatch = True
        reason = f"时长严重不符: 当前 {cur_dur:.1f}s vs 官方 {off_info['duration']}s"

    tag_artist = cur_tags.get('ARTIST') or cur_tags.get('TPE1') or ""
    if tag_artist and '郑智化' not in tag_artist:
        is_mismatch = True
        reason = f"ID3歌手标签为: {tag_artist} (非郑智化!)"

    print(f" [{'🔴 异常: ' + reason if is_mismatch else '🟢 正常'}]")
    audit_results.append({
        'id': sid,
        'album': alb,
        'title': tit,
        'path': path,
        'current_duration': cur_dur,
        'current_tags': cur_tags,
        'official_info': off_info,
        'is_mismatch': is_mismatch,
        'reason': reason
    })

with open('scratch/zheng_zhihua_full_audit.json', 'w', encoding='utf-8') as f:
    json.dump(audit_results, f, ensure_ascii=False, indent=2)

mismatches = [x for x in audit_results if x['is_mismatch']]
print(f"\n郑智化审核完毕! 共 {len(all_tracks)} 首，发现异常/错歌曲目: {len(mismatches)} 首")
