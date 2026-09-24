#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第一梯队 (Beyond & 陈奕迅) 严重错误曲目 (广告水印/破损文件) 彻底置换与治愈流水线 V2
- 增强：带 Prompt 引导消除 Whisper 弱音幻觉
- 增强：实时行缓冲输出
- 增强：严格黑名单门禁熔断
"""

import os
import sys
import json
import time
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics
import opencc

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

t2s = opencc.OpenCC('t2s')
s2t = opencc.OpenCC('s2t')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CFG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = "/tmp/remediate_tier1_severe"
os.makedirs(WORK_DIR, exist_ok=True)

with open(R2_CFG_PATH, "r", encoding="utf-8") as f:
    r2_all_cfg = json.load(f)["buckets"]

TARGET_B_ID = "account_09"
target_b_cfg = r2_all_cfg[TARGET_B_ID]
target_s3 = boto3.client(
    "s3",
    endpoint_url=target_b_cfg["endpoint_url"],
    aws_access_key_id=target_b_cfg["access_key_id"],
    aws_secret_access_key=target_b_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
target_b_name = target_b_cfg["name"]
target_pub_base = target_b_cfg["public_url"].rstrip("/")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
D1_LIGHT_API = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

# 广告黑名单词汇
REAL_AD_KEYWORDS = [
    "ghiền mì gõ", "subscribe cho kênh", "để không bỏ lỡ", 
    "优优独播剧场", "yoyo television series", "独播剧场"
]

REMEDIATION_TASKS = [
    {
        "id": 419,
        "artist": "Beyond",
        "album": "Beyond IV (超越時代紀念版)",
        "title": "曾是擁有",
        "vid": "SS_oZQ_HZd0"
    },
    {
        "id": 428,
        "artist": "Beyond",
        "album": "Beyond IV (超越時代紀念版)",
        "title": "你知道我的迷惘",
        "vid": "6e6iHODrdzU"
    },
    {
        "id": 618,
        "artist": "Beyond",
        "album": "正東10X10我至愛唱片:- Beyond『秘密警察』",
        "title": "衝開一切",
        "vid": "Y_kcxXljX54"
    },
    {
        "id": 795,
        "artist": "Beyond",
        "album": "Sound",
        "title": "Cryin'",
        "vid": "Qvkj_ziqKwY"
    },
    {
        "id": 809,
        "artist": "Beyond",
        "album": "愛與生活",
        "title": "Cryin'",
        "vid": "rxDTtB0HvHY"
    },
    {
        "id": 872,
        "artist": "Beyond",
        "album": "繼續革命",
        "title": "溫暖的家鄉",
        "vid": "R0_QuEeOUBw"
    },
    {
        "id": 884,
        "artist": "Beyond",
        "album": "信念",
        "title": "溫暖的家鄉",
        "vid": "R0_QuEeOUBw"
    },
    {
        "id": 892,
        "artist": "Beyond",
        "album": "真的見証",
        "title": "明日世界",
        "vid": "CYUBzNMv5fs"
    },
    {
        "id": 1152,
        "artist": "陈奕迅",
        "album": "...3mm",
        "title": "非禮",
        "vid": "lGPKGsoNkOc"
    },
    {
        "id": 1294,
        "artist": "陈奕迅",
        "album": "Life Continues",
        "title": "落花流水",
        "vid": "FF_35jGO53I"
    },
    {
        "id": 1524,
        "artist": "陈奕迅",
        "album": "68'29\"",
        "title": "原來這裡沒有你 (無線電視劇《雷霆第一關》片尾曲)",
        "vid": "E1KgwjVYYkY"
    },
    {
        "id": 1545,
        "artist": "陈奕迅",
        "album": "打得火熱",
        "title": "美麗謊言",
        "vid": "aAjN5BqyRuM"
    },
    {
        "id": 25596,
        "artist": "陈奕迅",
        "album": "H³M",
        "title": "七百年后",
        "vid": "99eiuuHgIgk"
    },
    {
        "id": 25548,
        "artist": "陈奕迅",
        "album": "上五樓的快活",
        "title": "多少",
        "vid": "44ZEvw3QBpc"
    }
]

def whisper_blind_test(clip_path, prompt_text=""):
    if not GROQ_KEY or not os.path.exists(clip_path) or os.path.getsize(clip_path) < 1000:
        return ""
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    for attempt in range(3):
        try:
            with open(clip_path, "rb") as f:
                data = {"model": "whisper-large-v3"}
                if prompt_text:
                    data["prompt"] = prompt_text
                r = requests.post(
                    GROQ_URL,
                    headers=headers,
                    files={"file": (os.path.basename(clip_path), f, "audio/mpeg")},
                    data=data,
                    timeout=15
                )
                if r.status_code == 200:
                    time.sleep(3.2)
                    return r.json().get("text", "").strip()
                elif r.status_code == 429:
                    time.sleep(5 + attempt * 2)
                else:
                    time.sleep(2)
        except Exception:
            time.sleep(2)
    return ""

def search_kugou_lrc(artist: str, title: str):
    keyword = f"{artist} - {title}"
    url = f"http://lyrics.kugou.com/search?ver=1&man=yes&client=pc&keyword={requests.utils.quote(keyword)}&duration=&hash="
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            candidates = r.json().get('candidates', [])
            if candidates:
                cand = candidates[0]
                cand_id = cand['id']
                accesskey = cand['accesskey']
                down_url = f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cand_id}&accesskey={accesskey}&fmt=lrc&charset=utf8"
                dr = requests.get(down_url, timeout=5)
                if dr.status_code == 200:
                    import base64
                    content_b64 = dr.json().get('content', '')
                    if content_b64:
                        return base64.b64decode(content_b64).decode('utf-8', errors='replace')
    except Exception:
        pass
    return None

def fetch_best_lrc(artist: str, title: str):
    clean_t = title.split('(')[0].strip()
    simp_t = t2s.convert(clean_t)
    trad_t = s2t.convert(clean_t)
    
    for q in [f"{artist} {clean_t}", f"{artist} {simp_t}", f"{artist} {trad_t}"]:
        try:
            lrc = syncedlyrics.search(q, providers=['NetEase', 'Lrclib'])
            if lrc and len(lrc) > 50 and '[' in lrc:
                return lrc
        except Exception:
            pass
        lrc = search_kugou_lrc(artist, clean_t)
        if lrc and len(lrc) > 50 and '[' in lrc:
            return lrc
    return None

def main():
    print(f"==================================================")
    print(f"🚀 开始第一梯队 14 首严重错误曲目无瑕置换 (EBU R128 + Xing Header)")
    print(f"==================================================")
    
    success_lights = []
    
    for idx, t in enumerate(REMEDIATION_TASKS, 1):
        sid = t["id"]
        artist = t["artist"]
        album = t["album"]
        title = t["title"]
        vid = t["vid"]
        
        print(f"\n--- [{idx}/{len(REMEDIATION_TASKS)}] {artist} - 《{title}》 (ID: {sid}) ---")
        raw_out = os.path.join(WORK_DIR, f"raw_{sid}.%(ext)s")
        clean_mp3 = os.path.join(WORK_DIR, f"s_{sid}.mp3")
        
        # 1. 下载官方音频
        print(f"   📥 从 YouTube Official Topic (ID: {vid}) 提取音频...")
        dl_cmd = [
            "yt-dlp", "--force-overwrites", "--no-playlist",
            "-f", "ba", "-o", raw_out, f"https://www.youtube.com/watch?v={vid}"
        ]
        subprocess.run(dl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
        
        found_raw = None
        for ext in ["webm", "m4a", "opus", "mp3"]:
            p = os.path.join(WORK_DIR, f"raw_{sid}.{ext}")
            if os.path.exists(p) and os.path.getsize(p) > 200000:
                found_raw = p
                break
                
        if not found_raw:
            print(f"   ❌ 音频下载失败!")
            continue
            
        # 2. EBU R128 标准化压制 + ID3v2 标签
        print(f"   🎛️ EBU R128 标准化 (-14 LUFS) 压制 160k CBR Xing MP3...")
        conv_cmd = [
            "ffmpeg", "-y", "-i", found_raw,
            "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
            "-b:a", "160k", "-ar", "44100", "-ac", "2",
            "-metadata", f"title={title}",
            "-metadata", f"artist={artist}",
            "-metadata", f"album={album}",
            clean_mp3
        ]
        subprocess.run(conv_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
        
        if not os.path.exists(clean_mp3) or os.path.getsize(clean_mp3) < 200000:
            print(f"   ❌ 音频压制失败!")
            continue
            
        dur = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", clean_mp3
        ]).decode().strip())
        print(f"   ⏱️ 压制成功: {dur:.1f}s, 大小: {os.path.getsize(clean_mp3)} 字节")
        
        # 3. 提取首尾 20s 进行带 Prompt 的 Whisper 深度质检
        head_clip = os.path.join(WORK_DIR, f"head_{sid}.mp3")
        tail_clip = os.path.join(WORK_DIR, f"tail_{sid}.mp3")
        subprocess.run(["ffmpeg", "-y", "-ss", "0", "-t", "20", "-i", clean_mp3, "-ac", "1", "-ar", "16000", head_clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["ffmpeg", "-y", "-ss", str(max(0, dur-20)), "-t", "20", "-i", clean_mp3, "-ac", "1", "-ar", "16000", tail_clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        prompt_txt = f"{artist} 《{title}》 官方录音室大碟原声"
        head_txt = whisper_blind_test(head_clip, prompt_txt)
        tail_txt = whisper_blind_test(tail_clip, prompt_txt)
        print(f"   🗣️ Head Whisper 转写: \"{head_txt}\"")
        print(f"   🗣️ Tail Whisper 转写: \"{tail_txt}\"")
        
        # 严格门禁：排查真实广告
        combined_text = (head_txt + " " + tail_txt).lower()
        has_ad = any(kw in combined_text for kw in REAL_AD_KEYWORDS)
        if has_ad:
            print(f"   🚫 门禁拦截：检测到真实广告口播！严禁入库！")
            continue
            
        # 4. 抓取高精度 LRC 歌词
        lrc_content = fetch_best_lrc(artist, title)
        lrc_file = os.path.join(WORK_DIR, f"s_{sid}.lrc")
        if lrc_content:
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write(lrc_content)
            print(f"   📝 获取到同步动态歌词 ({len(lrc_content.splitlines())} 行)")
        else:
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write(f"[ti:{title}]\n[ar:{artist}]\n[al:{album}]\n[00:00.00]{artist} - {title}\n")
            print(f"   ⚠️ 未抓取到全网动态歌词，写入元数据保护歌词")
            
        # 5. 上传到 Bucket 09
        mp3_key = f"music/{artist}/{album}/s_{sid}.mp3"
        lrc_key = f"lyrics/{artist}/{album}/s_{sid}.lrc"
        
        print(f"   ☁️ 上传到 Bucket 09: {mp3_key}...")
        target_s3.upload_file(clean_mp3, target_b_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        target_s3.upload_file(lrc_file, target_b_name, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        
        final_mp3_url = f"{target_pub_base}/{mp3_key}"
        final_lrc_url = f"{target_pub_base}/{lrc_key}"
        
        success_lights.append({
            "id": sid,
            "file_path": final_mp3_url,
            "lrc_path": final_lrc_url
        })
        print(f"   ✅ 上传成功并生成直链: {final_mp3_url}")
        
    # 6. 批量原子点亮 D1
    if success_lights:
        print(f"\n4️⃣ 正在批量调用 /api/admin/songs/batch-light 点亮 {len(success_lights)} 首新母带...")
        light_resp = requests.post(D1_LIGHT_API, json={"updates": success_lights}, timeout=15)
        print(f"   D1 响应: {light_resp.status_code} {light_resp.text}")
    
    print(f"\n==================================================")
    print(f"🎉 治理流水线圆满完成！成功重制点亮: {len(success_lights)} / {len(REMEDIATION_TASKS)}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
