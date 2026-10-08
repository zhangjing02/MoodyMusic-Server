#!/usr/bin/env python3
"""
五月天全盘立体化审计流水线 (audit_mayday_comprehensive.py)
=========================================================
针对五月天全库 233 首歌曲实施立体化审计：
1. LRC 真实性与有效性审计（排除外文乱入、空歌词）
2. 录音室基准时长比对（ffprobe 快速流探针 vs 网易云官方大碟时长）
3. 声学人声起唱语义锚定核验（Whisper 盲听 vs LRC 时间轴歌词字符重合度，彻底捕获《夜访吸血鬼》类错配）
4. 尾段现场欢呼/水印检测

输出：reports/MAYDAY_DEEP_AUDIT_REPORT.json
"""

import os, sys, json, time, re, subprocess, tempfile
import concurrent.futures
import requests
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
OUTPUT_PATH = REPORTS_DIR / "MAYDAY_DEEP_AUDIT_REPORT.json"
PROGRESS_PATH = REPORTS_DIR / "MAYDAY_AUDIT_PROGRESS.json"

PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
GROQ_TOKENS = [
    "YOUR_GROQ_KEY_1",
    "YOUR_GROQ_KEY_2",
    "YOUR_GROQ_KEY_3",
]
_token_idx = 0

def get_token():
    global _token_idx
    t = GROQ_TOKENS[_token_idx % len(GROQ_TOKENS)]
    _token_idx += 1
    return t

def get_audio_duration(url: str, timeout: int = 15) -> float | None:
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

def get_netease_studio_duration(title: str) -> float | None:
    try:
        query = f"五月天 {title}"
        resp = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": query, "type": 1, "limit": 8},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"},
            proxies=PROXIES, timeout=10
        )
        songs = resp.json().get("result", {}).get("songs", [])
        durs = []
        for s in songs:
            sname = s.get("name", "")
            sartists = [a["name"] for a in s.get("ar", [])]
            album = s.get("al", {}).get("name", "")
            dt_ms = s.get("dt", 0)
            
            clean_title = re.sub(r'[\(\)（）\s]', '', title)
            clean_sname = re.sub(r'[\(\)（）\s]', '', sname)
            name_ok = clean_title in clean_sname or clean_sname in clean_title
            artist_ok = any("五月天" in a for a in sartists)
            is_live = any(kw in album.lower() or kw in sname.lower()
                         for kw in ["live", "演唱会", "concert", "现场"])
            if name_ok and artist_ok and not is_live and dt_ms > 0:
                durs.append(dt_ms / 1000.0)
        if durs:
            return min(durs)
    except Exception:
        pass
    return None

def parse_lrc(lrc_url: str):
    """获取并解析 LRC，返回 (first_vocal_sec, text_snippet, is_foreign_or_invalid)"""
    if not lrc_url:
        return 0, "", True
    try:
        r = requests.get(lrc_url, proxies=PROXIES, timeout=10)
        if r.status_code != 200:
            return 0, "", True
        
        lines = r.text.strip().split("\n")
        vocal_lines = []
        first_sec = None
        
        for l in lines:
            m = re.match(r'\[(\d{2}):(\d{2})(?:\.(\d+))?\](.*)', l)
            if m:
                m_min, m_sec, _, txt = m.groups()
                total_s = int(m_min) * 60 + int(m_sec)
                txt_clean = txt.strip()
                if not txt_clean:
                    continue
                # 排除元数据标签
                if any(txt_clean.startswith(prefix) for prefix in ["作词", "作曲", "编曲", "演唱", "制作", "ar:", "ti:", "al:", "by:"]):
                    continue
                
                if first_sec is None:
                    first_sec = total_s
                vocal_lines.append(txt_clean)
        
        full_text = "".join(vocal_lines)
        if not full_text:
            return 0, "", True
        
        # 检查是否全是外文（如德语、纯英文）
        chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', full_text))
        is_foreign = (chinese_chars < 10) and (len(full_text) > 30)
        
        return (first_sec or 25), full_text[:400], is_foreign
    except Exception:
        return 0, "", True

def whisper_audio(url: str, start_sec: int, duration_sec: int = 30) -> str:
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
            tmp = tf.name
        
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(max(0, start_sec)), "-i", url,
            "-t", str(duration_sec), "-ar", "16000", "-ac", "1", tmp
        ], capture_output=True, timeout=25)
        
        if not os.path.exists(tmp) or os.path.getsize(tmp) < 500:
            return ""
        
        with open(tmp, "rb") as f:
            ab = f.read()
        os.unlink(tmp)
        
        for _ in range(len(GROQ_TOKENS)):
            tk = get_token()
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {tk}"},
                files={"file": ("c.mp3", ab, "audio/mpeg")},
                data={"model": "whisper-large-v3", "language": "zh", "response_format": "text"},
                proxies=PROXIES, timeout=35
            )
            if resp.status_code == 200:
                return resp.text.strip()
            time.sleep(1)
        return ""
    except Exception:
        return ""

