#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - 迪克牛仔 (72 首) & 郑智化 (88 首) 全专细腻度 AI 听音与歌词全盘审计
==============================================================================
标准：
1. Groq Whisper Large-v3 黄金切片深度听音 (30s-60s, 必要时 70s-100s)
2. 音频 ID3 标签与时长比对
3. LRC 歌词存在性、时间轴格式与文本一致性比对
4. 串歌、伴奏、李鬼原唱、错配歌词全面研判
==============================================================================
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
DICK_REPORT_PATH = os.path.join(REPORT_DIR, "DICK_COWBOY_DETAILED_AUDIT.json")
ZHENG_REPORT_PATH = os.path.join(REPORT_DIR, "ZHENG_ZHIHUA_DETAILED_AUDIT.json")

TMP_DIR = "/tmp/moody_deep_audit"
os.makedirs(TMP_DIR, exist_ok=True)

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_PROXIES = {'http': 'http://127.0.0.1:7898', 'https': 'http://127.0.0.1:7898'}
D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"

# 简繁归一化映射
TRAD_TO_SIMP = {
    '著': '着', '說': '说', '這': '这', '個': '个', '愛': '爱', '聽': '听',
    '從': '从', '來': '来', '開': '开', '關': '关', '過': '过', '進': '进',
    '為': '为', '與': '与', '頭': '头', '臉': '脸', '淚': '泪', '邊': '边',
    '風': '风', '飛': '飞', '沙': '沙', '樣': '样', '會': '会', '學': '学',
    '轉': '转', '身': '身', '後': '后', '裝': '装', '無': '无', '熱': '热',
    '血': '血', '請': '请', '放': '放', '別': '别', '讓': '让', '以': '以',
    '罪': '罪', '結': '结', '隊': '队', '燈': '灯', '點': '点', '戲': '戏',
    '墮': '堕', '落': '落', '國': '国', '夢': '梦', '沈': '沉', '夥': '伙'
}

def to_simp(t: str) -> str:
    return "".join(TRAD_TO_SIMP.get(c, c) for c in t)

def clean_text(t: str) -> str:
    if not t: return ""
    cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', t).lower()
    return to_simp(cleaned)

def fetch_songs(artist_name: str):
    resp = requests.get(D1_SONGS_URL, timeout=30)
    data = resp.json().get('data', [])
    target_songs = []
    for art in data:
        if art.get('name') == artist_name:
            for alb in art.get('albums', []):
                alb_title = alb.get('title')
                for s in alb.get('songs', []):
                    path = s.get('path') or ''
                    lrc = s.get('lrc_path') or ''
                    title = s.get('title') or ''
                    target_songs.append({
                        'artist': artist_name,
                        'album': alb_title,
                        'title': title,
                        'path': path,
                        'lrc_path': lrc
                    })
    return target_songs

def extract_clip_and_whisper(audio_url: str, start_sec: int, dur_sec: int, label: str) -> str:
    clip_path = os.path.join(TMP_DIR, f"clip_{label}_{start_sec}.mp3")
    cmd = [
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", str(dur_sec),
        "-i", audio_url, "-ac", "1", "-ar", "16000", clip_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=True)
        if not os.path.exists(clip_path) or os.path.getsize(clip_path) < 1000:
            return ""
            
        with open(clip_path, "rb") as f:
            files = {
                'file': (os.path.basename(clip_path), f, 'audio/mpeg'),
                'model': (None, 'whisper-large-v3')
            }
            resp = requests.post(
                'https://api.groq.com/openai/v1/audio/transcriptions',
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files=files, proxies=GROQ_PROXIES, timeout=30
            )
            if resp.status_code == 200:
                return resp.json().get('text', '').strip()
    except Exception as e:
        pass
    finally:
        if os.path.exists(clip_path):
            try: os.remove(clip_path)
            except: pass
    return ""

