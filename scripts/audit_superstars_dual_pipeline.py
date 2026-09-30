#!/usr/bin/env python3
"""
核心华语歌手全盘大碟立体化双轨正交审计流水线 (audit_superstars_dual_pipeline.py)
=============================================================================
支持对指定核心华语歌手（周杰伦、孙燕姿、陈奕迅、林俊杰、张学友等）实施严格的双轨正交闭环审计：
- Stage 1 (初筛探针):
  1. 音频实际流探针 (ffprobe 获取 actual_dur)
  2. 权威录音室元数据拉取 (Kugou/Netease/Kuwo 多源融合获取 studio_dur 与 official_lrc)
  3. 录音室基准时长比对 (抓 Live 现场加长版与截断)
  4. 歌词有效性与标题核心语义初步探测 (防双向李鬼)
  5. 首句时间戳锚定 + Whisper 声学盲听转录与搬运水印检测
- Stage 2 (独立正交交叉反向证伪，严防误杀):
  1. 对线上歌词与官方录音室正版歌词进行两两比对
  2. 若歌词与官方吻合 (>= 70%) 且时长正常且无水印 -> 坚决平反为假阳性 (杜绝误杀正常艺术表达)
  3. 实锤问题精准归类 (REPLACE_AUDIO_MASTER, REPLACE_LYRIC_ONLY, REPLACE_AUDIO_AND_LYRIC)

输出：reports/AUDIT_{artist}_DUAL_PIPELINE.json
"""

import os, sys, json, time, re, subprocess, tempfile, threading, argparse, base64
import concurrent.futures
import requests, zhconv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

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
    t = re.sub(r'[\(（\[【].*?[\)）\]】]', '', t)
    t = re.sub(r'[^\w\u4e00-\u9fa5]', '', t)
    return t.lower()

def compute_similarity(t1: str, t2: str) -> float:
    c1 = clean_text(t1)
    c2 = clean_text(t2)
    if not c1 or not c2: return 0.0
    s1, s2 = set(c1), set(c2)
    inter = len(s1.intersection(s2))
    union = len(s1.union(s2))
    return inter / max(union, 1)

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
        has_kana = bool(re.search(r'[\u3040-\u309f\u30a0-\u30ff]', raw_text))
        has_hanzi = bool(re.search(r'[\u4e00-\u9fa5]', clean_full))
        is_invalid = has_kana or (not has_hanzi and len(clean_full) > 50) or len(vocal_lines) < 3
        
        return first_sec or 15, clean_full[:150], is_invalid, raw_text
    except Exception:
        return 0, "", True, ""

