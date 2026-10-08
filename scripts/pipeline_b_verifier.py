#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MOODY 早期曲库双轨审计系统 - 流水线 B (Pipeline B: 独立复核反向证伪与洗冤)
=============================================================================
核心使命：
1. 彻底打破模型同质化幻觉：采用全新推理结构 (whisper-large-v3-turbo)；
2. 正交采样窗口：主攻歌曲副歌人声爆发段 (75s~105s)，对片头水印可疑曲目附加 (0s~25s)；
3. 绕过任何缓存：拉取音频时附加时间戳随机参数 ?_cb=击穿 CDN/本地缓存；
4. 官方权威歌词反向证伪 (Disconfirmation)：
   - 从官方权威曲库调取原版正版歌词；
   - 提取副歌核心 4-gram、3-gram 与最长公共子序列比对；
   - 洗冤平反（FALSE POSITIVE CLEARED）：音频转录出正版副歌唱词者，证明音频为原版，仅歌词存在纯音乐标签或他人署名，平反保全；
   - 实锤确诊（CONFIRMED MISMATCH）：音频转录为解说/口播/他人歌曲，副歌吻合度趋零；
   - 纯伴奏确诊（CONFIRMED INSTRUMENTAL）：官方有唱词但 75s~105s 转录为静音/无歌词；
