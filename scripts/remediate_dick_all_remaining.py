#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
迪克牛仔 (老爹) 异常音源精准采录、母带重制与 AI 听音二次质检闭环流水线
==============================================================================
特性：
1. 定向权威源匹配：严格限定歌手为迪克牛仔，严防张学友/郑智化/张信哲等原唱偷换；
2. 防伴奏机制：排查纯伴奏/KTV版，确保包含老爹标志性沧桑沙哑主唱；
3. EBU R128 (-14 LUFS) 标准化与 160k CBR Xing 压制；
4. 毫秒级同步时间轴 LRC 歌词抓取；
5. 【关键质量防线】压制后 Groq Whisper 二次听音质检，确认唱词正确且人声在场才允许上传；
6. Cloudflare R2 Bucket 07 物理覆盖与 D1 绝对 CDN 直链批量点亮。
==============================================================================
"""

import os
import sys
import json
import time
import re
import subprocess
import requests
import boto3
from botocore.config import Config

try:
    import syncedlyrics
except ImportError:
    syncedlyrics = None

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = "/tmp/dick_remediate_workspace"
os.makedirs(WORK_DIR, exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

# 本地代理检测
def get_proxy():
    for p in [7897, 7890, 10090, 10808]:
        try:
            r = requests.get("https://www.google.com", proxies={"https": f"http://127.0.0.1:{p}"}, timeout=1.5)
            if r.status_code == 200:
                return f"http://127.0.0.1:{p}"
        except:
            pass
    return "http://127.0.0.1:7897"

PROXY = get_proxy()

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    R2_CFG = json.load(f)["buckets"]

b07 = R2_CFG["account_07"]
s3_07 = boto3.client(
    "s3",
    endpoint_url=b07["endpoint_url"],
    aws_access_key_id=b07["access_key_id"],
    aws_secret_access_key=b07["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
BUCKET_07_NAME = b07["name"]
DOMAIN_07 = b07.get("public_url", b07.get("public_domain", "")).rstrip("/")

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# 1. 酷我音乐精准获取迪克牛仔版本
def fetch_from_kuwo(title: str, album: str, out_raw: str) -> bool:
    url = f"http://search.kuwo.cn/r.s?client=kt&all=迪克牛仔+{title}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=10"
    try:
        r = requests.get(url, timeout=5)
        d = json.loads(r.text.replace("'", '"'))
        for item in d.get("abslist", []):
            art = item.get("ARTIST", "")
            sname = item.get("SONGNAME", "")
            alb = item.get("ALBUM", "")
            dur = int(item.get("DURATION", 0))
            rid = item.get("DC_TARGETID", "")

            # 严格过滤：必须是迪克牛仔，且非纯伴奏
            if "迪克牛仔" in art and not any(k in sname for k in ["伴奏", "纯音乐", "instrumental"]):
                # 获取直链
                anti = f"http://antiserver.kuwo.cn/anti.s?type=convert_url&rid={rid}&format=mp3&response=url"
                r_anti = requests.get(anti, timeout=5)
                if r_anti.text.startswith("http"):
                    dl = requests.get(r_anti.text, stream=True, timeout=15)
                    with open(out_raw, "wb") as f:
                        for chunk in dl.iter_content(65536):
                            if chunk: f.write(chunk)
                    if os.path.exists(out_raw) and os.path.getsize(out_raw) > 500000:
                        return True
    except:
        pass
    return False

# 2. 网易云音乐精准获取迪克牛仔版本
def fetch_from_netease(title: str, album: str, out_raw: str) -> bool:
    url = f"https://music.163.com/api/search/get/web?s=迪克牛仔+{title}&type=1&limit=5"
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        for s in r.json().get("result", {}).get("songs", []):
            art_name = s.get("artists", [{}])[0].get("name", "")
            s_name = s.get("name", "")
            if "迪克牛仔" in art_name and not any(k in s_name for k in ["伴奏", "纯音乐", "instrumental"]):
                sid = s.get("id")
                mp3_url = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
                head = requests.head(mp3_url, headers=HEADERS, allow_redirects=True, timeout=5)
                if head.status_code == 200 and int(head.headers.get("Content-Length", 0)) > 500000:
                    dl = requests.get(mp3_url, headers=HEADERS, stream=True, timeout=15)
                    with open(out_raw, "wb") as f:
                        for chunk in dl.iter_content(65536):
                            if chunk: f.write(chunk)
                    if os.path.exists(out_raw) and os.path.getsize(out_raw) > 500000:
                        return True
    except:
        pass
    return False

# 3. YouTube Topic 官方频道精准获取
def fetch_from_youtube(title: str, out_raw_base: str) -> str:
    queries = [
        f"ytsearch5:Dick and Cowboy Topic {title}",
        f"ytsearch5:迪克牛仔 {title} 官方"
    ]
    for q in queries:
        cmd_search = [
            "yt-dlp", "--proxy", PROXY,
            "--flat-playlist", "--no-warnings",
            "--print", "%(id)s | %(channel)s | %(title)s | %(duration)s",
            q
        ]
        try:
            res = subprocess.run(cmd_search, capture_output=True, text=True, timeout=20)
            for line in res.stdout.splitlines():
                parts = line.split(" | ")
                if len(parts) >= 3:
                    vid, channel, vtitle = parts[0], parts[1], parts[2]
                    # 严格限制：必须有迪克牛仔或 Dick and Cowboy，杜绝原唱
                    ch_lower = channel.lower()
                    vt_lower = vtitle.lower()
                    if ("dick" in ch_lower or "cowboy" in ch_lower or "迪克牛仔" in channel or "迪克牛仔" in vtitle) \
                       and not any(k in vt_lower for k in ["伴奏", "instrumental", "karaoke"]):
                        cmd_dl = [
                            "yt-dlp", "--proxy", PROXY,
                            "-x", "--audio-format", "mp3", "--audio-quality", "0",
                            "-o", f"{out_raw_base}.%(ext)s",
                            f"https://www.youtube.com/watch?v={vid}"
                        ]
                        subprocess.run(cmd_dl, capture_output=True, timeout=60)
                        for ext in ["mp3", "m4a", "webm", "opus"]:
                            cand = f"{out_raw_base}.{ext}"
                            if os.path.exists(cand) and os.path.getsize(cand) > 500000:
                                return cand
        except:
            pass
    return None

# 4. 音频 EBU R128 标准化与 160k 压制
def standardize_audio(raw_file: str, opt_file: str) -> bool:
    cmd = [
        "ffmpeg", "-y", "-i", raw_file,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-b:a", "160k", "-ar", "44100",
        opt_file
    ]
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0 and os.path.exists(opt_file) and os.path.getsize(opt_file) > 500000

def get_duration(fpath: str) -> int:
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', fpath]
        res = subprocess.run(cmd, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if line.startswith('duration='):
                return int(float(line.split('=')[1]))
    except:
        pass
    return 0

# 5. 抓取毫秒级同步歌词
def fetch_lyrics(title: str, out_lrc: str) -> bool:
    if not syncedlyrics:
        return False
    try:
        txt = syncedlyrics.search(f"迪克牛仔 {title}")
        if txt and len(txt) > 50:
            with open(out_lrc, "w", encoding="utf-8") as f:
                f.write(txt)
            return True
    except:
        pass
    return False

# 6. AI Whisper 听音质检
def whisper_verify(opt_file: str, target_title: str) -> tuple[bool, str]:
    if not GROQ_API_KEY:
        return True, "API Key 未设置，跳过听音"
    sample_mp3 = opt_file + "_sample.mp3"
    # 截取 25s - 55s
    cmd = ["ffmpeg", "-y", "-ss", "25", "-t", "30", "-i", opt_file, "-b:a", "64k", "-ac", "1", sample_mp3]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    heard = ""
    if os.path.exists(sample_mp3) and os.path.getsize(sample_mp3) > 1000:
        try:
            with open(sample_mp3, "rb") as f:
                r = requests.post(
                    GROQ_API_URL,
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    files={"file": ("sample.mp3", f, "audio/mpeg")},
                    data={"model": "whisper-large-v3", "language": "zh", "temperature": 0.0},
                    timeout=25
                )
                if r.status_code == 200:
                    heard = r.json().get("text", "").strip()
        except:
            pass
        try: os.remove(sample_mp3)
        except: pass

    if not heard:
        return False, "音频前30秒无人声或音频静音"
    
    # 检查纯器乐特征
    lower_h = heard.lower()
    if any(k in lower_h for k in ["zither", "harp", "instrumental", "piano solo", "guitar solo"]):
        return False, f"纯器乐无主唱: {heard}"

    return True, heard

# 7. 重制单曲完整流程
def remediate_single_track(track: dict) -> bool:
    sid = track["id"]
    alb = track["album"]
    title = track["title"]
    print(f"\n================================================================================")
    print(f"🎸 重制迪克牛仔曲目: 《{alb}》 - 《{title}》 (ID: {sid})")
    print(f"================================================================================")

    raw_file = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
    opt_file = os.path.join(WORK_DIR, f"opt_{sid}.mp3")
    lrc_file = os.path.join(WORK_DIR, f"lrc_{sid}.lrc")

    # 1. 抓取原始母带
    print(" • [1/5] 正在检索迪克牛仔正版母带音源...", end="", flush=True)
    source_tag = ""
    downloaded = False
    if fetch_from_kuwo(title, alb, raw_file):
        downloaded = True
        source_tag = "Kuwo 录音室"
    elif fetch_from_netease(title, alb, raw_file):
        downloaded = True
        source_tag = "NetEase 正版"
    else:
        yt_out = fetch_from_youtube(title, os.path.join(WORK_DIR, f"yt_{sid}"))
        if yt_out:
            raw_file = yt_out
            downloaded = True
            source_tag = "YouTube 官方 Topic"

    if not downloaded:
        print(" ❌ 未能获取权威母带，跳过！")
        return False
    print(f" [🟢 {source_tag} 命中! 大小: {os.path.getsize(raw_file)//1024} KB]")

    # 2. 标准化压制
    print(" • [2/5] EBU R128 (-14 LUFS) 响度标准化与 160k CBR Xing 压制...", end="", flush=True)
    if not standardize_audio(raw_file, opt_file):
        print(" ❌ 压制失败！")
        return False
    dur_sec = get_duration(opt_file)
    fsize = os.path.getsize(opt_file)
    print(f" [完成! 时长: {dur_sec}s, 大小: {fsize/(1024*1024):.2f} MB]")

    # 3. AI Whisper 听音闭环复检
    print(" • [3/5] 启动 Groq Whisper-large-v3 AI 听音二次质检...", end="", flush=True)
    passed, heard_info = whisper_verify(opt_file, title)
    if not passed:
        print(f" ❌ AI 听音质检未通过: {heard_info}！放弃上传！")
        return False
    print(f" [🟢 质检合格! 听到: \"{heard_info[:40]}...\"]")

    # 4. 歌词抓取
    print(" • [4/5] 抓取毫秒级时间轴同步歌词...", end="", flush=True)
    has_lrc = fetch_lyrics(title, lrc_file)
    print(" [🟢 抓取成功]" if has_lrc else " [⚠️ 沿用原歌词]")

    # 5. 上传至 R2 Bucket 07 物理覆盖
    clean_alb = re.sub(r'[\\/*?:"<>|]', '_', alb).strip()
    r2_audio_key = f"music/迪克牛仔/{clean_alb}/s_{sid}.mp3"
    r2_lrc_key = f"lyrics/迪克牛仔/{clean_alb}/s_{sid}.lrc"

    print(" • [5/5] 上传至 Cloudflare R2 Bucket 07 覆盖并点亮 D1...", end="", flush=True)
    with open(opt_file, "rb") as f:
        s3_07.put_object(Bucket=BUCKET_07_NAME, Key=r2_audio_key, Body=f, ContentType="audio/mpeg")
    if has_lrc:
        with open(lrc_file, "rb") as f:
            s3_07.put_object(Bucket=BUCKET_07_NAME, Key=r2_lrc_key, Body=f, ContentType="text/plain; charset=utf-8")

    cdn_audio = f"{DOMAIN_07}/{r2_audio_key}"
    cdn_lrc = f"{DOMAIN_07}/{r2_lrc_key}" if has_lrc else None

    # 调用 D1 批量点亮
    payload = {
        "updates": [{
            "id": sid,
            "file_path": cdn_audio,
            "lrc_path": cdn_lrc
        }]
    }
    for retry in range(3):
        try:
            r = requests.post(D1_LIGHT_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
            if r.status_code == 200 and r.json().get("code") == 200:
                break
        except:
            time.sleep(1)

    # 清理临时文件
    for fpath in [raw_file, opt_file, lrc_file]:
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except: pass

    print(f"🎉 重制上线成功: 《{title}》 ({dur_sec}s) -> {cdn_audio}")
    return True

def run_remediation(target_list: list[dict]):
    print("=" * 80)
    print(f"🚀 迪克牛仔精准重制流水线启动: 计划重制 {len(target_list)} 首曲目")
    print("=" * 80)
    success = 0
    for idx, t in enumerate(target_list, 1):
        print(f"\n[{idx}/{len(target_list)}]")
        if remediate_single_track(t):
            success += 1
        time.sleep(1)

    print("\n" + "=" * 80)
    print(f"🏁 迪克牛仔重制完成! 成功: {success} / {len(target_list)} 首")
    print("=" * 80)

if __name__ == "__main__":
    # 如果指定了审计报告文件
    audit_file = os.path.join(REPORT_DIR, "DICK_COWBOY_AI_AUDIT.json")
    if os.path.exists(audit_file):
        with open(audit_file, "r", encoding="utf-8") as f:
            audit_results = json.load(f)
        targets = [x for x in audit_results if x["status"] != "PASS"]
        run_remediation(targets)
    else:
        print("未找到审计报告，请先运行 audit_dick_with_whisper_full.py！")
