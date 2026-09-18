#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 音乐曲库 - 分布式高并发采录引擎 [Worker 06]
=============================================================================
目标存储桶: moody-music-asset-06 (account_06)
公网 CDN 域名: https://pub-46ab5c0015d84be1b748cffecd23fdbb.r2.dev
分配歌手: 黄品源, 高胜美, 苏慧伦, 姜育恒, 陈奕迅, 邓丽君(传世大碟精选)
并发规格: 4 线程安全并发
母带规范: 100% 录音室母带 + EBU R128 + 160k CBR (44.1kHz) + Xing Header + 同步 LRC + D1 毫秒点亮
=============================================================================
"""

import os
import sys
import json
import time
import sqlite3
import subprocess
import requests
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import syncedlyrics

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
os.chdir(WORKSPACE)

BASE_DIR = os.path.join(WORKSPACE, "backend")
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
import r2_safety_guard
r2_safety_guard.assert_write_allowed("moody-music-asset-06")

DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "worker_06")
os.makedirs(WORK_DIR, exist_ok=True)

API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

TARGET_BUCKET_KEY = "account_06"
TARGET_ARTISTS = ['薛之谦', '张靓颖', '郁可唯', '方大同', '汪峰', 'JOLIN蔡依林', '曹格', '黄小琥']

# 邓丽君精选传世大碟
TERESA_TOP_ALBUMS = []

ARTIST_ALIASES = {
    '薛之谦': ['Joker Xue', '薛之謙'],
    '张靓颖': ['Jane Zhang', '張靚穎'],
    '郁可唯': ['Yisa Yu', '郁可唯'],
    '方大同': ['Khalil Fong', '方大同'],
    '汪峰': ['Wang Feng', '汪峰'],
    'JOLIN蔡依林': ['Jolin Tsai', '蔡依林', 'Jolin'],
    '曹格': ['Gary Chaw', '曹格'],
    '黄小琥': ['Tiger Huang', '黃小琥'],
    '黄品源': ['Huang Pin Yuan', '黃品源'],
    '万芳': ['Wan Fang', '萬芳', '林万芳'],
    '游鸿明': ['Chris Yu', '游鴻明'],
    '费玉清': ['Fei Yu-ching', '費玉清', '小哥'],
    '高胜美': ['Sammi Kao', '高勝美'],
    '苏慧伦': ['Tarcy Su', 'Lemon Tree'],
    '姜育恒': ['Johnny Jiang', '姜育恆'],
    '陈奕迅': ['Eason Chan', '陳奕迅'],
    '邓丽君': ['Teresa Teng', '鄧麗君']
}

TITLE_MAP = {
    "Xiao Wei": "小薇",
    "How Can You Let Me Sad": "你怎么舍得我难过",
    "Wave": "海浪",
    "Why Love You So Much": "那么爱你为什么",
    "White Egret": "白鹭鸶",
    "Wait A Thousand Years": "千年等一回",
    "Green Grass by the River": "青青河边草",
    "Crying Sand": "哭砂",
    "Duck": "鸭子",
    "Lemon Tree": "柠檬树",
    "Passive": "被动",
    "Look Back Again": "再回首",
    "Plum Blossom Three Movements": "梅花三弄",
    "Toast to the Past": "跟往事干杯",
    "Don't Let Me Drunk Alone": "别让我一个人醉",
    "Restless Heart": "驿动的心",
    "Ten Years": "十年",
    "King of Karaoke": "K歌之王",
    "Under Mount Fuji": "富士山下",
    "Exaggerated": "浮夸",
    "Long Time No See": "好久不见",
    "Red Rose": "红玫瑰",
    "Bicycle": "单车",
    "Love Transfer": "爱情转移",
    "Sweet As Honey": "甜蜜蜜",
    "The Moon Represents My Heart": "月亮代表我的心",
    "Story of Small Town": "小城故事",
    "I Only Care About You": "我只在乎你",
    "Wishing We Last Forever": "但愿人长久",
    "On the Water Side": "在水一方",
    "When Will You Return": "何日君再来",
    "Strolling Along the Path of Life": "漫步人生路",
    "Night Primrose": "夜来香"
}

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)

acc_info = r2_cfg["buckets"][TARGET_BUCKET_KEY]
BUCKET_NAME = acc_info["name"]
PUBLIC_DOMAIN = acc_info["public_domain"]

db_lock = threading.Lock()

def get_s3_client():
    return boto3.client(
        service_name="s3",
        endpoint_url=acc_info["endpoint_url"],
        aws_access_key_id=acc_info["access_key_id"],
        aws_secret_access_key=acc_info["secret_access_key"],
        region_name="auto",
        config=Config(s3={"addressing_style": "path"}, connect_timeout=10, read_timeout=20)
    )

BLACK_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会', '微电影', '剧情版', 
    '官方完整版mv', 'cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮'
]

TRUSTED_CHANNELS = [
    'topic', 'sound', 'records', 'music', 'rock', 'universal', 
    'sony', 'warner', 'avex', 'seed', 'rock records', '滾石唱片', 
    '相信音樂', '華研國際', '华谊兄弟', '福茂唱片', '亚神音乐', '索尼音乐', '环球唱片',
    'teresa teng', 'eason chan', 'huang pin yuan', 'wan fang', 'chris yu', 'fei yu-ching',
    'joker xue', 'jane zhang', 'yisa yu', 'khalil fong', 'wang feng', 'jolin tsai', 'gary chaw', 'tiger huang'
]

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

def title_matches(query_title, cand_title):
    q_core = query_title.split('(')[0].split('（')[0].strip().lower()
    c_lower = cand_title.lower()
    if q_core in c_lower:
        return True
    swaps = [('爱', '愛'), ('为', '為'), ('国', '國'), ('风', '風'), ('听', '聽'), ('说', '說'), ('话', '話'), ('见', '見'), ('来', '來'), ('欢', '歡'), ('发', '發'), ('头', '頭'), ('乐', '樂'), ('单', '單'), ('车', '車'), ('恋', '戀'), ('转', '轉'), ('关', '關')]
    q_alt = q_core
    for s1, s2 in swaps:
        if s1 in q_alt:
            q_alt = q_alt.replace(s1, s2)
        elif s2 in q_alt:
            q_alt = q_alt.replace(s2, s1)
    return q_alt in c_lower

def artist_matches(artist, cand_title, cand_channel, aliases):
    all_names = [artist.lower()] + [a.lower() for a in aliases]
    text = (cand_title + " " + cand_channel).lower()
    return any(name in text for name in all_names)

def search_candidate(artist, title, search_title, official_dur):
    clean_t = search_title.split('(')[0].split('（')[0].strip()
    aliases = ARTIST_ALIASES.get(artist, [])
    
    queries = [
        f"{artist} {clean_t} Topic",
        f"{artist} - {clean_t}",
        f"{artist} {clean_t}"
    ]
    for alias in aliases:
        queries.append(f"{alias} {clean_t} Topic")
        queries.append(f"{alias} {clean_t}")
        
    if title != search_title:
        queries.append(f"{artist} {title}")
    
    for q in queries:
        cmd = [
            'yt-dlp', '--default-search', 'ytsearch5',
            '--dump-json', '--no-playlist', f"ytsearch5:{q}"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25, encoding='utf-8', errors='ignore')
        except Exception:
            continue
            
        for line in res.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                v = json.loads(line)
            except Exception:
                continue
                
            v_title = v.get('title', '')
            v_ch = v.get('channel', '') or v.get('uploader', '')
            v_dur = v.get('duration', 0)
            v_id = v.get('id', '')
            
            lower_text = (v_title + " " + v_ch).lower()
            if any(bk in lower_text for bk in BLACK_KEYWORDS):
                continue
                
            # 1. 必须匹配歌名
            if not title_matches(search_title, v_title) and not title_matches(title, v_title):
                continue
                
            # 2. 必须匹配歌手本人
            if not artist_matches(artist, v_title, v_ch, aliases):
                continue
                
            is_trusted = any(tc in lower_text for tc in TRUSTED_CHANNELS)
            tolerance = 15 if is_trusted else 8
            
            if official_dur > 0 and v_dur > 0:
                if abs(v_dur - official_dur) <= tolerance:
                    return {'id': v_id, 'title': v_title, 'channel': v_ch, 'duration': v_dur, 'url': f"https://www.youtube.com/watch?v={v_id}"}
            else:
                if is_trusted:
                    return {'id': v_id, 'title': v_title, 'channel': v_ch, 'duration': v_dur, 'url': f"https://www.youtube.com/watch?v={v_id}"}
    return None

def fetch_lrc(artist, title, search_title):
    clean_tit = search_title.split('(')[0].split('（')[0].strip()
    queries = [f"{artist} {clean_tit}", clean_tit]
    for alias in ARTIST_ALIASES.get(artist, []):
        queries.append(f"{alias} {clean_tit}")
    if title != search_title:
        queries.append(f"{artist} {title}")
        queries.append(title)
        
    for q in queries:
        for prov in [['NetEase'], ['Lrclib'], ['Kugou']]:
            try:
                lrc = syncedlyrics.search(q, providers=prov)
                if lrc and len(lrc) > 50 and '[' in lrc and ':' in lrc:
                    return lrc
            except Exception:
                pass
    return None

def process_track(track_info):
    sid, artist, album, title = track_info
    s3 = get_s3_client()
    
    search_title = TITLE_MAP.get(title, title)
    extra_str = f" (映射: 《{search_title}》)" if search_title != title else ""
    print(f"\n🎵 [W06-{sid}] {artist} - 《{title}》{extra_str} ({album})")
    
    off_dur = get_official_dur(artist, search_title)
    cand = search_candidate(artist, title, search_title, off_dur)
    
    if not cand:
        print(f"   ⚪ [W06-{sid}] 未匹配到高信度录音室音源 -> 留白")
        with db_lock:
            conn = sqlite3.connect(DB_PATH, timeout=60.0)
            cur = conn.cursor()
            cur.execute("UPDATE tracks_sync_state SET status = 'UNLIT_SKIPPED', last_error = '未检索到高信度录音室音源', updated_at = CURRENT_TIMESTAMP WHERE song_id = ?", (sid,))
            conn.commit()
            conn.close()
        return False, f"未匹配音源: {artist} - 《{title}》"
        
    print(f"   ✅ [W06-{sid}] 命中: 【{cand['title']}】 ({cand['duration']}s | {cand['channel']})")
    
    raw_tmp = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
    clean_f = os.path.join(WORK_DIR, f"s_{sid}.mp3")
    local_lrc = os.path.join(WORK_DIR, f"s_{sid}.lrc")
    
    # 1. 下载原始音轨
    try:
        subprocess.run([
            'yt-dlp', '--force-overwrites', '--no-playlist', 
            '-x', '--audio-format', 'mp3', '--audio-quality', '0', 
            '-o', raw_tmp, cand['url']
        ], check=True, capture_output=True, timeout=90)
    except Exception as e:
        print(f"   ❌ [W06-{sid}] 下载异常: {e}")
        return False, f"下载异常: {e}"
        
    # 2. 转码 160k CBR + EBU R128 + Xing Header
    try:
        subprocess.run([
            'ffmpeg', '-y', '-i', raw_tmp, '-vn',
            '-af', 'loudnorm=I=-14:TP=-1.0:LRA=11',
            '-c:a', 'libmp3lame', '-b:a', '160k', '-ar', '44100', '-write_xing', '1',
            clean_f
        ], check=True, capture_output=True, timeout=60)
        if os.path.exists(raw_tmp):
            os.remove(raw_tmp)
    except Exception as e:
        print(f"   ❌ [W06-{sid}] 转码异常: {e}")
        return False, f"转码异常: {e}"
        
    # 3. 上传音频到 R2 (Bucket 06)
    r2_mp3_key = f"music/{artist}/{album}/s_{sid}.mp3"
    full_mp3_url = f"{PUBLIC_DOMAIN}/{r2_mp3_key}"
    try:
        s3.upload_file(clean_f, BUCKET_NAME, r2_mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        print(f"   🚀 [W06-{sid}] R2 上传完成: {r2_mp3_key}")
    except Exception as e:
        print(f"   ❌ [W06-{sid}] R2 上传失败: {e}")
        return False, f"上传失败: {e}"
        
    # 4. 抓取与上传歌词
    full_lrc_url = None
    lrc_text = fetch_lrc(artist, title, search_title)
    if lrc_text:
        with open(local_lrc, "w", encoding="utf-8") as f:
            f.write(lrc_text)
        r2_lrc_key = f"music/{artist}/{album}/s_{sid}.lrc"
        try:
            s3.upload_file(local_lrc, BUCKET_NAME, r2_lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            full_lrc_url = f"{PUBLIC_DOMAIN}/{r2_lrc_key}"
            print(f"   📜 [W06-{sid}] LRC 歌词已上传: {r2_lrc_key}")
        except Exception as e:
            print(f"   ⚠️ [W06-{sid}] LRC 上传异常: {e}")
            
    # 5. Cloudflare D1 边缘点亮
    payload = {"updates": [{"id": sid, "file_path": full_mp3_url, "lrc_path": full_lrc_url}]}
    try:
        resp = requests.post(API_BATCH_LIGHT_URL, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"   ✨ [W06-{sid}] D1 即时点亮成功！")
        else:
            print(f"   ⚠️ [W06-{sid}] D1 响应: {resp.status_code}")
    except Exception as e:
        print(f"   ⚠️ [W06-{sid}] D1 请求异常: {e}")
        
    # 6. 本地 DB 更新
    file_size = os.path.getsize(clean_f) if os.path.exists(clean_f) else 0
    with db_lock:
        conn = sqlite3.connect(DB_PATH, timeout=60.0)
        cur = conn.cursor()
        cur.execute("""
            UPDATE tracks_sync_state 
            SET r2_mp3_key = ?, 
                r2_lrc_key = ?,
                local_mp3 = ?,
                local_lrc = ?,
                file_size = ?,
                status = 'D1_LIT',
                lit_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP 
            WHERE song_id = ?
        """, (full_mp3_url, full_lrc_url, clean_f, local_lrc if full_lrc_url else None, file_size, sid))
        conn.commit()
        conn.close()
        
    print(f"   🎉 [W06-{sid}] {artist} - 《{title}》 完工点亮！")
    return True, f"成功: {artist} - 《{title}》"

def main():
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    cur = conn.cursor()
    
    placeholders = ','.join('?' for _ in TARGET_ARTISTS)
    teresa_placeholders = ','.join('?' for _ in TERESA_TOP_ALBUMS)
    
    query = f"""
        SELECT song_id, artist_name, album_title, song_title
        FROM tracks_sync_state
        WHERE (
            (artist_name IN ({placeholders}))
            OR 
            (artist_name = '邓丽君' AND album_title IN ({teresa_placeholders}))
        )
        AND (r2_mp3_key IS NULL OR r2_mp3_key = '' OR r2_mp3_key NOT LIKE 'https://%')
        AND status != 'D1_LIT'
        ORDER BY artist_name, album_title, track_index
    """
    
    params = list(TARGET_ARTISTS) + list(TERESA_TOP_ALBUMS)
    cur.execute(query, params)
    
    all_tracks = cur.fetchall()
    conn.close()
    
    print("=" * 85)
    print(f"🚀 MOODY 音乐高并发采录点亮引擎 [Worker 06] 启动！")
    print(f"📦 待处理曲目: {len(all_tracks)} 首 | 目标存储桶: {BUCKET_NAME}")
    print(f"🌐 绝对公网域名: {PUBLIC_DOMAIN}")
    print(f"⚡ 并发线程数: 4 线程安全并发")
    print(f"🎤 负责歌手: {', '.join(TARGET_ARTISTS)} + 邓丽君精选传世大碟({len(TERESA_TOP_ALBUMS)}张专)")
    print("=" * 85)
    
    success_cnt = 0
    fail_cnt = 0
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(process_track, t): t for t in all_tracks}
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
                print(f"❌ [W06] 线程异常: {t[1]} - 《{t[3]}》: {e}")
                
            done = success_cnt + fail_cnt
            if done % 10 == 0 or done == len(all_tracks):
                print(f"\n📊 [W06 进度播报] 完成: {done}/{len(all_tracks)} | 成功点亮: {success_cnt} 首 | 留白: {fail_cnt} 首\n")
                
    print("=" * 85)
    print(f"🏁 [Worker 06] 流水线执行完毕！累计点亮: {success_cnt} 首 | 留白: {fail_cnt} 首")
    print("=" * 85)

if __name__ == "__main__":
    main()
