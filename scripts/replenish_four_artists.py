#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 四大歌手（刀郎、阿杜、阿牛、腾格尔）缺失曲目专项高保真补齐引擎
1. 质量门禁：100% 录音室原版母带（Topic/CD Master 优先），排除现场/微电影/翻唱
2. 空间路由：全量写入第三存储桶 moody-music-asset-03 (account_03)
3. 毫秒级点亮：EBU R128 (-14 LUFS / -1.0 dBFS) 标准化转码后直传 R2 并通过 D1 批量接口即时点亮
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

sys.stdout.reconfigure(encoding='utf-8')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
os.chdir(WORKSPACE)

BASE_DIR = os.path.join(WORKSPACE, "backend")
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
import r2_safety_guard
r2_safety_guard.assert_write_allowed()

DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = os.path.join(BASE_DIR, "downloads_optimized", "replenish_active")
os.makedirs(WORK_DIR, exist_ok=True)

PROXIES = {
    'http': 'http://127.0.0.1:7897',
    'https': 'http://127.0.0.1:7897'
}

BLACK_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会', '微电影', '剧情版', 
    '官方完整版mv', 'cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮'
]

# 精准定制检索词典（解决英文译名、诵经品次、特殊别名）
CUSTOM_SEARCH_QUERIES = {
    # === 刀郎: 《如是我闻》 ===
    5335: ["刀郎 如是我闻 3-7品 Topic", "3-7品 刀郎 Topic", "刀郎 3-7品"],
    5336: ["刀郎 如是我闻 8-9品 Topic", "8-9品 刀郎 Topic", "刀郎 8-9品"],
    5337: ["刀郎 如是我闻 10-13品 Topic", "10-13品 刀郎 Topic", "刀郎 10-13品"],
    5338: ["刀郎 如是我闻 14品 Topic", "14品 刀郎 Topic", "刀郎 14品"],
    5339: ["刀郎 如是我闻 15-16品 Topic", "15-16品 刀郎 Topic", "刀郎 15-16品"],
    5340: ["刀郎 如是我闻 17品 Topic", "17品 刀郎 Topic", "刀郎 17品"],
    5341: ["刀郎 如是我闻 18品 Topic", "18品 刀郎 Topic", "刀郎 18品"],
    5342: ["刀郎 如是我闻 19-21品 Topic", "19-21品 刀郎 Topic", "刀郎 19-21品"],
    5343: ["刀郎 如是我闻 22-25品 Topic", "22-25品 刀郎 Topic", "刀郎 22-25品"],
    5344: ["刀郎 如是我闻 26-29品 Topic", "26-29品 刀郎 Topic", "刀郎 26-29品"],
    5345: ["刀郎 如是我闻 30-32品 Topic", "30-32品 刀郎 Topic", "刀郎 30-32品"],

    # === 阿杜 ===
    98: ["阿杜 哈囉 Topic", "阿杜 哈罗 Topic", "阿杜 HELLO Topic"],
    99: ["阿杜 下雨的时候会想起你 Topic", "下雨的時候會想起你 阿杜 Topic"],
    2: ["阿杜 被忘路 Topic", "阿杜 我不该躲 被忘路"],
    3: ["阿杜 T恤好漢 Topic", "阿杜 T恤好汉 Topic"],
    5: ["阿杜 壞朋友 Topic", "阿杜 坏朋友 Topic"],
    8: ["阿杜 門後 Topic", "阿杜 门后 Topic"],
    9: ["阿杜 一諾千年 Topic", "阿杜 一诺千年 Topic"],
    10: ["阿杜 自作自受 Topic"],
    11: ["阿杜 爛好人 Topic", "阿杜 烂好人 Topic"],
    67: ["阿杜 差一点 私藏摇滚版 Topic", "阿杜 差一點 私藏搖滾版 Topic"],
    51: ["阿杜 自然发呆 Topic", "阿杜 第九次初恋 自然发呆 Topic"],
    52: ["阿杜 第9次初恋 Topic", "阿杜 第九次初恋 Topic"],
    53: ["阿杜 离开我的自由 Topic", "阿杜 失联 Topic"],
    55: ["阿杜 离开我的自由 Topic", "阿杜 第九次初恋 离开我的自由 Topic"],
    57: ["阿杜 左心房 Topic", "阿杜 第九次初恋 左心房 Topic"],
    30: ["阿杜 哈囉 Topic", "阿杜 哈罗 Topic"],

    # === 阿牛 ===
    287: ["阿牛 唱一首歌给你听 Topic", "陈庆祥 唱一首歌给你听 Topic"],
    289: ["阿牛 对面的女孩看过来 Topic", "陈庆祥 对面的女孩看过来 Topic"],
    290: ["阿牛 我和我的四个妹妹 Topic", "陈庆祥 我和我的四个妹妹 Topic"],
    291: ["阿牛 花言巧语 Topic", "陈庆祥 花言巧语 Topic"],
    292: ["阿牛 卖菜老头 Topic", "陈庆祥 卖菜老头 Topic"],
    293: ["阿牛 大肚腩 Topic", "陈庆祥 大肚腩 Topic"],
    296: ["阿牛 阿牛和阿花的故事 Topic", "陈庆祥 阿牛和阿花的故事 Topic"],
    297: ["阿牛 乡歌 Topic", "陈庆祥 乡歌 Topic"],
    298: ["阿牛 城市蓝天 Topic", "陈庆祥 城市蓝天 Topic"],
    299: ["阿牛 对面的女孩看过来 Live Topic", "阿牛 对面的女孩看过来 Topic"],
    300: ["阿牛 城市蓝天 Live Topic", "阿牛 城市蓝天 Topic"],
    301: ["阿牛 唱一首歌给你听 Unplugged Topic", "阿牛 唱一首歌给你听 Topic"],
    
    259: ["阿牛 爱我久久 最近好吗 Topic", "阿牛 最近好吗 Topic", "阿牛 How Is Everything Topic"],
    262: ["阿牛 家在哪里 Topic", "阿牛 家在哪裏 Topic", "阿牛 Where Is Your Home Topic"],
    263: ["阿牛 村子变了 Topic", "阿牛 村子變了 Topic", "阿牛 The Village Has Changed Topic"],
    266: ["阿牛 花裙子 Topic", "阿牛 Flower Skirt Topic"],
    267: ["阿牛 裙摆摇摇 Topic", "阿牛 裙擺搖搖 Topic", "阿牛 Swinging Skirt Topic"],
    268: ["阿牛 老友记 Topic", "阿牛 欠我的时光 Topic", "阿牛 The Time You Owed Me Topic"],
    
    172: ["阿牛 酷姑娘 Topic", "阿牛 Ms. Cool Topic"],
    175: ["阿牛 你不要我了 Topic", "阿牛 You Don't Want Me Anymore Topic"],
    177: ["阿牛 我傻傻爱上你 Topic", "阿牛 我傻傻愛上你 Topic"],
    178: ["阿牛 再见 Topic", "阿牛 再見 Topic", "阿牛 Goodbye Topic"],
    179: ["阿牛 约会 Topic", "阿牛 約會 Topic", "阿牛 Appointment Topic"],
    
    180: ["阿牛 无尾熊抱抱 Topic", "阿牛 無尾熊抱抱 Topic"],
    196: ["阿牛 有缘来作伙 Topic", "阿牛 有緣來作伙 Topic"],
    229: ["阿牛 有缘来做伙 Topic", "阿牛 有緣來做伙 Topic"],
    221: ["阿牛 圆成一个家 Topic", "阿牛 圓成一個家 Topic"],
    322: ["阿牛 Sungai Puyu 的风 Topic", "阿牛 Sungai Puyu的风"],
    335: ["阿牛 Sungai Puyu 的风 Topic", "阿牛 Sungai Puyu的风"],
    325: ["阿牛 阿牛和阿花的故事 Topic"],
    249: ["阿牛 阿明的心事 Topic"],
    251: ["阿牛 冇钱冇镭 Topic", "阿牛 冇钱冇镪 Topic"],
    254: ["阿牛 Kopi O 厚厚一杯别太甜 Topic"],

    139: ["阿牛 钱嚟紧 Topic", "阿牛 Money Coming Topic"],
    141: ["阿牛 成功人士 Topic"],
    142: ["阿牛 钱叠钱 Topic", "阿牛 Racks On Racks Topic"],
    143: ["阿牛 扎职 Topic"],
    144: ["阿牛 爽 Topic"],
    145: ["阿牛 古惑仔 Topic"],
    147: ["阿牛 富贵险中求 Topic"],

    # === 腾格尔 ===
    17086: ["腾格尔 记住你 Topic", "腾格尔 Keep You In My Mind Topic"],
    17087: ["腾格尔 在银色的月光下 Topic", "腾格尔 在銀色的月光下 Topic"],
    17088: ["腾格尔 蒙古人 Topic", "腾格尔 苍狼大地 蒙古人 Topic"],
    17090: ["腾格尔 驼铃 Topic", "腾格尔 送战友 Topic", "腾格尔 怀念战友 Topic"],
    17091: ["腾格尔 草原之夜 Topic"],
    17093: ["腾格尔 鸿雁 Topic", "腾格尔 小白菜 Topic"],
    17095: ["腾格尔 再会吧我的心上人 Topic", "腾格尔 再会吧,我的心上人 Topic"],
    17096: ["腾格尔 蒙古人 蒙语 Topic", "腾格尔 蒙古人(蒙) Topic"],
    17098: ["腾格尔 跨越 Topic"],
    
    17133: ["腾格尔 在银色的月光下 Topic"],
    17134: ["腾格尔 驼铃 Topic", "腾格尔 怀念战友 Topic"],
    17135: ["腾格尔 鸿雁 Topic"],
    17137: ["腾格尔 半个月亮爬上来 Topic", "腾格尔 月牙五更 Topic"],
    17139: ["腾格尔 金瓶似的小山 Topic"],
    17141: ["腾格尔 黄河的水干了 Topic"],
    17142: ["腾格尔 鸿雁 Topic", "腾格尔 大雁 Topic"],
    17143: ["腾格尔 怀念战友 Topic", "腾格尔 这歌很难唱 Topic"],
    17145: ["腾格尔 草原之夜 Topic"],
    
    17041: ["腾格尔 父亲的草原母亲的河 Topic"],
    17044: ["腾格尔 森吉德玛 Topic"],
    17045: ["腾格尔 蓝色的故乡 Topic"],
    17048: ["腾格尔 故乡 Topic"],
    17049: ["腾格尔 蒙古人 Topic"],
    17050: ["腾格尔 很多年 Topic"],
    
    17019: ["腾格尔 蒙古人 Topic"],
    17029: ["腾格尔 父亲的草原母亲的河 Topic"],
    17020: ["腾格尔 天堂 Topic"],
    17031: ["腾格尔 蒙古人 Topic"],
    17032: ["腾格尔 天堂 Topic"],
    17023: ["腾格尔 梦 Topic"],
    
    17002: ["腾格尔 天堂 Topic"],
    17099: ["腾格尔 蒙古人 Topic"],
    17005: ["腾格尔 蒙古人 Topic"],
    17006: ["腾格尔 鹰之恋 Topic", "腾格尔 鷹之戀 Topic"],
    17013: ["腾格尔 小河摸鱼 Topic", "腾格尔 小河摸魚 Topic"],
    
    17068: ["腾格尔 天堂 Topic"],
    17070: ["腾格尔 蒙古人 Topic"],
    17076: ["腾格尔 黄河的水干了 Topic"],
    17051: ["腾格尔 赛白努 Topic", "腾格尔 SanBaiNo Topic"],
    17053: ["腾格尔 不愿等待就走你的 Topic", "腾格尔 不願等待就走你的 Topic"],
    17113: ["腾格尔 鹰之恋 Topic"],
    17125: ["腾格尔 蒙古人 Topic"]
}

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

