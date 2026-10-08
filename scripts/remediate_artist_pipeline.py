#!/usr/bin/env python3
"""
核心华语歌手全自动化单人独立闭环治理流水线 (remediate_artist_pipeline.py)
=============================================================================
功能：针对指定歌手，读取 AUDIT_{artist}_DUAL_PIPELINE.json 审计报告，
自动分流执行：
1. 【歌词清洗与归正】(REPLACE_LYRIC_ONLY)：
   - Kugou/Netease 官方正版时间轴 LRC 采录与门禁检验
   - 推流至 Account 12 R2 桶
   - 批量原子更新 D1 数据库 lrc_path
2. 【母带置换与404复活】(REPLACE_AUDIO_MASTER / REPLACE_AUDIO_AND_LYRIC)：
   - YouTube 官方 Topic / 录音室母带精准采录 (时长容差 <= 8s)
   - FFmpeg EBU R128 (-14 LUFS, 320kbps CBR, 44100Hz) 标准母带压制
   - 推流至 Account 12 R2 桶并配套正版歌词
   - 调用 D1 /api/admin/songs/batch-light 原子切链点亮
3. 【终极全盘回归验证】：
   - 全盘曲目 CDN HTTP 200/206 状态探测
   - 输出独立治理验收日志
"""

import os, sys, json, time, re, subprocess, tempfile, base64, argparse
import requests, boto3, zhconv
from pathlib import Path
import concurrent.futures

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
CACHE_DIR = Path("/tmp/remediate_audio_cache")
CACHE_DIR.mkdir(exist_ok=True)

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

def sanitize_key_part(p: str) -> str:
    if not p: return ""
    return re.sub(r'[\?\#\:\*\"\<\|\>]', '', p).strip()

def clean_text(t: str) -> str:
    if not t: return ""
    t = zhconv.convert(t, 'zh-cn')
    t = re.sub(r'[\(（\[【].*?[\)）\]】]', '', t)
    t = re.sub(r'[^\w\u4e00-\u9fa5]', '', t)
    return t.lower()

def compute_similarity(t1: str, t2: str) -> float:
    if not t1 or not t2: return 0.0
    has_hanzi = bool(re.search(r'[\u4e00-\u9fa5]', t1 + t2))
    if has_hanzi:
        c1 = clean_text(t1)
        c2 = clean_text(t2)
        if not c1 or not c2: return 0.0
        s1, s2 = set(c1), set(c2)
        inter = len(s1.intersection(s2))
        union = len(s1.union(s2))
        return inter / max(union, 1)
    else:
        w1 = set(re.findall(r'[a-zA-Z]{2,}', t1.lower()))
        w2 = set(re.findall(r'[a-zA-Z]{2,}', t2.lower()))
        if not w1 or not w2: return 0.0
        inter = len(w1.intersection(w2))
        union = len(w1.union(w2))
        return inter / max(union, 1)

