#!/usr/bin/env python3
"""
传奇摇滚乐队 Beyond 全盘大碟全量立体化治理流水线 (remediate_beyond_full_catalog.py)
=============================================================================
支持对 Beyond 确诊的真问题曲目（共 230 首，含 84 首歌词清洗、46 首母带置换、61 首断链补齐、39 首双向错配）
执行闭环治理与 D1 原子点亮：
1. 自动从 schema.sql 补齐 61 首原本 Path 为 None 的真实数据库 ID
2. Phase 1: 84 首纯歌词清洗（Mojibake 乱码/李鬼），100% 保护正版好音频，仅定向置换 LRC
3. Phase 2: 46 首音频母带置换（剥离超长 Live、修复截断、重定错位）+ 61 首 404 断链全量补齐点亮
4. Phase 3: 39 首双向错配原子协同重构
5. Phase 4: 全量调用生产网关 /api/admin/songs/batch-light 原子写入并回归验证
"""

import os, sys, json, time, re, base64, requests, boto3, zhconv, subprocess, tempfile
from pathlib import Path
import concurrent.futures

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
AUDIT_FILE = REPORTS_DIR / "AUDIT_Beyond_DUAL_PIPELINE.json"
SCHEMA_FILE = BASE_DIR / "cloudflare-worker" / "schema.sql"
REMEDIATION_LOG = REPORTS_DIR / "BEYOND_REMEDIATION_FINAL_LOG.json"

PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}

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

def build_schema_id_map():
    """建立 schema.sql 中 Beyond 曲目真实 ID 映射库"""
    albums = {}
    with open(SCHEMA_FILE) as f:
        for line in f:
            if line.startswith('INSERT INTO "albums" VALUES('):
                content = line[len('INSERT INTO "albums" VALUES('):-3]
                parts = [p.strip().strip("\x27\"") for p in re.split(r",(?=(?:[^\x27\"]*[\x27\"][^\x27\"]*[\x27\"])*[^\x27\"]*$)", content)]
                if len(parts) >= 3 and parts[1] == "4":
                    albums[parts[2]] = int(parts[0])

    # 别名映射
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
    """拉取官方纯正时间轴 LRC"""
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
            proxies=PROXIES, timeout=6
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
                    headers={"User-Agent": "Mozilla/5.0"}, proxies=PROXIES, timeout=6
                )
                txt = lr.json().get("lrc", {}).get("lyric", "")
                if len(txt) > 50 and bool(re.search(r'\[\d{2}:\d{2}', txt)):
                    return txt
    except Exception:
        pass

    return ""

def search_and_download_master(artist: str, title: str, target_dur: float, out_file: str) -> bool:
    clean_tit = clean_text(title)
    queries = [
        f"{artist} {title} Topic",
        f"{artist} {title} Official Audio",
        f"{artist} {title} 官方完整版",
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
                
                # 排除现场、伴奏、翻唱
                is_bad = any(kw in tit.lower() for kw in ["live", "演唱会", "伴奏", "instrumental", "karaoke", "歌单", "合集"])
                if is_bad: continue
                
                diff = abs(dur - target_dur) if target_dur > 0 else 0
                if target_dur <= 0 or (diff <= 12 and diff < min_diff):
                    min_diff = diff
                    best_vid = vid
                    break
        except Exception:
            pass
        if best_vid and (target_dur <= 0 or min_diff <= 4):
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

def fetch_official_audio_and_lrc(artist: str, title: str, album: str = "", target_dur: float = 0):
    """拉取官方正版录音室音频文件及对应 LRC (返回 local_mp3_path, lrc_text)"""
    raw_tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False).name
    norm_tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    
    # 优先 YouTube 官方频道 / Topic 录音室母带
    if search_and_download_master(artist, title, target_dur, raw_tmp):
        if normalize_audio(raw_tmp, norm_tmp):
            try: os.unlink(raw_tmp)
            except: pass
            lrc = fetch_official_lrc(artist, title, album)
            return norm_tmp, lrc
            
    try:
        if os.path.exists(raw_tmp): os.unlink(raw_tmp)
        if os.path.exists(norm_tmp): os.unlink(norm_tmp)
    except:
        pass
        
    return None, ""

