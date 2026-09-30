#!/usr/bin/env python3
"""
Beyond 剩余 35 首母带与断链专项攻坚流水线 (remediate_beyond_remaining_35.py)
=============================================================================
针对因 target_dur 偏差误判过滤的 35 首核心曲目（如《歲月無聲》《俾面派對》《無淚的遺憾》《無悔這一生》等），
实施官方 Topic (Universal Music Group / Cinepoly / 滚石) 权威母带精准采录与 D1 即时点亮。
"""

import os, sys, json, time, re, subprocess, tempfile, boto3, requests, zhconv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
PROGRESS_FILE = REPORTS_DIR / "BEYOND_AUDIO_MASTERS_PROGRESS.json"
SCHEMA_FILE = BASE_DIR / "cloudflare-worker" / "schema.sql"
CACHE_DIR = Path("/tmp/beyond_audio_cache")
CACHE_DIR.mkdir(exist_ok=True)

with open(BASE_DIR / "r2_config.json") as f:
    cfg = json.load(f)

acct12 = cfg['buckets']['account_12']
s3 = boto3.client(
    's3',
    endpoint_url=acct12['endpoint_url'],
    aws_access_key_id=acct12['access_key_id'],
    aws_secret_access_key=acct12['secret_access_key'],
    region_name='auto'
)
bucket_name = acct12['name']
public_base = acct12['public_url']

D1_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
d1_session = requests.Session()
d1_session.trust_env = False

def clean_text(t: str) -> str:
    if not t: return ""
    t = zhconv.convert(t, 'zh-cn')
    t = re.sub(r'[\(（\[【].*?[\)）\]】]', '', t)
    t = re.sub(r'[^\w\u4e00-\u9fa5]', '', t)
    return t.lower()

def search_official_topic_master(artist: str, title: str, album: str, out_file: str) -> bool:
    clean_tit = clean_text(title)
    queries = [
        f"{artist} {title} Topic",
        f"{artist} {title} {album}",
        f"{artist} {title}"
    ]
    
    best_vid = None
    
    for q in queries:
        cmd = [
            "yt-dlp", "--proxy", "http://127.0.0.1:7897",
            "--dump-json", "--flat-playlist", "--no-playlist",
            f"ytsearch5:{q}"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=18)
            for line in res.stdout.splitlines():
                if not line.strip(): continue
                d = json.loads(line)
                vid = d.get("id")
                dur = d.get("duration", 0)
                tit = d.get("title", "")
                desc = d.get("description", "")
                ch = d.get("channel", "")
                
                # 排除现场、伴奏、翻唱
                is_bad = any(kw in tit.lower() for kw in ["live", "演唱会", "伴奏", "karaoke", "reaction", "歌单", "合集"])
                if is_bad and "live" not in clean_tit:
                    continue
                    
                # 优先官方 Topic (Provided to YouTube by Universal/Cinepoly/Rock)
                is_official = ("provided to youtube by" in desc.lower()) or (ch == artist)
                if is_official and dur > 30:
                    best_vid = vid
                    break
                elif not best_vid and dur > 30 and (clean_tit in clean_text(tit) or clean_text(tit) in clean_tit):
                    best_vid = vid
        except Exception:
            pass
        if best_vid:
            break
            
    if not best_vid:
        return False
        
    dl_cmd = [
        "yt-dlp", "--proxy", "http://127.0.0.1:7897",
        "-f", "bestaudio/best",
        "-o", out_file,
        f"https://www.youtube.com/watch?v={best_vid}"
    ]
    try:
        subprocess.run(dl_cmd, capture_output=True, text=True, timeout=90)
        return os.path.exists(out_file) and os.path.getsize(out_file) > 100000
    except Exception:
        return False