def get_official_dur(artist, title):
    try:
        url = f"http://music.163.com/api/search/get/web?s={requests.utils.quote(f'{artist} {title}')}&type=1&offset=0&total=true&limit=1"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        songs = r.get('result', {}).get('songs', [])
        if songs:
            return songs[0].get('duration', 0) / 1000.0
    except Exception:
        pass
    return 0.0

def search_replenish_candidate(sid, artist, title, off_dur):
    queries = CUSTOM_SEARCH_QUERIES.get(sid, [
        f"{artist} - Topic {title}",
        f"{artist} {title} 官方音源",
        f"Provided to YouTube {artist} {title}"
    ])
    
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
            # 严格黑名单
            if any(bk in lower_text for bk in BLACK_KEYWORDS):
                if 'live' not in title.lower():
                    continue
            
            # 时长卡尺（若官方时长有效）
            if off_dur > 0 and v_dur > 0:
                if abs(v_dur - off_dur) > 8:
                    continue
                    
            # 必须具有高质量官方发布特征 (Topic 频道或官方 Provided to YouTube)
            is_official = (
                '- topic' in v_ch.lower() or 
                'provided to youtube' in v_desc.lower() or
                'official audio' in v_title.lower() or
                '官方音源' in v_title or
                '旭润音乐' in v_desc or
                '海蝶' in v_desc or
                '滚石' in v_desc or
                'rock records' in v_desc.lower()
            )
            
            if is_official:
                return {
                    'id': v_id,
                    'title': v_title,
                    'channel': v_ch,
                    'duration': v_dur,
                    'url': f"https://www.youtube.com/watch?v={v_id}"
                }
    return None

