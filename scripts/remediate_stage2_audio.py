#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MOODY 早期曲库治理 - 阶段 2：实锤伪劣曲目 (46 首) 定向重采、母带重制与 AI 听音替换
=============================================================================
核心使命：
1. 彻底肃清：短视频武器解说、电视剧压制音轨、海外古筝翻奏等 46 首劣质资源；
2. 权威源定向抓取：NetEase CloudSearch 正版 + Kuwo 录音室 + YouTube Topic 官方频道；
3. 防伴奏与防李鬼：严格校验歌手本尊，杜绝他人翻唱与纯伴奏；
4. EBU R128 (-14 LUFS) 响度标准化 + 160k CBR Xing 编码；
5. Groq Whisper 二次质检闭环：上传前听音验证人声在场且无违规关键词；
6. 毫秒级正版时间轴 LRC 配套同步；
7. 物理上传至 Cloudflare R2 Account 11 并调用 D1 接口原子更新；
8. 生成完整的修复前后对比日志。
=============================================================================
"""

import os
import sys
import json
import re
import time
import subprocess
import requests
import boto3
from botocore.config import Config

try:
    import syncedlyrics
except ImportError:
    syncedlyrics = None

try:
    from groq_manager import GroqTokenPool
except ImportError:
    from scripts.groq_manager import GroqTokenPool

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_FILE = os.path.join(BASE_DIR, "reports", "TASK_REMEDIATE_46_AUDIO.json")
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
LOG_DIR = os.path.join(BASE_DIR, "reports")
WORK_DIR = "/tmp/moody_remediate_audio_workspace"
os.makedirs(WORK_DIR, exist_ok=True)

D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/"
}

# 代理检测
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

# 加载 R2 配置
with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_data = json.load(f)["buckets"]

b11 = r2_data["account_11"]
s3_11 = boto3.client(
    "s3",
    endpoint_url=b11["endpoint_url"],
    aws_access_key_id=b11["access_key_id"],
    aws_secret_access_key=b11["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
BUCKET_NAME = b11["name"]
PUBLIC_DOMAIN = b11.get("public_url", "").rstrip("/")

def clean_title_for_search(title: str) -> str:
    return re.sub(r'\(.*?\)|\[.*?\]|（.*?）', '', title).strip()

# 1. 网易云权威源获取
def fetch_from_netease(artist: str, title: str, out_raw: str) -> tuple[bool, str]:
    c_title = clean_title_for_search(title)
    query = f"{artist} {c_title}"
    try:
        r = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": query, "type": 1, "limit": 6},
            headers=HEADERS,
            timeout=5
        )
        if r.status_code == 200:
            songs = r.json().get("result", {}).get("songs", [])
            for s in songs:
                art_name = s.get("artists", [{}])[0].get("name", "")
                s_name = s.get("name", "")
                # 校验歌手和歌名，且排除纯伴奏
                if (artist.lower() in art_name.lower() or art_name.lower() in artist.lower() or "群星" in art_name) \
                   and (c_title.lower() in s_name.lower() or s_name.lower() in c_title.lower()) \
                   and not any(k in s_name for k in ["伴奏", "纯音乐", "instrumental", "karaoke"]):
                    sid = s.get("id")
                    mp3_url = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
                    head = requests.head(mp3_url, headers=HEADERS, allow_redirects=True, timeout=5)
                    if head.status_code == 200 and int(head.headers.get("Content-Length", 0)) > 600000:
                        dl = requests.get(mp3_url, headers=HEADERS, stream=True, timeout=15)
                        with open(out_raw, "wb") as f:
                            for chunk in dl.iter_content(65536):
                                if chunk: f.write(chunk)
                        if os.path.exists(out_raw) and os.path.getsize(out_raw) > 600000:
                            return True, f"NetEase 正版 (ID: {sid})"
    except Exception:
        pass
    return False, ""

# 2. 酷我权威源获取
def fetch_from_kuwo(artist: str, title: str, out_raw: str) -> tuple[bool, str]:
    c_title = clean_title_for_search(title)
    url = f"http://search.kuwo.cn/r.s?client=kt&all={requests.utils.quote(f'{artist} {c_title}')}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=6"
    try:
        r = requests.get(url, timeout=5)
        d = json.loads(r.text.replace("'", '"'))
        for item in d.get("abslist", []):
            art = item.get("ARTIST", "")
            sname = item.get("SONGNAME", "")
            rid = item.get("DC_TARGETID", "")
            if (artist.lower() in art.lower() or art.lower() in artist.lower()) \
               and (c_title.lower() in sname.lower() or sname.lower() in c_title.lower()) \
               and not any(k in sname for k in ["伴奏", "纯音乐", "instrumental", "karaoke"]):
                anti = f"http://antiserver.kuwo.cn/anti.s?type=convert_url&rid={rid}&format=mp3&response=url"
                r_anti = requests.get(anti, timeout=5)
                if r_anti.text.startswith("http"):
                    dl = requests.get(r_anti.text, stream=True, timeout=15)
                    with open(out_raw, "wb") as f:
                        for chunk in dl.iter_content(65536):
                            if chunk: f.write(chunk)
                    if os.path.exists(out_raw) and os.path.getsize(out_raw) > 600000:
                        return True, f"Kuwo 录音室 (RID: {rid})"
    except Exception:
        pass
    return False, ""

# 3. YouTube 官方 Topic 兜底
def fetch_from_youtube(artist: str, title: str, out_raw_base: str) -> tuple[bool, str]:
    c_title = clean_title_for_search(title)
    queries = [
        f"ytsearch5:{artist} {c_title} Topic",
        f"ytsearch5:{artist} {c_title} 官方"
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
                    ch_lower = channel.lower()
                    vt_lower = vtitle.lower()
                    if (artist.lower() in ch_lower or artist.lower() in vt_lower) \
                       and not any(k in vt_lower for k in ["伴奏", "instrumental", "karaoke", "zither", "harp"]):
                        cmd_dl = [
                            "yt-dlp", "--proxy", PROXY,
                            "-x", "--audio-format", "mp3", "--audio-quality", "0",
                            "-o", f"{out_raw_base}.%(ext)s",
                            f"https://www.youtube.com/watch?v={vid}"
                        ]
                        subprocess.run(cmd_dl, capture_output=True, timeout=60)
                        for ext in ["mp3", "m4a", "webm", "opus"]:
                            cand = f"{out_raw_base}.{ext}"
                            if os.path.exists(cand) and os.path.getsize(cand) > 600000:
                                return True, f"YouTube 官方 Topic ({vid})"
        except Exception:
            pass
    return False, ""

def fetch_from_youtube_wrapper(artist: str, title: str, out_raw: str, work_dir: str, sid: int) -> tuple[bool, str]:
    base_prefix = os.path.join(work_dir, f"yt_{sid}")
    ok, desc = fetch_from_youtube(artist, title, base_prefix)
    if ok:
        for ext in ["mp3", "m4a", "webm", "opus"]:
            cand = f"{base_prefix}.{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 500000:
                if cand != out_raw:
                    subprocess.run(["ffmpeg", "-y", "-i", cand, "-b:a", "160k", out_raw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, desc
    return False, ""

# 标准化压制
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

# 抓取 LRC 歌词
def fetch_lyrics(artist: str, title: str, out_lrc: str) -> bool:
    c_title = clean_title_for_search(title)
    # 优先网易云
    try:
        r = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": f"{artist} {c_title}", "type": 1, "limit": 3},
            headers=HEADERS,
            timeout=5
        )
        if r.status_code == 200:
            songs = r.json().get("result", {}).get("songs", [])
            for s in songs:
                sid = s.get("id")
                lr = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1", headers=HEADERS, timeout=5)
                if lr.status_code == 200:
                    lrc = lr.json().get("lrc", {}).get("lyric", "")
                    if lrc and len(lrc) > 50 and "纯音乐，请欣赏" not in lrc:
                        with open(out_lrc, "w", encoding="utf-8") as f:
                            f.write(lrc)
                        return True
    except Exception:
        pass

    # 兜底 syncedlyrics
    if syncedlyrics:
        try:
            txt = syncedlyrics.search(f"{artist} {c_title}")
            if txt and len(txt) > 50 and "纯音乐，请欣赏" not in txt:
                with open(out_lrc, "w", encoding="utf-8") as f:
                    f.write(txt)
                return True
        except Exception:
            pass
    return False

# AI 听音质检闭环
def whisper_verify_remediated(pool: GroqTokenPool, opt_file: str) -> tuple[bool, str]:
    sample_mp3 = opt_file + "_sample.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-ss", "30", "-t", "30",
        "-i", opt_file,
        "-ac", "1", "-ar", "16000", "-b:a", "64k",
        sample_mp3
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not os.path.exists(sample_mp3) or os.path.getsize(sample_mp3) < 1000:
        return False, "切片抽取失败"

    res = pool.transcribe(sample_mp3, model="whisper-large-v3-turbo")
    if os.path.exists(sample_mp3):
        try: os.remove(sample_mp3)
        except: pass

    if not res.get("success"):
        return False, f"转录失败: {res.get('error')}"

    heard = res.get("text", "").strip()
    if not heard:
        return False, "音频30秒切片未检测到人声"

    lower_h = heard.lower()
    # 违规词拦截
    banned = ["zither", "harp", "字幕志愿者", "独播剧场", "后座力", "麦格农", "索兰娅", "非诚勿扰", "youtube", "piano cover"]
    detected = [w for w in banned if w in lower_h]
    if detected:
        return False, f"仍存在伪劣违规特征: {detected}"

    return True, heard

def remediate_single(pool: GroqTokenPool, item: dict) -> dict:
    sid = item["song_id"]
    artist = item["artist"]
    album = item["album"]
    title = item["title"]
    defect = item.get("defect_type", "UNKNOWN")

    print(f"\n================================================================================")
    print(f"🛠️ [治理替换] [{artist}] 《{album}》 - 《{title}》 (ID: {sid}) | 病灶: {defect}")
    print(f"================================================================================")

    raw_file = os.path.join(WORK_DIR, f"raw_{sid}.mp3")
    opt_file = os.path.join(WORK_DIR, f"opt_{sid}.mp3")
    lrc_file = os.path.join(WORK_DIR, f"lrc_{sid}.lrc")

    # 1~3. 多源级联检索、压制与 AI 质检（带自动故障转移）
    candidate_fetchers = [
        ("NetEase 正版", lambda rf: fetch_from_netease(artist, title, rf)),
        ("Kuwo 录音室", lambda rf: fetch_from_kuwo(artist, title, rf)),
        ("YouTube 官方 Topic", lambda rf: fetch_from_youtube_wrapper(artist, title, rf, WORK_DIR, sid))
    ]

    passed_source = None
    passed_heard_text = ""
    dur_sec = 0

    for s_name, fetcher_fn in candidate_fetchers:
        print(f" • 尝试音源渠道 [{s_name}]...", end="", flush=True)
        if os.path.exists(raw_file):
            try: os.remove(raw_file)
            except: pass
        if os.path.exists(opt_file):
            try: os.remove(opt_file)
            except: pass

        ok, desc = fetcher_fn(raw_file)
        if not ok or not os.path.exists(raw_file) or os.path.getsize(raw_file) < 500000:
            print(" ❌ 未检索到合适母带")
            continue

        print(f" [🟢 下载完成: {os.path.getsize(raw_file)//1024} KB] -> 压制标准化中...", end="", flush=True)
        if not standardize_audio(raw_file, opt_file):
            print(" ❌ 压制失败")
            continue

        dur_sec = get_duration(opt_file)
        print(f" [完成 {dur_sec}s] -> AI 听音质检中...", end="", flush=True)
        passed, heard_text = whisper_verify_remediated(pool, opt_file)
        if not passed:
            print(f" ⚠️ 质检未通过 ({heard_text})，自动切换至下一渠道！")
            continue

        print(f" [🟢 质检合格! 听到: \"{heard_text[:35]}...\"]")
        passed_source = desc or s_name
        passed_heard_text = heard_text
        break

    if not passed_source:
        print(f" ❌ 所有渠道音源均未通过 AI 质检或无可用源，放弃本次替换！")
        return {"status": "FAIL_ALL_SOURCES_REJECTED", "song_id": sid}

    heard_text = passed_heard_text
    source_desc = passed_source

    # 4. 同步抓取 LRC
    print(" • [4/5] 同步抓取官方毫秒级 LRC...", end="", flush=True)
    has_lrc = fetch_lyrics(artist, title, lrc_file)
    print(" [🟢 抓取成功]" if has_lrc else " [⚠️ 未抓取到新 LRC]")

    # 5. 上传至 R2 Account 11
    print(" • [5/5] 上传 R2 并原子更新 D1...", end="", flush=True)
    clean_alb = re.sub(r'[\\/*?:"<>|]', '_', album).strip()
    clean_art = re.sub(r'[\\/*?:"<>|]', '_', artist).strip()
    r2_audio_key = f"music/{clean_art}/{clean_alb}/s_{sid}.mp3"
    r2_lrc_key = f"lyrics/{clean_art}/{clean_alb}/s_{sid}.lrc"

    with open(opt_file, "rb") as f:
        s3_11.put_object(Bucket=BUCKET_NAME, Key=r2_audio_key, Body=f, ContentType="audio/mpeg")

    if has_lrc:
        with open(lrc_file, "rb") as f:
            s3_11.put_object(Bucket=BUCKET_NAME, Key=r2_lrc_key, Body=f, ContentType="text/plain; charset=utf-8")

    new_audio_url = f"{PUBLIC_DOMAIN}/{r2_audio_key}"
    new_lrc_url = f"{PUBLIC_DOMAIN}/{r2_lrc_key}" if has_lrc else item.get("lrc_path")

    payload = {
        "updates": [{
            "id": sid,
            "file_path": new_audio_url,
            "lrc_path": new_lrc_url
        }]
    }

    updated = False
    for retry in range(3):
        try:
            r = requests.post(D1_LIGHT_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            if r.status_code == 200 and r.json().get("code") == 200:
                updated = True
                break
        except Exception:
            time.sleep(1)

    # 清理临时文件
    for p in [raw_file, opt_file, lrc_file]:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

    if updated:
        print(f" 🎉 治理成功: 《{title}》 ({dur_sec}s) -> {new_audio_url}")
        return {
            "status": "SUCCESS",
            "song_id": sid,
            "artist": artist,
            "album": album,
            "title": title,
            "old_file": item.get("file_path"),
            "new_file": new_audio_url,
            "new_lrc": new_lrc_url,
            "source": source_desc,
            "whisper_sample": heard_text
        }
    else:
        print(" ❌ D1 点亮更新失败！")
        return {"status": "FAIL_D1_UPDATE", "song_id": sid}

def main():
    print("=" * 80)
    print("🚀 启动 MOODY 早期曲库治理 - 阶段 2：实锤伪劣曲目 (46 首) 定向重采、母带重制与 AI 听音替换")
    print("=" * 80)

    if not os.path.exists(TASK_FILE):
        print(f"❌ 任务文件不存在: {TASK_FILE}")
        sys.exit(1)

    with open(TASK_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    print(f"📋 待治理替换曲目数: {len(tasks)} 首")

    pool = GroqTokenPool()
    results = []

    success_cnt = 0
    fail_cnt = 0

    for idx, t in enumerate(tasks, 1):
        print(f"\n[{idx:02d}/{len(tasks):02d}] 准备处理: [{t['artist']}] 《{t['title']}》")
        res = remediate_single(pool, t)
        results.append(res)
        if res.get("status") == "SUCCESS":
            success_cnt += 1
        else:
            fail_cnt += 1
        time.sleep(1)

    record_file = os.path.join(LOG_DIR, "STAGE_2_AUDIO_REMEDIATION_LOG.json")
    with open(record_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"🏁 阶段 2 音频与歌词替换全部完成！")
    print(f"   • 成功替换: {success_cnt} 首")
    print(f"   • 失败/跳过: {fail_cnt} 首")
    print(f"   • 治理审计日志: {record_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
