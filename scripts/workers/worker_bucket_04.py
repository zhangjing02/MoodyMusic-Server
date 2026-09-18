#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 音乐曲库 - 分布式高并发采录引擎 [Worker 04]
=============================================================================
目标存储桶: moody-music-asset-04 (account_04)
公网 CDN 域名: https://pub-3507a1a1bc4b4ac3a3340833031078c2.r2.dev
分配歌手: 苏打绿, 飞儿乐团, 痛仰乐队, 徐佳莹, 曲婉婷, 卢广仲, 任贤齐
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
r2_safety_guard.assert_write_allowed("moody-music-asset-04")

DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "worker_04")
os.makedirs(WORK_DIR, exist_ok=True)

API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

TARGET_BUCKET_KEY = "account_04"
TARGET_ARTISTS = ['Beyond', '王菲', '张国荣', '罗大佑', '张惠妹', '范晓萱', '林宥嘉']

ARTIST_ALIASES = {
    'Beyond': ['黃家駒', '黄家驹', 'Wong Ka Kui', 'Beyond Band', '黄家强', '黄贯中', '叶世荣'],
    '王菲': ['Faye Wong', '王靖雯', 'Shirley Wong'],
    '张国荣': ['Leslie Cheung', '哥哥', '張國榮'],
    '罗大佑': ['Lo Ta-yu', '羅大佑'],
    '张惠妹': ['A-Mei', 'aMEI', '張惠妹', '阿妹'],
    '范晓萱': ['Mavis Fan', '范曉萱'],
    '林宥嘉': ['Yoga Lin', '林宥嘉'],
    '飞儿乐团': ['F.I.R.', 'FIR'],
    '苏打绿': ['Sodagreen', '魚丁糸'],
    '痛仰乐队': ['痛仰', 'Miserable Faith', '痛苦的信仰'],
    '徐佳莹': ['Lala Hsu', '徐佳瑩'],
    '曲婉婷': ['Wanting Qu', 'Wanting'],
    '卢广仲': ['Crowd Lu', '盧廣仲'],
    '任贤齐': ['Richie Jen', '任賢齊']
}

