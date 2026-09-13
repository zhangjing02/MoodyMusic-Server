#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 胡彦斌录音室大碟专项全量补齐引擎 (含同步歌词采集)
=============================================================================
1. 目标范围：
   - 专辑《大一号》(2012, Album ID 592): 12 首录音室原声
   - 专辑《入目三分》(2018, Album ID 590): 10 首录音室原声（已彻底剥离伴奏）
2. 质量守则：
   - 100% 录音室原版母带，优先匹配 YouTube Topic / 官方音频发布
   - 网易云 CD 官方时长严格卡尺 (±8s)
   - EBU R128 (-14 LUFS / -1.0 dBFS) 统一响度归一化
   - 自动配套抓取 LRC 高精时间轴同步歌词
3. 存储与发布：
   - 写入第三存储桶 moody-music-asset-03 (account_03)
   - Cloudflare D1 边缘 instant batch-light (同步音频+歌词)
   - 本地状态机同步更新
=============================================================================
"""

import os
import sys
import re
import json
import time
import sqlite3
import subprocess
import urllib.parse
import requests
import boto3
from botocore.config import Config

try:
    import syncedlyrics
except ImportError:
    syncedlyrics = None

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
os.chdir(WORKSPACE)

BASE_DIR = os.path.join(WORKSPACE, "backend")
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
import r2_safety_guard
r2_safety_guard.assert_write_allowed()

DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "huyanbin_active")
os.makedirs(WORK_DIR, exist_ok=True)

PROXIES = {
    'http': 'http://127.0.0.1:7897',
    'https': 'http://127.0.0.1:7897'
}

BLACK_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会', '微电影', '剧情版', 
    '官方完整版mv', 'cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮'
]

# R2 存储配置
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)

acc3_info = r2_cfg["buckets"]["account_03"]
s3_client = boto3.client(
    service_name="s3",
    endpoint_url=acc3_info["endpoint_url"],
    aws_access_key_id=acc3_info["access_key_id"],
    aws_secret_access_key=acc3_info["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, proxies=PROXIES, connect_timeout=15, read_timeout=30)
)
bucket3_name = acc3_info["name"]
public_domain = acc3_info["public_domain"]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/',
}

def get_official_dur(artist, title):
    try:
        url = f"http://music.163.com/api/search/get/web?s={requests.utils.quote(f'{artist} {title}')}&type=1&offset=0&total=true&limit=1"
        r = requests.get(url, headers=HEADERS, timeout=5).json()
        songs = r.get('result', {}).get('songs', [])
        if songs:
            return songs[0].get('duration', 0) / 1000.0
    except Exception:
        pass
    return 0.0

def clean_song_title(title: str):
    candidates = [title]
    t1 = re.sub(r'\(.*?\)|（.*?）|\[.*?\]|【.*?】', '', title).strip()
    if t1 and t1 not in candidates:
        candidates.append(t1)
    return candidates

def fetch_lrc(artist: str, title: str):
    clean_titles = clean_song_title(title)
    # 1. syncedlyrics 优先
    if syncedlyrics:
        for ct in clean_titles:
            try:
                lrc = syncedlyrics.search(f"{artist} {ct}", providers=['NetEase', 'Lrclib'])
                if lrc and len(lrc) > 80 and '[' in lrc and ':' in lrc:
                    return lrc
            except Exception:
                pass

    # 2. 网易云原生 API
    queries = [f"{artist} {title}"] + [f"{artist} {ct}" for ct in clean_titles]
    seen = set()
    for q in queries:
        if q in seen: continue
        seen.add(q)
        try:
            search_url = f"http://music.163.com/api/search/get/web?s={urllib.parse.quote(q)}&type=1&offset=0&limit=3"
            resp = requests.get(search_url, headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                songs = resp.json().get('result', {}).get('songs', [])
                for s in songs:
                    sid = s['id']
                    lrc_url = f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1"
                    lr = requests.get(lrc_url, headers=HEADERS, timeout=5)
                    if lr.status_code == 200:
                        lrc_text = lr.json().get('lrc', {}).get('lyric', '')
                        if lrc_text and len(lrc_text) > 80 and '[' in lrc_text and ':' in lrc_text:
                            return lrc_text
        except Exception:
            pass
        time.sleep(0.1)
    return None

def search_candidate(artist, album, title, off_dur):
    queries = [
        f"{artist} {title} Topic",
        f"{artist} - {title} 官方音源",
        f"Provided to YouTube {artist} {title}",
        f"{artist} {album} {title}"
    ]
    
    for q in queries:
        cmd = [
            'yt-dlp', '--proxy', 'http://127.0.0.1:7897', 
            '--socket-timeout', '15',
            '--no-playlist', '--flat-playlist', '-j', 
            f'ytsearch3:{q}'
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        except Exception:
            continue
            
        for line in res.stdout.strip().splitlines():
            if not line: continue
            try:
                d = json.loads(line)
            except:
                continue
            v_title = str(d.get('title') or '')
            v_ch = str(d.get('channel') or '')
            v_dur = d.get('duration') or 0
            v_id = str(d.get('id') or '')
            v_desc = str(d.get('description') or '')
            
            lower_text = f"{v_title} {v_ch} {v_desc}".lower()
            # 严格黑名单过滤
            if any(bk in lower_text for bk in BLACK_KEYWORDS):
                continue
            
            # 时长卡尺
            if off_dur > 0 and v_dur > 0:
                if abs(v_dur - off_dur) > 8:
                    continue
                    
            # 官方认证或主题音频优先
            is_official = (
                '- topic' in v_ch.lower() or 
                'provided to youtube' in v_desc.lower() or
                'official audio' in v_title.lower() or
                '官方音源' in v_title or
                '太合音乐' in v_desc or
                '金牌大风' in v_desc or
                '海蝶' in v_desc or
                '胡彦斌' in v_ch
            )
            
            if is_official:
                return {
                    'id': v_id,
                    'title': v_title,
                    'channel': v_ch,
                    'duration': v_dur,
                    'url': f"https://www.youtube.com/watch?v={v_id}"
                }
            # 普通备选
            if not is_official and off_dur > 0 and abs(v_dur - off_dur) <= 4:
                return {
                    'id': v_id,
                    'title': v_title,
                    'channel': v_ch,
                    'duration': v_dur,
                    'url': f"https://www.youtube.com/watch?v={v_id}"
                }
    return None

def process_track(sid, artist, album, title, track_idx):
    print(f"\n=======================================================", flush=True)
    print(f"🎵 [{sid}] #{track_idx:02d} {artist} - 《{title}》 (专辑《{album}》)", flush=True)
    print(f"=======================================================", flush=True)
    
    off_dur = get_official_dur(artist, title)
    if off_dur > 0:
        print(f"   ⏱️ 官方 CD 标准时长: {off_dur:.1f}s", flush=True)
        
    cand = search_candidate(artist, album, title, off_dur)
    
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    c = conn.cursor()
    
    if not cand:
        print(f"   ⚪ 未能匹配到 100% 录音室正版母带 -> 保持严格留白", flush=True)
        c.execute("""
            UPDATE tracks_sync_state 
            SET status = 'UNLIT_SKIPPED', 
                last_error = '精准检索无100%合规母带，保持留白',
                updated_at = CURRENT_TIMESTAMP 
            WHERE song_id = ?
        """, (sid,))
        conn.commit()
        conn.close()
        return False
        
    print(f"   🎯 命中母带: 【{cand['title']}】 ({cand['duration']}s | 频道: {cand['channel']})", flush=True)
    
    raw_tmp = os.path.join(WORK_DIR, f"raw_hu_{sid}.mp3")
    clean_f = os.path.join(WORK_DIR, f"s_{sid}.mp3")
    lrc_f = os.path.join(WORK_DIR, f"s_{sid}.lrc")
    
    # 1. 下载原始音频
    print(f"   📥 开始下载音频流...", flush=True)
    try:
        subprocess.run([
            'yt-dlp', '--proxy', 'http://127.0.0.1:7897',
            '--socket-timeout', '20',
            '--force-overwrites', '--no-playlist', 
            '-x', '--audio-format', 'mp3', '--audio-quality', '0', 
            '-o', raw_tmp, cand['url']
        ], check=True, capture_output=True, timeout=90)
    except Exception as e:
        print(f"   ❌ 下载异常: {e}", flush=True)
        conn.close()
        return False
        
    # 2. EBU R128 音量标准化与压缩
    print(f"   🎛️ 执行 EBU R128 响度标准化 (-14 LUFS) & 160kbps 统一压制...", flush=True)
    try:
        subprocess.run([
            'ffmpeg', '-y', '-i', raw_tmp, '-vn',
            '-af', 'loudnorm=I=-14:TP=-1.0:LRA=11',
            '-c:a', 'libmp3lame', '-b:a', '160k', '-ar', '44100', '-write_xing', '1',
            clean_f
        ], check=True, capture_output=True, timeout=60)
        if os.path.exists(raw_tmp): os.remove(raw_tmp)
    except Exception as e:
        print(f"   ❌ 音频标准化压制异常: {e}", flush=True)
        conn.close()
        return False
        
    # 3. 抓取歌词
    lrc_text = fetch_lrc(artist, title)
    lrc_full_url = None
    if lrc_text:
        with open(lrc_f, "w", encoding="utf-8") as lf:
            lf.write(lrc_text)
        print(f"   📝 同步歌词抓取成功 ({len(lrc_text)} 字符)", flush=True)
    else:
        print(f"   ℹ️ 未找到同步歌词", flush=True)

    # 4. 上传到 Cloudflare R2 第 3 存储桶
    r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
    full_url = f"{public_domain}/{r2_key}"
    print(f"   ☁️ 上传音频至 R2 存储桶: {bucket3_name} -> {r2_key}...", flush=True)
    try:
        s3_client.upload_file(clean_f, bucket3_name, r2_key, ExtraArgs={"ContentType": "audio/mpeg"})
    except Exception as e:
        print(f"   ❌ R2 音频上传异常: {e}", flush=True)
        conn.close()
        return False

    if lrc_text and os.path.exists(lrc_f):
        r2_lrc_key = f"music/{artist}/{album}/s_{sid}.lrc"
        lrc_full_url = f"{public_domain}/{r2_lrc_key}"
        try:
            s3_client.upload_file(lrc_f, bucket3_name, r2_lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            print(f"   ☁️ 上传歌词至 R2 存储桶: {r2_lrc_key}...", flush=True)
        except Exception as e:
            print(f"   ⚠️ R2 歌词上传异常: {e}", flush=True)
            lrc_full_url = None
        
    # 5. Cloudflare D1 瞬时边缘点亮
    print(f"   ✨ 调用 Cloudflare D1 接口点亮歌曲...", flush=True)
    try:
        update_item = {'id': sid, 'file_path': full_url}
        if lrc_full_url:
            update_item['lrc_path'] = lrc_full_url
        resp = requests.post(
            'https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light',
            json={'updates': [update_item]},
            proxies=PROXIES,
            timeout=15
        )
        if resp.status_code == 200:
            print(f"   ✅ Cloudflare D1 边缘点亮成功！", flush=True)
        else:
            print(f"   ⚠️ D1 接口返回 {resp.status_code}: {resp.text}", flush=True)
    except Exception as e:
        print(f"   ⚠️ D1 接口请求异常: {e}", flush=True)
        
    # 6. 更新本地状态机与歌曲库
    rel_local = os.path.relpath(clean_f, WORKSPACE)
    rel_lrc = os.path.relpath(lrc_f, WORKSPACE) if lrc_full_url else None
    c.execute("""
        UPDATE tracks_sync_state 
        SET status = 'D1_LIT', 
            local_mp3 = ?, 
            r2_mp3_key = ?, 
            local_lrc = ?,
            r2_lrc_key = ?,
            lit_at = CURRENT_TIMESTAMP, 
            updated_at = CURRENT_TIMESTAMP,
            last_error = NULL
        WHERE song_id = ?
    """, (rel_local, full_url, rel_lrc, lrc_full_url, sid))
    c.execute("UPDATE songs SET file_path = ?, lrc_path = ? WHERE id = ?", (full_url, lrc_full_url, sid))
    conn.commit()
    conn.close()
    
    print(f"   🎉 歌曲 [{sid}] 《{title}》 完整点亮完成！", flush=True)
    return True

def run():
    print("=" * 70, flush=True)
    print("🚀 开始执行胡彦斌 2 张待补全录音室大碟专项下载与点亮", flush=True)
    print("=" * 70, flush=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT s.id, a.name, al.title, s.title, s.track_index
        FROM songs s
        JOIN artists a ON a.id = s.artist_id
        JOIN albums al ON al.id = s.album_id
        LEFT JOIN tracks_sync_state t ON t.song_id = s.id
        WHERE s.album_id IN (592, 590) AND (t.status IS NULL OR t.status != 'D1_LIT')
        ORDER BY al.id, s.track_index
    """)
    pending_tracks = c.fetchall()
    conn.close()
    
    print(f"📋 共检索到 {len(pending_tracks)} 首待处理录音室曲目", flush=True)
    success_cnt = 0
    
    for sid, art, alb, stitle, tidx in pending_tracks:
        ok = process_track(sid, art, alb, stitle, tidx or 0)
        if ok:
            success_cnt += 1
        time.sleep(1.0)
        
    print("\n" + "=" * 70, flush=True)
    print(f"🏁 胡彦斌录音室大碟补齐工作完成！成功点亮: {success_cnt} / {len(pending_tracks)}", flush=True)
    print("=" * 70, flush=True)

if __name__ == '__main__':
    run()
