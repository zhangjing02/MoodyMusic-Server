#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MOODY 早期曲库双轨审计系统 - 流水线 A (Pipeline A: 初筛与异常特征捕获)
=============================================================================
阶段目标：
1. 遍历全盘已点亮 15,090 首歌曲的 LRC 歌词文本进行高并发上下文感知快筛；
2. 规避正文艺术词与版权声明假阳性，锁定“纯音乐占位”、“翻唱标头”、“他人署名”、“自媒体解说”；
3. 对初筛可疑歌曲拉取音频中段 (30s~60s)，调用 Groq Whisper-large-v3 盲听转录；
4. 结果完整沉淀并冻结归档至 reports/STAGE_1_SUSPECTS_AUDIT.json；
5. 【铁律】：只读运行，绝不修改 D1 数据库、不下架、不删除任何 R2 对象。
=============================================================================
"""

import os
import sys
import json
import re
import time
import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

# 导入多 Token 调度池
try:
    from groq_manager import GroqTokenPool, transcribe_audio_text
except ImportError:
    from scripts.groq_manager import GroqTokenPool, transcribe_audio_text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "all_lit_songs.json")
REPORT_PATH = os.path.join(BASE_DIR, "reports", "STAGE_1_SUSPECTS_AUDIT.json")
SCRATCH_DIR = "/tmp/moody_audit_stage1"
os.makedirs(SCRATCH_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)

# 纯正违规特征清单（上下文感知过滤）
STRONG_SUSPECT_PATTERNS = [
    r'纯音乐[，,\s]*请欣赏',
    r'伴奏[，,\s]*请欣赏',
    r'此歌曲为没有填词的纯音乐',
    r'【翻唱】',
    r'原唱信息\s*[:：]',
    r'翻唱信息\s*[:：]',
    r'优优独播剧场',
    r'独播剧场',
    r'字幕志愿者',
    r'字幕组',
    r'微信公众号',
    r'欢迎关注.*微信',
    r'欢迎收听.*电台',
    r'ghièn\s*mì\s*gõ',
    r'hãy\s*subscribe',
    r'zither\s*harp',
    r'piano\s*cover',
    r'麦格农.*子弹',
    r'后座力较大',
]

def resolve_artist(song):
    artist = song.get("artist_name") or song.get("artist")
    if not artist or artist == "None":
        fp = song.get("file_path") or ""
        m = re.search(r'/music/([^/]+)/', fp) or re.search(r'songs/([^/]+)/', fp)
        if m:
            artist = m.group(1)
        else:
            artist = "未知歌手"
    return artist

def is_false_positive_lyric(text: str, line: str, song_title: str) -> bool:
    """过滤正版版权声明与合法语义假阳性"""
    # 1. 版权法务保留声明（合法）
    if '未经著作权人' in line or '未经许可' in line or '不得以任何方式使用' in line or '著作权保留' in line:
        return True
    # 2. 歌名本身就含有该词（如《像一句广告》、《新广告歌》）
    if '广告' in line and ('广告' in song_title or '宣传' in song_title):
        return True
    # 3. 火星电台（著名作词/制作团队）
    if '火星电台' in line:
        return True
    # 4. 正文普通歌词描写（如“伴奏只有那烟味”）
    if '伴奏' in line and ('烟味' in line or '声音' in line or '响起' in line or '旋律' in line or '吉他' in line):
        return True
    return False

def check_single_lrc(song):
    """阶段一：单曲歌词上下文感知审查"""
    lrc_url = song.get("lrc_path")
    if not lrc_url:
        return None

    artist = resolve_artist(song)
    title = song.get("title", "")

    try:
        r = requests.get(lrc_url, timeout=6)
        if r.status_code != 200:
            return None
        text = r.text
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        hit_reasons = []

        # 1. 强特征正则匹配
        for pattern in STRONG_SUSPECT_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # 检查是否为版权保留白名单
                matched_line = ""
                for l in lines:
                    if re.search(pattern, l, re.IGNORECASE):
                        matched_line = l
                        break
                if not is_false_positive_lyric(text, matched_line, title):
                    hit_reasons.append(f"命中异常特征: {matches[0]}")

        # 2. 检查前 10 行元数据中的他人演唱者署名（李鬼歌手掉包）
        header_lines = lines[:12]
        for hl in header_lines:
            # 匹配 [ar:xxx] 或 歌手: xxx 或 演唱: xxx
            ar_match = re.search(r'\[ar\s*:\s*([^\]]+)\]', hl, re.IGNORECASE) or \
                       re.search(r'(?:歌手|演唱|原唱)\s*[:：]\s*([^\s\]/，,]+)', hl)
            if ar_match:
                singer_in_lrc = ar_match.group(1).strip()
                # 忽略通用占位
                if singer_in_lrc in ['华语群星', '群星', 'Various Artists', '未知']:
                    continue
                # 比对歌手名
                norm_artist = re.sub(r'[^\w]', '', artist.lower())
                norm_singer = re.sub(r'[^\w]', '', singer_in_lrc.lower())
                # 若两者完全无关，且歌词中明确标注他人演唱
                if norm_artist and norm_singer and (norm_artist not in norm_singer) and (norm_singer not in norm_artist):
                    # 避免合辑/合作歌手（如 动力火车 & 迪克牛仔）
                    if not any(token in singer_in_lrc for token in [artist, 'S.H.E', 'Beyond', '五月天']):
                        # 再次核验这是否为翻唱或李鬼
                        if any(k in hl for k in ['原唱', '翻唱', '演唱', 'ar:']):
                            hit_reasons.append(f"演唱者署名非本尊: [{singer_in_lrc}] (本库登记: [{artist}])")

        if hit_reasons:
            return {
                "song_id": song.get("id") or song.get("song_id"),
                "artist": artist,
                "album": song.get("album_title") or song.get("album") or "未知专辑",
                "title": title,
                "file_path": song.get("file_path"),
                "lrc_path": lrc_url,
                "hit_reasons": list(set(hit_reasons)),
                "lrc_snippet": "\n".join(lines[:8])
            }
    except Exception:
        pass

    return None

def verify_audio_with_stage1_whisper(pool, suspect):
    """流水线 A 第二步：拉取音频中段 30s~60s 执行 Whisper-large-v3 盲听初筛"""
    song_id = suspect["song_id"]
    file_url = suspect.get("file_path")
    if not file_url:
        suspect["whisper_stage1"] = {"status": "NO_AUDIO_URL", "text": ""}
        return suspect

    raw_path = os.path.join(SCRATCH_DIR, f"s1_{song_id}_raw.mp3")
    clip_path = os.path.join(SCRATCH_DIR, f"s1_{song_id}_clip30_60.mp3")

    try:
        # 下载音频
        r = requests.get(file_url, timeout=15)
        if r.status_code != 200:
            suspect["whisper_stage1"] = {"status": f"HTTP_{r.status_code}", "text": ""}
            return suspect

        with open(raw_path, "wb") as f:
            f.write(r.content)

        # 截取 30s ~ 60s 单声道 16kHz 紧凑切片
        subprocess.run([
            "ffmpeg", "-y", "-ss", "30", "-t", "30",
            "-i", raw_path,
            "-ac", "1", "-ar", "16000", "-b:a", "64k",
            clip_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not os.path.exists(clip_path) or os.path.getsize(clip_path) < 1000:
            suspect["whisper_stage1"] = {"status": "FFMPEG_CLIP_FAILED", "text": ""}
            return suspect

        # Whisper-large-v3 模型听音
        res = pool.transcribe(clip_path, model="whisper-large-v3")
        text = res.get("text", "").strip() if res.get("success") else f"ERROR: {res.get('error')}"

        suspect["whisper_stage1"] = {
            "model": "whisper-large-v3",
            "sample_range": "30s-60s",
            "text": text,
            "success": res.get("success", False)
        }

    except Exception as e:
        suspect["whisper_stage1"] = {"status": f"EXCEPTION_{e}", "text": ""}
    finally:
        # 清理临时切片
        for p in [raw_path, clip_path]:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass

    return suspect

def main():
    print("=" * 80)
    print("🚀 启动 MOODY 早期曲库双轨审计 - 流水线 A (初筛与异常特征捕获)")
    print("=" * 80)
    print(f"📂 载入全盘已点亮歌曲档案: {DATA_PATH}")

    if not os.path.exists(DATA_PATH):
        print(f"❌ 未找到文件: {DATA_PATH}")
        sys.exit(1)

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        all_songs = json.load(f)

    print(f"📊 曲目总数: {len(all_songs)} 首")
    print("🔍 阶段 1.1：启动 20 线程并发 LRC 上下文感知快筛 (避开正文版权声明假阳性)...")

    suspect_lyrics = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(check_single_lrc, s): s for s in all_songs}
        done_cnt = 0
        for f in as_completed(futures):
            done_cnt += 1
            if done_cnt % 3000 == 0 or done_cnt == len(all_songs):
                print(f"  • 进度: {done_cnt}/{len(all_songs)} ({done_cnt/len(all_songs)*100:.1f}%) | 当前命中嫌疑数: {len(suspect_lyrics)}")
            res = f.result()
            if res:
                suspect_lyrics.append(res)

    print("\n" + "-" * 80)
    print(f"🎯 阶段 1.1 完成！全盘共捕获可疑特征歌曲: {len(suspect_lyrics)} 首")
    print("-" * 80)

    # 阶段 1.2：Groq Whisper-large-v3 声学盲听初筛
    print(f"\n🎙️ 阶段 1.2：启动多 Token 调度池进行音频主干 (30s~60s) 声学盲听初筛...")
    pool = GroqTokenPool()

    stage1_results = []
    # 限制并发以配合 Groq RPM 速率
    for idx, s in enumerate(suspect_lyrics, 1):
        print(f"[{idx:03d}/{len(suspect_lyrics):03d}] 正在初筛: [{s['artist']}] 《{s['title']}》 - 命中: {s['hit_reasons']}")
        verified = verify_audio_with_stage1_whisper(pool, s)
        w_text = verified.get("whisper_stage1", {}).get("text", "")
        print(f"     Whisper 转录样本: {w_text[:70]}...")
        stage1_results.append(verified)

    # 阶段 1.3：持久化与完全冻结
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(stage1_results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"🔒 流水线 A 执行完毕！初筛嫌疑曲目已完全冻结归档至:")
    print(f"   {REPORT_PATH}")
    print(f"   总量: {len(stage1_results)} 首")
    print(f"   【铁律核验】：未发起任何数据库更新或下架删除操作。")
    print("=" * 80)

if __name__ == "__main__":
    main()
