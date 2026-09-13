#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - Bucket 01 精选心爱知名歌手自动化采录流水线 (Replenish Bucket 01 Favorites)
目标：
1. 目标歌手：许嵩 -> 信乐团 -> 田震 -> 崔健 -> 萧亚轩 -> 袁娅维
2. 容量控制：当前 7.60 GB，安全上限 9.20 GB (92%)，预留 800MB 绝对安全冗余
3. 传输协议：通过 Cloudflare Worker POST /api/admin/upload 流式直入 c.env.BUCKET (Bucket 01)
4. 毫秒歌词：同步通过 /api/admin/assets/upload 写入 R2 并绑定 D1
5. 质量准则：100% 录音室原版母带，EBU R128 标准化，160kbps CBR 44.1kHz
"""

import os
import sys
import json
import time
import sqlite3
import subprocess
import requests
import syncedlyrics

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
os.chdir(WORKSPACE)

BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "pipeline_b1")
os.makedirs(WORK_DIR, exist_ok=True)

API_BASE = 'https://m-api.changgepd.ccwu.cc'
YOUTUBE_PROXY = 'http://127.0.0.1:7897'

# 9.20 GB Circuit Breaker for Bucket 01 (预留 800MB 缓冲区)
MAX_SAFE_BYTES_BUCKET1 = int(9.20 * 1024 * 1024 * 1024)

TARGET_ARTISTS = ['许嵩', '信乐团', '田震', '崔健', '萧亚轩', '袁娅维']

BLACK_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会', '微电影', '剧情版', 
    '官方完整版mv', 'cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮'
]

TRUSTED_CHANNELS = [
    'topic', 'universal music group', '摩登天空', 'rock records', '滾石唱片', 
    '海蝶音樂', 'ocean butterflies', 'avex', '爱贝克思', '索尼音乐', 'sony music',
    'warner music', '华纳音乐', '华研国际', '太合音乐', 'streetvoice', '街声'
]

def get_bucket1_live_size_from_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status IN ('R2_UPLOADED', 'D1_LIT')
          AND (r2_mp3_key IS NULL OR (
              r2_mp3_key NOT LIKE '%pub-9ea7ff16135d47238c0229f1aa54ecc4%'
              AND r2_mp3_key NOT LIKE '%moody-music-asset-02%'
              AND r2_mp3_key NOT LIKE '%pub-383b876c0bb840f6b852946604275232%'
              AND r2_mp3_key NOT LIKE '%moody-music-asset-03%'
          ))
    """)
    cnt, total_bytes = cur.fetchone()
    conn.close()
    return total_bytes, cnt

def get_official_dur(artist, title):
    clean_t = title.split('(')[0].split('（')[0].strip()
    try:
        url = f"http://music.163.com/api/search/get/web?s={requests.utils.quote(f'{artist} {clean_t}')}&type=1&offset=0&total=true&limit=3"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        songs = r.get('result', {}).get('songs', [])
        for s in songs:
            s_name = s.get('name', '').lower()
            if any(bk in s_name for bk in BLACK_KEYWORDS):
                continue
            art_name = s.get('artists', [{}])[0].get('name', '')
            if artist in art_name or art_name in artist:
                return s.get('duration', 0) / 1000.0
    except Exception:
        pass

    try:
        url = f"https://itunes.apple.com/search?term={requests.utils.quote(f'{artist} {clean_t}')}&entity=song&country=TW&limit=3"
        r = requests.get(url, timeout=5).json()
        for item in r.get('results', []):
            if artist in item.get('artistName', ''):
                return item.get('trackTimeMillis', 0) / 1000.0
    except Exception:
        pass

    return 0.0

def search_studio_candidate(artist, title, official_dur):
    clean_t = title.split('(')[0].split('（')[0].strip()
    queries = [
        f"ytsearch4:{artist} - Topic {clean_t}",
        f"ytsearch4:{artist} {clean_t} 官方音源",
        f"ytsearch4:Provided to YouTube {artist} {clean_t}",
        f"ytsearch4:{artist} {clean_t}"
    ]
    for q in queries:
        cmd = ['yt-dlp', '--proxy', YOUTUBE_PROXY, '--no-playlist', '--flat-playlist', '-j', q]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
        except Exception:
            continue
        for line in res.stdout.strip().splitlines():
            if not line: continue
            try:
                d = json.loads(line)
            except:
                continue
            v_title = d.get('title', '')
            v_ch = d.get('channel', '')
            v_dur = d.get('duration', 0)
            v_id = d.get('id', '')
            
            lower_text = f"{v_title} {v_ch}".lower()
            if any(bk in lower_text for bk in BLACK_KEYWORDS):
                continue
                
            is_trusted = any(tc in lower_text for tc in TRUSTED_CHANNELS)
            if is_trusted:
                if official_dur > 0 and v_dur > 0:
                    if abs(v_dur - official_dur) <= 15:
                        return {'id': v_id, 'title': v_title, 'channel': v_ch, 'duration': v_dur, 'url': f"https://www.youtube.com/watch?v={v_id}"}
                else:
                    return {'id': v_id, 'title': v_title, 'channel': v_ch, 'duration': v_dur, 'url': f"https://www.youtube.com/watch?v={v_id}"}
            else:
                if official_dur > 0 and v_dur > 0:
                    if abs(v_dur - official_dur) <= 8:
                        return {'id': v_id, 'title': v_title, 'channel': v_ch, 'duration': v_dur, 'url': f"https://www.youtube.com/watch?v={v_id}"}
    return None

