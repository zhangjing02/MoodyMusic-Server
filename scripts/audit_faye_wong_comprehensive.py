#!/usr/bin/env python3
"""
王菲全盘立体化审计流水线 - 第一阶段初筛 (audit_faye_wong_comprehensive.py)
========================================================================
对王菲名下 25 张大碟共 411 首在线曲目执行立体化审计：
1. LRC 有效性与语言审计（排除空歌词、外文错配、假名）
2. 歌词与标题核心语义一致性校验（彻底捕获《棋子》播放成《天空》的“双向李鬼对撞”）
3. 录音室基准时长比对（ffprobe 快速流探针 vs 网易云官方录音室大碟时长）
4. 声学人声起唱语义锚定核验（Whisper 盲听 vs LRC 时间轴歌词字符重合度，低于 20% 强制拦截）
5. 搬运平台水印与广告检测（如“明镜与点点”、“优优独播剧场”、“字幕志愿者”等）

输出：reports/FAYE_WONG_STAGE1_AUDIT_REPORT.json
"""

import os, sys, json, time, re, subprocess, tempfile, threading
import concurrent.futures
import requests, zhconv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
OUTPUT_PATH = REPORTS_DIR / "FAYE_WONG_STAGE1_AUDIT_REPORT.json"
PROGRESS_PATH = REPORTS_DIR / "FAYE_WONG_STAGE1_PROGRESS.json"

PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}

with open(BASE_DIR / "groq_config.json") as f:
    cfg = json.load(f)
GROQ_TOKENS = cfg.get("tokens", [])
_token_idx = 0
_lock = threading.Lock()

def get_token():
    global _token_idx
    with _lock:
        t = GROQ_TOKENS[_token_idx % len(GROQ_TOKENS)]
        _token_idx += 1
        return t

def clean_text(t: str) -> str:
    if not t: return ""
    t = zhconv.convert(t, 'zh-cn')
    t = re.sub(r'[^\w\u4e00-\u9fa5]', '', t)
    return t.lower()

def get_audio_duration(url: str, timeout: int = 15) -> float | None:
    if not url: return None
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

def get_netease_studio_duration(title: str) -> tuple[float | None, int | None]:
    try:
        query = f"王菲 {title}"
        resp = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": query, "type": 1, "limit": 6},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"},
            proxies=PROXIES, timeout=10
        )
        songs = resp.json().get("result", {}).get("songs", [])
        clean_target = clean_text(title)
        
        for s in songs:
            sname = s.get("name", "")
            sartists = [a["name"] for a in s.get("ar", [])]
            album = s.get("al", {}).get("name", "")
            dt_ms = s.get("dt", 0)
            clean_sname = clean_text(sname)
            
            name_ok = clean_target in clean_sname or clean_sname in clean_target
            artist_ok = any("王菲" in a or "Faye" in a for a in sartists)
            is_live = any(kw in album.lower() or kw in sname.lower()
                         for kw in ["live", "演唱会", "concert", "现场", "巡回"])
            if name_ok and artist_ok and not is_live and dt_ms > 10000:
                return (dt_ms / 1000.0, s.get("id"))
    except Exception:
        pass
    return (None, None)

def parse_lrc(lrc_url: str):
    """解析 LRC 返回 (first_vocal_sec, text_snippet, is_invalid, raw_full_text)"""
    if not lrc_url:
        return 0, "", True, ""
    try:
        r = requests.get(lrc_url, proxies=PROXIES, timeout=10)
        if r.status_code != 200:
            return 0, "", True, ""
        
        raw_text = r.text
        lines = raw_text.strip().split("\n")
        vocal_lines = []
        first_sec = None
        
        for l in lines:
            m = re.match(r'\[(\d{2}):(\d{2})(?:\.(\d+))?\](.*)', l)
            if m:
                m_min, m_sec, _, txt = m.groups()
                sec = int(m_min) * 60 + int(m_sec)
                txt = txt.strip()
                if txt and not any(kw in txt for kw in ["作词", "作曲", "编曲", "制作", "监制", "词：", "曲："]):
                    if first_sec is None and sec >= 5:
                        first_sec = sec
                    vocal_lines.append(txt)
                    
        clean_full = clean_text(" ".join(vocal_lines))
        # 检查是否包含假名
        has_kana = bool(re.search(r'[\u3040-\u309f\u30a0-\u30ff]', raw_text))
        has_hanzi = bool(re.search(r'[\u4e00-\u9fa5]', clean_full))
        is_invalid = has_kana or (not has_hanzi and len(clean_full) > 50) or len(vocal_lines) < 3
        
        return first_sec or 15, clean_full[:150], is_invalid, raw_text
    except Exception:
        return 0, "", True, ""

def whisper_audio(url: str, start_sec: int = 15, duration_sec: int = 25) -> str:
    if not url: return ""
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
        tmp_path = f.name
        
    cmd = [
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", str(duration_sec),
        "-i", url,
        "-ar", "16000", "-ac", "1", "-b:a", "64k",
        tmp_path
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)
    
    if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 1000:
        if os.path.exists(tmp_path): os.unlink(tmp_path)
        return ""
        
    for _ in range(len(GROQ_TOKENS)):
        token = get_token()
        try:
            with open(tmp_path, "rb") as af:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("clip.mp3", af, "audio/mpeg")},
                    data={"model": "whisper-large-v3", "language": "zh"},
                    proxies=PROXIES,
                    timeout=20
                )
            if resp.status_code == 200:
                txt = resp.json().get("text", "")
                if os.path.exists(tmp_path): os.unlink(tmp_path)
                return txt
            elif resp.status_code == 429:
                time.sleep(1)
                continue
        except Exception:
            pass
            
    if os.path.exists(tmp_path): os.unlink(tmp_path)
    return ""