def audit_single_song(item: dict) -> dict:
    art = item['artist']
    alb = item['album']
    title = item['title']
    url = item['path']
    lrc_url = item['lrc_path']
    
    label = f"{art}_{alb}_{title}".replace(' ', '_').replace('/', '_')[:30]
    
    res = {
        'artist': art,
        'album': alb,
        'title': title,
        'path': url,
        'lrc_path': lrc_url,
        'duration': 0.0,
        'tags': {},
        'whisper_clip1': "",
        'whisper_clip2': "",
        'lrc_status': "UNKNOWN",
        'lrc_sample': "",
        'issue_type': None,
        'issue_detail': "合格",
        'is_normal': True
    }
    
    if not url or not url.startswith('http'):
        res['issue_type'] = "INVALID_PATH"
        res['issue_detail'] = "URL 为空或非绝对直链"
        res['is_normal'] = False
        return res

    # 1. ffprobe 获取时长与 ID3 tags
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration:format_tags=artist,title,album', '-of', 'json', url]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        pj = json.loads(p.stdout)
        res['duration'] = round(float(pj.get('format', {}).get('duration', 0)), 1)
        res['tags'] = pj.get('format', {}).get('tags', {})
    except Exception:
        pass

    # 2. 检查 LRC 歌词
    lrc_text = ""
    if not lrc_url or not lrc_url.startswith('http'):
        res['lrc_status'] = "MISSING_URL"
    else:
        try:
            r = requests.get(lrc_url, timeout=10)
            if r.status_code == 200:
                lrc_text = r.text.strip()
                lines = [l.strip() for l in lrc_text.split('\n') if l.strip()]
                has_timestamp = any(re.search(r'\[\d{2}:\d{2}', l) for l in lines)
                if not lrc_text or len(lines) < 3:
                    res['lrc_status'] = "EMPTY_OR_CORRUPT"
                elif not has_timestamp:
                    res['lrc_status'] = "NO_TIMESTAMPS"
                else:
                    res['lrc_status'] = "VALID"
                res['lrc_sample'] = ' | '.join(lines[:4]) if lines else ""
            else:
                res['lrc_status'] = f"HTTP_{r.status_code}"
        except Exception as e:
            res['lrc_status'] = f"ERROR_{str(e)[:20]}"

    # 3. Whisper 听辨：切片 1 (30s-60s)
    heard1 = extract_clip_and_whisper(url, 30, 30, f"{label}_c1")
    res['whisper_clip1'] = heard1
    
    heard = heard1
    # 如果第一段没听出明显内容，截取第二段 70s-100s
    if len(clean_text(heard1)) < 6:
        heard2 = extract_clip_and_whisper(url, 70, 30, f"{label}_c2")
        res['whisper_clip2'] = heard2
        if len(clean_text(heard2)) > len(clean_text(heard1)):
            heard = heard2

    norm_title = clean_text(title)
    norm_heard = clean_text(heard)
    norm_lrc = clean_text(lrc_text)

    # 4. 缺陷综合研判
    # 4.1 伴奏 / 无人声
    is_instrumental_track = "inst" in title.lower() or "纯音乐" in title
    if (len(norm_heard) < 5 or heard in ["🎵", "Music", "Música"]) and not is_instrumental_track:
        res['issue_type'] = "NO_VOCAL"
        res['issue_detail'] = "未检测到有效声乐主唱，疑似纯伴奏/和声轨/空白"
        res['is_normal'] = False
        return res
        
    # 4.2 民乐翻奏乐团
    if "zitherharp" in norm_heard:
        res['issue_type'] = "INSTRUMENTAL_COVER"
        res['issue_detail'] = "被 Zither Harp 古筝纯器乐伴奏污染"
        res['is_normal'] = False
        return res

    # 4.3 明显串歌为他人词曲（如李宗盛等）
    if "作词李宗盛" in norm_heard and "李宗盛" not in norm_title:
        res['issue_type'] = "CROSS_TALK"
        res['issue_detail'] = f"严重串歌为李宗盛作品: 听到 \"{heard[:40]}\""
        res['is_normal'] = False
        return res

    # 4.4 迪克牛仔特化研判：原唱李鬼检测
    if art == '迪克牛仔':
        # 4.4.1 《忘记我还是忘记他》专辑特化
        if title == "忘记我还是忘记他" and "三万英尺" in heard:
            res['issue_type'] = "CROSS_TALK"
            res['issue_detail'] = "串歌为《三万英尺》"
            res['is_normal'] = False
            return res
            
        if title == "水手" and ("李宗盛" in heard or "方言方语" in heard):
            res['issue_type'] = "CROSS_TALK"
            res['issue_detail'] = "严重串歌为李宗盛作品"
            res['is_normal'] = False
            return res

        # 4.4.2 标签显示为其他原唱歌手
        tag_art = res['tags'].get('ARTIST', '')
        if tag_art and '迪克牛仔' not in tag_art:
            res['issue_type'] = "SUSPECTED_ORIGINAL"
            res['issue_detail'] = f"ID3 标签原唱李鬼: 标明为 [{tag_art}]，非迪克牛仔"
            res['is_normal'] = False
            return res

    # 4.5 歌词错配与不匹配研判
    if res['lrc_status'] == "VALID" and len(norm_heard) >= 10:
        # 歌词中是否能找到哪怕一句听到的唱词核心词
        # 截取 heard 的前中后若干 6 字子串
        chunks = [norm_heard[i:i+6] for i in range(0, len(norm_heard)-5, 5)]
        match_count = sum(1 for c in chunks if c in norm_lrc)
        if match_count == 0 and len(chunks) >= 2:
            res['issue_type'] = "LRC_MISMATCH"
            res['issue_detail'] = f"歌词与音频严重不符！听辨唱词在歌词中完全无匹配"
            res['is_normal'] = False
            return res

    if res['lrc_status'] != "VALID":
        res['issue_type'] = "LRC_ANOMALY"
        res['issue_detail'] = f"歌词异常: {res['lrc_status']}"
        res['is_normal'] = False
        return res

    return res

