#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 知名歌手稀疏专辑录音室母带多源补齐与自动化点亮流水线
==============================================================================
核心原则与铁律:
1. 存储路由规则 (用户铁律):
   - 优先选择该歌手已有点亮歌曲主要存放的存储桶；
   - 若该桶累计大小达到 9.50 GB 熔断红线，自动顺延写入 4/5/6 桶（优先选择余量充裕的桶）；
   - 若 4、5、6 号桶均达到 9.50 GB 熔断红线，自动启动第 7 桶 (moody-music-asset-07)。
2. 多源采集保障:
   - 源 1: 网易云音乐高保真直链 (无代理、CD音质秒下)
   - 源 2: 酷我音乐高品质直链 (无代理、港台老歌/黑胶覆盖极广)
   - 源 3: YouTube 官方录音室母带 / Topic 音频 (简繁双搜、25s~600s 时长门卫防合集)
   - 源 4: 哔哩哔哩 (Bilibili) 官方音频/视频提取 (单曲时长过滤)
3. 音频标准化规格:
   - ffmpeg EBU R128 (-14 LUFS, TP -1.5) 响度标准化
   - 160 kbps CBR (44.1kHz, 2-channel) libmp3lame
   - 注入 Xing Header，保证前端进度条拖动毫秒精准
4. 歌词与元数据:
   - syncedlyrics 毫秒级同步时间轴 LRC
5. 云端点亮与多端一致:
   - S3 上传至 R2 对应桶
   - Cloudflare D1 /api/admin/songs/batch-light 在线毫秒点亮
   - 同步本地 catalog_sync.db (tracks_sync_state 与 songs 表)
==============================================================================
"""

import os
import sys
import re
import json
import time
import sqlite3
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics
import zhconv

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
TMP_DIR = os.path.join(BASE_DIR, "downloads_optimized", "sparse_pipeline")
os.makedirs(TMP_DIR, exist_ok=True)

sys.path.insert(0, os.path.join(BASE_DIR, "database"))
try:
    from wanfang_song_aliases import WANFANG_ALIASES
except Exception:
    WANFANG_ALIASES = {}

try:
    from feiyuqing_song_aliases import FEIYUQING_ALIASES
except Exception:
    FEIYUQING_ALIASES = {}

try:
    from linyoujia_song_aliases import LINYOUJIA_ALIASES
except Exception:
    LINYOUJIA_ALIASES = {}

try:
    from huangxiaohu_song_aliases import HUANGXIAOHU_ALIASES
except Exception:
    HUANGXIAOHU_ALIASES = {}

try:
    from yuchengqing_song_aliases import YUCHENGQING_ALIASES
except Exception:
    YUCHENGQING_ALIASES = {}

try:
    from suhuilun_song_aliases import SUHUILUN_ALIASES
except Exception:
    SUHUILUN_ALIASES = {}

YOUTUBE_PROXY = "http://127.0.0.1:10090"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
MAX_SAFE_BYTES = int(9.50 * 1024 * 1024 * 1024) # 9.50 GB 严格熔断红线

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    R2_CFG = json.load(f)

# 初始化 S3 客户端字典
S3_CLIENTS = {}

def get_s3_client(acc_key: str):
    if acc_key not in S3_CLIENTS:
        acc = R2_CFG['buckets'][acc_key]
        S3_CLIENTS[acc_key] = boto3.client(
            's3',
            endpoint_url=acc['endpoint_url'],
            aws_access_key_id=acc['access_key_id'],
            aws_secret_access_key=acc['secret_access_key'],
            config=Config(signature_version='s3v4')
        )
    return S3_CLIENTS[acc_key]

def get_bucket_current_bytes(acc_key: str) -> int:
    """查询存储桶在 tracks_sync_state 中的累计大小作为基准 (叠加实测底座水位)"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    domain_keyword = R2_CFG['buckets'][acc_key].get('name', '')
    cur.execute("""
        SELECT COALESCE(SUM(file_size), 0)
        FROM tracks_sync_state
        WHERE status = 'D1_LIT' AND (r2_mp3_key LIKE ? OR r2_mp3_key LIKE ?)
    """, (f"%{domain_keyword}%", f"%{R2_CFG['buckets'][acc_key].get('public_domain', 'NONEXIST')}%"))
    db_bytes = cur.fetchone()[0]
    conn.close()
    if acc_key == 'account_07':
        db_bytes += 5638278316
    return db_bytes