def compute_similarity(t1: str, t2: str) -> float:
    c1 = clean_text(t1)
    c2 = clean_text(t2)
    if not c1 or not c2: return 0.0
    common = 0
    for char in set(c1):
        if char in c2:
            common += 1
    return common / max(len(set(c1)), 1)

def audit_song(song: dict) -> dict:
    title = song.get("title", "")
    album = song.get("album", "")
    audio_url = song.get("path", "")
    lrc_url = song.get("lrc_path", "")
    
    issues = []
    meta = {}
    
    # 1. 音频可访问性与时长探针
    actual_dur = get_audio_duration(audio_url)
    meta["actual_dur"] = actual_dur
    if not actual_dur:
        issues.append("无法获取音频时长或文件无法访问")
        return {"song": song, "issues": issues, "meta": meta, "healthy": False}
        
    # 2. 录音室基准时长比对
    studio_dur, netease_id = get_netease_studio_duration(title)
    meta["studio_dur"] = studio_dur
    meta["netease_id"] = netease_id
    if studio_dur:
        ratio = actual_dur / studio_dur
        meta["duration_ratio"] = round(ratio, 2)
        if ratio > 1.20 and (actual_dur - studio_dur) >= 25:
            issues.append(f"时长偏长（实际 {actual_dur:.0f}s vs 录音室 {studio_dur:.0f}s，疑似 Live / 串烧）")
        elif ratio < 0.75 and (studio_dur - actual_dur) >= 25:
            issues.append(f"时长被截断（实际 {actual_dur:.0f}s vs 录音室 {studio_dur:.0f}s）")
            
    # 3. LRC 歌词解析
    first_vocal, lrc_sample, is_invalid_lrc, raw_lrc = parse_lrc(lrc_url)
    meta["first_vocal_sec"] = first_vocal
    meta["lrc_sample"] = lrc_sample[:100]
    if is_invalid_lrc:
        issues.append("LRC 缺失、无效或包含纯外文错配")
        
    # 4. 关键：歌名词根与歌词反向对齐（防御《棋子》播成《天空》的“双向李鬼对撞”）
    clean_target_title = clean_text(title)
    # 剔除副歌名括号部分，例如 "天空(Unplugged)" -> "天空"
    core_title = re.sub(r'[\(（].*?[\)）]', '', title).strip()
    clean_core = clean_text(core_title)
    
    # 如果歌词不是空，检查歌名词根是否在歌词文本或元数据中出现
    if raw_lrc and len(clean_core) >= 2:
        clean_raw_lrc = clean_text(raw_lrc)
        # 如果歌名词根压根不在歌词里
        if clean_core not in clean_raw_lrc:
            # 进一步检测是否错配成了其他王菲知名大歌（如把棋子配成天空）
            if "天空" in clean_raw_lrc and clean_core != "天空":
                issues.append(f"歌词与曲名严重错配 (曲名《{title}》，歌词实际为《天空》)")
            else:
                # 只有当歌词行数较多时才判定，避免极短口白误报
                if len(clean_raw_lrc) > 100:
                    issues.append(f"歌词内容中未找到曲名核心词《{core_title}》，疑似张冠李戴")
                    
    # 5. Whisper 盲听语义核查
    whisper_text = whisper_audio(audio_url, start_sec=first_vocal, duration_sec=25)
    meta["whisper_vocal"] = whisper_text[:120]
    
    if whisper_text:
        # 检测水印
        watermarks = ["请不吝点赞", "订阅", "字幕志愿者", "独播剧场", "明镜与点点", "杨茜茜"]
        for wm in watermarks:
            if wm in whisper_text:
                issues.append(f"音频中含有平台/搬运水印: '{wm}'")
                
        # 盲听语义比对
        if lrc_sample:
            sim = compute_similarity(whisper_text, lrc_sample)
            meta["semantic_sim"] = round(sim, 2)
            if sim < 0.20:
                issues.append(f"音频与歌词严重不符 (重合度仅 {sim*100:.0f}%, 音频实际转录: '{whisper_text[:40]}...')")
                
        # 检查盲听人声是否包含错误歌名（如《棋子》听到《天空》）
        if clean_core not in clean_text(whisper_text) and "天空" in whisper_text and clean_core != "天空":
            issues.append(f"声学实锤张冠李戴: 曲目为《{title}》，但音频实际演唱为《天空》")
            
    healthy = (len(issues) == 0)
    return {
        "song": song,
        "healthy": healthy,
        "issues": issues,
        "meta": meta
    }

def main():
    with open("/tmp/faye_wong_online_songs.json") as f:
        songs = json.load(f)
        
    print(f"==================================================")
    print(f" 王菲全盘立体化审计流水线 (Stage 1)")
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
                    if done % 20 == 0:
                        print(f"✅ [{done}/{len(songs)}] 健康曲目推进中...")
            except Exception as e:
                print(f"⚠️ [{done}/{len(songs)}] 审计异常: {e}")
                
            # 每 10 首歌落盘一次进度
            if done % 10 == 0:
                with open(PROGRESS_PATH, "w", encoding="utf-8") as pf:
                    json.dump({"done": done, "total": len(songs), "suspects_count": len(suspects)}, pf)
                    
    # 保存第一阶段全量报告
    final_report = {
        "scan_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(songs),
        "healthy_count": len(songs) - len(suspects),
        "suspects_count": len(suspects),
        "suspects": suspects
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)
        
    print("\n" + "="*50)
    print(f"王菲 Stage 1 审计完成！")
    print(f"总计扫描: {len(songs)} 首 | 发现嫌疑异常: {len(suspects)} 首")
    print(f"报告已保存至: {OUTPUT_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