def run_audit_for_artist(artist_name: str, report_path: str):
    print("=" * 80, flush=True)
    print(f"🔍 启动【{artist_name}】全专细腻度地毯式 AI 听音与歌词核验流水线", flush=True)
    print("=" * 80, flush=True)
    
    songs = fetch_songs(artist_name)
    print(f"📊 检索到【{artist_name}】全库曲目: {len(songs)} 首", flush=True)
    
    results = []
    normal_cnt = 0
    anomaly_cnt = 0
    
    # 限制并发为 4，保证 Groq Whisper 稳定性与网络质量
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(audit_single_song, s): s for s in songs}
        done_cnt = 0
        for f in as_completed(futures):
            res = f.result()
            results.append(res)
            done_cnt += 1
            if res['is_normal']:
                normal_cnt += 1
                status_icon = "🟢 正常"
            else:
                anomaly_cnt += 1
                status_icon = f"❌ 异常 [{res['issue_type']}]"
                
            clean_heard = res['whisper_clip1'].replace('\n', ' ')[:40]
            print(f"[{done_cnt:02d}/{len(songs)}] {status_icon}: 《{res['album']}》 - 《{res['title']}》 | 听到: \"{clean_heard}...\" | 歌词: {res['lrc_status']}", flush=True)
            if not res['is_normal']:
                print(f"     ⚠️ 原因: {res['issue_detail']}", flush=True)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print("\n" + "=" * 80, flush=True)
    print(f"🏁 【{artist_name}】审计完成！", flush=True)
    print(f"   • 总曲目数: {len(songs)} 首")
    print(f"   • 🟢 正常曲目: {normal_cnt} 首")
    print(f"   • ❌ 异常曲目: {anomaly_cnt} 首 (占比: {anomaly_cnt/len(songs)*100:.1f}%)")
    print(f"   • 详细报告落盘至: {report_path}")
    print("=" * 80, flush=True)
    return results

def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'zheng':
        run_audit_for_artist('郑智化', ZHENG_REPORT_PATH)
    else:
        run_audit_for_artist('迪克牛仔', DICK_REPORT_PATH)

if __name__ == "__main__":
    main()