def get_official_studio_meta(artist: str, title: str) -> dict:
    """多源融合获取权威录音室大碟的基准时长与正版歌词 (Kugou -> Netease -> Kuwo)"""
    clean_target = clean_text(title)
    q = f"{artist} {title}"
    
    # 1. 酷狗源 (涵盖周杰伦等华语全量大碟)
    try:
        url = f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={requests.utils.quote(q)}&page=1&pagesize=5"
        r = requests.get(url, timeout=6).json()
        songs = r.get("data", {}).get("info", [])
        for s in songs:
            sname = s.get("songname", "")
            clean_sn = clean_text(sname)
            s_art = s.get("singername", "")
            dur = s.get("duration", 0)
            h = s.get("hash", "")
            is_live = any(kw in sname.lower() for kw in ["live", "演唱会", "concert", "伴奏", "片段"])
            if (clean_target in clean_sn or clean_sn in clean_target) and clean_text(artist) in clean_text(s_art) and not is_live and dur > 15:
                # 获取官方 LRC
                lrc_text = ""
                try:
                    lr_search = f"http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword={requests.utils.quote(q)}&duration={dur*1000}&hash={h}"
                    cd = requests.get(lr_search, timeout=5).json().get("candidates", [])
                    if cd:
                        cid, akey = cd[0].get("id"), cd[0].get("accesskey")
                        dl = requests.get(f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cid}&accesskey={akey}&fmt=lrc&charset=utf8", timeout=5).json()
                        if dl.get("content"):
                            lrc_text = base64.b64decode(dl["content"]).decode("utf-8")
                except:
                    pass
                return {
                    "source": "kugou",
                    "duration": float(dur),
                    "songname": sname,
                    "artist": s_art,
                    "lrc": lrc_text
                }
    except Exception:
        pass
        
    # 2. 网易云源 (王菲、陈奕迅、孙燕姿等)
    try:
        r = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": q, "type": 1, "limit": 6},
            headers={"User-Agent": "Mozilla/5.0"},
            proxies=PROXIES, timeout=8
        )
        songs = r.json().get("result", {}).get("songs", [])
        for s in songs:
            clean_sname = clean_text(s.get("name", ""))
            sartists = [a["name"] for a in s.get("ar", [])]
            album = s.get("al", {}).get("name", "")
            dt_s = s.get("dt", 0) / 1000.0
            is_live = any(kw in album.lower() or kw in s.get("name", "").lower() for kw in ["live", "演唱会", "concert"])
            artist_ok = any(clean_text(artist) in clean_text(a) for a in sartists)
            if (clean_target in clean_sname or clean_sname in clean_target) and artist_ok and not is_live and dt_s > 15:
                # 获取歌词
                lr = requests.get(
                    f"https://music.163.com/api/song/lyric?os=pc&id={s['id']}&lv=-1&kv=-1&tv=-1",
                    headers={"User-Agent": "Mozilla/5.0"}, proxies=PROXIES, timeout=8
                )
                lrc_txt = lr.json().get("lrc", {}).get("lyric", "")
                return {
                    "source": "netease",
                    "duration": dt_s,
                    "songname": s.get("name"),
                    "artist": artist,
                    "album": album,
                    "lrc": lrc_txt
                }
    except Exception:
        pass

    # 3. 酷我源
    try:
        url = f"http://search.kuwo.cn/r.s?client=kt&all={requests.utils.quote(q)}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=5"
        r = requests.get(url, timeout=8)
        raw = r.text.replace("\x27", "\"")
        data = json.loads(raw)
        for s in data.get("abslist", []):
            clean_sn = clean_text(s.get("SONGNAME", ""))
            s_art = s.get("ARTIST", "")
            dur = float(s.get("DURATION", 0))
            is_live = any(kw in s.get("SONGNAME", "").lower() for kw in ["live", "演唱会", "伴奏"])
            if (clean_target in clean_sn or clean_sn in clean_target) and clean_text(artist) in clean_text(s_art) and not is_live and dur > 15:
                return {
                    "source": "kuwo",
                    "duration": dur,
                    "songname": s.get("SONGNAME"),
                    "artist": s_art,
                    "album": s.get("ALBUM"),
                    "lrc": ""
                }
    except Exception:
        pass

    return {}

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

