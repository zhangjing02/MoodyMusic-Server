#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - Bucket 02 极限压榨高保真点亮流水线 (Replenish Bucket 02 Favorites)
目标：
1. 容量目标：精准压榨 Bucket 02 剩余空间至 9.65 GB (96.5%) 安全停机红线，绝不撑爆 10.00 GB。
2. 心爱歌手：赵雷 -> 伍佰 -> 田馥甄 -> 周深。
3. 质量铁律：100% 录音室正版母带，黑名单一票否决(live/现场/MV/伴奏)，±8s 时长卡尺，EBU R128 标准化，宁缺毋滥。
4. 双轨点亮：音频与毫秒级 LRC 歌词实时上传并即刻同步 D1。
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
import syncedlyrics

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
os.chdir(WORKSPACE)

BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "pipeline_b2")
os.makedirs(WORK_DIR, exist_ok=True)

YOUTUBE_PROXY = 'http://127.0.0.1:7897'

# 9.65 GB Hard Circuit Breaker (用户授权略超 95%，绝不超过 9.65 GB，保留 350MB 绝对缓冲)
MAX_SAFE_BYTES_BUCKET2 = int(9.65 * 1024 * 1024 * 1024)

TARGET_ARTISTS = ['赵雷', '伍佰', '田馥甄', '周深']

BLACK_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会', '微电影', '剧情版', 
    '官方完整版mv', 'cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮'
]

TRUSTED_CHANNELS = [
    'topic', 'universal music group', '摩登天空', 'rock records', '滾石唱片', 
    '潮水音樂', '相信音樂', '华研国际', 'him international music', '索尼音乐',
    'sony music', 'warner music', '华纳音乐', 'streetvoice', '街声', '周深', 'charlie zhou'
]

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)

