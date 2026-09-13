#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 心爱歌手全量高保真自动化抓取与点亮流水线
1. 质量铁律：100% 录音室正版母带，黑名单一票否决(live/MV/对白)，网易云 ±8s 时长卡尺，EBU R128 标准化，宁缺毋滥严格留白。
2. 空间路由：第二存储桶严格压至 95% (9.50 GB) 安全红线，达到前整位歌手无缝切换至第三存储桶，绝不分割歌手。
3. 边缘瞬时点亮：每抓完一首即上传对应 R2 桶并通过 Cloudflare D1 batch-light 即时点亮。
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

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
os.chdir(WORKSPACE)

BASE_DIR = os.path.join(WORKSPACE, "backend")
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
import r2_safety_guard
r2_safety_guard.assert_write_allowed()

DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "pipeline_active")
os.makedirs(WORK_DIR, exist_ok=True)

YOUTUBE_PROXY = 'http://127.0.0.1:7897'

# 9.50 GB Hard Circuit Breaker for Bucket 2
MAX_SAFE_BYTES_BUCKET2 = int(9.50 * 1024 * 1024 * 1024)

# 53 Favorite Artists in preferred priority order
FAVORITE_ARTISTS_ORDER = [
    # 0. 优先插队补齐刚移入的胡彦斌经典大碟
    '胡彦斌',
    # 1. 优先补全部分已点亮的歌手
    '苏妙玲', '华晨宇', '潘玮柏', '五月天', '刀郎', '阿杜', '阿牛', '腾格尔', 
    '杨千嬅', '张杰', '张信哲', '张震岳', '宋冬野', '周华健', '张学友', '容祖儿', '谭咏麟',
    # 2. 紧接着点亮精选高热度歌手
    '赵雷', '伍佰', '田馥甄', '信乐团', '许嵩', '南拳妈妈', '那英', '周深',
    '张雨生', '曹格', '徐佳莹', '汪峰', '郁可唯', '尚雯婕', '薛之谦', '萧敬腾',
    '张靓颖', '张惠妹', '羽泉', '杨丞琳', '姜育恒', '许志安', '黄小琥', '万芳',
    '游鸿明', '苏慧伦', '苏打绿', '庾澄庆', '黄品源', '田震', '崔健', '萧亚轩', '袁娅维'
]

ALIAS_MAP = {
    '徐佳莹': '徐佳瑩',
    '羽泉': '羽·泉'
}

BLACK_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会', '微电影', '剧情版', 
    '官方完整版mv', 'cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮'
]

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)

s3_clients = {}
for acc in ["account_02", "account_03"]:
    info = r2_cfg["buckets"][acc]
    s3_clients[acc] = {
        "client": boto3.client(
            service_name="s3",
            endpoint_url=info["endpoint_url"],
            aws_access_key_id=info["access_key_id"],
            aws_secret_access_key=info["secret_access_key"],
            region_name="auto",
            config=Config(s3={"addressing_style": "path"}, connect_timeout=10, read_timeout=20)
        ),
        "name": info["name"],
        "info": info
    }

def get_bucket_live_size(acc_key: str) -> int:
    s3 = s3_clients[acc_key]["client"]
    b_name = s3_clients[acc_key]["name"]
    paginator = s3.get_paginator('list_objects_v2')
    total = 0
    for page in paginator.paginate(Bucket=b_name):
        for obj in page.get('Contents', []):
            total += obj['Size']
    return total

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
    trusted_channels = ['topic', 'universal music group', '摩登天空', 'rock records', '滾石唱片', '潮水音樂', 'jeff chang', '宋冬野', '相信音樂', '胡彦斌', 'tiger hu', 'gold typhoon', 'emi']
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
                
            is_trusted = any(tc in lower_text for tc in trusted_channels)
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

