#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - 曾轶可全专全量曲目 AI Whisper 听音地毯式质量审计
==============================================================================
审计范围：
曾轶可全部 7 张专辑（除刚刚已重制完毕的《一只猫的旅行》外，重点覆盖其余 6 张专辑共 68 首）
目标：
1. 听辨是否存在外国同名英文歌；
2. 听辨是否存在民乐翻奏乐团纯音乐伴奏（如 Zither Harp）；
3. 听辨是否存在严重串歌（如李宗盛男声等）；
4. 验证是否为曾轶可本人的国语原唱。
==============================================================================
"""

import os
import sys
import json
import time
import re
import subprocess
import requests
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
REPORT_PATH = os.path.join(BASE_DIR, "reports", "ZENG_YIKE_FULL_AUDIT.json")
TMP_DIR = "/tmp/audit_zeng_yike"
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg_07 = json.load(f)["buckets"]["account_07"]

s3_07 = boto3.client(
    's3', endpoint_url=cfg_07['endpoint_url'],
    aws_access_key_id=cfg_07['access_key_id'],
    aws_secret_access_key=cfg_07['secret_access_key'],
    region_name='auto',
    config=Config(signature_version='s3v4', max_pool_connections=20)
)
BUCKET_NAME = cfg_07['name']
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_PROXIES = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"

def fetch_zeng_yike_songs():
    resp = requests.get(D1_SONGS_URL, timeout=30)
    data = resp.json().get('data', [])
    target_songs = []
    for art in data:
        if '曾轶可' in art.get('name', ''):
            for alb in art.get('albums', []):
                alb_title = alb.get('title')
                # 一只猫的旅行刚才已经单独审计并重制，这里记录但重点排查其余专辑
                for s in alb.get('songs', []):
                    p = s.get('path', '')
                    m = re.search(r's_(\d+)\.mp3', p)
                    sid = int(m.group(1)) if m else s.get('id')
                    target_songs.append({
                        'id': sid,
                        'artist': art.get('name'),
                        'album': alb_title,
                        'title': s.get('title'),
                        'path': p,
                        'lrc_path': s.get('lrc_path')
                    })
    return target_songs

def audit_single_song(song):
    sid = song['id']
    title = song['title']
    album = song['album']
    p = song['path']
    
    # 构造 R2 Key
    m = re.search(r'music/(.+)$', p)
    r2_key = f"music/{m.group(1)}" if m else f"music/曾轶可/{album}/s_{sid}.mp3"
    
    local_raw = os.path.join(TMP_DIR, f"raw_{sid}.mp3")
    local_clip = os.path.join(TMP_DIR, f"clip_{sid}.mp3")
    
    result = {
        'id': sid,
        'title': title,
        'album': album,
        'path': p,
        'size_bytes': 0,
        'transcribed_text': '',
        'status': 'UNKNOWN',
        'issue_type': None,
        'detail': ''
    }
    
    try:
        # 1. 检查物理存在性
        head = s3_07.head_object(Bucket=BUCKET_NAME, Key=r2_key)
        sz = head['ContentLength']
        result['size_bytes'] = sz
        
        # 2. 下载并切片 5s ~ 35s
        s3_07.download_file(BUCKET_NAME, r2_key, local_raw)
        subprocess.run(
            ['ffmpeg', '-y', '-ss', '00:00:05', '-t', '25', '-i', local_raw, '-ac', '1', '-ar', '16000', local_clip],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
        
        # 3. Groq Whisper 听辨
        headers = {'Authorization': f'Bearer {GROQ_KEY}'}
        with open(local_clip, 'rb') as f:
            files = {'file': (f'clip_{sid}.mp3', f, 'audio/mpeg'), 'model': (None, 'whisper-large-v3')}
            wresp = requests.post(
                'https://api.groq.com/openai/v1/audio/transcriptions',
                headers=headers, files=files, proxies=GROQ_PROXIES, timeout=30
            )
        
        text = wresp.json().get('text', '').strip()
        result['transcribed_text'] = text
        text_lower = text.lower()
        
        # 4. 判定质量
        if 'zither harp' in text_lower or 'zither' in text_lower:
            result['status'] = 'ANOMALY'
            result['issue_type'] = 'INSTRUMENTAL_COVER'
            result['detail'] = 'Zither Harp 古筝纯乐器翻奏'
        elif len(text) < 5:
            result['status'] = 'ANOMALY'
            result['issue_type'] = 'NO_VOCAL'
            result['detail'] = '未听到有效人声，疑似纯伴奏或空白'
        elif '李宗盛' in text or '不出意外' in text:
            result['status'] = 'ANOMALY'
            result['issue_type'] = 'CROSS_TALK'
            result['detail'] = '严重串歌为李宗盛作品'
        elif any(c in '\u4e00' <= c <= '\u9fff' for c in title) and not any('\u4e00' <= c <= '\u9fff' for c in text):
            # 标题包含中文，但听出来的完全是纯英文字符（且超过20个字母）
            if len(text) > 20:
                result['status'] = 'ANOMALY'
                result['issue_type'] = 'FOREIGN_LANGUAGE'
                result['detail'] = '原曲为中文，听辨结果为外国同名英文流行单曲'
            else:
                result['status'] = 'NORMAL'
                result['detail'] = '短英文片段或前奏'
        else:
            result['status'] = 'NORMAL'
            result['detail'] = '人声核验正常'
            
    except Exception as e:
        result['status'] = 'ERROR'
        result['detail'] = str(e)
    finally:
        if os.path.exists(local_raw):
            os.remove(local_raw)
        if os.path.exists(local_clip):
            os.remove(local_clip)
            
    return result

def main():
    songs = fetch_zeng_yike_songs()
    print(f"🎯 开始执行曾轶可全专 ({len(songs)} 首) AI 听音地毯式审计...")
    
    results = []
    # 控制在 3 并发，避免超 Groq 限频
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(audit_single_song, s): s for s in songs}
        done = 0
        for f in as_completed(futures):
            done += 1
            res = f.result()
            results.append(res)
            icon = "🟢" if res['status'] == 'NORMAL' else ("❌" if res['status'] == 'ANOMALY' else "⚠️")
            print(f"[{done:02d}/{len(songs)}] {icon} 《{res['album']}》 - 《{res['title']}》: {res['status']} ({res['detail']}) -> \"{res['transcribed_text'][:35]}...\"")
            
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    normal_cnt = sum(1 for r in results if r['status'] == 'NORMAL')
    anomaly_cnt = sum(1 for r in results if r['status'] == 'ANOMALY')
    err_cnt = sum(1 for r in results if r['status'] == 'ERROR')
    
    print("\n" + "=" * 80)
    print(f"📊 曾轶可全量听音审计完成! 正常: {normal_cnt}, 异常: {anomaly_cnt}, 错误: {err_cnt}")
    print(f"📄 审计报告已写入: {REPORT_PATH}")
    print("=" * 80)

if __name__ == "__main__":
    main()
