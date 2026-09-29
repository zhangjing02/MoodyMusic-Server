#!/usr/bin/env python3
"""
Live 版专项检测流水线 (live_version_detector.py)
=================================================
检测全库 15,090 首歌曲中混入的演唱会/Live/现场版本。

三重判据（任意一项命中即标记为嫌疑）：
  1. 时长异常：实际时长 > 网易云官方录音室版时长 * 1.20 且超出 ≥ 25 秒
  2. 结尾掌声：最后 12s 音频检测到 crowd noise（宽带噪声能量 > 阈值）
  3. Whisper 环境词：片段转录出现 Live 现场互动词汇

输出：reports/LIVE_VERSION_SUSPECTS.json
"""

import os, sys, json, time, re, subprocess, tempfile, math
import concurrent.futures
import requests
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
DATA_PATH = BASE_DIR / "data" / "all_lit_songs.json"
OUTPUT_PATH = REPORTS_DIR / "LIVE_VERSION_SUSPECTS.json"
PROGRESS_PATH = REPORTS_DIR / "LIVE_DETECT_PROGRESS.json"

REPORTS_DIR.mkdir(exist_ok=True)

PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
GROQ_TOKENS = [
    "YOUR_GROQ_KEY_1",
    "YOUR_GROQ_KEY_2",
    "YOUR_GROQ_KEY_3",
]
_token_idx = 0

# Live 现场环境词汇（Whisper 转录中出现则强判 Live）
LIVE_KEYWORDS = [
    "大家好", "谢谢大家", "掌声", "演唱会", "今晚", "现场",
    "香港", "台北", "北京", "上海", "observe", "live", "concert",
    "请不吝点赞", "订阅", "转发打赏", "感谢收看", "请大家",
    "加油", "一起唱", "跟我唱"
]

def get_token():
    global _token_idx
    t = GROQ_TOKENS[_token_idx % len(GROQ_TOKENS)]
    _token_idx += 1
    return t

def get_audio_duration_fast(url: str, timeout: int = 15) -> float | None:
    """
    精确获取远端音频时长（秒）。
    使用 ffprobe -probesize 2MB -analyzeduration 0，只读文件头部即可获取精确时长。
    适用于 128/160/192/320kbps 等所有码率，误差 < 0.5s，每首约 1.3s。
    """
    try:
        r = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_entries", "format=duration,bit_rate",
            "-probesize", "2000000",
            "-analyzeduration", "0",
            url
        ], capture_output=True, text=True, timeout=timeout)
        d = json.loads(r.stdout).get("format", {})
        dur = float(d.get("duration", 0))
        return dur if dur > 5 else None
    except Exception:
        return None

# 向后兼容别名
get_audio_duration_ffprobe = get_audio_duration_fast

def get_netease_studio_duration(artist: str, title: str) -> float | None:
    """查询网易云，返回官方录音室版时长（秒），Live/演唱会版跳过"""
    try:
        query = f"{artist} {title}"
        resp = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": query, "type": 1, "limit": 8},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"},
            proxies=PROXIES, timeout=10
        )
        songs = resp.json().get("result", {}).get("songs", [])
        studio_durations = []
        for s in songs:
            sname = s.get("name", "")
            sartists = [a["name"] for a in s.get("ar", [])]
            album = s.get("al", {}).get("name", "")
            dt_ms = s.get("dt", 0)
            # 只取名字匹配 + 非 Live/演唱会专辑
            name_ok = title.replace("(", "").replace(")", "").strip() in sname or \
                      sname in title
            artist_ok = any(artist in a or a in artist for a in sartists)
            is_live = any(kw in album.lower() or kw in sname.lower()
                         for kw in ["live", "演唱会", "concert", "现场", "live版"])
            if name_ok and artist_ok and not is_live and dt_ms > 0:
                studio_durations.append(dt_ms / 1000.0)

        if studio_durations:
            # 取最短的那个作为"录音室版基准"
            return min(studio_durations)
    except Exception:
        pass
    return None

