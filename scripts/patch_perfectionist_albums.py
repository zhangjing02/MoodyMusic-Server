#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 音乐曲库 - 强迫症大圆满专项补全流水线 (Patch Perfectionist Albums)
=============================================================================
目标:
攻克 18 张经典专辑中最后缺失的 35 首零散曲目，让各大传世大碟达成 100% 满贯！
存储目标: Bucket 06 (moody-music-asset-06)
"""

import os
import sys
import json
import sqlite3
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.stdout.reconfigure(encoding='utf-8')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
BASE_DIR = os.path.join(WORKSPACE, "backend")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "perfectionist_patch")
os.makedirs(WORK_DIR, exist_ok=True)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

TARGET_BUCKET_KEY = "account_06"
acc_info = cfg["buckets"][TARGET_BUCKET_KEY]
BUCKET_NAME = acc_info["name"]
PUBLIC_DOMAIN = acc_info["public_domain"]
API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

s3 = boto3.client(
    service_name="s3",
    endpoint_url=acc_info["endpoint_url"],
    aws_access_key_id=acc_info["access_key_id"],
    aws_secret_access_key=acc_info["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, connect_timeout=10, read_timeout=20)
)

db_lock = threading.Lock()

TARGET_SONG_IDS = [
    18962, 25476, 1524, 1534, 25546, 25551, 99, 51, 53, 57,
    19173, 24292, 24296, 23658, 23544, 23725, 23726, 23664,
    23667, 23751, 23758, 8555, 8523, 8526, 13641, 13677,
    13718, 13721, 13711, 13712, 25928, 25930, 25892, 25894, 25895
]

# 定向精准搜索 query 字典
CUSTOM_QUERIES = {
    18962: ["薛之谦 你不是一个人", "Joker Xue 你不是一个人"],
    25476: ["陈奕迅 且听下回分解", "Eason Chan 且聽下回分解"],
    1524: ["陈奕迅 原来这里没有你", "Eason Chan 原來這裡沒有你"],
    1534: ["陈奕迅 现场直播", "Eason Chan 現場直播"],
    25546: ["陈奕迅 给我一个吻", "Eason Chan 給我一個吻"],
    25551: ["陈奕迅 我也知道", "Eason Chan 我也知道"],
    99: ["阿杜 下雨的时候会想起你", "阿杜 下雨的時候會想起你"],
    51: ["阿杜 纯净天然无害", "阿杜 纯净 天然 无害"],
    53: ["阿杜 挂失", "A-Do 挂失"],
    57: ["阿杜 左心房", "A-Do 左心房"],
    19173: ["萧敬腾 If", "Jam Hsiao If"],
    24292: ["萧敬腾 一辈子存在", "Jam Hsiao 一輩子存在"],
    24296: ["萧敬腾 够不够", "Jam Hsiao 夠不夠"],
    23658: ["齐秦 在第六对相遇", "齊秦 在第六對相遇"],
    23544: ["齐秦 也许就足够", "齊秦 也許就足夠"],
    23725: ["齐秦 出没", "齊秦 出沒"],
    23726: ["齐秦 让我孤独的时候还能够想着你", "齊秦 讓我孤獨的時候還能夠想著你"],
    23664: ["齐秦 斗鱼", "齊秦 鬥魚"],
    23667: ["齐秦 曾几何时", "齊秦 曾幾何時"],
    23751: ["齐秦 无情的雨无情的你", "齊秦 無情的雨無情的你"],
    23758: ["齐秦 野马", "齊秦 野馬"],
    8555: ["黄品源 不喜欢说再见", "黃品源 不喜歡說再見"],
    8523: ["黄品源 别离开我", "黃品源 別離開我"],
    8526: ["黄品源 为何你就这样走", "黃品源 為何你就這樣走"],
    13641: ["齐豫 Whoever Finds This I Love You", "Chyi Yu Whoever Finds This I Love You"],
    13677: ["齐豫 Wind Beneath My Wings", "Chyi Yu Wind Beneath My Wings"],
    13718: ["齐豫 Memory", "Chyi Yu Memory"],
    13721: ["齐豫 Love's In Disguise", "Chyi Yu Love's In Disguise"],
    13711: ["齐豫 He's So Beautiful To Me", "Chyi Yu He's So Beautiful To Me"],
    13712: ["齐豫 Angels Roses and Rain", "Chyi Yu Angels, Roses, and Rain"],
    25928: ["飞儿乐团 大航海斗士", "F.I.R. 大航海斗士"],
    25930: ["飞儿乐团 花疯", "F.I.R. 花疯"],
    25892: ["飞儿乐团 雨樱花", "F.I.R. 雨櫻花"],
    25894: ["飞儿乐团 飞行部落", "F.I.R. 飛行部落"],
    25895: ["飞儿乐团 北极圈", "F.I.R. 北極圈"]
}

ARTIST_ALIASES = {
    '薛之谦': ['Joker Xue', '薛之謙'],
    '陈奕迅': ['Eason Chan', '陳奕迅'],
    '阿杜': ['A-Do', 'A Do', '杜成义'],
    '萧敬腾': ['Jam Hsiao', '蕭敬騰'],
    '齐秦': ['Chyi Chin', '齊秦'],
    '黄品源': ['Huang Pin Yuan', '黃品源'],
    '齐豫': ['Chyi Yu', '齊豫'],
    '飞儿乐团': ['F.I.R.', 'FIR']
}

BLACK_KEYWORDS = ['cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮', 'Reaction', 'reaction']

def get_official_dur(artist, title):
    clean_t = title.split('(')[0].split('（')[0].strip()
    try:
        url = f"http://music.163.com/api/search/get/web?s={requests.utils.quote(f'{artist} {clean_t}')}&type=1&offset=0&total=true&limit=3"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        songs = r.get('result', {}).get('songs', [])
        for s in songs:
            s_name = s.get('name', '')
            if clean_t.lower() in s_name.lower():
                return s.get('duration', 0) / 1000.0
        if songs:
            return songs[0].get('duration', 0) / 1000.0
    except Exception:
        pass
    return 0.0

def search_best_candidate(sid, artist, title):
    clean_t = title.split('(')[0].split('（')[0].strip()
    official_dur = get_official_dur(artist, clean_t)
    
    queries = CUSTOM_QUERIES.get(sid, [f"{artist} {clean_t}"])
    # 增加 Topic query
    queries.append(f"{artist} {clean_t} Topic")
    
    aliases = ARTIST_ALIASES.get(artist, [])
    all_names = [artist.lower()] + [a.lower() for a in aliases]
    
    for q in queries:
        cmd = [
            'yt-dlp', f'ytsearch5:{q}',
            '--dump-json',
            '--default-search', 'ytsearch',
            '--no-playlist',
            '--ignore-errors'
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=25, encoding='utf-8', errors='ignore')
            if not res.stdout:
                continue
                
            for line in res.stdout.strip().split('\n'):
                if not line:
                    continue
                try:
                    meta = json.loads(line)
                    cand_t = meta.get('title', '')
                    cand_c = meta.get('channel', '')
                    cand_u = meta.get('uploader', '')
                    dur = meta.get('duration', 0)
                    url = meta.get('webpage_url', '')
                    
                    full_text = f"{cand_t} {cand_c} {cand_u}".lower()
                    
                    # 黑名单过滤
                    if any(b in cand_t.lower() for b in BLACK_KEYWORDS):
                        continue
                        
                    # 艺人核验
                    if not any(name in full_text for name in all_names):
                        continue
                        
                    # 核心歌名核验
                    core_q = clean_t.lower()
                    # 繁简通配
                    if core_q in full_text:
                        return url, cand_t, dur
                    # 英文歌名特殊匹配
                    if any(w.lower() in full_text for w in core_q.split() if len(w) > 3):
                        return url, cand_t, dur
                        
                    # 如果时长与官方网易云音轨极其相符 (±5秒)
                    if official_dur > 0 and abs(dur - official_dur) <= 5:
                        return url, cand_t, dur
                except Exception:
                    continue
        except Exception:
            continue
            
    return None, None, 0

def process_single_song(item):
    sid, artist, album, track_idx, title = item
    print(f"\n🎯 [Target #{sid}] {artist} - 《{title}》 (来自: 《{album}》)")
    
    best_url, cand_t, dur = search_best_candidate(sid, artist, title)
    if not best_url:
        print(f"   ⚪ [{sid}] 未检索到高信度母带")
        return False, f"未检索到: {artist} - {title}"
        
    print(f"   ✅ [{sid}] 锁定音源: 【{cand_t}】 ({dur}s)")
    
    raw_f = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
    clean_f = os.path.join(WORK_DIR, f"clean_{sid}.mp3")
    
    dl_cmd = [
        'yt-dlp', '--force-overwrites', '--no-playlist',
        '-x', '--audio-format', 'mp3', '--audio-quality', '0',
        '-o', raw_f, best_url
    ]
    try:
        subprocess.run(dl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=70, check=True)
    except Exception as e:
        print(f"   ❌ [{sid}] 下载异常: {e}")
        return False, f"下载异常: {artist} - {title}"
        
    # ffmpeg 转码: EBU R128 + 160k CBR + 44.1kHz
    ff_cmd = [
        'ffmpeg', '-y', '-i', raw_f,
        '-af', 'loudnorm=I=-14:LRA=11:TP=-1.5',
        '-ar', '44100', '-b:a', '160k', '-c:a', 'libmp3lame',
        '-write_xing', '1', '-id3v2_version', '3',
        clean_f
    ]
    try:
        subprocess.run(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
        if os.path.exists(raw_f):
            os.remove(raw_f)
    except Exception as e:
        print(f"   ❌ [{sid}] 压制异常: {e}")
        return False, f"压制异常: {artist} - {title}"
        
    # 歌词抓取
    lyrics_dir = os.path.join(BASE_DIR, "storage", "lyrics", artist, album)
    os.makedirs(lyrics_dir, exist_ok=True)
    local_lrc = os.path.join(lyrics_dir, f"s_{sid}.lrc")
    lrc_text = None
    lrc_queries = [f"{artist} {title}", title]
    for lq in lrc_queries:
        try:
            lrc_text = syncedlyrics.search(lq, providers=["NetEase", "Lrclib"])
            if lrc_text and "[" in lrc_text:
                break
        except Exception:
            pass
            
    if lrc_text:
        with open(local_lrc, "w", encoding="utf-8") as f:
            f.write(lrc_text)
            
    # 上传至 Bucket 06
    r2_mp3_key = f"music/{artist}/{album}/s_{sid}.mp3"
    s3.upload_file(clean_f, BUCKET_NAME, r2_mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
    full_mp3_url = f"{PUBLIC_DOMAIN}/{r2_mp3_key}"
    print(f"   🚀 [{sid}] R2 音频上传完成: {r2_mp3_key}")
    
    full_lrc_url = None
    if os.path.exists(local_lrc):
        r2_lrc_key = f"music/{artist}/{album}/s_{sid}.lrc"
        try:
            s3.upload_file(local_lrc, BUCKET_NAME, r2_lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            full_lrc_url = f"{PUBLIC_DOMAIN}/{r2_lrc_key}"
            print(f"   📜 [{sid}] LRC 歌词已上传: {r2_lrc_key}")
        except Exception:
            pass
            
    # D1 边缘即时点亮
    payload = {"updates": [{"id": sid, "file_path": full_mp3_url, "lrc_path": full_lrc_url}]}
    try:
        resp = requests.post(API_BATCH_LIGHT_URL, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"   ✨ [{sid}] D1 即时点亮成功！")
        else:
            print(f"   ⚠️ [{sid}] D1 状态: {resp.status_code}")
    except Exception as e:
        print(f"   ⚠️ [{sid}] D1 请求异常: {e}")
        
    # 本地 SQLite 更新
    file_size = os.path.getsize(clean_f) if os.path.exists(clean_f) else 0
    with db_lock:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        c = conn.cursor()
        c.execute("""
            UPDATE tracks_sync_state 
            SET status = 'D1_LIT',
                r2_mp3_key = ?,
                r2_lrc_key = ?,
                local_mp3_path = ?,
                local_lrc = ?,
                file_size_bytes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE song_id = ?
        """, (full_mp3_url, full_lrc_url, clean_f, local_lrc if full_lrc_url else None, file_size, sid))
        conn.commit()
        conn.close()
        
    print(f"   🎉 [{sid}] {artist} - 《{title}》 完工点亮！全专圆满！")
    return True, f"成功: {artist} - {title}"

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ','.join('?' for _ in TARGET_SONG_IDS)
    c.execute(f"""
        SELECT song_id, artist_name, album_title, track_index, song_title
        FROM tracks_sync_state
        WHERE song_id IN ({placeholders}) AND status != 'D1_LIT'
        ORDER BY artist_name, album_title, track_index
    """, TARGET_SONG_IDS)
    tasks = c.fetchall()
    conn.close()
    
    print("=" * 85)
    print(f"🏆 MOODY 音乐强迫症大圆满补全引擎启动！")
    print(f"📦 待补全缺失曲目: {len(tasks)} 首 | 目标存储桶: {BUCKET_NAME}")
    print(f"🌐 公网 CDN 域名: {PUBLIC_DOMAIN}")
    print("=" * 85)
    
    success_cnt = 0
    fail_cnt = 0
    
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(process_single_song, t): t for t in tasks}
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                ok, msg = fut.result()
                if ok:
                    success_cnt += 1
                else:
                    fail_cnt += 1
            except Exception as e:
                fail_cnt += 1
                print(f"❌ 线程异常: {t[1]} - 《{t[4]}》: {e}")
                
    print("\n" + "=" * 85)
    print(f"🏁 强迫症大圆满补全执行完毕！成功点亮: {success_cnt} 首 | 留白: {fail_cnt} 首")
    print("=" * 85)

if __name__ == '__main__':
    main()
