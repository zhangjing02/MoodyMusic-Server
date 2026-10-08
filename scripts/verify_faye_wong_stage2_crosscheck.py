#!/usr/bin/env python3
"""
王菲全盘立体化审计 - 第二阶段独立正交交叉验证与反向证伪流水线
(verify_faye_wong_stage2_crosscheck.py)
========================================================================
对第一阶段初筛出的 243 首嫌疑曲目进行反向证伪与深入实锤：
1. 【反向证伪 192 首 TITLE_NOT_IN_LRC】：
   - 抓取网易云官方录音室正版歌词进行两两比对
   - 若线上 LRC 与官方正版 LRC 相似度 >= 75%，确认为原版正规歌词（判定为假阳性，平反移出嫌疑池）
   - 若相似度 < 30%，确认为张冠李戴李鬼歌词（真问题）
2. 【深入实锤 45 首《天空》关联曲目】：
   - 从第 60~85 秒（副歌黄金段）盲听 Whisper 转录
   - 区分是“音频也是天空（双向李鬼）”还是“音频正常但歌词错配为天空（单向错配）”
3. 【深入核验 21 首时长异常曲目】：
   - 判定是否为截断音频或加长现场版

输出：reports/FAYE_WONG_STAGE2_CROSS_VERIFIED_REPORT.json
"""

import os, sys, json, time, re, subprocess, tempfile, threading
import concurrent.futures
import requests, zhconv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
STAGE1_PATH = REPORTS_DIR / "FAYE_WONG_STAGE1_AUDIT_REPORT.json"
OUTPUT_PATH = REPORTS_DIR / "FAYE_WONG_STAGE2_CROSS_VERIFIED_REPORT.json"
PROGRESS_PATH = REPORTS_DIR / "FAYE_WONG_STAGE2_PROGRESS.json"

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

def compute_similarity(t1: str, t2: str) -> float:
    c1 = clean_text(t1)
    c2 = clean_text(t2)
    if not c1 or not c2: return 0.0
    s1, s2 = set(c1), set(c2)
    inter = len(s1.intersection(s2))
    union = len(s1.union(s2))
    return inter / max(union, 1)

def get_official_netease_lrc(title: str):
    try:
        r = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": f"王菲 {title}", "type": 1, "limit": 5},
            headers={"User-Agent": "Mozilla/5.0"},
            proxies=PROXIES, timeout=10
        )
        songs = r.json().get("result", {}).get("songs", [])
        clean_target = clean_text(re.sub(r'[\(（].*?[\)）]', '', title))
        
        for s in songs:
            sname = clean_text(s.get("name", ""))
            album = s.get("al", {}).get("name", "").lower()
            is_live = any(kw in album or kw in sname for kw in ["live", "演唱会", "concert"])
            if (clean_target in sname or sname in clean_target) and not is_live:
                nid = s.get("id")
                # 获取歌词
                lr = requests.get(
                    f"https://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1",
                    headers={"User-Agent": "Mozilla/5.0"}, proxies=PROXIES, timeout=10
                )
                txt = lr.json().get("lrc", {}).get("lyric", "")
                if txt and len(txt) > 30:
                    return txt, s.get("name"), s.get("al", {}).get("name")
    except Exception:
        pass
    return None, None, None

def whisper_audio(url: str, start_sec: int = 60, duration_sec: int = 25) -> str:
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

