#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MoodyMusic 深度声学盲听检测引擎 (Deep Acoustic Live & Authenticity Detector)
核心功能：
1. 流式轻量截取物理音频双端边缘切片 (Head 0~20s + Tail 倒数 20s)；
2. 调用 Groq Whisper-large-v3 提取声学文本；
3. 精准排查“隐性现场版 (Live)”与“一级严重错误 (广告/李鬼伴奏)”；
4. 严格断点续存，支持大批量并发扫描。
"""

import os
import sys
import json
import time
import re
import subprocess
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# 现场版特征关键词 (排除通用词)
HEAD_LIVE_KEYWORDS = [
    "送给", "献给", "写给", "接下来这首歌", "为大家唱", "唱这首歌", "唱這首歌",
    "大家一起", "尖叫声", "掌声", "现场的朋友", "广州的朋友", "红馆的朋友", "台北的朋友",
    "北京的朋友", "现场的朋友们", "所有朋友", "大家好", "晚安", "最后为大家",
    "多谢大家", "多谢晒", "一首很老的老歌", "非常高兴今天", "再一次把掌声"
]

TAIL_LIVE_KEYWORDS = [
    "后会有期", "後會有期", "谢谢大家", "謝謝大家", "谢谢你们", "謝謝你們",
    "晚安大家", "晚安", "good night", "多谢晒", "多謝晒", "拜拜", "下次回见",
    "掌声鼓励", "谢谢所有的朋友", "再一次谢谢", "辛苦大家", "再见"
]

AD_KEYWORDS = [
    "点赞", "點贊", "订阅", "訂閱", "打赏", "打賞", "subscribe",
    "请关注", "請關注", "频道", "頻道", "视频片头", "广告", "水印",
    "ghiền mì gõ", "欢迎收看", "欢迎收听", "独播剧场", "獨播劇場", "独播", "剧场", "明镜"
]

SPOOF_KEYWORDS = [
    "纯音乐", "純音樂", "伴奏", "古筝", "二胡", "笛子",
    "zither harp", "instrumental", "伴唱", "卡拉ok", "karaoke"
]

def get_audio_duration(url):
    """获取音频时长 (秒)"""
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", url
        ], timeout=8).decode().strip()
        return float(out)
    except Exception:
        return 0.0

def extract_clip(url, start_sec, dur_sec, out_path):
    """流式提取音频片段"""
    cmd = [
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", str(dur_sec),
        "-i", url, "-ac", "1", "-ar", "16000", out_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12, check=True)

import threading

GROQ_LOCK = threading.Lock()
LAST_REQ_TIME = [0.0]

def whisper_transcribe(clip_path, prompt="", max_retries=3):
    """调用 Whisper 转写人声 (强制 verbose_json 结构化解析 + no_speech_prob <= 0.40 幻觉过滤)"""
    if not os.path.exists(clip_path) or os.path.getsize(clip_path) < 1000:
        return ""
    
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    
    for attempt in range(max_retries):
        try:
            # 严格全局排队与限流控制 (保证间隔 >= 3.2s)
            with GROQ_LOCK:
                now = time.time()
                elapsed = now - LAST_REQ_TIME[0]
                if elapsed < 3.2:
                    time.sleep(3.2 - elapsed)
                LAST_REQ_TIME[0] = time.time()

            with open(clip_path, "rb") as f:
                files = {"file": (os.path.basename(clip_path), f, "audio/mpeg")}
                data = {
                    "model": "whisper-large-v3",
                    "response_format": "verbose_json",
                    "language": "zh"
                }
                if prompt:
                    data["prompt"] = prompt
                
                resp = requests.post(GROQ_URL, headers=headers, files=files, data=data, timeout=15)
                if resp.status_code == 200:
                    payload = resp.json()
                    segments = payload.get("segments", [])
                    # 严格过滤 no_speech_prob > 0.40 的虚假自回归幻觉
                    valid_texts = []
                    for seg in segments:
                        nsp = seg.get("no_speech_prob", 0.0)
                        txt = seg.get("text", "").strip()
                        if nsp <= 0.40 and txt:
                            valid_texts.append(txt)
                    return "".join(valid_texts)
                elif resp.status_code == 429:
                    time.sleep(6 + attempt * 3)
                else:
                    time.sleep(2)
        except Exception:
            time.sleep(2)
            
    return ""

def probe_song_authenticity(song, work_dir="/tmp/acoustic_probes"):
    """对单首歌曲执行双端边缘盲听质检"""
    os.makedirs(work_dir, exist_ok=True)
    sid = song["id"]
    title = song["title"]
    album = song["album"]
    artist = song["artist"]
    url = song["file_path"]

    result = {
        "id": sid,
        "artist": artist,
        "album": album,
        "title": title,
        "file_path": url,
        "duration": 0.0,
        "head_text": "",
        "tail_text": "",
        "status": "HEALTHY",
        "issue_type": None,
        "detail": None
    }

    # 1. 探测时长
    dur = get_audio_duration(url)
    result["duration"] = dur
    if dur <= 10.0:
        result["status"] = "SEVERE_ERROR"
        result["issue_type"] = "BROKEN_OR_TRUNCATED"
        result["detail"] = f"文件异常过短或无法解析时长 ({dur:.1f}s)"
        return result

    head_clip = os.path.join(work_dir, f"head_{sid}.mp3")
    tail_clip = os.path.join(work_dir, f"tail_{sid}.mp3")

    try:
        # 2. 提取 Head 0~20s
        extract_clip(url, 0, 20, head_clip)
        head_txt = whisper_transcribe(head_clip, prompt="")
        result["head_text"] = head_txt

        # 3. 提取 Tail 倒数 20s
        tail_start = max(0, dur - 20)
        extract_clip(url, tail_start, 20, tail_clip)
        tail_txt = whisper_transcribe(tail_clip, prompt="")
        result["tail_text"] = tail_txt

        # 4. 特征分类研判
        head_lower = head_txt.lower()
        tail_lower = tail_txt.lower()

        # 检查广告水印 (严重错误) - 含细粒度二次分片验证防长上下文自回归幻觉
        hit_ad = [kw for kw in AD_KEYWORDS if kw in head_lower or kw in tail_lower]
        if hit_ad:
            confirmed_ad = False
            # 针对 Head 触发细粒度探测 (0~10s, 10~20s)
            if any(kw in head_lower for kw in hit_ad):
                sub1 = os.path.join(work_dir, f"sub_head1_{sid}.mp3")
                sub2 = os.path.join(work_dir, f"sub_head2_{sid}.mp3")
                try:
                    extract_clip(url, 0, 10, sub1)
                    extract_clip(url, 10, 10, sub2)
                    t1 = whisper_transcribe(sub1).lower()
                    t2 = whisper_transcribe(sub2).lower()
                    if any(kw in t1 or kw in t2 for kw in hit_ad):
                        confirmed_ad = True
                    else:
                        result["head_text"] = f"{t1} {t2}".strip()
                        head_lower = result["head_text"].lower()
                finally:
                    if os.path.exists(sub1): os.remove(sub1)
                    if os.path.exists(sub2): os.remove(sub2)

            # 针对 Tail 触发细粒度探测 (倒数 20~10s, 倒数 10~0s)
            if any(kw in tail_lower for kw in hit_ad):
                sub3 = os.path.join(work_dir, f"sub_tail1_{sid}.mp3")
                sub4 = os.path.join(work_dir, f"sub_tail2_{sid}.mp3")
                try:
                    extract_clip(url, max(0, dur - 20), 10, sub3)
                    extract_clip(url, max(0, dur - 10), 10, sub4)
                    t3 = whisper_transcribe(sub3).lower()
                    t4 = whisper_transcribe(sub4).lower()
                    if any(kw in t3 or kw in t4 for kw in hit_ad):
                        confirmed_ad = True
                    else:
                        result["tail_text"] = f"{t3} {t4}".strip()
                        tail_lower = result["tail_text"].lower()
                finally:
                    if os.path.exists(sub3): os.remove(sub3)
                    if os.path.exists(sub4): os.remove(sub4)

            if confirmed_ad:
                result["status"] = "SEVERE_ERROR"
                result["issue_type"] = "VIDEO_AD_WATERMARK"
                result["detail"] = f"检测到真实视频口播广告/水印词: {hit_ad} (Head: '{result['head_text']}' | Tail: '{result['tail_text']}')"
                return result

        # 检查李鬼伴奏/纯音乐 (严重错误)
        for kw in SPOOF_KEYWORDS:
            if kw in head_lower:
                result["status"] = "SEVERE_ERROR"
                result["issue_type"] = "INSTRUMENTAL_SPOOF"
                result["detail"] = f"检测到李鬼伴奏/纯音乐特征词: {kw} (Head: '{head_txt}')"
                return result

        # 检查现场发言 / 报幕 (隐性现场版 Live)
        head_hits = [kw for kw in HEAD_LIVE_KEYWORDS if kw in head_lower]
        tail_hits = [kw for kw in TAIL_LIVE_KEYWORDS if kw in tail_lower]

        if head_hits:
            result["status"] = "SUSPECT_LIVE"
            result["issue_type"] = "LIVE_STAGE_INTRO"
            result["detail"] = f"前奏检测到现场舞台报幕/互动发言: {head_hits} (Head: '{head_txt}')"
            return result

        if tail_hits:
            result["status"] = "SUSPECT_LIVE"
            result["issue_type"] = "LIVE_STAGE_OUTRO"
            result["detail"] = f"尾奏检测到现场谢幕/道别发言: {tail_hits} (Tail: '{tail_txt}')"
            return result

    except Exception as e:
        result["status"] = "PROBE_ERROR"
        result["detail"] = str(e)
    finally:
        if os.path.exists(head_clip): os.remove(head_clip)
        if os.path.exists(tail_clip): os.remove(tail_clip)

    return result

def query_artist_songs(artist_ids):
    """从 D1 提取目标歌手所有已点亮歌曲"""
    ids_str = ",".join(str(i) for i in artist_ids)
    sql = f"""
    SELECT s.id, ar.name as artist, a.title as album, s.title, s.file_path
    FROM songs s
    JOIN albums a ON s.album_id = a.id
    JOIN artists ar ON a.artist_id = ar.id
    WHERE ar.id IN ({ids_str}) AND s.file_path IS NOT NULL
    ORDER BY ar.id, a.id, s.id;
    """
    cmd = f'npx wrangler d1 execute DB --remote --command="{sql}"'
    out = subprocess.check_output(cmd, shell=True, cwd=os.path.join(BASE_DIR, "cloudflare-worker")).decode()
    start_idx = out.find("[")
    end_idx = out.rfind("]")
    data = json.loads(out[start_idx:end_idx+1])
    return data[0]["results"]

def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    if len(sys.argv) < 2:
        print("用法: python3 deep_acoustic_live_detector.py <batch_name> <artist_id_1> [artist_id_2 ...]")
        sys.exit(1)

    batch_name = sys.argv[1]
    artist_ids = [int(x) for x in sys.argv[2:]]
    progress_file = os.path.join(REPORT_DIR, f"acoustic_audit_{batch_name}.json")

    print("=" * 80)
    print(f"🎧 启动声学深度盲听体检流水线 - 批次: {batch_name}")
    print(f"📌 覆盖歌手 ID: {artist_ids}")
    print("=" * 80)

    # 1. 查询目标歌曲
    songs = query_artist_songs(artist_ids)
    print(f"📊 提取到已点亮待体检曲目: {len(songs)} 首")

    # 读取已有进度
    processed_map = {}
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                processed_map = {item["id"]: item for item in d.get("results", [])}
                print(f"🔄 发现历史进度，已完成: {len(processed_map)} 首")
        except Exception:
            pass

    pending_songs = [s for s in songs if s["id"] not in processed_map]
    print(f"⏳ 本次实际待扫描: {len(pending_songs)} 首")

    results = list(processed_map.values())
    suspect_live_count = sum(1 for r in results if r["status"] == "SUSPECT_LIVE")
    severe_error_count = sum(1 for r in results if r["status"] == "SEVERE_ERROR")

    # 2. 多线程流式双端盲听扫描 (并发度 5，保证 Groq API 限流平稳)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(probe_song_authenticity, s): s for s in pending_songs}
        
        for idx, fut in enumerate(as_completed(futures), 1):
            s = futures[fut]
            try:
                res = fut.result()
                results.append(res)
                processed_map[res["id"]] = res

                if res["status"] == "SUSPECT_LIVE":
                    suspect_live_count += 1
                    print(f"⚠️ [发现隐性现场版] [{res['id']}] {res['artist']} - 《{res['album']}》-《{res['title']}》")
                    print(f"   ↳ {res['detail']}")
                elif res["status"] == "SEVERE_ERROR":
                    severe_error_count += 1
                    print(f"❌ [发现一级严重错误] [{res['id']}] {res['artist']} - 《{res['album']}》-《{res['title']}》")
                    print(f"   ↳ {res['detail']}")
                else:
                    if idx % 10 == 0 or idx == len(pending_songs):
                        print(f"   ... 已扫描 {len(results)}/{len(songs)} 首 (Live: {suspect_live_count}, 严重错误: {severe_error_count})")

                # 每 10 首保存一次断点
                if idx % 10 == 0 or idx == len(pending_songs):
                    with open(progress_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "batch_name": batch_name,
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "total_songs": len(songs),
                            "scanned_count": len(results),
                            "suspect_live_count": suspect_live_count,
                            "severe_error_count": severe_error_count,
                            "results": results
                        }, f, ensure_ascii=False, indent=2)

            except Exception as e:
                print(f"Error processing {s['id']}: {e}")

    print("\n" + "=" * 80)
    print(f"🎉 批次 {batch_name} 声学深度盲听体检完成！")
    print(f"   • 总扫描曲目: {len(results)} 首")
    print(f"   • 确诊隐性现场版 (Live): {suspect_live_count} 首 (全部保持在线并建档待置换)")
    print(f"   • 确诊一级严重错误: {severe_error_count} 首")
    print(f"   • 结果保存路径: {progress_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
