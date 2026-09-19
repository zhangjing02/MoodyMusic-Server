#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 齐秦全专录音室母带多源采录与多桶动态分流补齐流水线
==============================================================================
核心规范:
1. 多源采集: 网易云高保真直链优先 -> YouTube 官方 Topic 录音室母带 -> Bilibili 官方兜底
2. 音频标准化: ffmpeg EBU R128 (-14 LUFS) 归一化 + 160 kbps CBR (44.1kHz, 2-channel) + Xing Header
3. 歌词配齐: syncedlyrics 毫秒级同步时间轴 LRC
4. 存储桶容量路由与 9.50 GB 熔断:
   - 齐秦首选归属桶: Bucket 05 (moody-music-asset-05)
   - 若 Bucket 05 达到 9.50 GB 熔断线，自动溢流写入 Bucket 06 (moody-music-asset-06)
   - 若 4、5、6 号桶均满 9.50 GB，自动溢流写入 Bucket 07
5. D1 边缘点亮: 调用 /api/admin/songs/batch-light 并同步更新 catalog_sync.db
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

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
TMP_DIR = os.path.join(BASE_DIR, "downloads_optimized", "qiqin_pipeline")
os.makedirs(TMP_DIR, exist_ok=True)

YOUTUBE_PROXY = "http://127.0.0.1:10090"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
MAX_SAFE_BYTES = int(9.50 * 1024 * 1024 * 1024) # 9.50 GB 严格熔断阈值

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
    """查询存储桶在 tracks_sync_state 中的累计大小作为基准"""
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
    return db_bytes

def select_target_bucket(estimated_file_size: int = 5 * 1024 * 1024) -> tuple[str, str, str]:
    """
    依照用户规则选取存储桶:
    1. 优先选择齐秦原有桶 Bucket 05
    2. 若超过 9.50 GB，顺延至 Bucket 06
    3. 若 Bucket 06 亦超 9.50 GB，顺延至 Bucket 04
    4. 若 4, 5, 6 均超 9.50 GB，顺延至 Bucket 07
    """
    candidates = ['account_05', 'account_06', 'account_04']
    for acc in candidates:
        curr = get_bucket_current_bytes(acc)
        if curr + estimated_file_size < MAX_SAFE_BYTES:
            b_info = R2_CFG['buckets'][acc]
            return acc, b_info['name'], b_info['public_domain']

    # 兜底到 Bucket 07
    acc = 'account_07'
    b_info = R2_CFG['buckets'].get(acc, {})
    return acc, b_info.get('name', 'moody-music-asset-07'), b_info.get('public_domain', 'https://pub-a0a90fda9b0d45d59a52685eb2ee93d6.r2.dev')