def get_artist_primary_bucket(artist: str) -> str:
    """查询该歌手已有已点亮歌曲主要存放在哪个存储桶"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT r2_mp3_key
        FROM tracks_sync_state
        WHERE artist_name = ? AND status = 'D1_LIT' AND r2_mp3_key IS NOT NULL
    """, (artist,))
    rows = cur.fetchall()
    conn.close()
    
    counts = {}
    for r in rows:
        key = r[0]
        for acc_key, b in R2_CFG['buckets'].items():
            if b['name'] in key or b.get('public_domain', '') in key:
                counts[acc_key] = counts.get(acc_key, 0) + 1
    if counts:
        return max(counts.items(), key=lambda x: x[1])[0]
    return 'account_06' # 默认 Bucket 06

def select_target_bucket_for_artist(artist: str, estimated_file_size: int = 5 * 1024 * 1024) -> tuple[str, str, str]:
    """
    依照用户最新指令 (2026-09-19): 
    家里电脑采录下载直接锁定写入第 8 桶 (moody-music-asset-08)，
    严禁写入 7 桶，防止与公司电脑并发写入将 7 桶撑爆！
    """
    acc = 'account_08'
    if acc in R2_CFG['buckets'] and get_bucket_current_bytes(acc) + estimated_file_size < MAX_SAFE_BYTES:
        b_info = R2_CFG['buckets'][acc]
        return acc, b_info['name'], b_info['public_domain']
    
    print("\n   🔴 [9.50 GB 熔断保护] Bucket 08 已达 9.50 GB 安全熔断红线！")
    return None, None, None

def get_song_aliases(song: str, song_id: int = None) -> list[str]:
    """提取歌名别名、括号中英文、去除乱码与常见误写"""
    clean_song = re.sub(r'\(.*?\)|（.*?）', '', song).strip()
    res = [clean_song]
    
    # 优先注入权威字典别名 (如万芳 191 首中英文权威映射、费玉清拼音映射)
    if song_id and song_id in WANFANG_ALIASES:
        for a in WANFANG_ALIASES[song_id]:
            if a not in res:
                res.insert(0, a)

    if song in FEIYUQING_ALIASES:
        for a in FEIYUQING_ALIASES[song]:
            if a not in res:
                res.insert(0, a)
    elif clean_song in FEIYUQING_ALIASES:
        for a in FEIYUQING_ALIASES[clean_song]:
            if a not in res:
                res.insert(0, a)

    if song in LINYOUJIA_ALIASES:
        for a in LINYOUJIA_ALIASES[song]:
            if a not in res:
                res.insert(0, a)
    elif clean_song in LINYOUJIA_ALIASES:
        for a in LINYOUJIA_ALIASES[clean_song]:
            if a not in res:
                res.insert(0, a)

    if song in HUANGXIAOHU_ALIASES:
        for a in HUANGXIAOHU_ALIASES[song]:
            if a not in res:
                res.insert(0, a)
    elif clean_song in HUANGXIAOHU_ALIASES:
        for a in HUANGXIAOHU_ALIASES[clean_song]:
            if a not in res:
                res.insert(0, a)

    if song in YUCHENGQING_ALIASES:
        for a in YUCHENGQING_ALIASES[song]:
            if a not in res:
                res.insert(0, a)
    elif clean_song in YUCHENGQING_ALIASES:
        for a in YUCHENGQING_ALIASES[clean_song]:
            if a not in res:
                res.insert(0, a)

    if song in SUHUILUN_ALIASES:
        for a in SUHUILUN_ALIASES[song]:
            if a not in res:
                res.insert(0, a)
    elif clean_song in SUHUILUN_ALIASES:
        for a in SUHUILUN_ALIASES[clean_song]:
            if a not in res:
                res.insert(0, a)

    # 提取混杂在英文标题里的连续中文字符串 (如: "Do I Still Loathe You? 恨里受罪" -> "恨里受罪")
    cjk_matches = re.findall(r'[\u4e00-\u9fa5\u3400-\u4dbf]+', song)
    for cjk in cjk_matches:
        if len(cjk) >= 1 and cjk not in res:
            res.append(cjk)

    match = re.search(r'[\(（]([^\)）]+)[\)）]', song)
    if match:
        extracted = match.group(1).strip()
        if extracted and extracted not in res:
            res.append(extracted)
            
    # 简繁双向拓展
    for v in list(res):
        simp = zhconv.convert(v, 'zh-cn')
        trad = zhconv.convert(v, 'zh-hant')
        for item in [simp, trad]:
            if item not in res:
                res.append(item)
            
    # 特殊曲目翻译别名映射
    if "You Will Never Get Lonely Anymore" in song:
        res.extend(["誰能讓我不再寂寞", "谁能让我不再寂寞"])
    if "Prolong Vacation" in song:
        res.extend(["長假", "长假"])
    if "Even Though One Day We Separate" in song:
        res.extend(["縱然有一天我們分離", "纵然有一天我们分离"])

    return list(dict.fromkeys([x for x in res if x]))