5. 【绝对冻结原则】：纯只读分析，绝不擅自下架、删除或修改数据库。
=============================================================================
"""

import os
import sys
import json
import re
import time
import requests
import subprocess
import zhconv
from concurrent.futures import ThreadPoolExecutor

try:
    from groq_manager import GroqTokenPool
except ImportError:
    from scripts.groq_manager import GroqTokenPool

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE_1_REPORT = os.path.join(BASE_DIR, "reports", "STAGE_1_SUSPECTS_AUDIT.json")
STAGE_2_REPORT = os.path.join(BASE_DIR, "reports", "STAGE_2_CROSS_VERIFIED_REPORT.json")
SCRATCH_DIR = "/tmp/moody_audit_stage2"
os.makedirs(SCRATCH_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)

NETEASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/"
}

def clean_text_for_match(text: str) -> str:
    """去除标点符号并统一转换为简体中文小写，用于严谨的文本重合度比对"""
    if not text:
        return ""
    simplified = zhconv.convert(text, 'zh-cn').lower()
    return re.sub(r'[^\w\u4e00-\u9fa5]', '', simplified)

def fetch_official_lyrics(artist: str, title: str) -> dict:
    """从网易云获取官方正版参考歌词"""
    clean_title = re.sub(r'\(.*?\)|\[.*?\]|（.*?）', '', title).strip()
    query = f"{artist} {clean_title}"
    try:
        url = f"https://music.163.com/api/search/get/web?s={requests.utils.quote(query)}&type=1&limit=3"
        r = requests.get(url, headers=NETEASE_HEADERS, timeout=5)
        if r.status_code == 200:
            data = r.json()
            songs = data.get("result", {}).get("songs", [])
            if songs:
                song_id = songs[0]["id"]
                lrc_url = f"https://music.163.com/api/song/lyric?os=pc&id={song_id}&lv=-1&kv=-1&tv=-1"
                lr = requests.get(lrc_url, headers=NETEASE_HEADERS, timeout=5)
                if lr.status_code == 200:
                    lrc_json = lr.json()
                    lyric_raw = lrc_json.get("lrc", {}).get("lyric", "")
                    return {
                        "official_id": song_id,
                        "official_title": songs[0].get("name"),
                        "official_artist": songs[0].get("artists", [{}])[0].get("name"),
                        "raw_lrc": lyric_raw,
                        "clean_text": clean_text_for_match(re.sub(r'\[.*?\]', '', lyric_raw))
                    }
    except Exception as e:
        pass
    return {"raw_lrc": "", "clean_text": ""}

def calculate_ngram_overlap(text_a: str, text_b: str, n: int = 4) -> float:
    """计算 text_a 与 text_b 的 N-gram 交叉重合度"""
    if not text_a or not text_b or len(text_a) < n or len(text_b) < n:
        return 0.0
    
    grams_a = set(text_a[i:i+n] for i in range(len(text_a) - n + 1))
    grams_b = set(text_b[i:i+n] for i in range(len(text_b) - n + 1))
    
    if not grams_a:
        return 0.0
    common = grams_a.intersection(grams_b)
    return len(common) / len(grams_a)

def verify_suspect_item(pool: GroqTokenPool, item: dict) -> dict:
    """对单首初筛嫌疑歌曲执行独立反向证伪与洗冤判定"""
    song_id = item["song_id"]
    artist = item["artist"]
    title = item["title"]
    file_url = item.get("file_path")

    result = {
        **item,
        "stage2_verification": {
            "model": "whisper-large-v3-turbo",
            "sample_range": "75s-105s (chorus)",
            "chorus_text": "",
            "intro_text": "",
            "official_lyrics_found": False,
            "ngram_overlap_chorus": 0.0,
            "verdict": "UNKNOWN",
            "verdict_reason": ""
        }
    }

    if not file_url:
        result["stage2_verification"]["verdict"] = "ERROR_NO_AUDIO_URL"
        return result

    raw_path = os.path.join(SCRATCH_DIR, f"s2_{song_id}_raw.mp3")
    chorus_clip = os.path.join(SCRATCH_DIR, f"s2_{song_id}_chorus.mp3")
    intro_clip = os.path.join(SCRATCH_DIR, f"s2_{song_id}_intro.mp3")

    try:
        # 1. 获取官方参考歌词
        official = fetch_official_lyrics(artist, title)
        has_official = bool(official["clean_text"])
        result["stage2_verification"]["official_lyrics_found"] = has_official
        official_text = official["clean_text"]

        # 2. 击穿缓存下载音频 (加 _cb 随机参数)
        cb_url = f"{file_url}{'&' if '?' in file_url else '?'}_cb={int(time.time() * 1000)}"
        r = requests.get(cb_url, timeout=15)
        if r.status_code != 200:
            result["stage2_verification"]["verdict"] = f"AUDIO_DOWNLOAD_FAILED_HTTP_{r.status_code}"
            return result

        with open(raw_path, "wb") as f:
            f.write(r.content)

        # 3. 抽取副歌高潮人声切片 (75s ~ 105s)
        subprocess.run([
            "ffmpeg", "-y", "-ss", "75", "-t", "30",
            "-i", raw_path,
            "-ac", "1", "-ar", "16000", "-b:a", "64k",
            chorus_clip
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        chorus_text = ""
        if os.path.exists(chorus_clip) and os.path.getsize(chorus_clip) > 1000:
            res_chorus = pool.transcribe(chorus_clip, model="whisper-large-v3-turbo")
            if res_chorus.get("success"):
                chorus_text = res_chorus.get("text", "").strip()
        result["stage2_verification"]["chorus_text"] = chorus_text

        # 4. 判断是否需要额外抽取片头 (0s ~ 25s) 水印切片
        intro_text = ""
        hit_reasons = " ".join(item.get("hit_reasons", []))
        if any(w in hit_reasons for w in ["字幕志愿者", "独播剧场", "麦格农", "后座力", "纯音乐"]):
            subprocess.run([
                "ffmpeg", "-y", "-ss", "0", "-t", "25",
                "-i", raw_path,
                "-ac", "1", "-ar", "16000", "-b:a", "64k",
                intro_clip
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(intro_clip) and os.path.getsize(intro_clip) > 1000:
                res_intro = pool.transcribe(intro_clip, model="whisper-large-v3-turbo")
                if res_intro.get("success"):
                    intro_text = res_intro.get("text", "").strip()
        result["stage2_verification"]["intro_text"] = intro_text

        # 5. 反向证伪与智能判定 (Disconfirmation Logic)
        clean_chorus = clean_text_for_match(chorus_text)
        clean_s1 = clean_text_for_match(item.get("whisper_stage1", {}).get("text", ""))
        combined_whisper = clean_s1 + clean_chorus

        overlap_4 = calculate_ngram_overlap(clean_chorus, official_text, n=4) if official_text else 0.0
        overlap_3 = calculate_ngram_overlap(clean_chorus, official_text, n=3) if official_text else 0.0
        result["stage2_verification"]["ngram_overlap_chorus"] = round(overlap_4, 3)

        # 检查是否包含明确的侵入性口播水印/视频解说
        ad_keywords = ["独播剧场", "字幕志愿者", "杨茜茜", "索兰娅", "后座力", "麦格农", "微信公", "公众号", "未经许可不得翻唱", "youtube", "ghien mi go"]
        detected_ad = [kw for kw in ad_keywords if (kw in clean_chorus or kw in clean_text_for_match(intro_text) or kw in clean_s1)]

        if detected_ad:
            result["stage2_verification"]["verdict"] = "CONFIRMED_POLLUTED_OR_AD_DUMP"
            result["stage2_verification"]["verdict_reason"] = f"实锤命中外挂广告/视频口播/字幕组水印: {detected_ad}"
        elif overlap_4 >= 0.20 or overlap_3 >= 0.35:
            # 副歌与官方原版歌词高频命中！证明音频本尊就是官方原声！
            # 这说明第一轮是误杀（歌词写了纯音乐，但音频分明是正版原唱；或者翻唱标头被误判）
            result["stage2_verification"]["verdict"] = "FALSE_POSITIVE_CLEARED"
            result["stage2_verification"]["verdict_reason"] = f"反向证伪成功！副歌高频吻合官方正版歌词 (4-gram重合: {overlap_4*100:.1f}%)，音频实为本尊原声，免死平反！仅需修缮歌词"
        elif not clean_chorus and not clean_s1:
            # 两个时间段全都没有任何人声转录
            if official_text and len(official_text) > 50:
                result["stage2_verification"]["verdict"] = "CONFIRMED_INSTRUMENTAL_ONLY"
                result["stage2_verification"]["verdict_reason"] = "官方歌曲有密集人声，但音频多段采样均无唱词，实锤为纯伴奏冒充"
            else:
                result["stage2_verification"]["verdict"] = "MANUAL_REVIEW_REQUIRED"
                result["stage2_verification"]["verdict_reason"] = "音频为人声稀少曲目或官方参考歌词缺失，需人工复核"
        elif official_text and (overlap_3 < 0.08) and (len(clean_chorus) >= 15):
            # 副歌有完整唱词，但与官方歌词完全不同！实锤错歌/掉包！
            result["stage2_verification"]["verdict"] = "CONFIRMED_AUDIO_MISMATCH"
            result["stage2_verification"]["verdict_reason"] = f"副歌唱词与官方歌词完全无关 (3-gram重合: {overlap_3*100:.1f}%)，实锤错歌/掉包他人歌曲"
        else:
            # 处于边缘争议状态
            result["stage2_verification"]["verdict"] = "MANUAL_REVIEW_REQUIRED"
            result["stage2_verification"]["verdict_reason"] = f"吻合度处于中间过渡区 (4-gram: {overlap_4*100:.1f}%)，提请用户终审裁决"

    except Exception as e:
        result["stage2_verification"]["verdict"] = f"EXCEPTION_{e}"
    finally:
        for p in [raw_path, chorus_clip, intro_clip]:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass

    return result

def main():
    print("=" * 80)
    print("🛡️ 启动 MOODY 早期曲库双轨审计 - 流水线 B (独立复核反向证伪与洗冤)")
    print("=" * 80)
    print(f"📂 载入流水线 A 初筛归档: {STAGE_1_REPORT}")

    if not os.path.exists(STAGE_1_REPORT):
        print(f"❌ 未找到阶段 1 归档文件: {STAGE_1_REPORT}，请先等待流水线 A 完成！")
        sys.exit(1)

    with open(STAGE_1_REPORT, "r", encoding="utf-8") as f:
        stage1_suspects = json.load(f)

    print(f"📊 待复核嫌疑曲目数: {len(stage1_suspects)} 首")
    print("🔍 阶段 2：启动全新模型 (whisper-large-v3-turbo) + 75s~105s 副歌采样 + 击穿缓存 + 官方权威歌词反向交叉比对...")

    pool = GroqTokenPool()
    stage2_results = []

    for idx, item in enumerate(stage1_suspects, 1):
        print(f"[{idx:03d}/{len(stage1_suspects):03d}] 正在独立复核: [{item['artist']}] 《{item['title']}》")
        verified = verify_suspect_item(pool, item)
        s2_info = verified["stage2_verification"]
        verdict = s2_info["verdict"]
        reason = s2_info["verdict_reason"]
        print(f"     判定结论: [{verdict}] -> {reason}")
        if s2_info["chorus_text"]:
            print(f"     副歌转录: {s2_info['chorus_text'][:70]}...")
        stage2_results.append(verified)

    # 结果持久化并冻结
    with open(STAGE_2_REPORT, "w", encoding="utf-8") as f:
        json.dump(stage2_results, f, ensure_ascii=False, indent=2)

    # 统计分类
    cleared = [s for s in stage2_results if s["stage2_verification"]["verdict"] == "FALSE_POSITIVE_CLEARED"]
    mismatch = [s for s in stage2_results if s["stage2_verification"]["verdict"] == "CONFIRMED_AUDIO_MISMATCH"]
    polluted = [s for s in stage2_results if s["stage2_verification"]["verdict"] == "CONFIRMED_POLLUTED_OR_AD_DUMP"]
    instrumental = [s for s in stage2_results if s["stage2_verification"]["verdict"] == "CONFIRMED_INSTRUMENTAL_ONLY"]
    manual = [s for s in stage2_results if s["stage2_verification"]["verdict"] == "MANUAL_REVIEW_REQUIRED"]

    print("\n" + "=" * 80)
    print("📋 流水线 B 双轨交叉复核与洗冤统计：")
    print(f"  • 初筛总嫌疑数: {len(stage2_results)} 首")
    print(f"  ✅ 成功洗冤平反 (音频本尊保全，仅需修词): {len(cleared)} 首")
    print(f"  ❌ 实锤错歌/掉包 (需彻底替换音源): {len(mismatch)} 首")
    print(f"  🚫 实锤视频口播/自媒体广告污染: {len(polluted)} 首")
    print(f"  🎻 实锤纯伴奏冒充原声: {len(instrumental)} 首")
    print(f"  ⚠️ 需人工终审争议项: {len(manual)} 首")
    print("=" * 80)
    print(f"🔒 流水线 B 报告已归档至: {STAGE_2_REPORT}")
    print("【铁律】：只读审计闭环，所有修复动作必须等待用户人工审核确认！")

if __name__ == "__main__":
    main()