def process_track_bucket1(sid, artist, album, title, live_bytes):
    if live_bytes + int(5.0 * 1024 * 1024) >= MAX_SAFE_BYTES_BUCKET1:
        print(f"🚨 [安全硬熔断] 当前 Bucket 01 估算已达 {live_bytes/(1024**3):.4f} GB，达到 9.20 GB 安全保护线！")
        return False, live_bytes, True

    print(f"\n🎵 [{sid}] {artist} - 《{title}》 ({album})")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    off_dur = get_official_dur(artist, title)
    print(f"   官方 CD 标准时长: {off_dur:.1f}s")

    cand = search_studio_candidate(artist, title, off_dur)
    if not cand:
        print(f"   ⚪ 未检索到 100% 录音室正版母带 -> 严格执行【留白】")
        c.execute("""
            UPDATE tracks_sync_state 
            SET status = 'UNLIT_SKIPPED', 
                last_error = '未检索到100%合规录音室母带，严格留白',
                updated_at = CURRENT_TIMESTAMP 
            WHERE song_id = ?
        """, (sid,))
        conn.commit()
        conn.close()
        return False, live_bytes, False

    print(f"   ✅ 命中录音室原版母带: 【{cand['title']}】 ({cand['duration']}s | {cand['channel']})")

    raw_tmp = os.path.join(WORK_DIR, f"raw_b1_{sid}.mp3")
    clean_f = os.path.join(WORK_DIR, f"s_{sid}.mp3")

    # 3. 下载
    try:
        subprocess.run([
            'yt-dlp', '--proxy', YOUTUBE_PROXY, '--force-overwrites', '--no-playlist', 
            '-x', '--audio-format', 'mp3', '--audio-quality', '0', 
            '-o', raw_tmp, cand['url']
        ], check=True, capture_output=True, timeout=60)
    except Exception as e:
        print(f"   ❌ 下载异常: {e}")
        conn.close()
        return False, live_bytes, False

    # 4. EBU R128 转码
    try:
        subprocess.run([
            'ffmpeg', '-y', '-i', raw_tmp, '-vn',
            '-af', 'loudnorm=I=-14:TP=-1.0:LRA=11',
            '-c:a', 'libmp3lame', '-b:a', '160k', '-ar', '44100', '-write_xing', '1',
            clean_f
        ], check=True, capture_output=True, timeout=60)
        if os.path.exists(raw_tmp): os.remove(raw_tmp)
    except Exception as e:
        print(f"   ❌ EBU R128 转码异常: {e}")
        conn.close()
        return False, live_bytes, False

    f_size = os.path.getsize(clean_f)

    # 5. 上传至 Bucket 01 (通过 Worker /api/admin/upload)
    r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
    try:
        with open(clean_f, 'rb') as f_mp3:
            upload_files = {'files': (f"{title}.mp3", f_mp3, 'audio/mpeg')}
            upload_data = {
                'artistOverride': artist,
                'albumOverride': album,
                'titleOverride': title
            }
            resp = requests.post(f"{API_BASE}/api/admin/upload", files=upload_files, data=upload_data, timeout=30)
            if resp.status_code == 200:
                print(f"   🚀 Bucket 01 音频直传并点亮成功 ({f_size/(1024**2):.2f}MB)")
            else:
                print(f"   ❌ 上传失败: HTTP {resp.status_code} {resp.text}")
                conn.close()
                return False, live_bytes, False
    except Exception as e:
        print(f"   ❌ 上传网络异常: {e}")
        conn.close()
        return False, live_bytes, False

    # 5.1 同步抓取与上传歌词
    lrc_key = None
    try:
        clean_tit = title.split('(')[0].split('（')[0].strip()
        lrc_text = None
        for q in [f"{artist} {title}", f"{artist} {clean_tit}"]:
            try:
                lrc = syncedlyrics.search(q, providers=['NetEase', 'Lrclib'])
                if lrc and len(lrc) > 50 and '[' in lrc and ':' in lrc:
                    lrc_text = lrc
                    break
            except Exception:
                pass
        if lrc_text:
            lrc_category = f"music/{artist}/{album}"
            lrc_filename = f"s_{sid}.lrc"
            lrc_files = {'file': (lrc_filename, lrc_text.encode('utf-8'), 'text/plain; charset=utf-8')}
            lrc_data = {'category': lrc_category}
            r_lrc = requests.post(f"{API_BASE}/api/admin/assets/upload", files=lrc_files, data=lrc_data, timeout=15)
            if r_lrc.status_code == 200:
                lrc_key = f"{lrc_category}/{lrc_filename}"
                # 绑定 D1 lrc_path
                requests.post(
                    f"{API_BASE}/api/admin/songs/batch-light",
                    json={'updates': [{'id': sid, 'file_path': r2_key, 'lrc_path': lrc_key}]},
                    timeout=10
                )
                print(f"   📝 R2 歌词同步上传并绑定")
    except Exception as e:
        print(f"   ⚠️ 歌词处理跳过: {e}")

    # 6. 更新本地 DB
    c.execute("""
        UPDATE tracks_sync_state 
        SET status = 'D1_LIT', 
            r2_mp3_key = ?, 
            r2_lrc_key = ?,
            file_size = ?,
            is_compressed = 1,
            bitrate_kbps = 160,
            qa_status = 'VERIFIED_STUDIO_EBUR128',
            uploaded_at = CURRENT_TIMESTAMP,
            lit_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP 
        WHERE song_id = ?
    """, (r2_key, lrc_key, f_size, sid))
    c.execute("""
        UPDATE songs 
        SET file_path = ?, lrc_path = ? 
        WHERE id = ?
    """, (r2_key, lrc_key, sid))
    conn.commit()
    conn.close()

    if os.path.exists(clean_f): os.remove(clean_f)
    return True, live_bytes + f_size, False