def compute_similarity(text1: str, text2: str) -> float:
    """计算中文字符重合比例"""
    c1 = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]', text1))
    c2 = set(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]', text2))
    if not c1 or not c2:
        return 0.0
    intersection = c1.intersection(c2)
    return len(intersection) / min(len(c1), len(c2))

def audit_song(song: dict) -> dict:
    sid = song.get("id")
    title = song.get("title", "")
    album = song.get("album", "")
    audio_url = song.get("path", "")
    lrc_url = song.get("lrc_path", "")
    
    issues = []
    meta = {}
    
    # 1. 音频时长
    actual_dur = get_audio_duration(audio_url)
    meta["actual_dur"] = actual_dur
    if not actual_dur:
        issues.append("无法获取音频时长或文件无法访问")
        return {"song": song, "issues": issues, "meta": meta, "healthy": False}
    
    # 2. 录音室基准时长比对
    studio_dur = get_netease_studio_duration(title)
    meta["studio_dur"] = studio_dur
    if studio_dur:
        ratio = actual_dur / studio_dur
        meta["duration_ratio"] = round(ratio, 2)
        if ratio > 1.20 and (actual_dur - studio_dur) >= 25:
            issues.append(f"时长偏长（实际 {actual_dur:.0f}s vs 录音室 {studio_dur:.0f}s，疑似 Live / 串烧）")
        elif ratio < 0.75 and (studio_dur - actual_dur) >= 25:
            issues.append(f"时长被截断（实际 {actual_dur:.0f}s vs 录音室 {studio_dur:.0f}s）")
            
    # 3. LRC 歌词核查
    first_vocal, lrc_sample, is_invalid_lrc = parse_lrc(lrc_url)
    meta["first_vocal_sec"] = first_vocal
    meta["lrc_sample"] = lrc_sample[:100]
    if is_invalid_lrc:
        issues.append("LRC 缺失、无效或包含纯外文错配")
        
    # 4. Whisper 盲听语义核查
    whisper_text = whisper_audio(audio_url, start_sec=first_vocal, duration_sec=30)
    meta["whisper_vocal"] = whisper_text[:120]
    
    if whisper_text and lrc_sample:
        sim = compute_similarity(whisper_text, lrc_sample)
        meta["semantic_sim"] = round(sim, 2)
        # 如果重合度低于 20%，强行预警歌词与音频不符
        if sim < 0.20:
            issues.append(f"音频与歌词严重不符 (重合度仅 {sim*100:.0f}%, 音频实际转录: '{whisper_text[:40]}...')")
            
    # 5. 水印与违规口播核查
    watermarks = ["请不吝点赞", "订阅", "字幕志愿者", "独播剧场", "明镜与点点"]
    for wm in watermarks:
        if wm in whisper_text:
            issues.append(f"音频中含有平台/搬运水印: '{wm}'")
            
    healthy = (len(issues) == 0)
    return {
        "song": song,
        "healthy": healthy,
        "issues": issues,
        "meta": meta
    }

def main():
    with open("/tmp/mayday_online_songs.json") as f:
        songs = json.load(f)
        
    print(f"==================================================")
    print(f" 五月天立体化双轨全量深度审计流水线")
    print(f" 待测曲目: {len(songs)} 首 | 线程数: 8")
    print(f"==================================================\n")
    
    results = []
    suspects = []
    done = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(audit_song, s): s for s in songs}
        for f in concurrent.futures.as_completed(futs):
            done += 1
            try:
                res = f.result(timeout=60)
                results.append(res)
                s = res["song"]
                if not res["healthy"]:
                    suspects.append(res)
                    print(f"🚨 [{done}/{len(songs)}] 发现异常: 《{s['title']}》[{s['album']}] -> {res['issues']}")
                else:
                    if done % 20 == 0 or done == len(songs):
                        print(f"✅ [{done}/{len(songs)}] 进度稳步推进 | 当前嫌疑: {len(suspects)} 首")
            except Exception as e:
                print(f"⚠ [{done}/{len(songs)}] 异常: {e}")
                
            if done % 25 == 0 or done == len(songs):
                with open(PROGRESS_PATH, "w", encoding="utf-8") as pf:
                    json.dump({"total": len(songs), "done": done, "suspects": suspects}, pf, ensure_ascii=False, indent=2)
                    
    report = {
        "scan_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(songs),
        "suspects_count": len(suspects),
        "suspects": sorted(suspects, key=lambda x: x["song"]["album"])
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as rf:
        json.dump(report, rf, ensure_ascii=False, indent=2)
        
    print("\n" + "="*50)
    print(f"五月天全盘审计完成！")
    print(f"总计扫描: {len(songs)} 首 | 发现异常: {len(suspects)} 首")
    print(f"报告已保存至: {OUTPUT_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