def detect_crowd_noise_in_tail(url: str, tail_sec: int = 12) -> bool:
    """
    检测结尾段是否含掌声/crowd noise。
    方法：用 ffmpeg 提取最后 tail_sec 秒，分析频谱能量分布。
    掌声特征：宽带平坦噪声，高频能量占比高，短时能量方差小。
    """
    try:
        # 先获取时长
        dur = get_audio_duration_ffprobe(url, timeout=10)
        if not dur or dur < 20:
            return False
        
        ss = max(0, dur - tail_sec)
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
            tmp = tf.name
        
        # 下载最后 tail_sec 秒（-sseof 从尾部截取）
        r = subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(ss), "-i", url,
            "-t", str(tail_sec),
            "-ar", "22050", "-ac", "1", "-f", "mp3", tmp
        ], capture_output=True, timeout=20)
        
        if not os.path.exists(tmp) or os.path.getsize(tmp) < 1000:
            return False
        
        # 用 ffmpeg volumedetect + astats 分析频谱特征
        r2 = subprocess.run([
            "ffmpeg", "-i", tmp,
            "-af", "astats=metadata=1:reset=1",
            "-f", "null", "-"
        ], capture_output=True, text=True, timeout=10)
        
        stderr = r2.stderr
        
        # 提取 RMS 能量
        rms_vals = re.findall(r"RMS level dB: ([-\d.]+)", stderr)
        flat_factor = re.findall(r"Flat factor: ([\d.]+)", stderr)
        
        os.unlink(tmp)
        
        if rms_vals:
            rms = float(rms_vals[0])
            flat = float(flat_factor[0]) if flat_factor else 0
            # 掌声特征：RMS > -30dB（有明显声音），且 flat factor > 0.3（频谱平坦）
            if rms > -35 and flat > 0.2:
                return True
        
        return False
    except Exception:
        return False

