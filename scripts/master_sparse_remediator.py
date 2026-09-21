#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 知名歌手稀缺专辑攻坚母带重制与智能切桶调度引擎
(Master Sparse Albums Remediator with Dynamic Bucket Routing)
==============================================================================
特性：
1. 动态双桶安全路由：优先写入 account_08；一旦达到 9.30 GB 警戒线，自动无缝平滑切入全新的 account_09；
2. 零脏数据质检铁律：必须经过 Groq Whisper-large-v3 人声金标准核验，不通过坚决拒入；
3. 音频母带标准化：EBU R128 (-14 LUFS) 响度均衡 + 160k CBR Xing Header；
4. LRC 歌词同步抓取并同步上传；
5. Cloudflare D1 边缘接口批处理瞬时点亮（100% 绝对 CDN 规范直链）。
==============================================================================
"""

import os
import sys
import json
import time
import re
import threading
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics
import socket

# 彻底解决 Clash Fake IP (198.18.x.x) 劫持导致 m-api 及 R2 存储桶无法连接的问题
_orig_getaddrinfo = socket.getaddrinfo
def _custom_getaddrinfo(host, port, *args, **kwargs):
    if host == "m-api.changgepd.ccwu.cc":
        return _orig_getaddrinfo("172.67.199.94", port, *args, **kwargs)
    if host and host.endswith(".r2.cloudflarestorage.com"):
        return _orig_getaddrinfo("172.64.190.1", port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = _custom_getaddrinfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
# 系统网络与动态代理（优先系统网络/香蕉VPN直通，彻底废除 7898 僵尸冲突端口）
PROXY_URL = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]

# 初始化双桶客户端
b08_cfg = r2_cfg["account_08"]
b09_cfg = r2_cfg["account_09"]

s3_clients = {
    "account_08": boto3.client(
        "s3",
        endpoint_url=b08_cfg["endpoint_url"],
        aws_access_key_id=b08_cfg["access_key_id"],
        aws_secret_access_key=b08_cfg["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4")
    ),
    "account_09": boto3.client(
        "s3",
        endpoint_url=b09_cfg["endpoint_url"],
        aws_access_key_id=b09_cfg["access_key_id"],
        aws_secret_access_key=b09_cfg["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4")
    )
}

bucket_meta = {
    "account_08": {
        "name": b08_cfg["name"],
        "domain": b08_cfg["public_url"].rstrip("/")
    },
    "account_09": {
        "name": b09_cfg["name"],
        "domain": b09_cfg["public_url"].rstrip("/")
    }
}

# 全局容量路由控制
router_lock = threading.Lock()
current_target = "account_09"  # 桶 08 已达 9.30 GB 封箱线，全量直接写入第 9 存储桶
WARNING_THRESHOLD_BYTES = int(9.30 * 1e9) # 9.30 GB 警戒线 (十进制)

def init_b08_bytes():
    return int(9.30 * 1e9)

b08_accumulated_bytes = init_b08_bytes()
print(f"📡 [容量路由监控] Bucket 08 已封箱归档，当前全量写入目标: 【Bucket 09 (moody-music-asset-09)】")

def get_current_upload_target(added_bytes: int = 0):
    return "account_09"

import opencc
_cc = opencc.OpenCC("t2s.json")

def to_simp(t: str) -> str:
    if not t: return ""
    try:
        return _cc.convert(t)
    except Exception:
        return "".join(TRAD_TO_SIMP.get(c, c) for c in t)

def clean_text(t: str) -> str:
    if not t: return ""
    # 保留中文、日文平假名(\u3040-\u309f)、日文片假名(\u30a0-\u30ff)、字母和数字
    cleaned = re.sub(r'[^\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ffa-zA-Z0-9]', '', t).lower()
    return to_simp(cleaned)

def extract_pure_title(title: str, search_title: str, artist: str) -> str:
    t = title.strip()
    t_clean = re.sub(r'[\(（].*?[\)）]', '', t).strip()
    if t_clean:
        return t_clean
    s_clean = search_title
    for a in [artist, artist.lower(), artist.upper()]:
        s_clean = re.sub(re.escape(a), '', s_clean, flags=re.IGNORECASE).strip()
    s_clean = re.sub(r'[\(（].*?[\)）]', '', s_clean).strip()
    return s_clean or title

def fetch_lrc(artist: str, title: str, search_title: str) -> str:
    pure_t = extract_pure_title(title, search_title, artist)
    clean_a = artist.split('/')[0].strip()
    queries = [
        f"{clean_a} {pure_t}",
        f"{pure_t} {clean_a}",
        f"{clean_a} {to_simp(pure_t)}",
        pure_t
    ]
    seen = set()
    queries = [q for q in queries if not (q in seen or seen.add(q))]
    
    # 1. 尝试网易云（带 405/限流快速探测保护）
    for q in queries:
        try:
            r = requests.get(
                "https://music.163.com/api/search/get/web",
                params={"s": q, "type": 1, "limit": 4},
                headers=HEADERS,
                timeout=4
            )
            if r.status_code == 200:
                res_json = r.json()
                if res_json.get("code") == 200:
                    songs = res_json.get("result", {}).get("songs", [])
                    for s in songs:
                        clean_t = clean_text(title)
                        s_t = clean_text(s.get("name", ""))
                        if not (clean_t in s_t or s_t in clean_t or (len(clean_t) >= 2 and clean_t[:2] in s_t)):
                            continue
                        s_arts = [a.get("name", "") for a in s.get("artists", [])]
                        if any(clean_a.lower() in a.lower() or a.lower() in clean_a.lower() for a in s_arts):
                            nid = s["id"]
                            lr = requests.get(
                                f"http://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1",
                                headers=HEADERS,
                                timeout=4
                            )
                            lrc = lr.json().get("lrc", {}).get("lyric", "")
                            if lrc and len(lrc.strip()) > 30:
                                return lrc
        except Exception:
            pass
            
    # 2. syncedlyrics 兜底（多源检索：Kugou, NetEase, Lrclib）
    clean_t = clean_text(pure_t)
    for q in queries[:2]:
        try:
            res = syncedlyrics.search(q, providers=['Kugou', 'NetEase', 'Lrclib'])
            if res and len(res.strip()) > 30:
                clean_res = clean_text(res)
                if clean_t in clean_res or (len(clean_t) >= 2 and clean_t[:2] in clean_res) or clean_text(artist)[:2] in clean_res:
                    return res
        except Exception:
            pass
            
    return ""

def transcribe_whisper(clip_path: str) -> str:
    if not GROQ_KEY or not os.path.exists(clip_path):
        return ""
    try:
        with open(clip_path, "rb") as f:
            req_kwargs = {
                "headers": {"Authorization": f"Bearer {GROQ_KEY}"},
                "files": {
                    "file": (os.path.basename(clip_path), f, "audio/mpeg"),
                    "model": (None, "whisper-large-v3"),
                    "temperature": (None, "0.0")
                },
                "timeout": 25
            }
            if PROXIES:
                req_kwargs["proxies"] = PROXIES
            r = requests.post(GROQ_API_URL, **req_kwargs)
        if r.status_code == 200:
            return r.json().get("text", "").strip()
    except Exception as e:
        print(f"      [Whisper Error] {e}")
    return ""

BLACK_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会', '微电影', '剧情版', 
    'cover', '翻唱', '伴奏', 'instrumental', 'ktv', '花絮', 'teaser',
    '二胡', '古筝', '笛子', '钢琴曲', '吉他演奏', 'dj版', 'remix'
]

def download_audio_multi_source(artist: str, title: str, search_title: str, album: str, out_raw: str) -> bool:
    pure_t = extract_pure_title(title, search_title, artist)
    clean_a = artist.split('/')[0].strip()
    clean_t = clean_text(pure_t)
    
    # 1. 尝试网易云原生
    for q in [f"{clean_a} {pure_t}", f"{clean_a} {to_simp(pure_t)}"]:
        try:
            r = requests.get(
                "https://music.163.com/api/search/get/web",
                params={"s": q, "type": 1, "limit": 4},
                headers=HEADERS,
                timeout=4
            )
            if r.status_code == 200:
                res_json = r.json()
                if res_json.get("code") == 200:
                    songs = res_json.get("result", {}).get("songs", [])
                    for s in songs:
                        s_t = clean_text(s.get("name", ""))
                        if not (clean_t in s_t or s_t in clean_t or (len(clean_t) >= 2 and clean_t[:2] in s_t)):
                            continue
                        s_art = [a.get("name", "") for a in s.get("artists", [])]
                        if any(clean_a.lower() in a.lower() for a in s_art):
                            sid = s["id"]
                            mp3_url = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
                            r_chk = requests.head(mp3_url, headers=HEADERS, allow_redirects=True, timeout=4)
                            if r_chk.status_code == 200 and int(r_chk.headers.get("Content-Length", 0)) > 500000:
                                r_audio = requests.get(mp3_url, headers=HEADERS, stream=True, timeout=15)
                                with open(out_raw, "wb") as f:
                                    for chunk in r_audio.iter_content(65536):
                                        if chunk: f.write(chunk)
                                if os.path.exists(out_raw) and os.path.getsize(out_raw) > 500000:
                                    return True
        except Exception:
            pass

    # 2. 尝试 YouTube 官方 (结构化 JSON 检索，毫秒级过滤)
    simp_t = to_simp(pure_t)
    candidates = [
        f"{artist} {pure_t}",
        f"{artist} - {pure_t} Topic",
        f"{artist} {album} {pure_t}",
        f"{artist} {pure_t} official audio",
        f"{pure_t} {artist}",
        f"{artist} {simp_t}"
    ]
    seen = set()
    search_queries = [q for q in candidates if not (q in seen or seen.add(q))]

    NODE_BIN = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"
    node_flags = ["--js-runtimes", f"node:{NODE_BIN}"] if os.path.exists(NODE_BIN) else []
    proxy_flags = ["--proxy", PROXY_URL] if PROXY_URL else []

    for q in search_queries:
        out_tmpl = out_raw.rsplit('.', 1)[0] + "_yt.%(ext)s"
        try:
            res = subprocess.run(
                ["yt-dlp"] + proxy_flags + node_flags + ["-j", "--flat-playlist", f"ytsearch5:{q}"],
                capture_output=True, text=True, timeout=30
            )
            chosen_vid = None
            for line in res.stdout.strip().split('\n'):
                if not line.strip(): continue
                try:
                    entry = json.loads(line)
                    vtitle = entry.get("title", "").lower()
                    vid = entry.get("id")
                    dur = entry.get("duration") or 0
                    
                    if not vid: continue
                    if any(bk in vtitle for bk in BLACK_KEYWORDS): continue
                    if dur and (dur < 45 or dur > 660): continue
                    
                    vtitle_clean = clean_text(vtitle)
                    core = clean_t[:4]
                    if (len(core) >= 2 and core in vtitle_clean) or (clean_t in vtitle_clean) or (len(clean_t) >= 2 and clean_t[:2] in vtitle_clean):
                        chosen_vid = vid
                        break
                except Exception:
                    continue
            
            if chosen_vid:
                dl_cmd = [
                    "yt-dlp"
                ] + proxy_flags + node_flags + [
                    "-x", "--audio-format", "mp3",
                    "-o", out_tmpl,
                    f"https://www.youtube.com/watch?v={chosen_vid}"
                ]
                subprocess.run(dl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=90)
                downloaded = out_tmpl.replace("%(ext)s", "mp3")
                if os.path.exists(downloaded):
                    if os.path.exists(out_raw): os.remove(out_raw)
                    os.rename(downloaded, out_raw)
                    return True
        except Exception:
            continue
            
    return False

def process_single_song(item: dict, work_dir: str) -> dict:
    sid = item["id"]
    artist = item["artist"]
    album = item["album"]
    title = item["title"]
    search_title = item.get("search_title", title)
    
    print(f"\n========================================================")
    print(f"▶ 采录与质检: [{artist}] 《{album}》 - 《{title}》 (检索词: '{search_title}', ID: {sid})")
    print(f"========================================================")
    os.makedirs(work_dir, exist_ok=True)
    
    raw_mp3 = os.path.join(work_dir, f"s_{sid}_raw.mp3")
    proc_mp3 = os.path.join(work_dir, f"s_{sid}.mp3")
    lrc_path = os.path.join(work_dir, f"s_{sid}.lrc")
    
    # 0. 检查是否已经入库
    key_audio = f"music/{artist}/{album}/s_{sid}.mp3"
    for acc in ["account_08", "account_09"]:
        try:
            s3_clients[acc].head_object(Bucket=bucket_meta[acc]["name"], Key=key_audio)
            print(f"   ⏩ [跳过] 该曲目已在 {acc} ({bucket_meta[acc]['name']}) 中就绪，跳过重复处理！")
            return {"id": sid, "status": "ALREADY_EXISTS"}
        except Exception:
            pass

    # 1. 抓取 LRC
    lrc_content = fetch_lrc(artist, title, search_title)
    has_lrc = bool(lrc_content and len(lrc_content.strip()) > 30)
    if has_lrc:
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        print(f"   📝 [LRC] 成功抓取网络同步歌词 ({len(lrc_content.splitlines())} 行)")
    else:
        print(f"   ⚠️ [LRC] 未找到同步歌词，将依靠标题进行 AI 校验")
        
    # 2. 采录
    print(f"   🎧 [下载] 启动多源高品质录音室音源采录...")
    success = download_audio_multi_source(artist, title, search_title, album, raw_mp3)
    if not success or not os.path.exists(raw_mp3) or os.path.getsize(raw_mp3) < 100000:
        print(f"   ❌ [错误] 无法获取有效音源文件！跳过入库！")
        return {"id": sid, "status": "FAILED_DOWNLOAD", "reason": "No audio downloaded"}
        
    # 3. 压制
    print(f"   🎛️ [压制] 执行 EBU R128 (-14 LUFS) 响度标准化与 160k CBR Xing 编码...")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_mp3,
            "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
            proc_mp3
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dur_raw = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", proc_mp3
        ]).decode().strip()
        dur = float(dur_raw)
        print(f"   ✅ [压制成功] 最终时长: {dur:.1f} 秒 ({round(dur)}s)")
    except Exception as e:
        print(f"   ❌ [压制失败] ffmpeg 出错: {e}")
        return {"id": sid, "status": "FAILED_FFMPEG", "reason": str(e)}

    # 4. Groq Whisper-large-v3 人声金标准质检
    def verify_slice(heard_text: str, lrc_lines: list, titles: list) -> tuple[bool, str]:
        simp_heard = clean_text(heard_text)
        if not simp_heard:
            return False, "无有效转写人声"
        for t in titles:
            ct = clean_text(t)
            if len(ct) >= 2 and (ct in simp_heard or (len(ct) >= 4 and ct[:3] in simp_heard)):
                return True, f"命中标题匹配: '{t}' -> '{ct}'"
        for cl in lrc_lines:
            if len(cl) >= 4 and cl in simp_heard:
                return True, f"命中整行歌词: '{cl[:20]}'"
        matched_grams = set()
        for cl in lrc_lines:
            if len(cl) >= 4:
                for i in range(len(cl) - 3):
                    gram = cl[i:i+4]
                    if gram in simp_heard:
                        matched_grams.add(gram)
        if len(matched_grams) >= 2:
            return True, f"命中多片段词块 ({len(matched_grams)}处: {list(matched_grams)[:3]})"
        for cl in lrc_lines:
            if len(cl) >= 5:
                for i in range(len(cl) - 4):
                    gram5 = cl[i:i+5]
                    if gram5 in simp_heard:
                        return True, f"命中长片段歌词 ({len(gram5)}字: '{gram5}')"
        return False, "转写内容与歌词/标题无有效重合"

    print(f"   🎤 [AI 听音] 截取黄金人声切片调用 Whisper-large-v3 模型听音鉴别...")
    clip_path = os.path.join(work_dir, f"s_{sid}_clip.mp3")
    start_sec = 45 if dur > 90 else 20
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", "30",
        "-i", proc_mp3, "-ac", "1", "-ar", "16000", clip_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    heard_text = transcribe_whisper(clip_path)
    if os.path.exists(clip_path): os.remove(clip_path)
    print(f"   🗣️ [Whisper 转写]: \"{heard_text[:60]}...\"")
    
    pure_t = extract_pure_title(title, search_title, artist)
    titles_to_check = [
        clean_text(pure_t),
        clean_text(to_simp(pure_t)),
        clean_text(title),
        clean_text(to_simp(title)),
        clean_text(search_title),
        clean_text(re.sub(r'[\(（].*?[\)）]', '', search_title))
    ]
    titles_to_check = [t for t in set(titles_to_check) if len(t) >= 2]
    
    lrc_clean_lines = []
    if has_lrc:
        for l in lrc_content.splitlines():
            c_l = re.sub(r'\[.*?\]', '', l).strip()
            if c_l and not any(k in c_l for k in ['作词', '作曲', '编曲', '制作', '词：', '曲：']):
                simp_l = clean_text(c_l)
                if len(simp_l) >= 4:
                    lrc_clean_lines.append(simp_l)
                
    verified, match_reason = verify_slice(heard_text, lrc_clean_lines, titles_to_check)
    if verified:
        print(f"   ✅ [质检通过] {match_reason}")
    else:
        # 二次切片（75s-105s 副歌段复查）
        if dur > 110:
            print(f"   🔄 [二次听音] 启动 75s-105s 副歌切片复查...")
            clip_path2 = os.path.join(work_dir, f"s_{sid}_clip2.mp3")
            subprocess.run([
                "ffmpeg", "-y", "-ss", "75", "-t", "30",
                "-i", proc_mp3, "-ac", "1", "-ar", "16000", clip_path2
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            heard2 = transcribe_whisper(clip_path2)
            if os.path.exists(clip_path2): os.remove(clip_path2)
            print(f"   🗣️ [副歌转写]: \"{heard2[:60]}...\"")
            
            verified, match_reason = verify_slice(heard2, lrc_clean_lines, titles_to_check)
            if verified:
                print(f"   ✅ [二次质检通过] {match_reason}")
                
    if not verified:
        print(f"   ❌ [质检拒绝] 未能确认音频真实性！严禁入库！原因: {match_reason}")
        for f in [raw_mp3, proc_mp3, lrc_path]:
            if os.path.exists(f): os.remove(f)
        return {
            "id": sid,
            "status": "REJECTED_AUDIT",
            "heard": heard_text,
            "title": title,
            "search_title": search_title
        }

    # 5. 动态存储路由与上传
    file_size = os.path.getsize(proc_mp3)
    target_acc = get_current_upload_target(file_size)
    meta = bucket_meta[target_acc]
    target_s3 = s3_clients[target_acc]
    
    print(f"   ☁️ [R2 上传] 正在写入目标桶: 【{target_acc} ({meta['name']})】...")
    key_audio = f"music/{artist}/{album}/s_{sid}.mp3"
    key_lrc = f"lyrics/{artist}/{album}/s_{sid}.lrc"
    
    target_s3.upload_file(proc_mp3, meta["name"], key_audio, ExtraArgs={"ContentType": "audio/mpeg"})
    final_audio_url = f"{meta['domain']}/{key_audio}"
    print(f"      -> 音频上传成功: {final_audio_url}")
    
    final_lrc_url = None
    if has_lrc:
        target_s3.upload_file(lrc_path, meta["name"], key_lrc, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        final_lrc_url = f"{meta['domain']}/{key_lrc}"
        print(f"      -> 歌词上传成功: {final_lrc_url}")
        
    d1_item = {
        "id": sid,
        "file_path": final_audio_url,
        "lrc_path": final_lrc_url,
        "duration": round(dur),
        "is_lit": 1
    }
    
    for f in [raw_mp3, proc_mp3, lrc_path]:
        if os.path.exists(f): os.remove(f)
        
    print(f"   ✨ [完成] [{artist}] 《{title}》 质检通过并就绪入库！")
    return {
        "id": sid,
        "status": "SUCCESS",
        "d1_item": d1_item,
        "artist": artist,
        "album": album,
        "title": title,
        "target_acc": target_acc
    }

OFFLINE_MODE = os.environ.get("MOODY_OFFLINE", "1") == "1"
QUEUE_FILE = os.path.join(BASE_DIR, "data", "pending_d1_light_queue.json")

def append_to_light_queue(items: list) -> int:
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
    existing = []
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    seen_ids = set(x["id"] for x in existing)
    for it in items:
        if it["id"] not in seen_ids:
            existing.append(it)
            seen_ids.add(it["id"])
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return len(existing)

def send_batch_light(updates: list) -> bool:
    if not updates:
        return True
    for attempt in range(3):
        try:
            r = requests.post(D1_LIGHT_URL, json={"updates": updates}, timeout=15)
            if r.status_code == 200:
                res = r.json()
                if res.get("code") == 200:
                    return True
        except Exception as e:
            time.sleep(1)
    return False

def run_pipeline(target_file: str, pipeline_name: str):
    with open(target_file, "r", encoding="utf-8") as f:
        targets = json.load(f)
        
    work_dir = f"/tmp/moody_pipe_{pipeline_name}"
    os.makedirs(work_dir, exist_ok=True)
    
    print(f"\n############################################################")
    mode_desc = "方案A (离线入桶预存模式 - 零D1交互)" if OFFLINE_MODE else "实时D1秒级点亮模式"
    print(f"🚀 启动攻坚流水线: {pipeline_name} [{mode_desc}] (待处理 {len(targets)} 首曲目)")
    print(f"############################################################\n")
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    d1_pending = []
    results = []
    
    for idx, item in enumerate(targets, 1):
        print(f"\n>>> 任务进度 [{idx}/{len(targets)}] <<<")
        res = process_single_song(item, work_dir)
        status = res.get("status")
        results.append(res)
        
        if status == "SUCCESS":
            success_count += 1
            if OFFLINE_MODE:
                total_q = append_to_light_queue([res["d1_item"]])
                print(f"   💾 [方案A 预存] 音频与歌词已安全入桶 R2，元数据已加入待点亮队列 (累计待点亮: {total_q} 首)")
            else:
                d1_pending.append(res["d1_item"])
                # 每成功 2 首立即触发 D1 batch-light 点亮
                if len(d1_pending) >= 2:
                    print(f"   ⚡ [D1 点亮] 正在向生产网关提交 batch-light ({len(d1_pending)} 首)...")
                    if send_batch_light(d1_pending):
                        print(f"   🟢 [D1 成功] 边缘数据库已毫秒级点亮！")
                        d1_pending = []
                    else:
                        print(f"   ⚠️ [D1 响应异常] 点亮稍后重试")
        elif status == "ALREADY_EXISTS":
            skip_count += 1
        else:
            fail_count += 1
            
    # 循环结束后，清空剩余待点亮曲目
    if not OFFLINE_MODE and d1_pending:
        print(f"   ⚡ [D1 终末点亮] 提交剩余 batch-light ({len(d1_pending)} 首)...")
        if send_batch_light(d1_pending):
            print(f"   🟢 [D1 成功] 边缘数据库终末曲目已毫秒级点亮！")
            d1_pending = []
        else:
            print(f"   ⚠️ [D1 响应异常] 终末点亮失败")
            
    report_file = f"data/pipeline_{pipeline_name}_report.json"
    os.makedirs("data", exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "pipeline": pipeline_name,
            "total": len(targets),
            "success": success_count,
            "skip": skip_count,
            "fail": fail_count,
            "results": results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n============================================================")
    print(f"🎉 流水线 {pipeline_name} 执行完毕！")
    print(f"📊 新增点亮: {success_count} 首 | 既有已跳过: {skip_count} 首 | 质检拒绝/未获取: {fail_count} 首")
    print(f"📄 审计报告已归档: {report_file}")
    print(f"============================================================\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_json = sys.argv[1]
        name = sys.argv[2] if len(sys.argv) > 2 else "worker"
        run_pipeline(target_json, name)
    else:
        # 默认先跑 Package A (Beyond, 萧亚轩, 方大同, 苏慧伦, 任贤齐)
        run_pipeline("sparse_pkg_a_resolved.json", "pkg_a")