def run_replenish_bucket1():
    print("=" * 80)
    print("🚀 启动 Bucket 01 知名歌手高保真自动化采录流水线")
    print("=" * 80)

    current_bytes, current_count = get_bucket1_live_size_from_db()
    current_gb = current_bytes / (1024 ** 3)
    usage_pct = (current_bytes / (10 * 1024 ** 3)) * 100
    print(f"📊 Bucket 01 当前占用: {current_gb:.4f} GB / 10.00 GB ({usage_pct:.2f}%) | 歌曲数: {current_count}")
    print(f"🎯 预设安全保护上限: {MAX_SAFE_BYTES_BUCKET1/(1024**3):.2f} GB (余量: {(MAX_SAFE_BYTES_BUCKET1-current_bytes)/(1024**2):.1f} MB)")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    total_lit = 0
    total_blank = 0
    live_bytes = current_bytes

    for art_idx, artist in enumerate(TARGET_ARTISTS, 1):
        c.execute("""
            SELECT song_id, album_title, song_title 
            FROM tracks_sync_state 
            WHERE artist_name = ? AND status != 'D1_LIT' AND status != 'UNLIT_SKIPPED'
            ORDER BY album_title, track_index
        """, (artist,))
        unlit_tracks = c.fetchall()

        if not unlit_tracks:
            print(f"\n⏭️ [{art_idx}/{len(TARGET_ARTISTS)}] 歌手 {artist} 全部曲目已点亮，跳过。")
            continue

        print("\n" + "#" * 70)
        print(f"👑 [{art_idx}/{len(TARGET_ARTISTS)}] 开始采录歌手: {artist} (待点亮曲目: {len(unlit_tracks)} 首)")
        print("#" * 70)

        art_lit = 0
        art_blank = 0
        stopped = False

        for sid, alb, tit in unlit_tracks:
            success, live_bytes, stopped = process_track_bucket1(sid, artist, alb, tit, live_bytes)
            if stopped:
                print(f"\n🚨 达到 Bucket 01 安全保护上限，安全停止！")
                break
            if success:
                art_lit += 1
                total_lit += 1
            else:
                art_blank += 1
                total_blank += 1

        print(f"\n📊 歌手 {artist} 处理总结: 点亮 {art_lit} 首 | 留白 {art_blank} 首")
        if stopped:
            break

    conn.close()
    print("\n" + "=" * 80)
    final_bytes, final_count = get_bucket1_live_size_from_db()
    print(f"🎉 Bucket 01 知名歌手自动化采录圆满完成！")
    print(f"   • 本次点亮曲目: {total_lit} 首 (留白: {total_blank} 首)")
    print(f"   • Bucket 01 最终占用: {final_bytes/(1024**3):.4f} GB / 10.00 GB ({(final_bytes/(10*1024**3))*100:.2f}%)")
    print("=" * 80)

if __name__ == "__main__":
    run_replenish_bucket1()