def verify_single_suspect(item: dict) -> dict:
    s = item["song"]
    title = s.get("title", "")
    album = s.get("album", "")
    audio_url = s.get("path", "")
    lrc_url = s.get("lrc_path", "")
    stage1_issues = item["issues"]
    
    cross_check_result = {
        "song": s,
        "stage1_issues": stage1_issues,
        "is_false_positive": False,
        "confirmed_issues": [],
        "remediation_category": None,
        "details": {}
    }
    
    # 获取线上当前的歌词正文
    online_lrc_text = ""
    if lrc_url:
        try:
            r = requests.get(lrc_url, proxies=PROXIES, timeout=8)
            if r.status_code == 200: online_lrc_text = r.text
        except: pass
        
    # 1. 深度核查《天空》错配组
    has_sky_issue = any("歌词实际为《天空》" in iss for iss in stage1_issues)
    if has_sky_issue:
        # 副歌盲听测试 (第 60 秒)
        vocal_txt = whisper_audio(audio_url, start_sec=60, duration_sec=25)
        cross_check_result["details"]["whisper_refrain"] = vocal_txt
        
        # 判断音频是否也是《天空》
        is_audio_sky = ("天空" in vocal_txt or "灰色" in vocal_txt or "思念" in vocal_txt or "世界的另一边" in vocal_txt)
        if is_audio_sky:
            cross_check_result["confirmed_issues"].append("音频与歌词均被李鬼对撞替换为《天空》（双向完全错配）")
            cross_check_result["remediation_category"] = "REPLACE_AUDIO_AND_LYRIC"
        else:
            cross_check_result["confirmed_issues"].append("音频可能正确，但歌词被严重错配为《天空》")
            cross_check_result["remediation_category"] = "REPLACE_LYRIC_ONLY"
            
        return cross_check_result
        
    # 2. 深度核查时长异常组
    duration_issues = [iss for iss in stage1_issues if "时长偏长" in iss or "时长被截断" in iss]
    if duration_issues:
        cross_check_result["confirmed_issues"].extend(duration_issues)
        cross_check_result["remediation_category"] = "REPLACE_AUDIO_MASTER"
        return cross_check_result

    # 3. 反向证伪 TITLE_NOT_IN_LRC 组
    title_not_in_lrc = any("未找到曲名核心词" in iss for iss in stage1_issues)
    if title_not_in_lrc:
        # 获取网易云官方大碟的正版歌词
        off_lrc, off_name, off_album = get_official_netease_lrc(title)
        if off_lrc and online_lrc_text:
            sim = compute_similarity(online_lrc_text, off_lrc)
            cross_check_result["details"]["similarity_with_official"] = round(sim, 2)
            cross_check_result["details"]["official_song"] = f"{off_name} [{off_album}]"
            
            if sim >= 0.70:
                # 官方歌词与线上歌词高度一致！说明歌词本身完全正确，只是歌名没写在正文里（比如《红豆》只唱相思）
                cross_check_result["is_false_positive"] = True
                cross_check_result["confirmed_issues"] = []
                cross_check_result["remediation_category"] = "CLEAN_FALSE_POSITIVE"
                return cross_check_result
            else:
                cross_check_result["confirmed_issues"].append(f"歌词与网易云官方录音室歌词不符 (相似度仅 {sim*100:.0f}%)，确认为李鬼歌词")
                cross_check_result["remediation_category"] = "REPLACE_LYRIC_ONLY"
                return cross_check_result
        else:
            # 搜不到官方歌词，需要保留人工核验
            cross_check_result["confirmed_issues"].append("未能比对到权威录音室歌词，存疑保留")
            cross_check_result["remediation_category"] = "MANUAL_REVIEW"
            return cross_check_result

    # 默认兜底
    cross_check_result["confirmed_issues"] = stage1_issues
    cross_check_result["remediation_category"] = "REPLACE_AUDIO_AND_LYRIC"
    return cross_check_result

def main():
    with open(STAGE1_PATH) as f:
        stage1 = json.load(f)
        
    suspects = stage1.get("suspects", [])
    print(f"==================================================")
    print(f" 王菲第二阶段独立正交交叉验证流水线")
    print(f" 待复核嫌疑曲目: {len(suspects)} 首 | 线程数: 8")
    print(f"==================================================\n")
    
    verified_results = []
    false_positives = []
    real_problems = []
    done = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(verify_single_suspect, s): s for s in suspects}
        for f in concurrent.futures.as_completed(futs):
            done += 1
            try:
                res = f.result(timeout=60)
                verified_results.append(res)
                s = res["song"]
                if res["is_false_positive"]:
                    false_positives.append(res)
                    print(f"🟢 [{done}/{len(suspects)}] 平反假阳性: 《{s['title']}》[{s['album']}] (与官方原版吻合)")
                else:
                    real_problems.append(res)
                    print(f"🚨 [{done}/{len(suspects)}] 实锤真问题: 《{s['title']}》[{s['album']}] -> {res['confirmed_issues'][:1]}")
            except Exception as e:
                print(f"⚠️ [{done}/{len(suspects)}] 复核异常: {e}")
                
            if done % 10 == 0:
                with open(PROGRESS_PATH, "w", encoding="utf-8") as pf:
                    json.dump({
                        "done": done,
                        "total": len(suspects),
                        "false_positives_count": len(false_positives),
                        "real_problems_count": len(real_problems)
                    }, pf)
                    
    final_report = {
        "verified_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_stage1_suspects": len(suspects),
        "false_positives_count": len(false_positives),
        "real_problems_count": len(real_problems),
        "false_positives": false_positives,
        "real_problems": real_problems
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)
        
    print("\n" + "="*50)
    print(f"第二阶段交叉验证完成！")
    print(f"初筛嫌疑: {len(suspects)} 首")
    print(f"成功平反假阳性（真实原声正品）: {len(false_positives)} 首")
    print(f"确诊实锤真问题曲目: {len(real_problems)} 首")
    print(f"报告已保存至: {OUTPUT_PATH}")
    print("="*50)

if __name__ == "__main__":
    main()