def normalize_audio(in_file: str, out_file: str) -> bool:
    cmd = [
        "ffmpeg", "-y", "-i", in_file,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-b:a", "320k", "-ar", "44100",
        out_file
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
        return os.path.exists(out_file) and os.path.getsize(out_file) > 100000
    except Exception:
        return False

def fetch_official_lrc(artist: str, title: str, album: str = "") -> str:
    clean_target = clean_text(title)
    q = f"{artist} {title}"
    try:
        url = f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={requests.utils.quote(q)}&page=1&pagesize=5"
        r = requests.get(url, timeout=5).json()
        songs = r.get("data", {}).get("info", [])
        for s in songs:
            sname = s.get("songname", "")
            s_art = s.get("singername", "")
            dur = s.get("duration", 0)
            h = s.get("hash", "")
            if (clean_target in clean_text(sname) or clean_text(sname) in clean_target) and clean_text(artist) in clean_text(s_art) and dur > 15:
                lr_search = f"http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword={requests.utils.quote(q)}&duration={dur*1000}&hash={h}"
                cd = requests.get(lr_search, timeout=5).json().get("candidates", [])
                if cd:
                    cid, akey = cd[0].get("id"), cd[0].get("accesskey")
                    dl = requests.get(f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cid}&accesskey={akey}&fmt=lrc&charset=utf8", timeout=5).json()
                    if dl.get("content"):
                        import base64
                        txt = base64.b64decode(dl["content"]).decode("utf-8")
                        if len(txt) > 50 and bool(re.search(r'\[\d{2}:\d{2}', txt)):
                            return txt
    except Exception:
        pass
    return ""

def push_file_to_r2(local_path: str, remote_key: str, content_type: str) -> str:
    with open(local_path, "rb") as f:
        s3.put_object(
            Bucket=bucket_name,
            Key=remote_key,
            Body=f,
            ContentType=content_type
        )
    return f"{public_base}/{remote_key}"

def push_text_to_r2(text: str, remote_key: str) -> str:
    s3.put_object(
        Bucket=bucket_name,
        Key=remote_key,
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8"
    )
    return f"{public_base}/{remote_key}"

def main():
    print("==================================================")
    print(" Beyond 剩余 35 首母带与断链专项攻坚流水线")
    print("==================================================")

    with open(PROGRESS_FILE) as pf:
        progress = json.load(pf)

    failed_keys = [k for k, v in progress.items() if v.get("d1_status") != "SUCCESS"]
    print(f"待攻坚目标曲目: {len(failed_keys)} 首\n")

    remedy_success = 0

    for idx, key in enumerate(failed_keys, 1):
        item = progress[key]
        title = item.get("title")
        album = item.get("album")
        m = re.search(r"_(\d+)$", key)
        sid = int(m.group(1)) if m else None

        if not sid:
            continue

        print(f"[{idx}/{len(failed_keys)}] 深度攻坚官方母带: 《{title}》[{album}] (ID {sid})...")

        raw_file = str(CACHE_DIR / f"raw_remedy_{sid}.webm")
        norm_file = str(CACHE_DIR / f"norm_remedy_{sid}.mp3")

        dl_ok = search_official_topic_master("Beyond", title, album, raw_file)
        if not dl_ok:
            print(f"  ❌ 检索失败: 未能在官方源命中可用母带")
            time.sleep(1)
            continue

        norm_ok = normalize_audio(raw_file, norm_file)
        if not norm_ok:
            print(f"  ❌ 压制失败")
            if os.path.exists(raw_file): os.unlink(raw_file)
            time.sleep(1)
            continue

        lrc_text = fetch_official_lrc("Beyond", title, album)

        rkey_mp3 = f"music/Beyond/{album}/s_{sid}.mp3"
        rkey_lrc = f"music/Beyond/{album}/s_{sid}.lrc"
        new_mp3_url = push_file_to_r2(norm_file, rkey_mp3, "audio/mpeg")
        new_lrc_url = push_text_to_r2(lrc_text, rkey_lrc) if lrc_text else None

        if os.path.exists(raw_file): os.unlink(raw_file)
        if os.path.exists(norm_file): os.unlink(norm_file)

        # 原子点亮 D1
        d1_payload = {
            "updates": [{
                "id": int(sid),
                "file_path": new_mp3_url,
                "lrc_path": new_lrc_url or ""
            }]
        }
        try:
            r = d1_session.post(D1_URL, json=d1_payload, timeout=8)
            if r.status_code == 200 and r.json().get("code") == 200:
                print(f"  🚀 [D1 点亮成功] 《{title}》 -> R2 & D1 双链原子闭环！")
                progress[key] = {
                    "status": "SUCCESS",
                    "d1_status": "SUCCESS",
                    "file_path": new_mp3_url,
                    "lrc_path": new_lrc_url,
                    "title": title,
                    "album": album
                }
                remedy_success += 1
            else:
                print(f"  ⚠️ [D1 提交异常] {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"  ⚠️ [D1 请求异常] {e}")

        with open(PROGRESS_FILE, "w", encoding="utf-8") as pf:
            json.dump(progress, pf, ensure_ascii=False, indent=2)

        time.sleep(1.5)

    print("\n" + "="*50)
    print("【Beyond】35 首专项攻坚执行完毕！")
    print(f"新增攻坚成功点亮: {remedy_success} 首")
    print(f"最新进展保存在: {PROGRESS_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