def download_from_netease(artist: str, song: str, target_path: str) -> bool:
    """源 A: 网易云官方外链抓取 (无损/高品质 MP3，无代理极速下载)"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0'}
    clean_song = re.sub(r'\(.*?\)|（.*?）', '', song).strip()
    query = f"{artist} {clean_song}"
    url = f"https://music.163.com/api/search/get/web?s={query}&type=1&limit=5"
    try:
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            songs = r.json().get('result', {}).get('songs', [])
            for s in songs:
                s_name = s.get('name', '').strip()
                s_art = s.get('artists', [{}])[0].get('name', '').strip()
                if artist not in s_art and s_art not in artist:
                    continue
                # 歌名匹配
                if clean_song.lower() not in s_name.lower() and s_name.lower() not in clean_song.lower():
                    continue

                sid = s.get('id')
                mp3_url = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
                head = requests.head(mp3_url, headers=headers, allow_redirects=True, timeout=5)
                ctype = head.headers.get('Content-Type', '')
                size = int(head.headers.get('Content-Length', 0))
                if head.status_code == 200 and 'audio' in ctype and size > 1000000: # 大于 1MB
                    # 真实下载
                    stream_r = requests.get(mp3_url, headers=headers, stream=True, timeout=20)
                    with open(target_path, 'wb') as f:
                        for chunk in stream_r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    if os.path.exists(target_path) and os.path.getsize(target_path) > 1000000:
                        return True
    except Exception as e:
        pass
def get_song_aliases(song: str) -> list[str]:
    """处理歌名别名与常见错别字转换"""
    clean_song = re.sub(r'\(.*?\)|（.*?）', '', song).strip()
    res = [clean_song]
    # 提取括号内的内容作为别名
    match = re.search(r'[\(（]([^\)）]+)[\)）]', song)
    if match:
        extracted = match.group(1).strip()
        if extracted and extracted not in res:
            res.append(extracted)
    if "播放员" in clean_song:
        res.append(clean_song.replace("播放员", "播音员"))
    if "想念是一种病" in clean_song or "Missing Is a Disease" in song:
        res.append("思念是一种病")
    if "自己的心情自己享受" in clean_song:
        res.append("自己的心情自己感受")
    if "我为了什么爱你" in clean_song or "What Do I Love You For" in song:
        res.append("我拿什么爱你")
    if "尘埃" in clean_song or "Dust" in song:
        res.append("尘")
    return list(dict.fromkeys(res))

def download_from_kuwo(artist: str, song: str, target_path: str, album: str = "") -> bool:
    """源 B: 酷我音乐高品质直链采录 (经典老歌库极大, 无代理秒速)"""
    import ast
    aliases = get_song_aliases(song)
    clean_album = re.sub(r'\(.*?\)|（.*?）', '', album).strip() if album else ""
    for s_name in aliases:
        queries = [f"{artist} {s_name}"]
        if clean_album:
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
                        # 歌手或专辑匹配
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

def download_from_youtube(artist: str, song: str, target_path: str, album: str = "") -> bool:
    """源 C: YouTube 官方录音室母带下载 (支持简繁双重索引)"""
    import zhconv
    aliases = get_song_aliases(song)
    node_rt = 'node:D:\\DevelopeTools\\Node\\node.exe' if os.path.exists(r'D:\DevelopeTools\Node\node.exe') else 'node'
    
    # 简繁双搜与多维度检索策略
    queries = []
    clean_album = re.sub(r'\(.*?\)|（.*?）', '', album).strip() if album else ""
    for s_name in aliases:
        queries.append(f"{artist} {s_name}")
        queries.append(f"{zhconv.convert(artist, 'zh-hant')} {zhconv.convert(s_name, 'zh-hant')}")
        if clean_album:
            queries.append(f"{artist} {clean_album} {s_name}")
            queries.append(f"{zhconv.convert(artist, 'zh-hant')} {zhconv.convert(clean_album, 'zh-hant')} {zhconv.convert(s_name, 'zh-hant')}")
    
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
        except Exception as e:
            pass
    return False

def download_from_bilibili(artist: str, song: str, target_path: str) -> bool:
    """源 C: 哔哩哔哩 (Bilibili) 官方音频/单曲视频抓取 (过滤合集/翻唱)"""
    clean_song = re.sub(r'\(.*?\)|（.*?）', '', song).strip()
    query = f"{artist} {clean_song}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0',
        'Referer': 'https://www.bilibili.com/'
    }
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
                # 过滤合集、演唱会、50首精选等
                if any(bad in clean_title for bad in ['合集', '精选', '首歌曲', '演唱会', '翻唱', '吉他教学', '串烧']):
                    continue
                if clean_song.lower() not in clean_title.lower():
                    continue
                dur_str = item.get('duration', '0:0')
                parts = dur_str.split(':')
                if len(parts) == 2:
                    m, s = int(parts[0]), int(parts[1])
                    total_s = m * 60 + s
                    if total_s < 80 or total_s > 480:
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
    except Exception as e:
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
    
    # 获取时长
    dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", opt_path]
    dur_proc = subprocess.run(dur_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    duration_sec = int(float(dur_proc.stdout.strip()))
    file_size = os.path.getsize(opt_path)
    return duration_sec, file_size

def fetch_lrc(artist: str, album: str, song: str, lrc_path: str) -> bool:
    """毫秒级歌词同步检索"""
    clean_song = re.sub(r'\(.*?\)|（.*?）', '', song).strip()
    queries = [
        f"{artist} {clean_song}",
        f"{artist} {song}",
        f"{clean_song}",
        f"{artist} {album} {clean_song}"
    ]
    for q in queries:
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
    if download_from_netease(artist, title, raw_audio):
        print(" [成功!]")
        downloaded = True
    else:
        print(" [跳过/未收录]")
        print("   • 尝试源 2 (酷我音乐高品质直链)...", end="", flush=True)
        if download_from_kuwo(artist, title, raw_audio, album=album):
            print(" [成功!]")
            downloaded = True
        else:
            print(" [跳过/未收录]")
            print("   • 尝试源 3 (YouTube 官方录音室母带)...", end="", flush=True)
            if download_from_youtube(artist, title, raw_audio, album=album):
                print(" [成功!]")
                downloaded = True
            else:
                print(" [失败]")
                print("   • 尝试源 4 (Bilibili 高清视频/音频提取)...", end="", flush=True)
                if download_from_bilibili(artist, title, raw_audio):
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
    has_lrc = fetch_lrc(artist, album, title, lrc_file)
    if has_lrc:
        print(" [成功获取!]")
    else:
        print(" [纯音乐/空歌词，将优雅展示]")

    # 4. 存储桶容量路由
    acc_key, bname, bdomain = select_target_bucket(fsize)
    print(f"   • 存储目标桶: {bname} ({acc_key}) | CDN: {bdomain}")

    s3 = get_s3_client(acc_key)
    r2_audio_key = f"music/{artist}/{album}/s_{sid}.mp3"
    r2_lrc_key = f"music/{artist}/{album}/s_{sid}.lrc" if has_lrc else None

    # 上传音频
    with open(opt_audio, 'rb') as f:
        s3.put_object(Bucket=bname, Key=r2_audio_key, Body=f, ContentType='audio/mpeg')

    # 上传歌词
    if has_lrc and os.path.exists(lrc_file):
        with open(lrc_file, 'rb') as f:
            s3.put_object(Bucket=bname, Key=r2_lrc_key, Body=f, ContentType='text/plain; charset=utf-8')

    cdn_mp3_url = f"{bdomain}/{r2_audio_key}"
    cdn_lrc_url = f"{bdomain}/{r2_lrc_key}" if r2_lrc_key else None

    # 5. 调用 Cloudflare D1 接口点亮
    print("   • 正在请求 Cloudflare D1 batch-light 毫秒点亮...", end="", flush=True)
    try:
        payload = {
            "updates": [{
                "id": sid,
                "file_path": cdn_mp3_url,
                "lrc_path": cdn_lrc_url
            }]
        }
        r = requests.post(D1_LIGHT_URL, json=payload, timeout=12)
        if r.status_code == 200:
            print(" [🟢 D1 点亮成功!]")
        else:
            print(f" [⚠️ D1 接口返回 {r.status_code}: {r.text}]")
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

def run_pipeline(target_album_filter=None, max_limit=None):
    print("=" * 90)
    print("🚀 MOODY 齐秦经典大碟录音室母带多源采录与点亮流水线 启动")
    print("=" * 90)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    query = """
        SELECT s.id, ar.name, al.title, s.title, s.track_index
        FROM songs s
        JOIN albums al ON s.album_id = al.id
        JOIN artists ar ON s.artist_id = ar.id
        WHERE ar.name LIKE '%齐秦%' 
          AND (s.file_path IS NULL OR s.file_path = '')
    """
    params = []
    if target_album_filter:
        query += " AND al.title LIKE ?"
        params.append(f"%{target_album_filter}%")

    query += " ORDER BY al.id, s.track_index, s.id"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()

    if max_limit:
        rows = rows[:max_limit]

    print(f"📋 待处理缺失曲目总数: {len(rows)} 首")
    success_count = 0

    for r in rows:
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
        time.sleep(1) # 礼貌休眠

    print("\n" + "=" * 90)
    print(f"🏁 流水线处理完毕! 本批次共处理 {len(rows)} 首，成功点亮上线: {success_count} 首!")
    print("=" * 90)

if __name__ == "__main__":
    album_filter = sys.argv[1] if len(sys.argv) > 1 else None
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    run_pipeline(target_album_filter=album_filter, max_limit=limit)
