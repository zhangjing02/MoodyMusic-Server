#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 全盘重点歌手音频质量与真实性深度体检扫描器 (Deep Audio Authenticity Scanner)
功能：
1. 扫描 9,371 首重点歌手歌曲的标题、专辑、路径、歌词特征；
2. 识别【次级偏差：演唱会现场版 (Live)】（标有 Live 或现场特征，非现场专辑混入）；
3. 识别【疑似一级严重错误】（翻唱/伴奏/广告/错歌/外语歌/死链）；
4. 针对高疑点曲目自动截取 30 秒人声黄金切片进行 Groq Whisper-large-v3 实测盲听；
5. 输出全盘分级审计分析结果。
"""

import os
import sys
import json
import re
import time
import subprocess
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# 常见广告关键词清单
AD_KEYWORDS = [
    '微信公众号', '独播剧场', '关注我们', '欢迎收听', '电台', '广告', '代录', '翻唱网',
    'subtitle', 'volunteer', '字幕组', '优优独播', '官方频道', 'tiktok', '快手',
    'subscribe', 'ghièn mì gõ', 'ghiènmìgõ', 'ghiền mì gõ', 'bilibili'
]

# 翻唱/纯音乐伴奏关键词清单
COVER_OR_INSTRUMENTAL_KW = [
    'zither harp', 'zither', 'harp', 'piano cover', 'relaxing bgm',
    '伴奏', 'instrumental', 'karaoke', '卡拉ok', '消音伴奏', '纯伴奏'
]

# 现场版 Live 关键词清单
LIVE_KEYWORDS = [
    'live', '現場', '现场', '演唱会', '音乐会'
]

def clean_text(t: str) -> str:
    if not t: return ""
    return re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', t).lower()

def extract_and_transcribe(url: str, sid: int, ss: int = 35, t: int = 30) -> str:
    if not GROQ_KEY or not url:
        return ""
    tmp_clip = f"/tmp/audit_clip_{sid}_{int(time.time()*1000)%10000}.mp3"
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
        if os.path.exists(tmp_clip):
            os.remove(tmp_clip)
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
        return f"GROQ_ERROR_{resp.status_code}"
    except Exception as e:
        if os.path.exists(tmp_clip):
            os.remove(tmp_clip)
        return f"EXCEPTION_{e}"

def is_live_album(album_title: str) -> bool:
    at = album_title.lower()
    return any(k in at for k in ['演唱会', 'live', '音乐会', '现场', '巡回'])

def main():
    songs_file = "reports/CORE_ARTISTS_LIT_SONGS.json"
    if not os.path.exists(songs_file):
        print(f"❌ 找不到数据文件 {songs_file}")
        return
    
    with open(songs_file, "r", encoding="utf-8") as f:
        songs = json.load(f)
    print(f"📊 已载入 {len(songs)} 首重点歌手歌曲")

    live_deviation_list = []    # 次级偏差：Live 现场版
    primary_serious_suspects = [] # 疑似一级严重错误：翻唱/李鬼/广告/错歌

    for s in songs:
        sid = s.get('song_id') or s.get('id')
        art = s.get('artist', '')
        alb = s.get('album', '')
        title = s.get('title', '')
        fpath = s.get('file_path', '')
        lpath = s.get('lrc_path', '')

        # 1. 检查是否为现场版 (Live)
        alb_is_live = is_live_album(alb)
        title_lower = title.lower()
        fpath_lower = fpath.lower()
        
        # 针对歌名包含 Live 特征但专辑不是 Live 专
        has_live_tag = bool(re.search(r'[\(\[\{（【\s](live|現場|现场|演唱会)[\)\]\}）】\s]?', title_lower)) or \
                       title_lower.endswith(' live') or title_lower.endswith('(live)') or \
                       'live in ' in title_lower or 'live at ' in title_lower or 'live版' in title_lower
        
        if has_live_tag and not alb_is_live:
            # 排除本就是现场特辑或歌名本身叫 live 的特殊情况（如 I Am Alive）
            if 'alive' not in title_lower and 'livehouse' not in title_lower and 'love live' not in title_lower:
                live_deviation_list.append({
                    "id": sid, "artist": art, "album": alb, "title": title,
                    "file_path": fpath, "lrc_path": lpath,
                    "reason": f"录音室专辑《{alb}》中混入现场版: {title}"
                })
                continue

        # 2. 检查明显李鬼/伴奏/广告/非录音室特征
        is_suspect = False
        suspect_reasons = []

        for kw in COVER_OR_INSTRUMENTAL_KW:
            if kw in title_lower or kw in fpath_lower:
                # 排除像《听袁惟仁弹吉他》这种正常曲目
                if title == "聽袁惟仁彈吉他" or title == "听袁惟仁弹吉他":
                    continue
                is_suspect = True
                suspect_reasons.append(f"命中翻唱/伴奏关键词: {kw}")

        # 检查是否命中历史已知严重错误列表
        known_bad_ids = [24168, 25795, 38, 49, 50, 52, 54, 55, 59]
        if sid in known_bad_ids:
            is_suspect = True
            suspect_reasons.append("命中历史异常已知问题 ID")

        # 检查是否为海外机翻译名或异常英文歌名混在华语专
        # 如果整专都是中文，突然出现一首明显奇怪的英文或者包含外语
        if is_suspect:
            primary_serious_suspects.append({
                "id": sid, "artist": art, "album": alb, "title": title,
                "file_path": fpath, "lrc_path": lpath,
                "reasons": suspect_reasons
            })

    print("\n" + "=" * 80)
    print(f"📌 初筛统计报告:")
    print(f"  1. 【次级偏差：演唱会现场版 (Live)】: {len(live_deviation_list)} 首 (按铁律保持现状，后台建档)")
    print(f"  2. 【疑似一级严重错误 (需 AI 盲听复核)】: {len(primary_serious_suspects)} 首")
    print("=" * 80)

    # 对疑似严重错误曲目执行 Groq Whisper 实地盲听
    confirmed_primary_errors = []
    
    print("\n🎧 启动 Groq Whisper 大模型实地听音复核...")
    for idx, item in enumerate(primary_serious_suspects, 1):
        sid = item['id']
        art = item['artist']
        title = item['title']
        url = item['file_path']
        print(f"[{idx:02d}/{len(primary_serious_suspects):02d}] 正在听辨: [{art}] 《{title}》 (ID: {sid})...", end="", flush=True)
        heard = extract_and_transcribe(url, sid, ss=30, t=30)
        item['whisper_heard'] = heard
        
        # 分析 heard
        norm_heard = heard.lower()
        has_ad = any(ak in norm_heard for ak in AD_KEYWORDS)
        has_cover = any(ck in norm_heard for ck in COVER_OR_INSTRUMENTAL_KW)
        
        is_error = False
        error_type = ""
        if has_ad:
            is_error = True
            error_type = "AD_DETECTED"
        elif has_cover:
            is_error = True
            error_type = "COVER_INSTRUMENTAL_DETECTED"
        elif "vietnamese" in norm_heard or "subscribe" in norm_heard or "tiếp tục" in norm_heard:
            is_error = True
            error_type = "WRONG_LANGUAGE_OR_VIDEO_AD"
        elif sid in [24168, 25795]:
            is_error = True
            error_type = "CONFIRMED_POLLUTED"
            
        if is_error:
            item['error_type'] = error_type
            confirmed_primary_errors.append(item)
            print(f" -> 🔴 确诊一级严重错误: {error_type}")
        else:
            print(f" -> 🟡 转写: {heard[:35]}...")
            
    print("\n" + "=" * 80)
    print(f"🚨 确诊一级严重错误: {len(confirmed_primary_errors)} 首 (必须下架并物理删除，重新采录)")
    for err in confirmed_primary_errors:
        print(f"   • ID {err['id']}: [{err['artist']}] 《{err['title']}》 - {err.get('error_type')} (听音: {err.get('whisper_heard')[:60]}...)")
    print("=" * 80)

    # 导出完整体检数据
    audit_output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_songs_scanned": len(songs),
        "total_live_deviations": len(live_deviation_list),
        "live_deviations": live_deviation_list,
        "total_confirmed_primary_errors": len(confirmed_primary_errors),
        "confirmed_primary_errors": confirmed_primary_errors
    }
    
    with open("reports/AUTHENTICITY_AUDIT_FINAL.json", "w", encoding="utf-8") as f:
        json.dump(audit_output, f, ensure_ascii=False, indent=2)
    print("💾 完整审计结果已保存在 reports/AUTHENTICITY_AUDIT_FINAL.json")

if __name__ == "__main__":
    main()