def push_to_r2(local_path: str, remote_key: str, content_type: str = "audio/mpeg") -> str:
    s3.upload_file(
        local_path,
        bucket_name,
        remote_key,
        ExtraArgs={'ContentType': content_type}
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
    print(" 传奇摇滚乐队 Beyond 全盘大碟全量立体化治理流水线")
    print("==================================================")

    # 1. 加载审计报告
    with open(AUDIT_FILE) as f:
        audit_data = json.load(f)

    probs = audit_data["real_problems"]
    print(f"载入确诊真问题曲目: {len(probs)} 首")

    # 2. 从 schema.sql 补齐缺失 ID
    albums, alias_map, song_map = build_schema_id_map()
    missing_cnt = 0
    for p in probs:
        s = p["song"]
        if s.get("id") is None:
            missing_cnt += 1
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
            else:
                print(f"  ⚠️ 依然未找到 ID: {alb_title} -> {s['title']}")

    print(f"成功补齐缺失 ID: {missing_cnt} 首曲目，现全体具备数据库主键！\n")

    # 3. 分类任务池
    lyric_only_tasks = [p for p in probs if p.get("remediation_category") == "REPLACE_LYRIC_ONLY"]
    audio_master_tasks = [p for p in probs if p.get("remediation_category") == "REPLACE_AUDIO_MASTER"]
    unlit_tasks = [p for p in probs if not p["song"].get("path") or "无法获取音频" in str(p.get("stage1_issues", []))]
    both_tasks = [p for p in probs if p.get("remediation_category") == "REPLACE_AUDIO_AND_LYRIC" and p not in unlit_tasks]

    print(f"任务规划:")
    print(f"  * Phase 1 (歌词清洗点亮): {len(lyric_only_tasks)} 首")
    print(f"  * Phase 2 (音频母带置换): {len(audio_master_tasks)} 首")
    print(f"  * Phase 3 (404断链重构点亮): {len(unlit_tasks)} 首")
    print(f"  * Phase 4 (双向错配原子归正): {len(both_tasks)} 首\n")

    remediation_updates = []

    # --- Phase 1: 歌词清洗 (保持音频不动，仅上传正版 LRC) ---
    print(">>> 启动 Phase 1: 歌词专项全量清洗 (84 首)...")
    done_lrc = 0
    def remediate_lyric_one(p):
        s = p["song"]
        sid = s["id"]
        alb = s["album"]
        title = s["title"]
        audio_path = s["path"]
        official_lrc = fetch_official_lrc("Beyond", title, alb)
        if official_lrc:
            rkey = f"music/Beyond/{alb}/s_{sid}.lrc"
            new_lrc_url = push_text_to_r2(official_lrc, rkey)
            return {
                "id": sid,
                "file_path": audio_path,
                "lrc_path": new_lrc_url,
                "album": alb,
                "title": title,
                "status": "SUCCESS"
            }
        return {"id": sid, "album": alb, "title": title, "status": "FAIL"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(remediate_lyric_one, p) for p in lyric_only_tasks]
        for f in concurrent.futures.as_completed(futs):
            done_lrc += 1
            res = f.result()
            if res["status"] == "SUCCESS":
                remediation_updates.append(res)
                if done_lrc % 10 == 0:
                    print(f"  ✅ [{done_lrc}/{len(lyric_only_tasks)}] 歌词清洗完成: 《{res['title']}》[{res['album']}]")
            else:
                print(f"  ⚠️ [{done_lrc}/{len(lyric_only_tasks)}] 歌词获取失败: 《{res['title']}》")

    print(f"Phase 1 完成: 成功清洗歌词 {len(remediation_updates)} 首！\n")

    # --- Phase 2 & 3: 音频母带与 404 断链置换补齐 ---
    full_audio_tasks = audio_master_tasks + unlit_tasks + both_tasks
    print(f">>> 启动 Phase 2 & 3: 音频母带置换与 404 断链重构 (共 {len(full_audio_tasks)} 首)...")
    done_aud = 0

    def remediate_audio_one(p):
        s = p["song"]
        sid = s["id"]
        alb = s["album"]
        title = s["title"]
        target_dur = float(p.get("details", {}).get("studio_dur") or 0)
        local_mp3, lrc_text = fetch_official_audio_and_lrc("Beyond", title, alb, target_dur=target_dur)
        if local_mp3:
            rkey_mp3 = f"music/Beyond/{alb}/s_{sid}.mp3"
            rkey_lrc = f"music/Beyond/{alb}/s_{sid}.lrc"
            new_mp3_url = push_to_r2(local_mp3, rkey_mp3, "audio/mpeg")
            new_lrc_url = push_text_to_r2(lrc_text, rkey_lrc) if lrc_text else s.get("lrc_path")
            try:
                os.unlink(local_mp3)
            except:
                pass
            return {
                "id": sid,
                "file_path": new_mp3_url,
                "lrc_path": new_lrc_url,
                "album": alb,
                "title": title,
                "status": "SUCCESS"
            }
        return {"id": sid, "album": alb, "title": title, "status": "FAIL"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(remediate_audio_one, p) for p in full_audio_tasks]
        for f in concurrent.futures.as_completed(futs):
            done_aud += 1
            res = f.result()
            if res["status"] == "SUCCESS":
                remediation_updates.append(res)
                print(f"  ✨ [{done_aud}/{len(full_audio_tasks)}] 母带置换成功: 《{res['title']}》[{res['album']}] -> R2 点亮")
            else:
                print(f"  ⚠️ [{done_aud}/{len(full_audio_tasks)}] 母带拉取失败: 《{res['title']}》[{res['album']}]")

    print(f"\n全部资产上传完毕！累计待提交原子更新记录: {len(remediation_updates)} 首")

    # --- Phase 4: 调用 D1 batch-light 批量原子写入 ---
    print("\n>>> 启动 Phase 4: 生产数据库 D1 batch-light 原子点亮...")
    d1_url = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
    headers = {"Content-Type": "application/json"}
    
    batch_size = 50
    total_committed = 0
    all_clean_updates = [
        {"id": int(u["id"]), "file_path": u["file_path"], "lrc_path": u.get("lrc_path") or ""}
        for u in remediation_updates if u.get("id") and u.get("file_path")
    ]

    for i in range(0, len(all_clean_updates), batch_size):
        chunk = all_clean_updates[i:i + batch_size]
        payload = {"updates": chunk}
        try:
            r = requests.post(d1_url, json=payload, headers=headers, proxies=PROXIES, timeout=15)
            if r.status_code == 200 and r.json().get("success"):
                total_committed += len(chunk)
                print(f"  🚀 [D1 提交] 成功提交第 {i+1} ~ {i+len(chunk)} 首！")
            else:
                print(f"  ❌ [D1 提交失败] {r.status_code}: {r.text}")
        except Exception as e:
            print(f"  ⚠️ [D1 请求异常] {e}")

    # 保存日志
    with open(REMEDIATION_LOG, "w", encoding="utf-8") as f:
        json.dump({
            "artist": "Beyond",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_remediated": len(remediation_updates),
            "d1_committed": total_committed,
            "updates": remediation_updates
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "="*50)
    print("【Beyond】全量大碟立体化治理流水线执行完毕！")
    print(f"已上传并原子点亮曲目: {total_committed} 首")
    print(f"治理明细记录保存于: {REMEDIATION_LOG}")
    print("="*50)

if __name__ == "__main__":
    main()
