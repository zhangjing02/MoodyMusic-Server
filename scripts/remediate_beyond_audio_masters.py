#!/usr/bin/env python3
"""
Beyond 音频母带置换与 404 断链全量闭环流水线 (remediate_beyond_audio_masters.py)
=============================================================================
支持对 146 首母带异常曲目（超长 Live、腰斩截断、错位）以及 404 断链曲目
实施高精度单线程稳健采录、EBU R128 标准化压制与 D1 生产网关逐单首即时原子点亮。
支持断点续传。
"""

import os, sys, json, time, re, subprocess, tempfile, boto3, requests, zhconv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
AUDIT_FILE = REPORTS_DIR / "AUDIT_Beyond_DUAL_PIPELINE.json"
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

def build_schema_id_map():
    albums = {}
    with open(SCHEMA_FILE) as f:
        for line in f:
            if line.startswith('INSERT INTO "albums" VALUES('):
                content = line[len('INSERT INTO "albums" VALUES('):-3]
                parts = [p.strip().strip("\x27\"") for p in re.split(r",(?=(?:[^\x27\"]*[\x27\"][^\x27\"]*[\x27\"])*[^\x27\"]*$)", content)]
                if len(parts) >= 3 and parts[1] == "4":
                    albums[parts[2]] = int(parts[0])

    alias_map = {
        "猶豫": 36,
        "猶豫 (超越時代紀念版)": 32,
        "Deliberate You Yu": 36,
        "Beyond Deliberate You Yu ( Chao Yue Shi Dai Ji Nian Ban )": 32,
    }

    song_map = {}
    with open(SCHEMA_FILE) as f:
        for line in f:
            if line.startswith('INSERT INTO "songs" VALUES('):
                content = line[len('INSERT INTO "songs" VALUES('):-3]
                parts = [p.strip().strip("\x27\"") for p in re.split(r",(?=(?:[^\x27\"]*[\x27\"][^\x27\"]*[\x27\"])*[^\x27\"]*$)", content)]
                if len(parts) >= 14 and parts[1] == "4":
                    sid = int(parts[0])
                    aid = int(parts[2])
                    title = parts[3]
                    t_idx = int(parts[13]) if parts[13].isdigit() else 0
                    song_map[(aid, title)] = sid
                    song_map[(aid, t_idx)] = sid

    return albums, alias_map, song_map

def fetch_official_lrc(artist: str, title: str, album: str = "") -> str:
    clean_target = clean_text(title)
    q = f"{artist} {title}"
    clean_alb = clean_text(album)

    # 1. Kugou
    try:
        url = f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={requests.utils.quote(q)}&page=1&pagesize=8"
        r = requests.get(url, timeout=5).json()
        songs = r.get("data", {}).get("info", [])
        best_cand = None
        for s in songs:
            sname = s.get("songname", "")
            s_art = s.get("singername", "")
            dur = s.get("duration", 0)
            h = s.get("hash", "")
            s_alb = clean_text(s.get("album_name", ""))
            if (clean_target in clean_text(sname) or clean_text(sname) in clean_target) and clean_text(artist) in clean_text(s_art) and dur > 15:
                cand = (s, dur, h)
                if clean_alb and (clean_alb in s_alb or s_alb in clean_alb):
                    best_cand = cand
                    break
                if not best_cand:
                    best_cand = cand
        if best_cand:
            s, dur, h = best_cand
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

    # 2. Netease
    try:
        r = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": q, "type": 1, "limit": 6},
            headers={"User-Agent": "Mozilla/5.0"},
            proxies={"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"},
            timeout=6
        )
        songs = r.json().get("result", {}).get("songs", [])
        for s in songs:
            clean_sname = clean_text(s.get("name", ""))
            sartists = [a["name"] for a in s.get("ar", [])]
            al_name = s.get("al", {}).get("name", "").lower()
            is_live = any(kw in al_name or kw in s.get("name", "").lower() for kw in ["live", "演唱会", "concert"])
            artist_ok = any(clean_text(artist) in clean_text(a) for a in sartists)
            if (clean_target in clean_sname or clean_sname in clean_target) and artist_ok and not is_live:
                nid = s.get("id")
                lr = requests.get(
                    f"https://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1",
                    headers={"User-Agent": "Mozilla/5.0"},
                    proxies={"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"},
                    timeout=6
                )
                txt = lr.json().get("lrc", {}).get("lyric", "")
                if len(txt) > 50 and bool(re.search(r'\[\d{2}:\d{2}', txt)):
                    return txt
    except Exception:
        pass

    return ""