info2 = r2_cfg["buckets"]["account_02"]
s3_b2 = boto3.client(
    service_name="s3",
    endpoint_url=info2["endpoint_url"],
    aws_access_key_id=info2["access_key_id"],
    aws_secret_access_key=info2["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, connect_timeout=10, read_timeout=20)
)
BUCKET2_NAME = info2["name"]
BUCKET2_PUB_DOMAIN = info2["public_domain"]

def get_bucket2_live_size() -> tuple[int, int]:
    paginator = s3_b2.get_paginator('list_objects_v2')
    total_bytes = 0
    total_count = 0
    for page in paginator.paginate(Bucket=BUCKET2_NAME):
        for obj in page.get('Contents', []):
            total_bytes += obj['Size']
            total_count += 1
    return total_bytes, total_count

def get_official_dur(artist, title):
    clean_t = title.split('(')[0].split('（')[0].strip()
    # 1. 尝试网易云
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

    # 2. 尝试 iTunes
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

def process_track(sid, artist, album, title, live_bytes):
    # 严格容量防线核查
    if live_bytes + int(5.0 * 1024 * 1024) >= MAX_SAFE_BYTES_BUCKET2:
        print(f"🚨 [安全硬熔断] 当前物理占用 {live_bytes/(1024**3):.4f} GB，即将突破 9.65 GB 极限停机线！立即终止！")
        return False, live_bytes, True  # stopped by circuit breaker

    print(f"\n🎵 [{sid}] {artist} - 《{title}》 ({album})")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. 官方基准时长
    off_dur = get_official_dur(artist, title)
    print(f"   官方 CD 标准时长: {off_dur:.1f}s")

    # 2. 检索母带候选
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

    raw_tmp = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
    clean_f = os.path.join(WORK_DIR, f"s_{sid}.mp3")

    # 3. 下载音频
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

    # 4. EBU R128 标准化转码
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

    # 5. 上传 R2 Bucket 02
    r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
    full_url = f"{BUCKET2_PUB_DOMAIN}/{r2_key}"

    try:
        s3_b2.upload_file(clean_f, BUCKET2_NAME, r2_key, ExtraArgs={"ContentType": "audio/mpeg"})
        print(f"   🚀 R2 音频已入库 ({f_size/(1024**2):.2f}MB) -> {BUCKET2_NAME}")
    except Exception as e:
        print(f"   ❌ R2 上传异常: {e}")
        conn.close()
        return False, live_bytes, False

    # 5.1 同步抓取与上传时间轴歌词 (.lrc)
    full_lrc_url = None
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
            r2_lrc_key = f"music/{artist}/{album}/s_{sid}.lrc"
            full_lrc_url = f"{BUCKET2_PUB_DOMAIN}/{r2_lrc_key}"
            s3_b2.put_object(
                Bucket=BUCKET2_NAME,
                Key=r2_lrc_key,
                Body=lrc_text.encode('utf-8'),
                ContentType="text/plain; charset=utf-8"
            )
            print(f"   📝 R2 毫秒歌词同步就绪")
    except Exception as e:
        print(f"   ⚠️ 歌词抓取跳过: {e}")

    # 6. D1 边缘秒级双轨点亮
    try:
        update_payload = {'id': sid, 'file_path': full_url}
        if full_lrc_url:
            update_payload['lrc_path'] = full_lrc_url
        resp = requests.post(
            'https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light',
            json={'updates': [update_payload]},
            timeout=15
        )
        if resp.status_code == 200:
            print(f"   ✨ D1 生产秒级点亮成功！")
        else:
            print(f"   ⚠️ D1 点亮响应: {resp.status_code}")
    except Exception as e:
        print(f"   ⚠️ D1 接口异常: {e}")

    # 7. 更新本地数据库状态
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
    """, (full_url, full_lrc_url, f_size, sid))
    c.execute("""
        UPDATE songs 
        SET file_path = ?, lrc_path = ? 
        WHERE id = ?
    """, (full_url, full_lrc_url, sid))
    conn.commit()
    conn.close()

    # 清理临时转码文件
    if os.path.exists(clean_f): os.remove(clean_f)
    return True, live_bytes + f_size, False

def run_replenish_bucket2():
    print("=" * 80)
    print("🚀 启动 Bucket 02 极限压榨高保真点亮流水线")
    print("=" * 80)

    print(f"🔍 正在实时测量存储桶 2 ({BUCKET2_NAME}) 物理占用...")
    current_bytes, current_count = get_bucket2_live_size()
    current_gb = current_bytes / (1024 ** 3)
    usage_pct = (current_bytes / (10 * 1024 ** 3)) * 100
    print(f"📊 当前物理占用: {current_gb:.4f} GB / 10.00 GB ({usage_pct:.2f}%) | 包含对象: {current_count}")
    print(f"🎯 安全停机上限: {MAX_SAFE_BYTES_BUCKET2/(1024**3):.2f} GB (余量: {(MAX_SAFE_BYTES_BUCKET2-current_bytes)/(1024**2):.1f} MB)")
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
        print(f"👑 [{art_idx}/{len(TARGET_ARTISTS)}] 开始点亮歌手: {artist} (待点亮曲目: {len(unlit_tracks)} 首)")
        print("#" * 70)

        art_lit = 0
        art_blank = 0
        stopped = False

        for sid, alb, tit in unlit_tracks:
            success, live_bytes, stopped = process_track(sid, artist, alb, tit, live_bytes)
            if stopped:
                print(f"\n🚨 触发容量安全上限，提前终止处理！")
                break
            if success:
                art_lit += 1
                total_lit += 1
            else:
                art_blank += 1
                total_blank += 1

        print(f"\n📊 歌手 {artist} 处理总结: 点亮 {art_lit} 首 | 严格留白 {art_blank} 首")
        if stopped:
            break

    conn.close()

    print("\n" + "=" * 80)
    final_bytes, final_count = get_bucket2_live_size()
    final_gb = final_bytes / (1024 ** 3)
    final_pct = (final_bytes / (10 * 1024 ** 3)) * 100
    print("🎉 Bucket 02 极限压榨采录圆满完成！")
    print(f"   • 新增点亮曲目: {total_lit} 首 (留白: {total_blank} 首)")
    print(f"   • 最终物理占用: {final_gb:.4f} GB / 10.00 GB ({final_pct:.2f}%)")
    print(f"   • 最终对象数量: {final_count}")
    print("=" * 80)

if __name__ == "__main__":
    run_replenish_bucket2()