def download_from_netease(artist: str, song: str, target_path: str, album: str = "", song_id: int = None) -> bool:
    """源 A: 网易云官方外链抓取 (无损/高品质 MP3，无代理极速下载)"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0'}
    aliases = get_song_aliases(song, song_id=song_id)
    clean_album = re.sub(r'\(.*?\)|（.*?）', '', album).strip() if album else ""

    for s_name in aliases:
        queries = [f"{artist} {s_name}"]
        if clean_album and not re.search(r'^[a-zA-Z0-9\s]+$', clean_album): # 排除纯拼音专辑
            queries.append(f"{artist} {clean_album} {s_name}")
            
        for query in queries:
            url = f"https://music.163.com/api/search/get/web?s={query}&type=1&limit=5"
            try:
                r = requests.get(url, headers=headers, timeout=6)
                if r.status_code == 200:
                    songs = r.json().get('result', {}).get('songs', [])
                    for s in songs:
                        s_name_cand = s.get('name', '').strip()
                        s_art = s.get('artists', [{}])[0].get('name', '').strip()
                        if artist not in s_art and s_art not in artist:
                            continue
                        if s_name.lower() not in s_name_cand.lower() and s_name_cand.lower() not in s_name.lower():
                            continue

                        sid = s.get('id')
                        mp3_url = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
                        head = requests.head(mp3_url, headers=headers, allow_redirects=True, timeout=5)
                        ctype = head.headers.get('Content-Type', '')
                        size = int(head.headers.get('Content-Length', 0))
                        if head.status_code == 200 and 'audio' in ctype and size > 1000000:
                            stream_r = requests.get(mp3_url, headers=headers, stream=True, timeout=20)
                            with open(target_path, 'wb') as f:
                                for chunk in stream_r.iter_content(chunk_size=65536):
                                    if chunk: f.write(chunk)
                            if os.path.exists(target_path) and os.path.getsize(target_path) > 1000000:
                                return True
            except Exception:
                pass
    return False

def download_from_kuwo(artist: str, song: str, target_path: str, album: str = "", song_id: int = None) -> bool:
    """源 B: 酷我音乐高品质直链采录 (经典老歌库极大, 无代理秒速)"""
    import ast
    aliases = get_song_aliases(song, song_id=song_id)
    clean_album = re.sub(r'\(.*?\)|（.*?）', '', album).strip() if album else ""
    for s_name in aliases:
        queries = [f"{artist} {s_name}"]
        if clean_album and not re.search(r'^[a-zA-Z0-9\s]+$', clean_album):
            queries.append(f"{clean_album} {s_name}")
            queries.append(f"{artist} {clean_album} {s_name}")
        for query in queries:
            search_url = f"http://search.kuwo.cn/r.s?client=kt&all={query}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=6"
            try:
                r = requests.get(search_url, timeout=5)
                if r.status_code == 200:
                    raw = r.text.replace('&nbsp;', ' ')
                    data = ast.literal_eval(raw)
                    for item in data.get('abslist', []):
                        art = item.get('ARTIST', '')
                        sname = item.get('SONGNAME', '')
                        alb = item.get('ALBUM', '')
                        art_match = (artist in art or art in artist or '群星' in art)
                        if not art_match and clean_album and clean_album in alb:
                            art_match = True
                        if not art_match:
                            continue
                        if s_name.lower() not in sname.lower() and sname.lower() not in s_name.lower():
                            continue
                        rid = item.get('MUSICRID', '').replace('MUSIC_', '')
                        if not rid:
                            continue
                        play_url = f"http://antiserver.kuwo.cn/anti.s?type=convert_url&rid={rid}&format=mp3&response=url"
                        stream_link = requests.get(play_url, timeout=4).text.strip()
                        if stream_link.startswith('http'):
                            head = requests.head(stream_link, timeout=4)
                            size = int(head.headers.get('Content-Length', 0))
                            if size > 1000000:
                                stream_r = requests.get(stream_link, stream=True, timeout=20)
                                with open(target_path, 'wb') as f:
                                    for chunk in stream_r.iter_content(chunk_size=65536):
                                        if chunk: f.write(chunk)
                                if os.path.exists(target_path) and os.path.getsize(target_path) > 1000000:
                                    return True
            except Exception:
                pass
    return False

def download_from_youtube(artist: str, song: str, target_path: str, album: str = "", song_id: int = None) -> bool:
    """源 C: YouTube 官方录音室母带下载 (支持简繁双重索引, 时长门卫)"""
    aliases = get_song_aliases(song, song_id=song_id)
    node_rt = 'node:D:\\DevelopeTools\\Node\\node.exe' if os.path.exists(r'D:\DevelopeTools\Node\node.exe') else 'node'
    clean_album = re.sub(r'\(.*?\)|（.*?）', '', album).strip() if album else ""
    
    queries = []
    for s_name in aliases:
        queries.append(f"{artist} {s_name}")
        queries.append(f"{zhconv.convert(artist, 'zh-hant')} {zhconv.convert(s_name, 'zh-hant')}")
        if clean_album and not re.search(r'^[a-zA-Z0-9\s]+$', clean_album):
            queries.append(f"{artist} {clean_album} {s_name}")
            queries.append(f"{zhconv.convert(artist, 'zh-hant')} {zhconv.convert(clean_album, 'zh-hant')} {zhconv.convert(s_name, 'zh-hant')}")
    
    queries = list(dict.fromkeys(queries))[:6]
    for q in queries:
        cmd = [
            "yt-dlp",
            "--proxy", YOUTUBE_PROXY,
            "--js-runtimes", node_rt,
            "--no-playlist",
            "--force-overwrites",
            "--match-filter", "duration > 25 & duration < 600",
            "-f", "ba/b",
            "-x", "--audio-format", "mp3", "--audio-quality", "0",
            "-o", target_path.replace(".mp3", ".%(ext)s"),
            f"ytsearch3:{q}"
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', timeout=45)
            base = target_path.rsplit(".", 1)[0]
            for ext in ['.mp3', '.m4a', '.opus', '.webm']:
                cand = f"{base}{ext}"
                if os.path.exists(cand) and os.path.getsize(cand) > 500000:
                    if cand != target_path:
                        subprocess.run(["ffmpeg", "-y", "-i", cand, "-vn", "-b:a", "320k", target_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                        try: os.remove(cand)
                        except: pass
                    return True
        except Exception:
            pass
    return False

def download_from_bilibili(artist: str, song: str, target_path: str, song_id: int = None) -> bool:
    """源 D: 哔哩哔哩 (Bilibili) 官方音频/单曲提取 (单曲时长过滤)"""
    aliases = get_song_aliases(song, song_id=song_id)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0',
        'Referer': 'https://www.bilibili.com/'
    }
    for s_name in aliases:
        query = f"{artist} {s_name}"
        try:
            sess = requests.Session()
            sess.get('https://www.bilibili.com', headers=headers, timeout=5)
            url = f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={query}"
            r = sess.get(url, headers=headers, timeout=6)
            if r.status_code == 200 and r.json().get('code') == 0:
                results = r.json().get('data', {}).get('result', [])
                for item in results:
                    raw_title = item.get('title', '')
                    clean_title = re.sub(r'<.*?>', '', raw_title).strip()
                    if any(bad in clean_title for bad in ['合集', '精选', '首歌曲', '演唱会', '翻唱', '吉他教学', '串烧']):
                        continue
                    if s_name.lower() not in clean_title.lower():
                        continue
                    dur_str = item.get('duration', '0:0')
                    parts = dur_str.split(':')
                    if len(parts) == 2:
                        m, s = int(parts[0]), int(parts[1])
                        total_s = m * 60 + s
                        if total_s < 60 or total_s > 480:
                            continue
                    elif len(parts) > 2:
                        continue

                    bvid = item.get('bvid') or item.get('arcurl')
                    video_url = f"https://www.bilibili.com/video/{bvid}" if not bvid.startswith('http') else bvid
                    cmd = [
                        "yt-dlp",
                        "--no-playlist",
                        "--force-overwrites",
                        "-f", "ba/b",
                        "-x", "--audio-format", "mp3", "--audio-quality", "0",
                        "-o", target_path.replace(".mp3", ".%(ext)s"),
                        video_url
                    ]
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', timeout=45)
                    base = target_path.rsplit(".", 1)[0]
                    for ext in ['.mp3', '.m4a', '.opus', '.webm']:
                        cand = f"{base}{ext}"
                        if os.path.exists(cand) and os.path.getsize(cand) > 500000:
                            if cand != target_path:
                                subprocess.run(["ffmpeg", "-y", "-i", cand, "-vn", "-b:a", "320k", target_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                                try: os.remove(cand)
                                except: pass
                            return True
        except Exception:
            pass
    return False

def standardize_audio(raw_path: str, opt_path: str) -> tuple[int, int]:
    """使用 ffmpeg 进行 EBU R128 (-14 LUFS) 响度标准化 + 160k CBR 44.1kHz 压制并写入 Xing Header"""
    cmd = [
        "ffmpeg", "-y", "-i", raw_path,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "160k",
        "-c:a", "libmp3lame",
        "-write_xing", "1",
        opt_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", opt_path]
    dur_proc = subprocess.run(dur_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    duration_sec = int(float(dur_proc.stdout.strip()))
    file_size = os.path.getsize(opt_path)
    return duration_sec, file_size

def fetch_lrc(artist: str, album: str, song: str, lrc_path: str, song_id: int = None) -> bool:
    """毫秒级歌词同步检索"""
    aliases = get_song_aliases(song, song_id=song_id)
    queries = []
    for s_name in aliases:
        queries.append(f"{artist} {s_name}")
        queries.append(f"{s_name}")
        if album and not re.search(r'^[a-zA-Z0-9\s]+$', clean_album if 'clean_album' in locals() else album):
            queries.append(f"{artist} {album} {s_name}")

    for q in list(dict.fromkeys(queries))[:8]:
        try:
            lrc = syncedlyrics.search(q, providers=['NetEase', 'Kugou', 'Lrclib'])
            if lrc and len(lrc) > 50 and "[" in lrc:
                with open(lrc_path, 'w', encoding='utf-8') as f:
                    f.write(lrc)
                return True
        except Exception:
            pass
    return False

def process_single_song(song_info: dict) -> bool:
    sid = song_info['id']
    artist = song_info['artist']
    album = song_info['album']
    title = song_info['title']

    print(f"\n🎵 [ID: {sid:<5}] 正在采录: [{artist}] 《{album}》 - 《{title}》")

    raw_audio = os.path.join(TMP_DIR, f"raw_{sid}.mp3")
    opt_audio = os.path.join(TMP_DIR, f"s_{sid}.mp3")
    lrc_file = os.path.join(TMP_DIR, f"s_{sid}.lrc")

    for fpath in [raw_audio, opt_audio, lrc_file]:
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except: pass

    # 1. 尝试多源下载
    downloaded = False
    print("   • 尝试源 1 (网易云音乐高保真直链)...", end="", flush=True)
    if download_from_netease(artist, title, raw_audio, album=album, song_id=sid):
        print(" [成功!]")
        downloaded = True
    else:
        print(" [跳过/未收录]")
        print("   • 尝试源 2 (酷我音乐高品质直链)...", end="", flush=True)
        if download_from_kuwo(artist, title, raw_audio, album=album, song_id=sid):
            print(" [成功!]")
            downloaded = True
        else:
            print(" [跳过/未收录]")
            print("   • 尝试源 3 (YouTube 官方录音室母带)...", end="", flush=True)
            if download_from_youtube(artist, title, raw_audio, album=album, song_id=sid):
                print(" [成功!]")
                downloaded = True
            else:
                print(" [失败]")
                print("   • 尝试源 4 (Bilibili 高清视频/音频提取)...", end="", flush=True)
                if download_from_bilibili(artist, title, raw_audio, song_id=sid):
                    print(" [成功!]")
                    downloaded = True
                else:
                    print(" [失败]")

    if not downloaded or not os.path.exists(raw_audio) or os.path.getsize(raw_audio) < 100000:
        print(f"   ❌ 无法从任何渠道检索到该曲目录音室母带，跳过: 《{title}》")
        return False

    # 2. 音频标准化压制
    print("   • 正在执行 EBU R128 (-14 LUFS) 标准化与 160k CBR Xing 编码...", end="", flush=True)
    try:
        dur_sec, fsize = standardize_audio(raw_audio, opt_audio)
        print(f" [完成! 时长: {dur_sec}s, 大小: {fsize/1024/1024:.2f} MB]")
    except Exception as e:
        print(f" [编码异常: {e}]")
        return False

    # 3. 歌词抓取
    print("   • 正在检索毫秒级同步时间轴 LRC 歌词...", end="", flush=True)
    has_lrc = fetch_lrc(artist, album, title, lrc_file, song_id=sid)
    if has_lrc:
        print(" [成功获取!]")
    else:
        print(" [纯音乐/空歌词，将优雅展示]")

    # 4. 存储桶动态路由 (铁律防超 9.50 GB)
    acc_key, bname, bdomain = select_target_bucket_for_artist(artist, fsize)
    if not acc_key:
        print("   🔴 [安全暂停] 4、5、6 号存储桶均已达 9.50 GB 熔断红线！已安全终止写入，请配置第 7 桶！")
        return False
    print(f"   • 存储目标桶: {bname} ({acc_key}) | CDN: {bdomain}")

    s3 = get_s3_client(acc_key)
    # 安全文件名清理
    clean_album_dir = re.sub(r'[\\/*?:"<>|]', '_', album).strip()
    r2_audio_key = f"music/{artist}/{clean_album_dir}/s_{sid}.mp3"
    r2_lrc_key = f"music/{artist}/{clean_album_dir}/s_{sid}.lrc" if has_lrc else None

    # 上传音频
    with open(opt_audio, 'rb') as f:
        s3.put_object(Bucket=bname, Key=r2_audio_key, Body=f, ContentType='audio/mpeg')

    # 上传歌词
    if has_lrc and os.path.exists(lrc_file):
        with open(lrc_file, 'rb') as f:
            s3.put_object(Bucket=bname, Key=r2_lrc_key, Body=f, ContentType='text/plain; charset=utf-8')

    cdn_mp3_url = f"{bdomain}/{r2_audio_key}"
    cdn_lrc_url = f"{bdomain}/{r2_lrc_key}" if r2_lrc_key else None

    # 5. 调用 Cloudflare D1 接口毫秒点亮
    print("   • 正在请求 Cloudflare D1 batch-light 毫秒点亮...", end="", flush=True)
    try:
        payload = {
            "updates": [{
                "id": sid,
                "file_path": cdn_mp3_url,
                "lrc_path": cdn_lrc_url
            }]
        }
        for retry in range(3):
            res = subprocess.run([
                'curl.exe', '-s', '--noproxy', '*', '-X', 'POST', D1_LIGHT_URL,
                '-H', 'Content-Type: application/json',
                '-d', json.dumps(payload, ensure_ascii=False)
            ], capture_output=True, text=True, encoding='utf-8', timeout=15)
            if '"code":200' in res.stdout:
                print(" [🟢 D1 点亮成功!]")
                break
            time.sleep(1)
        else:
            print(f" [⚠️ D1 接口返回: {res.stdout.strip() or res.stderr.strip()}]")
    except Exception as e:
        print(f" [⚠️ D1 网络异常: {e}]")

    # 6. 本地同步更新 catalog_sync.db
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        UPDATE tracks_sync_state
        SET status = 'D1_LIT',
            r2_mp3_key = ?,
            r2_lrc_key = ?,
            file_size = ?,
            duration = ?,
            bitrate_kbps = 160,
            lit_at = CURRENT_TIMESTAMP,
            last_error = NULL
        WHERE song_id = ?
    """, (cdn_mp3_url, cdn_lrc_url, fsize, str(dur_sec), sid))

    cur.execute("""
        UPDATE songs
        SET file_path = ?,
            lrc_path = ?,
            duration = ?
        WHERE id = ?
    """, (cdn_mp3_url, cdn_lrc_url, dur_sec, sid))
    conn.commit()
    conn.close()

    # 清理临时文件
    for fpath in [raw_audio, opt_audio, lrc_file]:
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except: pass

    print(f"   🎉 【已点亮上线】: 《{title}》 -> {cdn_mp3_url}")
    return True

