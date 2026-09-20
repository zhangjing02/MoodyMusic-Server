#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""郑智化 33 首攻坚重铸最终流水线 (全自动官方源匹配 + 双切片 Whisper 质检 + 双 Bucket 智能路由)"""

import os, sys, json, time, re, subprocess, requests, boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
WORK_DIR = "/tmp/zheng_remediate_final"
os.makedirs(WORK_DIR, exist_ok=True)

# 1. 加载双 Bucket 配置
with open(os.path.join(BASE_DIR, "r2_config.json"), "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]

s3_clients = {}
domains = {}
buckets = {}
for acc in ["account_07", "account_08"]:
    cfg = r2_cfg[acc]
    s3_clients[acc] = boto3.client(
        "s3",
        endpoint_url=cfg["endpoint_url"],
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4")
    )
    domains[acc] = cfg.get("public_url", cfg.get("public_domain", "")).rstrip("/")
    buckets[acc] = cfg["name"]

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_PROXIES = {"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}
D1_LIGHT_API = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def clean_text(t):
    return re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", t).lower()

def transcribe_whisper(clip_path):
    if not GROQ_KEY:
        return ""
    with open(clip_path, "rb") as f:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": (os.path.basename(clip_path), f, "audio/mpeg"), "model": (None, "whisper-large-v3")},
            proxies=GROQ_PROXIES,
            timeout=25
        )
    return r.json().get("text", "").strip()

def search_best_youtube(title, album, target_dur):
    # 优先 Timeless Music / 官方
    queries = [
        f"ytsearch5:鄭智化 {title} 官方完整版",
        f"ytsearch5:鄭智化 {title}",
    ]
    for q in queries:
        try:
            cmd = [
                "yt-dlp", "--proxy", "http://127.0.0.1:7898",
                "--flat-playlist", "--no-warnings",
                "--print", "%(id)s\t%(channel)s\t%(title)s\t%(duration)s",
                q
            ]
            output = subprocess.check_output(cmd, timeout=25).decode().strip().splitlines()
            candidates = []
            for line in output:
                parts = line.split("\t")
                if len(parts) == 4:
                    vid, channel, vtitle, vdur = parts[0], parts[1], parts[2], float(parts[3] or 0)
                    # 过滤黑名单
                    if any(k in vtitle for k in ["古筝", "Zither", "伴奏", "纯音乐", "吉他谱", "翻唱", "Cover"]):
                        continue
                    if any(k in channel for k in ["Zither"]):
                        continue
                    score = 0
                    if any(k in channel for k in ["Timeless", "滾石", "飛碟", "Warner"]):
                        score += 50
                    if any(k in vtitle for k in ["官方", "Official", "完整版"]):
                        score += 30
                    if target_dur > 0 and abs(vdur - target_dur) < 25:
                        score += 20
                    candidates.append((score, vid, channel, vtitle, vdur))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best = candidates[0]
                return best[1], best[3], best[4]
        except Exception as e:
            continue
    return None, None, 0

def get_netease_lrc(title):
    try:
        r = requests.get(f"https://music.163.com/api/search/get/web?s=郑智化+{title}&type=1&limit=3", headers=HEADERS, timeout=6)
        songs = r.json().get("result", {}).get("songs", [])
        for s in songs:
            if "郑智化" in s.get("artists", [{}])[0].get("name", ""):
                nid = s["id"]
                lr = requests.get(f"http://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1", headers=HEADERS, timeout=6)
                lrc = lr.json().get("lrc", {}).get("lyric", "")
                if lrc and len(lrc) > 30:
                    return lrc
    except:
        pass
    return None

def process_track(track):
    sid = int(track["id"])
    title = track["title"]
    album = track["album"]
    target_dur = float(track.get("duration") or 0)
    orig_path = track.get("path", "")

    # 判断写入 Bucket
    if "pub-dd32e05660c74c3dba04d231391eb82b" in orig_path or album == "游戏人间":
        acc = "account_08"
    else:
        acc = "account_07"

    print(f"\n▶ 开始处理: 《{title}》 (专辑: {album}, ID: {sid}) -> 目标存储: {acc}")

    raw_mp3 = f"{WORK_DIR}/s_{sid}_raw.mp3"
    proc_mp3 = f"{WORK_DIR}/s_{sid}.mp3"
    lrc_file = f"{WORK_DIR}/s_{sid}.lrc"

    # 1. 查找 YouTube 视频
    vid, vtitle, vdur = search_best_youtube(title, album, target_dur)
    if not vid:
        print(f"   ❌ 未检索到可信官方音源")
        return None

    print(f"   🎥 锁定音源: [{vid}] {vtitle} ({vdur:.0f}s)")
    try:
        subprocess.run([
            "yt-dlp", "--proxy", "http://127.0.0.1:7898",
            "-x", "--audio-format", "mp3",
            "-o", f"{WORK_DIR}/s_{sid}_yt.%(ext)s",
            f"https://www.youtube.com/watch?v={vid}"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=120)
        os.rename(f"{WORK_DIR}/s_{sid}_yt.mp3", raw_mp3)
    except Exception as e:
        print(f"   ❌ 下载音源失败: {e}")
        return None

    # 2. 获取 LRC
    lrc_text = get_netease_lrc(title)
    if not lrc_text and track.get("lrc_path"):
        try:
            r = requests.get(track["lrc_path"], timeout=5)
            if r.status_code == 200 and len(r.text) > 30:
                lrc_text = r.text
        except:
            pass
    if lrc_text:
        with open(lrc_file, "w", encoding="utf-8") as f:
            f.write(lrc_text)

    # 3. EBU R128 + 160k CBR Xing 压制
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_mp3,
            "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1",
            proc_mp3
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dur = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", proc_mp3
        ]).decode().strip())
        print(f"   ✅ EBU R128 压制成功: 时长 {dur:.1f}s")
    except Exception as e:
        print(f"   ❌ 音频压制失败: {e}")
        return None

    # 4. Whisper 质检 (双切片策略)
    passed = False
    heard_final = ""
    for ss in [40, 75]:
        clip = f"{WORK_DIR}/s_{sid}_clip_{ss}.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(ss), "-t", "30",
            "-i", proc_mp3, "-ac", "1", "-ar", "16000", clip
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(clip):
            heard = transcribe_whisper(clip)
            os.remove(clip)
            if "Zither Harp" in heard or "古筝" in heard:
                print(f"   🚫 拦截: 检测到古筝器乐侵占")
                return None
            if len(clean_text(heard)) >= 6:
                passed = True
                heard_final = heard
                break

    if not passed:
        print(f"   🚫 质检未通过: 未听到有效主唱声乐")
        return None

    print(f"   🎯 质检通过: 听辨 '{heard_final[:40]}...'")

    # 5. 上传至对应 Bucket
    key_audio = f"music/郑智化/{album}/s_{sid}.mp3"
    key_lrc = f"lyrics/郑智化/{album}/s_{sid}.lrc"
    s3_clients[acc].upload_file(proc_mp3, buckets[acc], key_audio, ExtraArgs={"ContentType": "audio/mpeg"})
    print(f"   ☁️ R2 音频覆写成功: {buckets[acc]}/{key_audio}")

    if os.path.exists(lrc_file):
        s3_clients[acc].upload_file(lrc_file, buckets[acc], key_lrc, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        print(f"   ☁️ R2 歌词覆写成功: {buckets[acc]}/{key_lrc}")

    # 清理本地临时文件
    for f_p in [raw_mp3, proc_mp3, lrc_file]:
        if os.path.exists(f_p):
            try: os.remove(f_p)
            except: pass

    cdn = domains[acc]
    return {
        "id": sid,
        "file_path": f"{cdn}/{key_audio}",
        "lrc_path": f"{cdn}/{key_lrc}",
        "duration": round(dur),
        "is_lit": 1
    }

def main():
    tasks_file = os.path.join(REPORT_DIR, "zheng_remaining_33.json")
    with open(tasks_file, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    print(f"================================================================================")
    print(f"🚀 启动【郑智化】终极攻坚重铸流水线 (共 {len(tasks)} 首)")
    print(f"================================================================================")

    d1_updates = []
    for i, t in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}]", end="")
        res = process_track(t)
        if res:
            d1_updates.append(res)
            # 每 5 首或最后一首批量点亮一次，避免单次 payload 丢失
            if len(d1_updates) >= 5 or i == len(tasks):
                try:
                    r = requests.post(D1_LIGHT_API, json={"updates": d1_updates}, timeout=20)
                    print(f"\n📡 D1 原子批量点亮响应: {r.status_code} | {r.text}")
                    d1_updates.clear()
                except Exception as e:
                    print(f"\n⚠️ D1 点亮异常: {e}")

    print(f"\n================================================================================")
    print(f"🎉 郑智化攻坚重铸完成！")
    print(f"================================================================================")

if __name__ == "__main__":
    main()
