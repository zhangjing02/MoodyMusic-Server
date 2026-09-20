#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
迪克牛仔全专 72 首曲目 AI 听音辨曲与真伪全盘普查脚本 (Groq Whisper-large-v3)
==============================================================================
"""

import os
import sys
import json
import time
import re
import subprocess
import requests

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)
REPORT_FILE = os.path.join(REPORT_DIR, "DICK_COWBOY_AI_AUDIT.json")
TEMP_DIR = "/tmp/dick_whisper_audit"
os.makedirs(TEMP_DIR, exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"

try:
    import syncedlyrics
except ImportError:
    syncedlyrics = None

def extract_sample(url: str, out_file: str, ss: int = 25, t: int = 30) -> bool:
    if os.path.exists(out_file):
        try: os.remove(out_file)
        except: pass
    cmd = [
        "ffmpeg", "-y", "-ss", str(ss), "-t", str(t),
        "-i", url, "-b:a", "64k", "-ac", "1", out_file
    ]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        return r.returncode == 0 and os.path.exists(out_file) and os.path.getsize(out_file) > 1000
    except:
        return False

def whisper_stt(audio_file: str) -> str:
    if not GROQ_API_KEY or not os.path.exists(audio_file):
        return ""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    try:
        with open(audio_file, "rb") as f:
            files = {"file": (os.path.basename(audio_file), f, "audio/mpeg")}
            data = {"model": "whisper-large-v3", "language": "zh", "temperature": 0.0}
            resp = requests.post(GROQ_API_URL, headers=headers, files=files, data=data, timeout=30)
            if resp.status_code == 200:
                return resp.json().get("text", "").strip()
    except Exception as e:
        pass
    return ""

def get_official_duration_and_artist(title: str, album: str) -> dict:
    url = f"http://search.kuwo.cn/r.s?client=kt&all=迪克牛仔+{title}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=5"
    try:
        r = requests.get(url, timeout=5)
        d = json.loads(r.text.replace("'", '"'))
        for item in d.get('abslist', []):
            art = item.get('ARTIST', '')
            if '迪克牛仔' in art:
                return {
                    'artist': art,
                    'album': item.get('ALBUM'),
                    'duration': int(item.get('DURATION', 0)),
                    'rid': item.get('DC_TARGETID')
                }
    except:
        pass
    return None

def get_ffprobe_info(url: str) -> tuple[float, dict]:
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration,tags', url]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        dur = 0.0
        tags = {}
        for line in res.stdout.splitlines():
            if line.startswith('duration='):
                dur = float(line.split('=')[1])
            elif '=' in line:
                k, v = line.split('=', 1)
                tags[k.upper()] = v
        return dur, tags
    except:
        return 0.0, {}

def normalize_text(text: str) -> str:
    if not text: return ""
    return re.sub(r'[\s\t\n\r\-—·、，,。．；;：:！!？?（）\(\)\[\]【】《》〈〉\._]', '', text.lower())

def audit_song(s: dict) -> dict:
    sid = s['id']
    alb = s['album']
    title = s['title']
    path = s['path']
    lrc_path = s['lrc_path']

    sample_path = os.path.join(TEMP_DIR, f"sample_{sid}.mp3")
    ok = extract_sample(path, sample_path, ss=25, t=30)
    if not ok:
        ok = extract_sample(path, sample_path, ss=15, t=30)

    heard = ""
    if ok:
        heard = whisper_stt(sample_path)
        try: os.remove(sample_path)
        except: pass

    cur_dur, cur_tags = get_ffprobe_info(path)
    off_info = get_official_duration_and_artist(title, alb)

    norm_heard = normalize_text(heard)
    norm_title = normalize_text(title)

    status = "PASS"
    reason = "正常"

    # 1. 检测纯乐器/无主唱
    if not heard or len(heard.strip()) == 0:
        status = "SILENT_OR_INSTRUMENTAL"
        reason = "前30秒无有效人声或音频静音"
    elif any(k in norm_heard for k in ['zither', 'harp', 'instrumental', 'piano', 'guitar', 'solo']):
        status = "INSTRUMENTAL_ONLY"
        reason = f"检出纯器乐伴奏无主唱 (听音: {heard})"
    # 2. 检测串歌 (例如唱的是三万英尺)
    elif norm_title not in norm_heard:
        # 如果唱词里完全没有这首歌的名词，检查是否包含了明显其他名曲
        if '飞机正在抵抗地球' in norm_heard and '三万英尺' not in title:
            status = "MISMATCH_SERIOUS"
            reason = f"严重串歌: 实唱为《三万英尺》 (听音: '{heard}')"
        elif '苦涩的沙' in norm_heard or '晴空万里' in norm_heard:
            if '水手' not in title:
                status = "MISMATCH_SERIOUS"
                reason = f"严重串歌: 实唱为《水手》"
            else:
                # 歌名叫水手，但是郑智化的原声！
                # 检查 ID3 标签或时长
                id3_artist = cur_tags.get('TAG:ARTIST') or cur_tags.get('ARTIST') or ""
                if '郑智化' in id3_artist:
                    status = "WRONG_ARTIST"
                    reason = f"偷换原唱: 歌手为郑智化而非老爹"

    # 3. ID3 标签非迪克牛仔检测
    id3_artist = cur_tags.get('TAG:ARTIST') or cur_tags.get('ARTIST') or cur_tags.get('TPE1') or ""
    if id3_artist and '迪克牛仔' not in id3_artist and id3_artist.strip() != '':
        status = "WRONG_ARTIST"
        reason = f"ID3歌手标注为: {id3_artist} (非迪克牛仔!)"

    # 4. 时长差异检测 (相差超过 20 秒)
    if off_info and abs(cur_dur - off_info['duration']) > 20:
        if status == "PASS":
            status = "SUSPECT_DURATION"
            reason = f"时长与官方不符: 当前 {cur_dur:.1f}s vs 官方 {off_info['duration']}s"

    return {
        "id": sid,
        "album": alb,
        "title": title,
        "path": path,
        "lrc_path": lrc_path,
        "current_duration": cur_dur,
        "official_info": off_info,
        "tags": cur_tags,
        "whisper_heard": heard,
        "status": status,
        "reason": reason
    }

def main():
    print("=" * 80)
    print("🎸 迪克牛仔全专 72 首 AI 听音辨曲地毯式普查启动")
    print("=" * 80)

    resp = requests.get(D1_SONGS_URL, timeout=30)
    data = resp.json().get('data', [])
    dick_data = None
    for a in data:
        if '迪克牛仔' in a.get('name', ''):
            dick_data = a
            break

    if not dick_data:
        print("❌ 未在 D1 找到迪克牛仔！")
        return

    all_tracks = []
    for alb in dick_data.get('albums', []):
        albtitle = alb.get('title')
        for s in alb.get('songs', []):
            all_tracks.append({
                'id': s.get('id'),
                'album': albtitle,
                'title': s.get('title'),
                'path': s.get('path'),
                'lrc_path': s.get('lrc_path')
            })

    print(f"📊 待普查迪克牛仔全量曲目: {len(all_tracks)} 首 (涵盖 7 张大碟)")

    results = []
    for idx, t in enumerate(all_tracks, 1):
        print(f"[{idx:02d}/{len(all_tracks):02d}] 正在听辨: 《{t['album']}》 - 《{t['title']}》...", end="", flush=True)
        res = audit_song(t)
        results.append(res)
        st = res['status']
        if st == "PASS":
            print(f" -> 🟢 PASS")
        else:
            print(f" -> 🔴 {st} ({res['reason']})")
        time.sleep(1.0)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    abnormal = [r for r in results if r['status'] != 'PASS']
    print("\n" + "=" * 80)
    print(f"🏁 迪克牛仔全专听音审计完成! 报告已保存至 {REPORT_FILE}")
    print(f"  • 总曲目数: {len(results)} 首")
    print(f"  • 合格曲目: {len(results) - len(abnormal)} 首")
    print(f"  • 异常/需重制曲目: {len(abnormal)} 首")
    print("=" * 80)

if __name__ == "__main__":
    main()