TITLE_MAP = {
    "Look Over Here Girl": "对面的女孩看过来",
    "The Sad Pacific": "伤心太平洋",
    "Sad Pacific": "伤心太平洋",
    "I'm a Fish": "我是一只鱼",
    "I Am a Fish": "我是一只鱼",
    "Tears Flowing On Your Face": "流着泪的你的脸",
    "Storm": "风暴",
    "Give You Happiness": "给你幸福",
    "Don't Come Back If You Leave": "出去就别回来",
    "Far Away Place": "遥远的地方",
    "Train Station": "心情车站",
    "Waves Like Flowers": "浪花一朵朵",
    "Girls Looking At You from the Other Side": "对面的女孩看过来",
    "One Person": "一个人",
    "Bottom Up": "乾杯",
    "Hard to Let Go": "舍不得",
    "If Someone Loves You More": "如果有人比我更爱你",
    "Difficult to Know You": "知难而退",
    "The Passage of Youth": "少年游",
    "Song of Old Chang": "老张的歌",
    "Really Icy Power": "超魔神",
    "How So?": "怎么会呢",
    "Blind Spot": "盲点",
    "Understanding": "理解",
    "Hand in Hand": "浪漫手牵手",
    "Something's Coming": "有事发生",
    "Crying in the Night": "夜了哭吧",
    "A Man's Tears": "一个男人的眼泪",
    "The Bell Hanging On the Ivy 1997": "长藤挂铜铃1997",
    "For Love": "为了爱",
    "Keep Distance": "保持距离",
    "Love Won't Hurt Until Loved": "爱怎么会痛",
    "Too Soft-Hearted": "心太软",
    "Can't Be Killed": "任逍遥",
    "Just You and Me On the Way of Love": "爱的路上只有我和你",
    "Starting Over": "从头做起",
    "Let You Be Free and Easy": "让你走",
    "Brotherhood": "兄弟",
    "Hurt Badly": "很受伤",
    "Siou-Shua": "好歹拢是命",
    "Don't Change": "不变",
    "Love Is Crazy": "爱疯狂",
    "Everlasting Night": "永远",
    "One Man": "一个男人的眼泪",
    "Three Minutes": "三分钟",
    "Can't Stop Loving You": "无法停止爱你",
    "對面的女孩看過來": "对面的女孩看过来",
    "Lydia": "Lydia",
    "Our Love": "我们的爱",
    "Fly Away": "Fly Away",
    "千年之恋": "千年之恋",
    "光茫": "光芒",
    "小情歌": "小情歌",
    "我好想你": "我好想你",
    "无与伦比的美丽": "无与伦比的美丽",
    "起风了": "起风了",
    "再见杰克": "再见杰克",
    "西湖": "西湖",
    "公路之歌": "公路之歌",
    "为你唱首歌": "为你唱首歌",
    "安阳": "安阳",
    "身骑白马": "身骑白马",
    "失落沙洲": "失落沙洲",
    "言不由衷": "言不由衷",
    "寻人启事": "寻人启事",
    "我的歌声里": "我的歌声里",
    "爱的海洋": "爱的海洋",
    "慢灵魂": "慢灵魂",
    "早安,晨之美!": "早安晨之美",
    "鱼仔": "鱼仔",
    "刻在我心底的名字": "刻在我心底的名字"
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
    'sodagreen', 'f.i.r.', 'miserable faith', '添翼',
    'beyond', 'faye wong', 'leslie cheung', 'lo ta-yu', 'a-mei', 'mavis fan', 'yoga lin'
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
    print(f"\n🎵 [W04-{sid}] {artist} - 《{title}》{extra_str} ({album})")
    
    off_dur = get_official_dur(artist, search_title)
    cand = search_candidate(artist, title, search_title, off_dur)
    
    if not cand:
        print(f"   ⚪ [W04-{sid}] 未匹配到高信度录音室音源 -> 留白")
        with db_lock:
            conn = sqlite3.connect(DB_PATH, timeout=60.0)
            cur = conn.cursor()
            cur.execute("UPDATE tracks_sync_state SET status = 'UNLIT_SKIPPED', last_error = '未检索到高信度录音室音源', updated_at = CURRENT_TIMESTAMP WHERE song_id = ?", (sid,))
            conn.commit()
            conn.close()
        return False, f"未匹配音源: {artist} - 《{title}》"
        
    print(f"   ✅ [W04-{sid}] 命中: 【{cand['title']}】 ({cand['duration']}s | {cand['channel']})")
    
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
        print(f"   ❌ [W04-{sid}] 下载异常: {e}")
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
        print(f"   ❌ [W04-{sid}] 转码异常: {e}")
        return False, f"转码异常: {e}"
        
    # 3. 上传音频到 R2
    r2_mp3_key = f"music/{artist}/{album}/s_{sid}.mp3"
    full_mp3_url = f"{PUBLIC_DOMAIN}/{r2_mp3_key}"
    try:
        s3.upload_file(clean_f, BUCKET_NAME, r2_mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        print(f"   🚀 [W04-{sid}] R2 上传完成: {r2_mp3_key}")
    except Exception as e:
        print(f"   ❌ [W04-{sid}] R2 上传失败: {e}")
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
            print(f"   📜 [W04-{sid}] LRC 歌词已上传: {r2_lrc_key}")
        except Exception as e:
            print(f"   ⚠️ [W04-{sid}] LRC 上传异常: {e}")
            
    # 5. Cloudflare D1 边缘点亮
    payload = {"updates": [{"id": sid, "file_path": full_mp3_url, "lrc_path": full_lrc_url}]}
    try:
        resp = requests.post(API_BATCH_LIGHT_URL, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"   ✨ [W04-{sid}] D1 即时点亮成功！")
        else:
            print(f"   ⚠️ [W04-{sid}] D1 响应: {resp.status_code}")
    except Exception as e:
        print(f"   ⚠️ [W04-{sid}] D1 请求异常: {e}")
        
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
        
    print(f"   🎉 [W04-{sid}] {artist} - 《{title}》 完工点亮！")
    return True, f"成功: {artist} - 《{title}》"

def main():
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    cur = conn.cursor()
    
    placeholders = ','.join('?' for _ in TARGET_ARTISTS)
    cur.execute(f"""
        SELECT song_id, artist_name, album_title, song_title
        FROM tracks_sync_state
        WHERE artist_name IN ({placeholders})
          AND (r2_mp3_key IS NULL OR r2_mp3_key = '' OR r2_mp3_key NOT LIKE 'https://%')
          AND status != 'D1_LIT'
        ORDER BY artist_name, album_title, track_index
    """, TARGET_ARTISTS)
    
    all_tracks = cur.fetchall()
    conn.close()
    
    print("=" * 85)
    print(f"🚀 MOODY 音乐高并发采录点亮引擎 [Worker 04] 启动！")
    print(f"📦 待处理曲目: {len(all_tracks)} 首 | 目标存储桶: {BUCKET_NAME}")
    print(f"🌐 绝对公网域名: {PUBLIC_DOMAIN}")
    print(f"⚡ 并发线程数: 4 线程安全并发")
    print(f"🎤 负责歌手: {', '.join(TARGET_ARTISTS)}")
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
                print(f"❌ [W04] 线程异常: {t[1]} - 《{t[3]}》: {e}")
                
            done = success_cnt + fail_cnt
            if done % 10 == 0 or done == len(all_tracks):
                print(f"\n📊 [W04 进度播报] 完成: {done}/{len(all_tracks)} | 成功点亮: {success_cnt} 首 | 留白: {fail_cnt} 首\n")
                
    print("=" * 85)
    print(f"🏁 [Worker 04] 流水线执行完毕！累计点亮: {success_cnt} 首 | 留白: {fail_cnt} 首")
    print("=" * 85)

if __name__ == "__main__":
    main()