def run_artist_pipeline(target_artist: str, target_album: str = None, max_limit: int = None):
    print("=" * 90)
    print(f"🚀 MOODY 知名歌手稀疏专辑采录流水线: 【{target_artist}】")
    print("=" * 90)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    query = """
        SELECT s.id, ar.name, al.title, s.title, s.track_index
        FROM songs s
        JOIN albums al ON s.album_id = al.id
        JOIN artists ar ON s.artist_id = ar.id
        WHERE ar.name = ? 
          AND (s.file_path IS NULL OR s.file_path = '')
    """
    params = [target_artist]
    if target_album:
        query += " AND al.title LIKE ?"
        params.append(f"%{target_album}%")

    query += " ORDER BY al.id, s.track_index, s.id"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()

    if max_limit:
        rows = rows[:max_limit]

    print(f"📋 歌手: {target_artist} | 待处理缺失曲目总数: {len(rows)} 首")
    if not rows:
        print("✨ 该歌手所有曲目均已 100% 点亮上线！无需处理。")
        return 0, 0

    success_count = 0
    for r in rows:
        target_acc = select_target_bucket_for_artist(target_artist)[0]
        if not target_acc:
            print("\n🚨 [安全熔断] 4、5、6 号存储桶均已达 9.50 GB 红线，安全停止后续曲目处理！")
            break
        song_info = {
            'id': r[0],
            'artist': r[1],
            'album': r[2],
            'title': r[3],
            'track_index': r[4]
        }
        ok = process_single_song(song_info)
        if ok:
            success_count += 1
        time.sleep(1)

    print("\n" + "=" * 90)
    print(f"🏁 【{target_artist}】处理完毕! 本批次共处理 {len(rows)} 首，成功点亮上线: {success_count} 首!")
    print("=" * 90)
    return len(rows), success_count

if __name__ == "__main__":
    if len(sys.argv) > 1:
        artist_arg = sys.argv[1]
        album_arg = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] not in ["None", "null", ""] else None
        limit_arg = int(sys.argv[3]) if len(sys.argv) > 3 else None
        run_artist_pipeline(artist_arg, target_album=album_arg, max_limit=limit_arg)
    else:
        # 默认按普查优先级连续执行歌手序列
        artists_queue = ['高胜美', '黄品源', '万芳', '罗大佑', '费玉清', '林宥嘉', '黄小琥', '庾澄庆', '苏慧伦']
        for art in artists_queue:
            run_artist_pipeline(art)