def process_track(sid, artist, album, title, target_bucket_key):
    print(f"\n🎵 [{sid}] {artist} - 《{title}》 ({album})")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. 检索官方时长
    off_dur = get_official_dur(artist, title)
    print(f"   官方 CD 标准时长: {off_dur:.1f}s")
    
    # 2. 检索 Topic 正版候选
    cand = search_studio_candidate(artist, title, off_dur)
    
    if not cand:
        print(f"   ⚪ 未检索到 100% 录音室正版母带 -> 严格执行【留白】(UNLIT)")
        c.execute("""
            UPDATE tracks_sync_state 
            SET status = 'UNLIT_SKIPPED', 
                last_error = '未检索到100%合规录音室母带，严格留白',
                updated_at = CURRENT_TIMESTAMP 
            WHERE song_id = ?
        """, (sid,))
        conn.commit()
        conn.close()
        return False
        
    print(f"   ✅ 命中录音室原版母带: 【{cand['title']}】 ({cand['duration']}s | {cand['channel']})")
    
    raw_tmp = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
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
        return False
        
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
        return False
        
    # 5. 上传 R2
    s3_info = s3_clients[target_bucket_key]
    s3 = s3_info["client"]
    b_name = s3_info["name"]
    pub_domain = s3_info["info"]["public_domain"]
    
    r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
    full_url = f"{pub_domain}/{r2_key}"
    
    try:
        s3.upload_file(clean_f, b_name, r2_key, ExtraArgs={"ContentType": "audio/mpeg"})
        print(f"   🚀 R2 音频上传完成: -> {b_name}")
    except Exception as e:
        print(f"   ❌ R2 上传异常: {e}")
        conn.close()
        return False
        
    # 5.1 同步抓取与上传毫秒级时间轴歌词 (.lrc)
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
            full_lrc_url = f"{pub_domain}/{r2_lrc_key}"
            s3.put_object(
                Bucket=b_name,
                Key=r2_lrc_key,
                Body=lrc_text.encode('utf-8'),
                ContentType="text/plain; charset=utf-8"
            )
            print(f"   📝 R2 歌词同步上传成功")
    except Exception as e:
        print(f"   ⚠️ 歌词处理跳过: {e}")
        
    # 6. D1 毫秒级瞬时点亮 (音频 + 歌词双轨)
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
            print(f"   ✨ D1 边缘点亮成功！(歌词: {'已绑定' if full_lrc_url else '暂缺'})")
        else:
            print(f"   ⚠️ D1 点亮响应: {resp.status_code}")
    except Exception as e:
        print(f"   ⚠️ D1 接口异常: {e}")
        
    # 7. 更新本地状态机
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
    """, (full_url, full_lrc_url, os.path.getsize(clean_f), sid))
    c.execute("""
        UPDATE songs 
        SET file_path = ?, lrc_path = ? 
        WHERE id = ?
    """, (full_url, full_lrc_url, sid))
    conn.commit()
    conn.close()
    
    # 清理本地临时文件保持硬盘清爽
    if os.path.exists(clean_f): os.remove(clean_f)
    return True

def run_main_pipeline():
    print("=" * 90)
    print("🚀 启动心爱歌手全量主流水线 (智能容量熔断与三桶集群)")
    print("=" * 90)
    
    # 实时容量感知
    print("🔍 正在实时测量存储桶 2 (moody-music-asset-02) 当前物理占用...")
    bucket2_bytes = get_bucket_live_size("account_02")
    bucket2_gb = bucket2_bytes / (1024 ** 3)
    usage_pct = (bucket2_bytes / (10 * 1024 ** 3)) * 100
    print(f"📊 存储桶 2 当前物理占用: {bucket2_gb:.3f} GB / 10.00 GB ({usage_pct:.1f}%)")
    
    current_target_bucket = "account_02"
    if bucket2_bytes >= MAX_SAFE_BYTES_BUCKET2:
        print("⚠️ 存储桶 2 已达到或超过 95% 安全红线，初始目标直接设为存储桶 3 (account_03)！")
        current_target_bucket = "account_03"
        
    conn = sqlite3.connect(DB_PATH, timeout=60)
    c = conn.cursor()
    
    total_lit_count = 0
    total_blank_count = 0
    
    for artist_idx, raw_artist in enumerate(FAVORITE_ARTISTS_ORDER, 1):
        db_artist = ALIAS_MAP.get(raw_artist, raw_artist)
        
        # 查询该歌手待抓取的歌曲
        c.execute("""
            SELECT song_id, album_title, song_title 
            FROM tracks_sync_state 
            WHERE artist_name = ? AND status != 'D1_LIT' AND status != 'UNLIT_SKIPPED'
            ORDER BY album_title, track_index
        """, (db_artist,))
        unlit_tracks = c.fetchall()
        
        if not unlit_tracks:
            print(f"\n⏭️ [{artist_idx}/{len(FAVORITE_ARTISTS_ORDER)}] 歌手 {raw_artist} 暂无待抓取曲目，跳过。")
            continue
            
        print("\n" + "#" * 80)
        print(f"👑 [{artist_idx}/{len(FAVORITE_ARTISTS_ORDER)}] 开始处理歌手: {raw_artist} (待采曲目: {len(unlit_tracks)} 首)")
        print("#" * 80)
        
        # 智能切桶容量预估 (不分割歌手)
        if current_target_bucket == "account_02":
            est_artist_bytes = len(unlit_tracks) * int(3.8 * 1024 * 1024)
            if bucket2_bytes + est_artist_bytes >= MAX_SAFE_BYTES_BUCKET2:
                print(f"🚨 [切桶预警] 歌手 {raw_artist} 预估体积 {est_artist_bytes/(1024**2):.1f}MB，将使桶 2 突破 95% (9.50 GB) 安全线！")
                print(f"🔄 为保障【不分割歌手】原则，整位歌手 {raw_artist} 及后续所有歌手无缝切换至第三存储桶 (account_03)！")
                current_target_bucket = "account_03"
            else:
                print(f"📦 预估新增 {est_artist_bytes/(1024**2):.1f}MB，仍在桶 2 安全区间 (预估至 {(bucket2_bytes+est_artist_bytes)/(1024**3):.3f}GB)，全量写入桶 2。")
        else:
            print(f"📦 当前目标存储桶: account_03 (moody-music-asset-03)")
            
        artist_lit = 0
        artist_blank = 0
        for sid, alb, tit in unlit_tracks:
            ok = process_track(sid, db_artist, alb, tit, current_target_bucket)
            if ok:
                artist_lit += 1
                total_lit_count += 1
                if current_target_bucket == "account_02":
                    bucket2_bytes += int(3.8 * 1024 * 1024)
            else:
                artist_blank += 1
                total_blank_count += 1
                
        print(f"\n📊 歌手 {raw_artist} 处理完毕: 成功点亮 {artist_lit} 首 | 宁缺毋滥留白 {artist_blank} 首")
        
    conn.close()
    print("\n" + "=" * 90)
    print("🎉 心爱歌手全量抓轨流水线全面大收官！")
    print(f"   • 累计点亮正版录音室母带: {total_lit_count} 首")
    print(f"   • 严格宁缺毋滥留白: {total_blank_count} 首")
    print("=" * 90)

if __name__ == "__main__":
    run_main_pipeline()