def audit_song_stage1(artist: str, song: dict) -> dict:
    title = song.get("title", "")
    album = song.get("album", "")
    audio_url = song.get("path", "")
    lrc_url = song.get("lrc_path", "")
    
    issues = []
    meta = {}
    
    # 1. 实际音频时长获取
    actual_dur = get_audio_duration(audio_url)
    meta["actual_dur"] = actual_dur
    if not actual_dur:
        issues.append("无法获取音频时长或文件无法访问")
        return {"song": song, "issues": issues, "meta": meta, "healthy": False}
        
    # 2. 权威录音室元数据拉取
    official_meta = get_official_studio_meta(artist, title)
    meta["official_meta"] = official_meta
    studio_dur = official_meta.get("duration")
    if studio_dur:
        ratio = actual_dur / studio_dur
        meta["duration_ratio"] = round(ratio, 2)
        meta["studio_dur"] = studio_dur
        if ratio > 1.15 and (actual_dur - studio_dur) >= 20:
            issues.append(f"时长偏长（实际 {actual_dur:.0f}s vs 录音室 {studio_dur:.0f}s，疑似 Live / 冗余）")
        elif ratio < 0.85 and (studio_dur - actual_dur) >= 20:
            issues.append(f"时长被截断（实际 {actual_dur:.0f}s vs 录音室 {studio_dur:.0f}s）")
            
    # 3. 线上歌词解析
    first_vocal, lrc_sample, is_invalid_lrc, raw_lrc = parse_lrc(lrc_url)
    meta["first_vocal_sec"] = first_vocal
    meta["lrc_sample"] = lrc_sample[:100]
    meta["online_lrc_raw"] = raw_lrc
    if is_invalid_lrc:
        issues.append("线上 LRC 缺失、无效或包含纯外文错配")
        
    # 4. 歌名词根初探 (初筛嫌疑，待 Stage 2 反向证伪)
    clean_target_title = clean_text(title)
    if raw_lrc and len(clean_target_title) >= 2:
        clean_raw_lrc = clean_text(raw_lrc)
        if clean_target_title not in clean_raw_lrc and len(clean_raw_lrc) > 100:
            issues.append(f"歌词正文中未找到曲名核心词《{title}》（初筛嫌疑）")
            
    # 5. Whisper 盲听语义与水印探针
    whisper_text = whisper_audio(audio_url, start_sec=first_vocal, duration_sec=25)
    meta["whisper_vocal"] = whisper_text[:120]
    
    if whisper_text:
        watermarks = ["请不吝点赞", "订阅", "字幕志愿者", "独播剧场", "明镜与点点", "杨茜茜", "关注微信", "公众号"]
        for wm in watermarks:
            if wm in whisper_text:
                issues.append(f"音频中含有平台/搬运水印: '{wm}'")
                
        if lrc_sample:
            sim = compute_similarity(whisper_text, lrc_sample)
            meta["semantic_sim"] = round(sim, 2)
            if sim < 0.20:
                issues.append(f"音频声学与歌词初步匹配偏低 (转录: '{whisper_text[:30]}...')")
                
    healthy = (len(issues) == 0)
    return {
        "song": song,
        "healthy": healthy,
        "issues": issues,
        "meta": meta
    }