def fetch_official_lrc(artist: str, title: str, album: str = "") -> str:
    clean_target = clean_text(title)
    q = f"{artist} {title}"
    clean_alb = clean_text(album)
    
    # 1. 尝试 Kugou 源
    try:
        url = f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={requests.utils.quote(q)}&page=1&pagesize=8"
        r = requests.get(url, timeout=5).json()
        songs = r.get("data", {}).get("info", [])
        best_candidate = None
        for s in songs:
            sname = s.get("songname", "")
            s_art = s.get("singername", "")
            dur = s.get("duration", 0)
            h = s.get("hash", "")
            s_alb = clean_text(s.get("album_name", ""))
            is_live = any(kw in sname.lower() for kw in ["live", "演唱会", "伴奏", "instrumental"])
            if (clean_target in clean_text(sname) or clean_text(sname) in clean_target) and clean_text(artist) in clean_text(s_art) and not is_live and dur > 10:
                candidate = (dur, h)
                if clean_alb and (clean_alb in s_alb or s_alb in clean_alb):
                    best_candidate = candidate
                    break
                if not best_candidate:
                    best_candidate = candidate
        if best_candidate:
            dur, h = best_candidate
            lr_search = f"http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword={requests.utils.quote(q)}&duration={dur*1000}&hash={h}"
            cd = requests.get(lr_search, timeout=5).json().get("candidates", [])
            if cd:
                cid, akey = cd[0].get("id"), cd[0].get("accesskey")
                dl = requests.get(f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cid}&accesskey={akey}&fmt=lrc&charset=utf8", timeout=5).json()
                if dl.get("content"):
                    return base64.b64decode(dl["content"]).decode("utf-8")
    except Exception:
        pass

    # 2. 尝试网易云源
    try:
        r = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": q, "type": 1, "limit": 6},
            headers={"User-Agent": "Mozilla/5.0"},
            proxies=PROXIES, timeout=8
        )
        songs = r.json().get("result", {}).get("songs", [])
        for s in songs:
            clean_sname = clean_text(s.get("name", ""))
            sartists = [a["name"] for a in s.get("ar", [])]
            al_name = s.get("al", {}).get("name", "")
            is_live = any(kw in al_name.lower() or kw in s.get("name", "").lower() for kw in ["live", "演唱会"])
            artist_ok = any(clean_text(artist) in clean_text(a) for a in sartists)
            if (clean_target in clean_sname or clean_sname in clean_target) and artist_ok and not is_live:
                lr = requests.get(
                    f"https://music.163.com/api/song/lyric?os=pc&id={s['id']}&lv=-1&kv=-1&tv=-1",
                    headers={"User-Agent": "Mozilla/5.0"}, proxies=PROXIES, timeout=8
                )
                lrc_txt = lr.json().get("lrc", {}).get("lyric", "")
                if lrc_txt and len(lrc_txt) > 30:
                    return lrc_txt
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
            f"ytsearch6:{q}"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=18)
            for line in res.stdout.splitlines():
                if not line.strip(): continue
                d = json.loads(line)
                vid = d.get("id")
                dur = d.get("duration", 0)
                tit = d.get("title", "")
                
                is_bad = any(kw in tit.lower() for kw in ["live", "演唱会", "伴奏", "instrumental", "karaoke", "歌单", "合集"])
                if is_bad: continue
                
                clean_vtit = clean_text(tit)
                has_title_kw = (clean_tit in clean_vtit or clean_vtit in clean_tit)
                is_fallback_dur = (abs(target_dur - 240.0) < 1e-3)
                
                if is_fallback_dur and has_title_kw and 100 <= dur <= 450:
                    best_vid = vid
                    break
                else:
                    diff = abs(dur - target_dur)
                    if diff <= 8 and diff < min_diff:
                        min_diff = diff
                        best_vid = vid
                        break
        except Exception:
            pass
        if best_vid and min_diff <= 3:
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
        r = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=90)
        return os.path.exists(out_file) and os.path.getsize(out_file) > 100000
    except Exception:
        return False

def normalize_audio(in_file: str, out_file: str) -> float | None:
    cmd = [
        "ffmpeg", "-y", "-i", in_file,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-b:a", "320k", "-ar", "44100",
        out_file
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
        if os.path.exists(out_file) and os.path.getsize(out_file) > 100000:
            p_res = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_entries", "format=duration", out_file
            ], capture_output=True, text=True)
            dur = float(json.loads(p_res.stdout).get("format", {}).get("duration", 0))
            return dur
    except Exception:
        pass
    return None

