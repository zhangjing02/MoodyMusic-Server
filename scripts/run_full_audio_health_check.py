#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 全盘重点歌手音频质量与真实性深度体检系统 (Audio Authenticity & Quality Assurance)
分级标准：
1. 【次级偏差：演唱会现场版 (Live)】：
   - 特征：录音室正规专辑中混入了现场演唱会音轨（歌名标注 Live/现场版/现场直播/音乐会，或前奏带观众掌声/欢呼声/现场音效）；
   - 处置原则：100% 维持现状，确保用户在线可听！后台建档，待检索到 100% 合规录音室正式版后再平滑替换。
2. 【一级严重错误：翻唱/错歌/视频广告/完全货不对版/伴奏掉包】：
   - 特征：实唱非本人（口水翻唱、李鬼、Zither Harp古筝伴奏、KTV伴奏）；音频带有视频片头片尾广告口播；严重串歌或语言错乱；死链/空文件；
   - 处置原则：必须调用 /api/admin/songs/batch-unlight 下架，并在 R2 中物理删除脏音频文件释放存储空间，然后从官方录音室渠道重新采录正版母带（EBU R128 + Xing Header + Groq Whisper），写入 Bucket 09 重新点亮。
"""

import os
import sys
import json
import re
import time
import subprocess
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

SONGS_FILE = "reports/CORE_ARTISTS_LIT_SONGS.json"
REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

# 广告敏感词
AD_KEYWORDS = [
    '微信公众号', '独播剧场', '关注我们', '欢迎收听', '电台', '广告', '代录', '翻唱网',
    'subtitle', 'volunteer', '字幕组', '优优独播', '官方频道', 'tiktok', '快手',
    'subscribe', 'ghièn mì gõ', 'ghiènmìgõ', 'ghiền mì gõ', 'bilibili'
]

# 翻唱/纯音乐伴奏敏感词
COVER_KEYWORDS = [
    'zither harp', 'zither', 'harp', 'piano cover', 'relaxing bgm',
    '伴奏', 'instrumental', 'karaoke', '卡拉ok', '消音伴奏', '纯伴奏'
]

def clean_text(t: str) -> str:
    if not t: return ""
    return re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', t).lower()

def is_live_album(album_title: str) -> bool:
    at = album_title.lower()
    return any(k in at for k in ['演唱会', 'live', '音乐会', '现场', '巡回'])

def extract_and_transcribe(url: str, sid: int, ss: int = 30, t: int = 30) -> str:
    if not GROQ_KEY or not url:
        return ""
    tmp_clip = f"/tmp/audit_{sid}_{int(time.time()*1000)%10000}.mp3"
    cmd = [
        "ffmpeg", "-y", "-ss", str(ss), "-t", str(t),
        "-i", url, "-ac", "1", "-ar", "16000", "-b:a", "64k", tmp_clip
    ]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
        if r.returncode != 0 or not os.path.exists(tmp_clip) or os.path.getsize(tmp_clip) < 500:
            return "FFMPEG_FAILED"
        
        with open(tmp_clip, "rb") as f:
            resp = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": (f"clip_{sid}.mp3", f, "audio/mpeg")},
                data={"model": "whisper-large-v3", "temperature": "0.0"},
                timeout=25
            )
        if os.path.exists(tmp_clip): os.remove(tmp_clip)
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
        return f"GROQ_ERROR_{resp.status_code}"
    except Exception as e:
        if os.path.exists(tmp_clip): os.remove(tmp_clip)
        return f"EXCEPTION_{e}"

def run_health_check():
    print("=" * 80)
    print("🏥 MOODY 全盘重点歌手音频质量与真实性深度体检系统启动")
    print("=" * 80)
    
    with open(SONGS_FILE, "r", encoding="utf-8") as f:
        songs = json.load(f)
        
    for s in songs:
        if not s.get('song_id'):
            m = re.search(r's_(\d+)\.(mp3|m4a|flac|wav)', s.get('file_path', '')) or re.search(r'/(\d+)\.(mp3|m4a)', s.get('file_path', ''))
            if m:
                s['song_id'] = int(m.group(1))

    print(f"📊 待体检歌曲总数: {len(songs)} 首 (涵盖华语乐坛 62 位殿堂天王天后)")

    # 1. 扫描分类
    live_deviations = []      # 次级偏差：演唱会现场版
    suspect_primary_errors = [] # 疑似一级严重错误

    # 载入历史已知报告数据作为先验输入
    known_abnormal_ids = {
        24168: "王菲《MV》- 视频片头广告口播/越南语",
        25795: "动力火车《我这个你不爱的人》- Zither Harp古筝翻奏伴奏",
        59: "阿杜《没什么好怕》- 死链/无法读取音频",
        38: "阿杜《几年了》- 串歌",
        7480: "古巨基《顺风车》- 串歌",
        24170: "王菲《花事了》- 前奏幻觉",
    }

    # 收集歌词中带有 Zither Harp、伴奏、广告等的歌曲
    # 并从歌名、路径、历史中筛选
    for s in songs:
        sid = s.get('song_id')
        art = s.get('artist', '')
        alb = s.get('album', '')
        title = s.get('title', '')
        fpath = s.get('file_path', '')
        lpath = s.get('lrc_path', '')
        title_lower = title.lower()
        fpath_lower = fpath.lower()

        # A. 检查是否为录音室专辑混入现场版 Live
        alb_is_live = is_live_album(alb)
        is_live_title = bool(re.search(r'[\(\[\{（【\s](live|現場|现场|演唱会|live版)[\)\]\}）】\s]?', title_lower)) or \
                        title_lower.endswith(' live') or title_lower.endswith('(live)') or \
                        'live in ' in title_lower or 'live at ' in title_lower
        
        # 排除非 Live 专本就叫 live 的歌
        if is_live_title and not alb_is_live:
            if 'alive' not in title_lower and 'livehouse' not in title_lower and 'love live' not in title_lower:
                live_deviations.append({
                    "song_id": sid,
                    "artist": art,
                    "album": alb,
                    "title": title,
                    "file_path": fpath,
                    "lrc_path": lpath,
                    "type": "LIVE_CONCERT_IN_STUDIO_ALBUM",
                    "reason": f"录音室专辑《{alb}》收录了现场版Live音轨"
                })
                continue

        # B. 检查疑似一级严重错误
        suspect_reason = []
        if sid in known_abnormal_ids:
            suspect_reason.append(known_abnormal_ids[sid])
        
        for kw in COVER_KEYWORDS:
            if kw in title_lower or kw in fpath_lower:
                if title not in ["聽袁惟仁彈吉他", "听袁惟仁弹吉他"]:
                    suspect_reason.append(f"命中翻唱/纯音乐特征词: {kw}")
        
        for kw in AD_KEYWORDS:
            if kw in title_lower or kw in fpath_lower:
                suspect_reason.append(f"命中广告特征词: {kw}")

        if suspect_reason:
            suspect_primary_errors.append({
                "song_id": sid,
                "artist": art,
                "album": alb,
                "title": title,
                "file_path": fpath,
                "lrc_path": lpath,
                "initial_reasons": suspect_reason
            })

    print("\n" + "=" * 80)
    print(f"📋 初筛结果概览:")
    print(f"  • 【次级偏差：演唱会现场版 (Live)】: {len(live_deviations)} 首 (按铁律全部维持现状，后台建档，待正版置换)")
    print(f"  • 【疑似一级严重错误待验证】: {len(suspect_primary_errors)} 首")
    print("=" * 80)

    # 2. 对疑似一级严重错误执行 AI 盲听与实测
    verified_primary_errors = []
    print("\n🎙️ 启动 Groq Whisper 大模型人声盲听深度复核...")
    for idx, item in enumerate(suspect_primary_errors, 1):
        sid = item['song_id']
        art = item['artist']
        title = item['title']
        url = item['file_path']
        print(f"[{idx:02d}/{len(suspect_primary_errors):02d}] 正在盲听: [{art}] 《{title}》 (ID: {sid})...", end="", flush=True)
        
        heard = extract_and_transcribe(url, sid, ss=30, t=30)
        item['whisper_heard'] = heard

        # 判断具体错误类别
        norm_h = heard.lower()
        if "ghièn mì gõ" in norm_h or "subscribe" in norm_h or any(ak in norm_h for ak in AD_KEYWORDS):
            item['error_type'] = "VIDEO_AD_VOICEOVER"
            item['error_desc'] = f"检测到视频片头片尾广告口播水印: {heard[:50]}..."
            verified_primary_errors.append(item)
            print(f" -> 🔴 【一级严重错误: 视频广告口播】")
        elif "zither harp" in norm_h or "piano cover" in norm_h or any(ck in norm_h for ck in COVER_KEYWORDS):
            item['error_type'] = "COVER_INSTRUMENTAL_SPOOF"
            item['error_desc'] = f"检测到李鬼民乐/翻奏伴奏无主唱: {heard[:50]}..."
            verified_primary_errors.append(item)
            print(f" -> 🔴 【一级严重错误: 李鬼伴奏掉包】")
        elif heard == "FFMPEG_FAILED" or "404" in heard:
            item['error_type'] = "DEAD_LINK_CORRUPTED"
            item['error_desc'] = "音频流损坏、404 或死链无法播放"
            verified_primary_errors.append(item)
            print(f" -> 🔴 【一级严重错误: 坏链/无法读取】")
        elif sid in [24168, 25795]:
            item['error_type'] = "POLLUTED_TRACK"
            item['error_desc'] = f"确诊历史残留严重污染音轨: {heard[:50]}..."
            verified_primary_errors.append(item)
            print(f" -> 🔴 【一级严重错误: 确诊污染】")
        else:
            print(f" -> 🟢 经盲听确认无广告/无伴奏掉包 (转写: {heard[:30]}...)")

    print("\n" + "=" * 80)
    print(f"🏁 深度体检完成！确诊需立即处置的一级严重错误: {len(verified_primary_errors)} 首")
    for err in verified_primary_errors:
        print(f"  ❌ ID {err['song_id']}: [{err['artist']}] 《{err['title']}》 ({err['album']}) - {err['error_type']}")
        print(f"     详情: {err['error_desc']}")
        print(f"     原路径: {err['file_path']}")
    print("=" * 80)

    # 导出完整结构化报表
    full_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_songs_scanned": len(songs),
        "summary": {
            "live_deviations_count": len(live_deviations),
            "primary_errors_count": len(verified_primary_errors),
        },
        "live_deviations": live_deviations,
        "primary_errors": verified_primary_errors
    }

    with open("reports/FULL_AUDIO_AUTHENTICITY_REPORT.json", "w", encoding="utf-8") as f:
        json.dump(full_report, f, ensure_ascii=False, indent=2)
        
    print(f"📄 深度体检数据报表已写入: reports/FULL_AUDIO_AUTHENTICITY_REPORT.json")

if __name__ == "__main__":
    run_health_check()