def verify_suspect_stage2(artist: str, item: dict) -> dict:
    """Stage 2: 独立正交交叉反向证伪与严谨确诊，杜绝误杀"""
    s = item["song"]
    title = s.get("title", "")
    album = s.get("album", "")
    stage1_issues = item["issues"]
    meta = item.get("meta", {})
    actual_dur = meta.get("actual_dur")
    online_lrc_raw = meta.get("online_lrc_raw", "")
    whisper_vocal = meta.get("whisper_vocal", "")
    
    official_meta = meta.get("official_meta") or get_official_studio_meta(artist, title)
    studio_dur = official_meta.get("duration")
    official_lrc = official_meta.get("lrc", "")
    
    cross_result = {
        "song": s,
        "stage1_issues": stage1_issues,
        "is_false_positive": False,
        "confirmed_issues": [],
        "remediation_category": None,
        "details": {
            "actual_dur": actual_dur,
            "studio_dur": studio_dur,
            "source": official_meta.get("source")
        }
    }
    
    # 1. 维度 A: 线上歌词 vs 官方录音室歌词
    lrc_sim = 0.0
    if online_lrc_raw and official_lrc:
        lrc_sim = compute_similarity(online_lrc_raw, official_lrc)
        cross_result["details"]["lrc_official_similarity"] = round(lrc_sim, 2)
        
    # 2. 维度 B: 时长吻合度判断
    duration_match = False
    duration_live = False
    duration_truncated = False
    if actual_dur and studio_dur:
        dur_diff = abs(actual_dur - studio_dur)
        ratio = actual_dur / studio_dur
        if dur_diff <= 12 or (0.95 <= ratio <= 1.05):
            duration_match = True
        elif ratio > 1.15 and (actual_dur - studio_dur) >= 20:
            duration_live = True
        elif ratio < 0.85 and (studio_dur - actual_dur) >= 20:
            duration_truncated = True

    # 3. 维度 C: 水印实锤
    watermark_issues = [iss for iss in stage1_issues if "水印" in iss]
    
    # === 正交判定逻辑 ===
    # 判定 1: 成功平反假阳性 (杜绝误杀)
    # 条件：歌词与官方高度一致 (>= 70%)，时长吻合录音室原版，且无水印
    if lrc_sim >= 0.70 and duration_match and not watermark_issues:
        cross_result["is_false_positive"] = True
        cross_result["confirmed_issues"] = []
        cross_result["remediation_category"] = "CLEAN_FALSE_POSITIVE"
        cross_result["details"]["verdict"] = "歌词与官方正版一致且时长吻合，Whisper偏低系伴奏/快歌假阳性，成功平反"
        return cross_result
        
    # 判定 2: 仅音频问题 (REPLACE_AUDIO_MASTER)
    # 歌词正常，但时长为 Live 版或被截断，或含有口播水印
    if (lrc_sim >= 0.70 or "线上 LRC 缺失" not in str(stage1_issues)) and (duration_live or duration_truncated or watermark_issues):
        if duration_live:
            cross_result["confirmed_issues"].append(f"音频为现场Live版/过长 (实际 {actual_dur:.0f}s vs 录音室 {studio_dur:.0f}s)")
        if duration_truncated:
            cross_result["confirmed_issues"].append(f"音频被严重截断 (实际 {actual_dur:.0f}s vs 录音室 {studio_dur:.0f}s)")
        if watermark_issues:
            cross_result["confirmed_issues"].extend(watermark_issues)
        cross_result["remediation_category"] = "REPLACE_AUDIO_MASTER"
        return cross_result

    # 判定 3: 仅歌词问题 (REPLACE_LYRIC_ONLY)
    # 音频时长吻合录音室，但歌词缺失、乱码或与官方正版严重对不上
    if duration_match and not watermark_issues and (lrc_sim < 0.35 or not online_lrc_raw):
        # 进一步核验：Whisper 识别的内容是否在官方歌词中命中？
        if whisper_vocal and official_lrc and compute_similarity(whisper_vocal, official_lrc) >= 0.20:
            cross_result["confirmed_issues"].append("音频正确吻合录音室，但线上歌词缺失或为错配李鬼歌词")
            cross_result["remediation_category"] = "REPLACE_LYRIC_ONLY"
            return cross_result
        else:
            # 可能是李鬼歌词
            cross_result["confirmed_issues"].append("线上歌词与官方正版严重不符")
            cross_result["remediation_category"] = "REPLACE_LYRIC_ONLY"
            return cross_result

    # 判定 4: 双向错配全错 (REPLACE_AUDIO_AND_LYRIC)
    # 歌词错且音频也错（如播了另一首歌）
    cross_result["confirmed_issues"].extend(stage1_issues)
    cross_result["remediation_category"] = "REPLACE_AUDIO_AND_LYRIC"
    return cross_result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist", type=str, default="周杰伦", help="歌手名称")
    args = parser.parse_args()
    artist = args.artist
    
    print(f"==================================================")
    print(f" 核心华语歌手全盘大碟立体化双轨正交审计流水线")
    print(f" 目标歌手: {artist}")
    print(f"==================================================")
    
    # 1. 获取该歌手全盘歌曲
    r = requests.get(f"https://m-api.changgepd.ccwu.cc/api/songs?artist={artist}", headers={"User-Agent": "Mozilla/5.0"}, proxies=PROXIES, timeout=15)
    data = r.json()
    if not data.get("data") or len(data["data"]) == 0:
        print(f"❌ 未找到歌手: {artist}")
        return
        
    art = data["data"][0]
    albums = art["albums"]
    all_songs = []
    for alb in albums:
        for s in alb["songs"]:
            # 从 path 提取 song_id
            full_p = (s.get("path") or "") + (s.get("lrc_path") or "")
            m = re.search(r"s_(\d+)\.(mp3|lrc|flac)", full_p)
            sid = int(m.group(1)) if m else None
            all_songs.append({
                "id": sid,
                "album": alb["title"],
                "title": s["title"],
                "path": s.get("path"),
                "lrc_path": s.get("lrc_path"),
                "track_index": s.get("TrackIndex")
            })
            
    print(f"大碟数: {len(albums)} 张 | 待测曲目: {len(all_songs)} 首\n")
    
    # --- STAGE 1: 全量初筛 ---
    print(">>> 启动 STAGE 1: 全量初筛审计 (时长探针 + 声学盲听 + 权威元数据比对)...")
    stage1_suspects = []
    done1 = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(audit_song_stage1, artist, s): s for s in all_songs}
        for f in concurrent.futures.as_completed(futs):
            done1 += 1
            try:
                res = f.result(timeout=60)
                if not res["healthy"]:
                    stage1_suspects.append(res)
                    print(f"  🚨 [{done1}/{len(all_songs)}] 初筛嫌疑: 《{res['song']['title']}》[{res['song']['album']}] -> {res['issues']}")
                else:
                    if done1 % 20 == 0:
                        print(f"  ✅ [{done1}/{len(all_songs)}] 初筛平稳推进中...")
            except Exception as e:
                print(f"  ⚠️ 初筛异常: {e}")
                
    print(f"\nStage 1 初筛完成: 扫描 {len(all_songs)} 首，发现嫌疑 {len(stage1_suspects)} 首")
    
    # --- STAGE 2: 独立正交交叉反向证伪 ---
    print("\n>>> 启动 STAGE 2: 独立正交交叉反向证伪 (官方歌词与时长对齐，杜绝误杀)...")
    false_positives = []
    real_problems = []
    done2 = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(verify_suspect_stage2, artist, s): s for s in stage1_suspects}
        for f in concurrent.futures.as_completed(futs):
            done2 += 1
            try:
                res = f.result(timeout=60)
                s = res["song"]
                if res["is_false_positive"]:
                    false_positives.append(res)
                    print(f"  🟢 [{done2}/{len(stage1_suspects)}] 平反假阳性: 《{s['title']}》[{s['album']}] ({res['details'].get('verdict')})")
                else:
                    real_problems.append(res)
                    print(f"  🚨 [{done2}/{len(stage1_suspects)}] 实锤真问题 [{res['remediation_category']}]: 《{s['title']}》[{s['album']}] -> {res['confirmed_issues']}")
            except Exception as e:
                print(f"  ⚠️ 复核异常: {e}")
                
    final_output = {
        "artist": artist,
        "scan_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_songs": len(all_songs),
        "total_albums": len(albums),
        "stage1_suspects_count": len(stage1_suspects),
        "false_positives_count": len(false_positives),
        "real_problems_count": len(real_problems),
        "false_positives": false_positives,
        "real_problems": real_problems
    }
    
    report_file = REPORTS_DIR / f"AUDIT_{artist}_DUAL_PIPELINE.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
        
    print("\n" + "="*50)
    print(f"【{artist}】双轨正交审计全流程闭环！")
    print(f"全盘曲目: {len(all_songs)} 首")
    print(f"初筛嫌疑: {len(stage1_suspects)} 首")
    print(f"成功平反假阳性: {len(false_positives)} 首 (杜绝误杀)")
    print(f"确诊实锤真问题: {len(real_problems)} 首")
    print(f"报告已保存至: {report_file}")
    print("="*50)

if __name__ == "__main__":
    main()