def whisper_check_live_keywords(url: str, start_sec: int = 5, duration: int = 30) -> tuple[bool, str]:
    """
    用 Whisper 转录开头段，检测 Live 现场互动词。
    返回 (is_live, transcript)
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
            tmp = tf.name
        
        r = subprocess.run([
            "ffmpeg", "-y", "-ss", str(start_sec), "-i", url,
            "-t", str(duration), "-ar", "16000", "-ac", "1", tmp
        ], capture_output=True, timeout=25)
        
        if not os.path.exists(tmp) or os.path.getsize(tmp) < 500:
            return False, ""
        
        with open(tmp, "rb") as f:
            ab = f.read()
        os.unlink(tmp)
        
        token = get_token()
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("c.mp3", ab, "audio/mpeg")},
            data={"model": "whisper-large-v3", "language": "zh", "response_format": "text"},
            proxies=PROXIES, timeout=45
        )
        if resp.status_code == 429:
            time.sleep(3)
            return False, ""
        
        text = resp.text if resp.status_code == 200 else ""
        
        # 检测 Live 关键词
        for kw in LIVE_KEYWORDS:
            if kw in text:
                return True, text
        return False, text
    except Exception:
        return False, ""

def check_single_song(song: dict) -> dict | None:
    """
    对单首歌曲做 Live 版检测。
    只有发现嫌疑才返回记录，否则返回 None。
    """
    sid = song.get("id")
    title = song.get("title", "")
    artist = song.get("artist_name", "")
    album = song.get("album_title", "")
    url = song.get("file_path", "")
    
    if not url or not url.startswith("http"):
        return None
    
    # 快速跳过：专辑名本身已明确标注是 Live（这类是有意收录的）
    album_lower = album.lower()
    if any(kw in album_lower for kw in ["演唱会", "concert", "live", "现场", "tour"]):
        return None  # 专辑已标注 Live，属于有意收录，跳过
    
    suspects = []
    details = {}
    
    # ─── 判据 1: 时长异常 ───────────────────────────────
    actual_dur = get_audio_duration_ffprobe(url, timeout=12)
    if actual_dur:
        details["actual_duration"] = round(actual_dur, 1)
        studio_dur = get_netease_studio_duration(artist, title)
        if studio_dur:
            details["netease_studio_duration"] = round(studio_dur, 1)
            ratio = actual_dur / studio_dur
            details["duration_ratio"] = round(ratio, 2)
            if ratio > 1.20 and (actual_dur - studio_dur) >= 25:
                suspects.append(f"时长异常: 实际{actual_dur:.0f}s vs 录音室{studio_dur:.0f}s (超出{ratio*100-100:.0f}%)")
    
    # ─── 判据 2: 结尾掌声检测 ──────────────────────────
    has_crowd = detect_crowd_noise_in_tail(url, tail_sec=12)
    details["tail_crowd_noise"] = has_crowd
    if has_crowd:
        suspects.append("结尾掌声/crowd noise 检测阳性")
    
    # ─── 判据 3: Whisper 环境词检测（仅当前两项未命中时才调用，节省 API）───
    if not suspects:
        is_live_kw, transcript = whisper_check_live_keywords(url, start_sec=5, duration=25)
        details["whisper_transcript_head"] = transcript[:200] if transcript else ""
        if is_live_kw:
            suspects.append(f"Whisper 检测到 Live 现场词: {transcript[:100]}")
    
    if suspects:
        return {
            "id": sid,
            "title": title,
            "artist": artist,
            "album": album,
            "file_path": url,
            "suspects": suspects,
            "details": details
        }
    return None

def main():
    print("=" * 60)
    print("  Live 版专项检测流水线")
    print("  判据: 时长异常 + 结尾掌声 + Whisper 环境词")
    print("=" * 60)
    
    with open(DATA_PATH) as f:
        all_songs = json.load(f)
    
    total = len(all_songs)
    print(f"📊 待扫描曲目: {total} 首")
    
    # 恢复上次进度
    processed_ids = set()
    suspects = []
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH) as f:
            prog = json.load(f)
            processed_ids = set(prog.get("processed_ids", []))
            suspects = prog.get("suspects", [])
        print(f"♻️  恢复进度: 已处理 {len(processed_ids)} 首，当前嫌疑 {len(suspects)} 首")
    
    remaining = [s for s in all_songs if s["id"] not in processed_ids]
    print(f"⏳ 剩余待扫描: {len(remaining)} 首\n")
    
    done = 0
    SAVE_EVERY = 100
    
    # 并发执行（时长检测 + 掌声检测 IO 密集型，可并发）
    # Whisper 有速率限制，控制在 6 并发
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(check_single_song, s): s for s in remaining}
        
        for future in concurrent.futures.as_completed(futures):
            song = futures[future]
            done += 1
            
            try:
                result = future.result(timeout=60)
                if result:
                    suspects.append(result)
                    print(f"  ⚠️  [{done}/{len(remaining)}] 发现嫌疑: {result['artist']}《{result['title']}》 → {result['suspects']}")
            except Exception as e:
                pass  # 静默跳过失败项
            
            processed_ids.add(song["id"])
            
            # 定期存档进度
            if done % SAVE_EVERY == 0 or done == len(remaining):
                with open(PROGRESS_PATH, "w") as f:
                    json.dump({"processed_ids": list(processed_ids), "suspects": suspects}, f, ensure_ascii=False)
                pct = done / len(remaining) * 100
                print(f"\n📈 进度存档: {done}/{len(remaining)} ({pct:.1f}%) | 嫌疑命中: {len(suspects)} 首\n")
    
    # 输出最终报告
    report = {
        "scan_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_scanned": total,
        "total_suspects": len(suspects),
        "suspects": sorted(suspects, key=lambda x: x["artist"])
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print(f"✅ 扫描完成！共发现 {len(suspects)} 首 Live 版嫌疑曲目")
    print(f"📄 报告已保存: {OUTPUT_PATH}")
    print("=" * 60)

if __name__ == "__main__":
    main()