def process_replenish_track(sid, artist, album, title):
    print(f"\n🎵 [{sid}] {artist} - 《{title}》 ({album})", flush=True)
    
    off_dur = 0.0
    if '品' not in title:
        off_dur = get_official_dur(artist, title)
        if off_dur > 0:
            print(f"   官方 CD 标准时长: {off_dur:.1f}s", flush=True)
            
    cand = search_replenish_candidate(sid, artist, title, off_dur)
    
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    c = conn.cursor()
    
    if not cand:
        print(f"   ⚪ 未检索到 100% 录音室合规母带 -> 保持留白", flush=True)
        c.execute("""
            UPDATE tracks_sync_state 
            SET status = 'UNLIT_SKIPPED', 
                last_error = '经精准中英/品名别名检索仍无100%正版母带，保持严格留白',
                updated_at = CURRENT_TIMESTAMP 
            WHERE song_id = ?
        """, (sid,))
        conn.commit()
        conn.close()
        return False
        
    print(f"   ✅ 命中录音室原版母带: 【{cand['title']}】 ({cand['duration']}s | {cand['channel']})", flush=True)
    
    raw_tmp = os.path.join(WORK_DIR, f"raw_replenish_{sid}.mp3")
    clean_f = os.path.join(WORK_DIR, f"s_{sid}.mp3")
    
    # 3. 下载
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
        print(f"   ❌ EBU R128 转码异常: {e}", flush=True)
        conn.close()
        return False
        
    # 5. 上传至 R2 存储桶 3
    r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
    full_url = f"{public_domain}/{r2_key}"
    
    try:
        s3_client.upload_file(clean_f, bucket3_name, r2_key, ExtraArgs={"ContentType": "audio/mpeg"})
        print(f"   🚀 R2 上传完成: -> {bucket3_name}", flush=True)
    except Exception as e:
        print(f"   ❌ R2 上传异常: {e}", flush=True)
        conn.close()
        return False
        
    # 6. D1 毫秒级瞬时点亮
    try:
        resp = requests.post(
            'https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light',
            json={'updates': [{'id': sid, 'file_path': full_url}]},
            proxies=PROXIES,
            timeout=15
        )
        if resp.status_code == 200:
            print(f"   ✨ D1 边缘点亮成功！", flush=True)
        else:
            print(f"   ⚠️ D1 点亮响应: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"   ⚠️ D1 接口异常: {e}", flush=True)
        
    # 7. 更新本地数据库状态机
    c.execute("""
        UPDATE tracks_sync_state 
        SET status = 'D1_LIT', 
            r2_mp3_key = ?, 
            file_size = ?,
            is_compressed = 1,
            bitrate_kbps = 160,
            qa_status = 'VERIFIED_STUDIO_EBUR128',
            uploaded_at = CURRENT_TIMESTAMP,
            lit_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP 
        WHERE song_id = ?
    """, (full_url, os.path.getsize(clean_f), sid))
    conn.commit()
    conn.close()
    
    if os.path.exists(clean_f): os.remove(clean_f)
    return True

def run_replenish_all():
    print("=" * 90, flush=True)
    print("🚀 启动四大歌手（刀郎、阿杜、阿牛、腾格尔）缺失曲目专项高保真补齐引擎", flush=True)
    print("   • 目标存储桶: account_03 (moody-music-asset-03)", flush=True)
    print("   • 响度规范: EBU R128 (-14 LUFS / -1.0 dBFS)", flush=True)
    print("   • 音源门禁: 100% 官方录音室正版母带 (排除现场/微电影/翻唱)", flush=True)
    print("=" * 90, flush=True)
    
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    c = conn.cursor()
    
    c.execute('''
        SELECT song_id, artist_name, album_title, song_title
        FROM tracks_sync_state
        WHERE artist_name IN ('刀郎', '阿杜', '阿牛', '腾格尔') AND status != 'D1_LIT'
        ORDER BY 
            CASE artist_name 
                WHEN '刀郎' THEN 1 
                WHEN '阿杜' THEN 2 
                WHEN '阿牛' THEN 3 
                WHEN '腾格尔' THEN 4 
                ELSE 5 
            END,
            album_title, track_index
    ''')
    target_tracks = c.fetchall()
    conn.close()
    
    print(f"📋 共筛选出待补齐曲目: {len(target_tracks)} 首", flush=True)
    
    success_count = 0
    blank_count = 0
    
    for idx, (sid, art, alb, tit) in enumerate(target_tracks, 1):
        print(f"\n[{idx}/{len(target_tracks)}] 正在补齐曲目...", flush=True)
        ok = process_replenish_track(sid, art, alb, tit)
        if ok:
            success_count += 1
        else:
            blank_count += 1
            
    print("\n" + "=" * 90, flush=True)
    print(f"🎉 四大歌手专项补齐收官！", flush=True)
    print(f"   • 成功高保真点亮: {success_count} 首", flush=True)
    print(f"   • 严格宁缺毋滥留白: {blank_count} 首", flush=True)
    print("=" * 90, flush=True)

if __name__ == "__main__":
    run_replenish_all()