def build_artist_song_id_map(artist: str) -> dict:
    """从本地 batches_v2 SQL 拓扑精准还原该歌手所有歌曲的真实 song_id"""
    art_id = None
    try:
        with open(BASE_DIR / "tmp/batches_v2/01_artists.sql", "r", encoding="utf-8") as f:
            for line in f:
                if f"'{artist}'" in line:
                    m = re.match(r'INSERT INTO \"artists\" VALUES\((\d+),', line)
                    if m:
                        art_id = int(m.group(1))
                        break
        if not art_id:
            return {}
            
        alb_map = {}
        with open(BASE_DIR / "tmp/batches_v2/02_albums.sql", "r", encoding="utf-8") as f:
            for line in f:
                if f",{art_id}," in line:
                    m = re.match(r'INSERT INTO \"albums\" VALUES\((\d+),\d+,\'((?:[^\']|\'\')+)\'', line)
                    if m:
                        alb_map[int(m.group(1))] = m.group(2).replace("''", "'")
                        
        alb_songs = {}
        for sf in sorted((BASE_DIR / "tmp/batches_v2").glob("songs_batch_*.sql")):
            with open(sf, "r", encoding="utf-8") as f:
                for line in f:
                    if f",{art_id}," in line:
                        m = re.match(r'INSERT INTO \"songs\" VALUES\((\d+),\d+,(\d+),\'((?:[^\']|\'\')+)\',.*?,(\d+),\'primary\'\);', line)
                        if m:
                            sid, aid, tit, tidx = int(m.group(1)), int(m.group(2)), m.group(3).replace("''", "'"), int(m.group(4))
                            if aid not in alb_songs: alb_songs[aid] = []
                            alb_songs[aid].append((sid, tidx, tit))
                            
        for aid in alb_songs:
            alb_songs[aid].sort(key=lambda x: x[1])
            
        return {"art_id": art_id, "alb_map": alb_map, "alb_songs": alb_songs}
    except Exception as e:
        print(f"⚠️ 构建拓扑映射失败: {e}")
        return {}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist", type=str, required=True, help="歌手名称")
    args = parser.parse_args()
    artist = args.artist
    
    report_file = REPORTS_DIR / f"AUDIT_{artist}_DUAL_PIPELINE.json"
    if not report_file.exists():
        print(f"❌ 审计报告不存在: {report_file}，请先执行双轨正交审计流水线！")
        sys.exit(1)
        
    with open(report_file, "r", encoding="utf-8") as f:
        audit_data = json.load(f)
        
    real_problems = audit_data.get("real_problems", [])
    print("=" * 60)
    print(f" 核心华语歌手全自动化单人闭环治理流水线: 【{artist}】")
    print(f" 确诊实锤真问题总数: {len(real_problems)} 首")
    print("=" * 60)
    
    if not real_problems:
        print("🎉 该歌手经双轨正交审计验证，全盘健康满格，无需治理！")
        return

    # 拓扑物理找回缺失的 song.id
    topo = build_artist_song_id_map(artist)
    alb_songs = topo.get("alb_songs", {})
    alb_map = topo.get("alb_map", {})
    if alb_songs:
        try:
            q_art = requests.utils.quote(artist)
            r_art = requests.get(f"https://m-api.changgepd.ccwu.cc/api/songs?artist={q_art}", proxies=PROXIES, timeout=15)
            remote_albs = r_art.json().get("data", [])[0].get("albums", [])
            
            # 为每张专辑定位真实的 album_id
            album_to_aid = {}
            for ra in remote_albs:
                rtitle = ra.get("title")
                # 策略 1: 优先专辑名直接语义匹配
                for aid, atitle in alb_map.items():
                    if clean_text(rtitle) == clean_text(atitle) or atitle in rtitle or rtitle in atitle:
                        album_to_aid[rtitle] = aid
                        break
                # 策略 2: 既有曲目 ID 反查兜底
                if rtitle not in album_to_aid:
                    for s in ra.get("songs", []):
                        p = (s.get("path") or "") + (s.get("lrc_path") or "")
                        m = re.search(r"s_(\d+)\.", p)
                        if m:
                            sid = int(m.group(1))
                            for aid, slist in alb_songs.items():
                                if any(x[0] == sid for x in slist):
                                    album_to_aid[rtitle] = aid
                                    break
                        if rtitle in album_to_aid:
                            break
                        
            # 对 real_problems 赋上 song_id
            for p in real_problems:
                s = p["song"]
                if s.get("id") is None:
                    alb = s.get("album")
                    aid = album_to_aid.get(alb)
                    if aid and aid in alb_songs:
                        slist = alb_songs[aid]
                        stit = s.get("title")
                        # 策略 1: 精确歌名匹配
                        matched_sid = None
                        for l_sid, l_tidx, l_tit in slist:
                            if clean_text(stit) == clean_text(l_tit):
                                matched_sid = l_sid
                                break
                        # 策略 2: 按 remote 专辑内的曲序匹配
                        if matched_sid is None:
                            for ra in remote_albs:
                                if ra.get("title") == alb:
                                    for s_idx, r_song in enumerate(ra.get("songs", [])):
                                        if clean_text(r_song.get("title")) == clean_text(stit):
                                            if s_idx < len(slist):
                                                matched_sid = slist[s_idx][0]
                                            break
                                    break
                        if matched_sid is not None:
                            s["id"] = matched_sid
        except Exception as e:
            print(f"⚠️ 拓扑找回异常: {e}")
            
    lyric_tasks = []
    audio_tasks = []
    
    for p in real_problems:
        s = p["song"]
        cat = p.get("remediation_category")
        st1 = p.get("stage1_issues", [])
        dt = p.get("details", {})
        stu = dt.get("studio_dur") or 240.0
        
        is_404 = any("无法获取音频" in iss for iss in st1)
        is_audio = cat in ["REPLACE_AUDIO_MASTER", "REPLACE_AUDIO_AND_LYRIC"] or is_404
        
        if is_audio:
            audio_tasks.append({
                "song": s,
                "target_dur": stu,
                "is_404": is_404,
                "issues": p.get("confirmed_issues", [])
            })
        else:
            lyric_tasks.append({
                "song": s,
                "issues": p.get("confirmed_issues", [])
            })
            
    print(f"治理分类排布: 纯歌词清洗 {len(lyric_tasks)} 首 | 音频/母带置换与404复活 {len(audio_tasks)} 首\n")
    
    # -------------------------------------------------------------
    # 步骤 1: 纯歌词清洗与置换
    # -------------------------------------------------------------
    lyric_success = []
    if lyric_tasks:
        print(f">>> [梯队 1] 启动纯歌词清洗与 R2 推流 (共 {len(lyric_tasks)} 首)...")
        for idx, t in enumerate(lyric_tasks, 1):
            s = t["song"]
            sid = s.get("id")
            tit = s.get("title")
            alb = s.get("album")
            old_audio = s.get("path")
            
            lrc_content = fetch_official_lrc(artist, tit, alb)
            if not lrc_content or len(lrc_content) < 30:
                print(f"  ⚠️ [{idx}/{len(lyric_tasks)}] 未拉取到有效官方歌词: 《{tit}》")
                continue
                
            safe_alb = sanitize_key_part(alb)
            r2_key = f"music/{artist}/{safe_alb}/s_{sid}.lrc"
            try:
                s3.put_object(
                    Bucket=bucket_name,
                    Key=r2_key,
                    Body=lrc_content.encode("utf-8"),
                    ContentType="text/plain; charset=utf-8"
                )
                pub_lrc = f"{public_base}/{r2_key}"
                lyric_success.append({
                    "id": int(sid),
                    "file_path": old_audio,
                    "lrc_path": pub_lrc
                })
                print(f"  ✨ [{idx}/{len(lyric_tasks)}] 歌词清洗推流成功: 《{tit}》[{alb}]")
            except Exception as e:
                print(f"  ❌ [{idx}/{len(lyric_tasks)}] 推流失败: 《{tit}》 -> {e}")
                
        # 批量入库
        if lyric_success:
            print(f"\n>>> 批量提交生产环境 D1 点亮纯歌词更新 ({len(lyric_success)} 首)...")
            sess = requests.Session()
            sess.trust_env = False
            for item in lyric_success:
                try:
                    r = sess.post(
                        "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light",
                        json={"updates": [item]},
                        timeout=12
                    )
                    if r.status_code != 200:
                        print(f"  ⚠️ D1 单条更新返回: id={item['id']} {r.status_code} | {r.text[:60]}")
                except Exception as e:
                    print(f"  ❌ D1 更新异常: id={item['id']} -> {e}")
            print(f"  ⚡ D1 纯歌词原子点亮全部提交完毕！")

    # -------------------------------------------------------------
    # 步骤 2: 音频母带置换与 404 复活
    # -------------------------------------------------------------
    audio_success = []
    if audio_tasks:
        print(f"\n>>> [梯队 2] 启动音频母带置换与404复活流水线 (共 {len(audio_tasks)} 首)...")
        sess = requests.Session()
        sess.trust_env = False
        
        for idx, t in enumerate(audio_tasks, 1):
            s = t["song"]
            sid = s.get("id")
            tit = s.get("title")
            alb = s.get("album")
            tdur = t["target_dur"]
            
            print(f"[{idx}/{len(audio_tasks)}] 正在置换: 《{tit}》[{alb}] (基准时长: {tdur:.0f}s)...")
            raw_tmp = str(CACHE_DIR / f"raw_{artist}_{sid}.webm")
            norm_mp3 = str(CACHE_DIR / f"norm_{artist}_{sid}.mp3")
            
            ok = search_and_download_master(artist, tit, tdur, raw_tmp)
            if not ok:
                print(f"  ❌ 采录失败: 未能在官方源命中时配合格母带")
                continue
                
            real_dur = normalize_audio(raw_tmp, norm_mp3)
            if not real_dur:
                print(f"  ❌ 压制失败")
                if os.path.exists(raw_tmp): os.unlink(raw_tmp)
                continue
                
            safe_alb = sanitize_key_part(alb)
            r2_audio_key = f"music/{artist}/{safe_alb}/s_{sid}.mp3"
            r2_lrc_key = f"music/{artist}/{safe_alb}/s_{sid}.lrc"
            try:
                with open(norm_mp3, "rb") as mf:
                    s3.put_object(
                        Bucket=bucket_name,
                        Key=r2_audio_key,
                        Body=mf,
                        ContentType="audio/mpeg"
                    )
                pub_audio_url = f"{public_base}/{r2_audio_key}"
                
                # 同步拉取正版 LRC 并推流
                lrc_txt = fetch_official_lrc(artist, tit, alb)
                pub_lrc_url = s.get("lrc_path")
                if lrc_txt and len(lrc_txt) > 30:
                    s3.put_object(
                        Bucket=bucket_name,
                        Key=r2_lrc_key,
                        Body=lrc_txt.encode("utf-8"),
                        ContentType="text/plain; charset=utf-8"
                    )
                    pub_lrc_url = f"{public_base}/{r2_lrc_key}"
                    
                print(f"  ⚡ 推流成功: 时长 {real_dur:.1f}s -> {pub_audio_url}")
                
                # 原子点亮 D1
                d1_payload = {"updates": [{
                    "id": int(sid),
                    "file_path": pub_audio_url,
                    "lrc_path": pub_lrc_url
                }]}
                d1_ok = False
                for d1_attempt in range(3):
                    try:
                        r_d1 = sess.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json=d1_payload, timeout=20)
                        if r_d1.status_code == 200:
                            d1_ok = True
                            break
                        else:
                            time.sleep(1)
                    except Exception:
                        time.sleep(1)
                
                if d1_ok:
                    print(f"  🌟 D1 数据库原子点亮成功！")
                    audio_success.append({
                        "id": sid,
                        "title": tit,
                        "album": alb,
                        "duration": real_dur,
                        "path": pub_audio_url
                    })
                else:
                    print(f"  ⚠️ D1 点亮失败 (重试 3 次均未成功)")
            except Exception as e:
                print(f"  ❌ 推流/入库异常: {e}")
            finally:
                if os.path.exists(raw_tmp): os.unlink(raw_tmp)
                if os.path.exists(norm_mp3): os.unlink(norm_mp3)
                
    # -------------------------------------------------------------
    # 步骤 3: 终极全盘回归验证
    # -------------------------------------------------------------
    print("\n" + "=" * 60, flush=True)
    print(f"【{artist}】治理完成，启动全盘终极连通性回归验证 (25并发)...", flush=True)
    print("=" * 60, flush=True)
    r_all = requests.get(f"https://m-api.changgepd.ccwu.cc/api/songs?artist={artist}", timeout=15)
    all_art_data = r_all.json().get("data", [])[0]
    all_albs = all_art_data.get("albums", [])
    
    all_verify_items = []
    for alb in all_albs:
        for s in alb.get("songs", []):
            all_verify_items.append((s.get("title"), alb.get("title"), s.get("path"), s.get("lrc_path"), s.get("id")))

    total_songs = len(all_verify_items)
    
    def _verify_one(item):
        tit, alb, p, lp, sid = item
        if not p:
            return (tit, alb, False, "缺少音频路径")
        ok = False
        last_err = ""
        for attempt in range(2):
            try:
                r_head = requests.head(p, proxies=PROXIES, timeout=8)
                if r_head.status_code in [200, 206]:
                    ok = True
                    break
                else:
                    last_err = f"音频 HTTP {r_head.status_code}"
            except Exception as e:
                last_err = f"网络超时: {e}"
        return (tit, alb, ok, last_err)

    total_verified = 0
    broken_songs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as ex:
        results = list(ex.map(_verify_one, all_verify_items))

    for tit, alb, ok, err in results:
        if ok:
            total_verified += 1
        else:
            broken_songs.append((tit, alb, err))

    print(f"验收结果: 全盘 {total_songs} 首中，成功点亮连通 {total_verified} 首", flush=True)
    if broken_songs:
        print(f"⚠️ 仍存在 {len(broken_songs)} 首异常曲目:", flush=True)
        for b in broken_songs[:10]:
            print(f"   - 《{b[0]}》[{b[1]}]: {b[2]}", flush=True)
    else:
        print(f"🎉 100% 满格点亮！零断链、零死链！", flush=True)
        
    # 保存治理闭环日志
    remedy_log = {
        "artist": artist,
        "finish_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_songs": total_songs,
        "verified_healthy": total_verified,
        "lyric_fixed": len(lyric_success),
        "audio_fixed": len(audio_success),
        "broken_songs": broken_songs
    }
    with open(REPORTS_DIR / f"REMEDIATION_{artist}_LOG.json", "w", encoding="utf-8") as f:
        json.dump(remedy_log, f, ensure_ascii=False, indent=2)
    print(f"治理闭环报告已保存至: {REPORTS_DIR / f'REMEDIATION_{artist}_LOG.json'}")

if __name__ == "__main__":
    main()
