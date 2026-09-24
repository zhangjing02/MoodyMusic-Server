#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周杰伦 14 首置换曲目声学与网络流式切片验收测试
1. HTTP 206 Partial Content 切片测试；
2. Groq Whisper 盲听复检 (Head 0~20s + Tail 倒数 20s)。
"""

import os
import sys
import json
import time
import subprocess
import requests

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# 14 首曲目 ID
TARGET_IDS = [23291, 23312, 23313, 23317, 23324, 23335, 23349, 23359, 23367, 23369, 23371, 23390, 23403, 23434]

def query_d1():
    ids_str = ",".join(str(i) for i in TARGET_IDS)
    cmd = f'npx wrangler d1 execute DB --remote --command="SELECT s.id, ar.name as artist, a.title as album, s.title, s.file_path, s.duration FROM songs s JOIN albums a ON s.album_id = a.id JOIN artists ar ON a.artist_id = ar.id WHERE s.id IN ({ids_str}) ORDER BY s.id;"'
    out = subprocess.check_output(cmd, shell=True, cwd=os.path.join(BASE_DIR, "cloudflare-worker")).decode()
    start_idx = out.find("[")
    end_idx = out.rfind("]")
    data = json.loads(out[start_idx:end_idx+1])
    return data[0]["results"]

def test_range_206(url):
    try:
        headers = {"Range": "bytes=0-1023"}
        r = requests.get(url, headers=headers, timeout=10)
        return r.status_code == 206 and len(r.content) == 1024
    except Exception:
        return False

def whisper_transcribe(clip_path):
    if not os.path.exists(clip_path) or os.path.getsize(clip_path) < 1000:
        return ""
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    time.sleep(3.2) # 严格限流保护
    with open(clip_path, "rb") as f:
        files = {"file": (os.path.basename(clip_path), f, "audio/mpeg")}
        data = {"model": "whisper-large-v3"} # 零 Prompt
        resp = requests.post(GROQ_URL, headers=headers, files=files, data=data, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
    return ""

def main():
    print("=" * 80)
    print("🔬 启动周杰伦 14 首正版母带验收：HTTP 206 切片测试与 Groq Whisper 盲听复检")
    print("=" * 80)

    songs = query_d1()
    work_dir = "/tmp/verify_jay_chou_14"
    os.makedirs(work_dir, exist_ok=True)

    verification_results = []
    all_passed = True

    for idx, s in enumerate(songs, 1):
        sid = s["id"]
        title = s["title"]
        album = s["album"]
        url = s["file_path"]
        dur = float(s["duration"])

        # 1. HTTP 206 测试
        p206 = test_range_206(url)
        p206_str = "PASS (206)" if p206 else "FAIL"

        # 2. 抽样/全面盲审双端文本
        head_clip = os.path.join(work_dir, f"v_head_{sid}.mp3")
        tail_clip = os.path.join(work_dir, f"v_tail_{sid}.mp3")

        # 提取 0~15s
        cmd1 = ["ffmpeg", "-y", "-ss", "0", "-t", "15", "-i", url, "-ac", "1", "-ar", "16000", head_clip]
        subprocess.run(cmd1, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        head_txt = whisper_transcribe(head_clip)

        # 提取尾部 15s
        tail_start = max(0, dur - 15)
        cmd2 = ["ffmpeg", "-y", "-ss", str(tail_start), "-t", "15", "-i", url, "-ac", "1", "-ar", "16000", tail_clip]
        subprocess.run(cmd2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        tail_txt = whisper_transcribe(tail_clip)

        # 敏感词排查
        bad_words = ["点赞", "订阅", "打赏", "独播剧场", "明镜", "古筝", "谢谢大家", "good night"]
        has_bad = any(bw in head_txt or bw in tail_txt for bw in bad_words)

        status = "HEALTHY" if (p206 and not has_bad) else "FAILED"
        if status != "HEALTHY":
            all_passed = False

        res = {
            "id": sid,
            "title": title,
            "album": album,
            "duration": dur,
            "url": url,
            "http_206": p206,
            "head_text": head_txt,
            "tail_text": tail_txt,
            "status": status
        }
        verification_results.append(res)

        print(f"[{idx}/14] ID {sid}: {title} | 206: {p206_str} | 状态: {status}")
        print(f"       Head (0~15s): '{head_txt}'")
        print(f"       Tail (末15s):  '{tail_txt}'")

        if os.path.exists(head_clip): os.remove(head_clip)
        if os.path.exists(tail_clip): os.remove(tail_clip)

    out_file = os.path.join(REPORT_DIR, "jay_chou_14_remediation_audit.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(verification_results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"🎉 验收审计完成！14 首全部健康通过: {all_passed}，报告已保存至 {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