def search_and_download_master(artist: str, title: str, album: str, target_dur: float, out_file: str) -> bool:
    clean_tit = clean_text(title)
    queries = [
        f"{artist} {title} Topic",
        f"{artist} {title} {album}",
        f"{artist} {title} Official Audio",
        f"{artist} {title}"
    ]
    
    best_vid = None
    min_diff = 999
    
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
                
                is_bad = any(kw in tit.lower() for kw in ["live", "演唱会", "伴奏", "karaoke", "歌单", "合集", "reaction"])
                if is_bad: continue
                
                diff = abs(dur - target_dur) if target_dur > 0 else 0
                if target_dur <= 0 or (diff <= 10 and diff < min_diff):
                    min_diff = diff
                    best_vid = vid
                    break
        except Exception:
            pass
        if best_vid and (target_dur <= 0 or min_diff <= 3):
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
    print(" Beyond 音频母带置换与 404 断链重构流水线")
    print("==================================================")

    # 1. 载入审计报告
    with open(AUDIT_FILE) as f:
        audit_data = json.load(f)

    probs = audit_data["real_problems"]
    albums, alias_map, song_map = build_schema_id_map()

    # 2. 补齐 ID
    for p in probs:
        s = p["song"]
        if s.get("id") is None:
            alb_title = s["album"]
            aid = alias_map.get(alb_title) or albums.get(alb_title)
            if not aid:
                for at, id_val in albums.items():
                    if alb_title.lower() in at.lower() or at.lower() in alb_title.lower():
                        aid = id_val
                        break
            sid = song_map.get((aid, s["title"])) or song_map.get((aid, s.get("track_index")))
            if sid:
                s["id"] = sid

    # 3. 收集目标任务 (排除纯歌词修复的)
    audio_master_tasks = [p for p in probs if p.get("remediation_category") == "REPLACE_AUDIO_MASTER"]
    unlit_tasks = [p for p in probs if not p["song"].get("path") or "无法获取音频" in str(p.get("stage1_issues", []))]
    both_tasks = [p for p in probs if p.get("remediation_category") == "REPLACE_AUDIO_AND_LYRIC" and p not in unlit_tasks]
    target_tasks = audio_master_tasks + unlit_tasks + both_tasks

    print(f"待处理音频母带与断链重构曲目总数: {len(target_tasks)} 首\n")

    # 4. 载入断点记录
    progress = {}
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE) as pf:
                progress = json.load(pf)
        except:
            progress = {}

    print(f"已完成断点曲目: {len(progress)} 首\n")

    success_cnt = 0
    fail_cnt = 0

    for idx, p in enumerate(target_tasks, 1):
        s = p["song"]
        sid = s.get("id")
        title = s.get("title")
        album = s.get("album")
        key = f"{album}_{title}_{sid}"

        if not sid:
            print(f"[{idx}/{len(target_tasks)}] ⚠️ 跳过无 ID 歌曲: 《{title}》[{album}]")
            continue

        if key in progress and progress[key].get("d1_status") == "SUCCESS":
            print(f"[{idx}/{len(target_tasks)}] ⏩ 已在断点中完成: 《{title}》[{album}]")
            success_cnt += 1
            continue

        target_dur = float(p.get("details", {}).get("studio_dur") or 0)
        print(f"[{idx}/{len(target_tasks)}] 正在治理母带: 《{title}》[{album}] (录音室标称: {target_dur:.0f}s)...")

        raw_file = str(CACHE_DIR / f"raw_{sid}.webm")
        norm_file = str(CACHE_DIR / f"norm_{sid}.mp3")

        # 下载
        dl_ok = search_and_download_master("Beyond", title, album, target_dur, raw_file)
        if not dl_ok:
            print(f"  ❌ 采录失败: 官方源未检索到吻合录音室母带")
            fail_cnt += 1
            progress[key] = {"status": "DL_FAIL", "title": title, "album": album}
            with open(PROGRESS_FILE, "w") as pf: json.dump(progress, pf, ensure_ascii=False, indent=2)
            time.sleep(1)
            continue

        # 压制
        norm_ok = normalize_audio(raw_file, norm_file)
        if not norm_ok:
            print(f"  ❌ 压制失败")
            fail_cnt += 1
            if os.path.exists(raw_file): os.unlink(raw_file)
            progress[key] = {"status": "NORM_FAIL", "title": title, "album": album}
            with open(PROGRESS_FILE, "w") as pf: json.dump(progress, pf, ensure_ascii=False, indent=2)
            time.sleep(1)
            continue

        # 获取 LRC
        lrc_text = fetch_official_lrc("Beyond", title, album)

        # 推送到 R2
        rkey_mp3 = f"music/Beyond/{album}/s_{sid}.mp3"
        rkey_lrc = f"music/Beyond/{album}/s_{sid}.lrc"
        new_mp3_url = push_file_to_r2(norm_file, rkey_mp3, "audio/mpeg")
        new_lrc_url = push_text_to_r2(lrc_text, rkey_lrc) if lrc_text else s.get("lrc_path")

        # 清理临时文件
        if os.path.exists(raw_file): os.unlink(raw_file)
        if os.path.exists(norm_file): os.unlink(norm_file)

        # 即时原子点亮 D1
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
                success_cnt += 1
            else:
                print(f"  ⚠️ [D1 提交异常] {r.status_code}: {r.text[:100]}")
                progress[key] = {
                    "status": "SUCCESS",
                    "d1_status": "FAIL",
                    "file_path": new_mp3_url,
                    "lrc_path": new_lrc_url,
                    "title": title,
                    "album": album
                }
        except Exception as e:
            print(f"  ⚠️ [D1 请求异常] {e}")

        # 持久化进度
        with open(PROGRESS_FILE, "w", encoding="utf-8") as pf:
            json.dump(progress, pf, ensure_ascii=False, indent=2)

        # 保护性轻微冷却，防止 YouTube 封控
        time.sleep(1.5)

    print("\n" + "="*50)
    print("【Beyond】音频母带置换与断链重构全流程闭环！")
    print(f"成功点亮: {success_cnt} 首 | 失败: {fail_cnt} 首")
    print(f"断点记录保存在: {PROGRESS_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
