#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
《我是歌手》第二季 (12首) 与第三季 (13首) 工业级全自动化高可用治理与点亮脚本
==============================================================================
"""

import os
import sys
import json
import time
import urllib.parse
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = "/tmp/i_am_singer_s2_s3_work"
os.makedirs(WORK_DIR, exist_ok=True)

NODE_PATH = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"
PROXY_URL = "http://127.0.0.1:7897"
API_BASE = "https://m-api.changgepd.ccwu.cc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfgs = json.load(f)["buckets"]

r2_cfg = r2_cfgs["account_12"]
s3_client = boto3.client(
    "s3",
    endpoint_url=r2_cfg["endpoint_url"],
    aws_access_key_id=r2_cfg["access_key_id"],
    aws_secret_access_key=r2_cfg["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4", connect_timeout=15, read_timeout=30)
)
BUCKET_NAME = r2_cfg["name"]
PUBLIC_BASE = r2_cfg["public_url"].rstrip("/")

session = requests.Session()
session.trust_env = False

def safe_api_get(url, params=None, timeout=25, retries=3):
    for i in range(retries):
        try:
            r = session.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
        except Exception as e:
            if i == retries - 1:
                raise e
            time.sleep(1.5)
    return None

def safe_api_post(url, json_data=None, timeout=30, retries=3):
    for i in range(retries):
        try:
            r = session.post(url, json=json_data, headers=HEADERS, timeout=timeout)
            if r.status_code in [200, 201]:
                return r
        except Exception as e:
            if i == retries - 1:
                raise e
            time.sleep(1.5)
    return None

def fetch_lrc_multi(query: str) -> str:
    # 通道 1: 网易云原生接口 (直连超高成功率)
    try:
        r = requests.get(
            f"https://music.163.com/api/search/get/web?s={query}&type=1&limit=3",
            headers=HEADERS,
            timeout=6
        ).json()
        songs = r.get("result", {}).get("songs", [])
        if songs:
            sid = songs[0]["id"]
            lr = requests.get(
                f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1",
                headers=HEADERS,
                timeout=6
            ).json()
            lrc_text = lr.get("lrc", {}).get("lyric", "")
            if lrc_text and len(lrc_text.strip()) > 50:
                clean_lines = [l for l in lrc_text.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
                return "\n".join(clean_lines).strip()
    except Exception:
        pass

    # 通道 2: syncedlyrics
    try:
        lrc_text = syncedlyrics.search(query)
        if lrc_text and len(lrc_text.strip()) > 50:
            clean_lines = [l for l in lrc_text.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
            return "\n".join(clean_lines).strip()
    except Exception:
        pass

    return ""

def check_r2_object_exists(key: str) -> int:
    try:
        res = s3_client.head_object(Bucket=BUCKET_NAME, Key=key)
        return int(res.get("ContentLength", 0))
    except Exception:
        return 0

# ==============================================================================
# 第二季 (2014) 执行流水线
# ==============================================================================
def process_season_2():
    aid = 1946
    aname = "第二季 (2014)"
    print("\n" + "=" * 80)
    print("🚀 [SEASON 2] 开始处理《我是歌手》第二季 (2014)...")
    print("=" * 80)

    # 1. 检查张杰《勿忘心安》(31110)
    mp3_key = f"music/我是歌手/{aname}/s_31110.mp3"
    lrc_key = f"lyrics/我是歌手/{aname}/s_31110.lrc"
    
    if check_r2_object_exists(mp3_key) < 1000000:
        print("▶ [31110] 正在处理张杰《勿忘心安》音频压制与上传...")
        raw_source = "/tmp/test_zhangjie.webm"
        if not os.path.exists(raw_source) or os.path.getsize(raw_source) < 500000:
            cmd = ["yt-dlp", "--proxy", PROXY_URL, "-f", "ba/b", "-o", raw_source, "https://www.youtube.com/watch?v=jJFJkKulRws"]
            subprocess.run(cmd, check=True)

        norm_mp3 = f"{WORK_DIR}/s_31110.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-i", raw_source,
            "-vn", "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1", "-ar", "44100",
            norm_mp3
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        s3_client.upload_file(norm_mp3, BUCKET_NAME, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        print(f"   ✅ 张杰《勿忘心安》音频上传成功: {mp3_key}")

        lrc_text = fetch_lrc_multi("张杰 勿忘心安")
        if lrc_text:
            s3_client.put_object(Bucket=BUCKET_NAME, Key=lrc_key, Body=lrc_text.encode("utf-8"), ContentType="text/plain; charset=utf-8")
            print(f"   📄 张杰《勿忘心安》歌词上传成功: {lrc_key} ({len(lrc_text)} 字节)")

    # 2. 检查品冠与动力火车歌词补充 (如果 R2 缺失)
    for sid, q in [(31111, "品冠 掌心"), (31114, "动力火车 当")]:
        lk = f"lyrics/我是歌手/{aname}/s_{sid}.lrc"
        if check_r2_object_exists(lk) < 50:
            lt = fetch_lrc_multi(q)
            if lt:
                s3_client.put_object(Bucket=BUCKET_NAME, Key=lk, Body=lt.encode("utf-8"), ContentType="text/plain; charset=utf-8")
                print(f"   📄 补充上传 [{sid}] {q} 歌词 ({len(lt)} 字节)")

    # 3. 提交第二季全专 D1 批量标准化点亮
    print("\n⚡ 提交第二季 12 首全量标准编码批量点亮...")
    enc_artist = urllib.parse.quote("我是歌手")
    enc_album = urllib.parse.quote(aname)

    detail = safe_api_get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}").json()
    songs = detail.get("data", {}).get("songs", [])

    updates = []
    for s in songs:
        sid = s["id"]
        mp3_url = f"{PUBLIC_BASE}/music/{enc_artist}/{enc_album}/s_{sid}.mp3"
        lrc_url = f"{PUBLIC_BASE}/lyrics/{enc_artist}/{enc_album}/s_{sid}.lrc"
        updates.append({"id": sid, "file_path": mp3_url, "lrc_path": lrc_url})

    res_lit = safe_api_post(f"{API_BASE}/api/admin/songs/batch-light", json_data={"updates": updates})
    print(f"   • batch-light 响应: {res_lit.status_code} | {res_lit.text}")

    # 4. 第二季终验
    print("\n🔍 正在对第二季 12 首进行生产端 1:1 物理字节审计...")
    all_pass = True
    final_detail = safe_api_get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}").json()
    final_songs = final_detail.get("data", {}).get("songs", [])

    for s in sorted(final_songs, key=lambda x: x["track_index"]):
        sid = s["id"]
        title = s["title"]
        tidx = s["track_index"]
        fpath = s.get("file_path")
        lpath = s.get("lrc_path")

        r_mp3 = None
        for _ in range(2):
            try:
                r_mp3 = session.head(fpath, headers=HEADERS, timeout=10)
                if r_mp3.status_code == 200: break
            except Exception: pass
        mp3_len = int(r_mp3.headers.get("content-length", 0)) if (r_mp3 and r_mp3.status_code == 200) else 0

        r_lrc = None
        for _ in range(2):
            try:
                r_lrc = session.head(lpath, headers=HEADERS, timeout=10)
                if r_lrc.status_code == 200: break
            except Exception: pass
        lrc_len = int(r_lrc.headers.get("content-length", 0)) if (r_lrc and r_lrc.status_code == 200) else 0

        ok = (r_mp3 and r_mp3.status_code == 200 and mp3_len > 1000000 and r_lrc and r_lrc.status_code == 200 and lrc_len > 100)
        if not ok: all_pass = False

        status = "✅ PASS" if ok else "❌ FAIL"
        c_m = r_mp3.status_code if r_mp3 else 0
        c_l = r_lrc.status_code if r_lrc else 0
        print(f"Track {tidx:2d} | [{sid}] {title:<40} | {status} | MP3: {mp3_len/1024/1024:.2f}MB (HTTP {c_m}) | LRC: {lrc_len}B (HTTP {c_l})")

    print(f"\n第二季验收: {'🎉 100% 满格通过！' if all_pass else '⚠️ 存在未通过项！'}")
    return all_pass

# ==============================================================================
# 第三季 (2015) 执行流水线
# ==============================================================================
def process_season_3():
    aid = 1947
    aname = "第三季 (2015)"
    print("\n" + "=" * 80)
    print("🚀 [SEASON 3] 开始处理《我是歌手》第三季 (2015)...")
    print("=" * 80)

    # 1. 规范既有 7 首曲目曲名与曲序
    print("\n📝 [Step 1] 更新第三季既有曲目元数据...")
    reuse_updates = [
        {"id": 27631, "track_index": 1, "title": "天亮了 - 韩红"},
        {"id": 27636, "track_index": 2, "title": "是否爱过我 - 孙楠"},
        {"id": 27632, "track_index": 3, "title": "我用所有报答爱 - 张靓颖"},
        {"id": 27635, "track_index": 4, "title": "给我一个理由忘记 - A-Lin"},
        {"id": 27634, "track_index": 5, "title": "爱与诚 - 古巨基"},
        {"id": 27637, "track_index": 8, "title": "模特 - 李荣浩"},
        {"id": 27633, "track_index": 9, "title": "贝加尔湖畔 - 李健"}
    ]
    res_up = safe_api_post(f"{API_BASE}/api/admin/songs/batch-update", json_data={"updates": reuse_updates})
    print(f"   • batch-update 响应: {res_up.status_code} | {res_up.text}")

    # 2. 插入新增的 6 首曲目
    print("\n📝 [Step 2] 插入新增的 6 首首秀曲目...")
    insert_tracks = [
        {"track_index": 6, "title": "山丘 - 胡彦斌", "yt_id": "Bxv-S-LodmQ", "lrc_query": "胡彦斌 山丘"},
        {"track_index": 7, "title": "心动 - 陈洁仪", "yt_id": "YkLrZASoJmc", "lrc_query": "陈洁仪 心动"},
        {"track_index": 10, "title": "灯塔 - 谭维维", "yt_id": "niLRCMmvAE0", "lrc_query": "谭维维 灯塔"},
        {"track_index": 11, "title": "那个男人 - 郑淳元", "yt_id": "fvPfjGgjTXc", "lrc_query": "郑淳元 那个男人"},
        {"track_index": 12, "title": "煎熬 - 李佳薇", "yt_id": "LJd5xIjvMCg", "lrc_query": "李佳薇 煎熬"},
        {"track_index": 13, "title": "你是我的眼 - 萧煌奇", "yt_id": "X1mAQeVKqPg", "lrc_query": "萧煌奇 你是我的眼"}
    ]
    # 先检查是否已经插入
    curr_detail = safe_api_get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}").json()
    curr_songs = curr_detail.get("data", {}).get("songs", [])
    curr_titles = {s["title"] for s in curr_songs}

    to_insert = [t for t in insert_tracks if t["title"] not in curr_titles]
    if to_insert:
        payload_ins = {
            "album_id": aid,
            "songs": [{"title": t["title"], "track_index": t["track_index"], "storage_id": "primary"} for t in to_insert]
        }
        res_ins = safe_api_post(f"{API_BASE}/api/admin/songs/batch-insert", json_data=payload_ins)
        print(f"   • batch-insert 响应: {res_ins.status_code} | {res_ins.text}")

    # 重新拉取以获取 ID
    after_detail = safe_api_get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}").json()
    all_songs = after_detail.get("data", {}).get("songs", [])
    song_id_map = {s["title"]: s["id"] for s in all_songs}

    # 3. 采录清单
    targets_to_record = [
        {"id": 27636, "title": "是否爱过我 - 孙楠", "yt_id": "XbScXJHZYuo", "lrc_query": "孙楠 是否爱过我"},
        {"id": 27632, "title": "我用所有报答爱 - 张靓颖", "yt_id": "vHqyG6M4b6g", "lrc_query": "张靓颖 我用所有报答爱"},
        {"id": 27634, "title": "爱与诚 - 古巨基", "yt_id": "LgajARxwfzE", "lrc_query": "古巨基 爱与诚"},
        {"id": song_id_map["山丘 - 胡彦斌"], "title": "山丘 - 胡彦斌", "yt_id": "Bxv-S-LodmQ", "lrc_query": "胡彦斌 山丘"},
        {"id": song_id_map["心动 - 陈洁仪"], "title": "心动 - 陈洁仪", "yt_id": "YkLrZASoJmc", "lrc_query": "陈洁仪 心动"},
        {"id": song_id_map["灯塔 - 谭维维"], "title": "灯塔 - 谭维维", "yt_id": "niLRCMmvAE0", "lrc_query": "谭维维 灯塔"},
        {"id": song_id_map["那个男人 - 郑淳元"], "title": "那个男人 - 郑淳元", "yt_id": "fvPfjGgjTXc", "lrc_query": "郑淳元 那个男人"},
        {"id": song_id_map["煎熬 - 李佳薇"], "title": "煎熬 - 李佳薇", "yt_id": "LJd5xIjvMCg", "lrc_query": "李佳薇 煎熬"},
        {"id": song_id_map["你是我的眼 - 萧煌奇"], "title": "你是我的眼 - 萧煌奇", "yt_id": "X1mAQeVKqPg", "lrc_query": "萧煌奇 你是我的眼"}
    ]

    print(f"\n🎛️ [Step 3] 启动第三季 {len(targets_to_record)} 首曲目的采录与母带压制...")
    for idx, t in enumerate(targets_to_record, 1):
        sid = t["id"]
        title = t["title"]
        yt_id = t["yt_id"]
        lrc_query = t["lrc_query"]

        mp3_key = f"music/我是歌手/{aname}/s_{sid}.mp3"
        lrc_key = f"lyrics/我是歌手/{aname}/s_{sid}.lrc"

        if check_r2_object_exists(mp3_key) > 1000000 and check_r2_object_exists(lrc_key) > 100:
            print(f"[{idx}/{len(targets_to_record)}] [{sid}] 《{title}》 远端对象已达标，跳过压制。")
            continue

        print(f"\n--- [{idx}/{len(targets_to_record)}] 采录 [{sid}] 《{title}》 (YouTube ID: {yt_id}) ---")
        raw_audio = os.path.join(WORK_DIR, f"raw_{sid}.%(ext)s")
        norm_mp3 = os.path.join(WORK_DIR, f"s_{sid}.mp3")
        lrc_file = os.path.join(WORK_DIR, f"s_{sid}.lrc")

        for f in [norm_mp3, lrc_file]:
            if os.path.exists(f): os.remove(f)

        dl_cmd = [
            "yt-dlp", "--proxy", PROXY_URL, "--js-runtimes", f"node:{NODE_PATH}",
            "-f", "ba/b", "-o", raw_audio, f"https://www.youtube.com/watch?v={yt_id}"
        ]
        subprocess.run(dl_cmd, capture_output=True, text=True)

        actual_raw = None
        for ext in ["webm", "m4a", "opus", "mp3", "mp4", "mkv"]:
            cand = os.path.join(WORK_DIR, f"raw_{sid}.{ext}")
            if os.path.exists(cand) and os.path.getsize(cand) > 100000:
                actual_raw = cand
                break

        if not actual_raw:
            print(f"   ❌ 音频下载失败!")
            continue

        cmd_ffmpeg = [
            "ffmpeg", "-y", "-i", actual_raw,
            "-vn", "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "160k", "-write_xing", "1", "-ar", "44100",
            norm_mp3
        ]
        subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(norm_mp3) or os.path.getsize(norm_mp3) < 500000:
            print(f"   ❌ 压制失败或文件过小!")
            continue

        dur_raw = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", norm_mp3
        ]).decode().strip()
        dur = float(dur_raw)
        print(f"   ✅ 母带压制达标: 时长 {int(dur//60)}分{int(dur%60):02d}秒 ({dur:.1f}s), 体积 {os.path.getsize(norm_mp3)/1024/1024:.2f} MB")

        lrc_text = fetch_lrc_multi(lrc_query)
        if lrc_text:
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            print(f"   📄 同步歌词就绪: {len(lrc_text)} 字节")

        s3_client.upload_file(norm_mp3, BUCKET_NAME, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        print(f"   🚀 R2 音频上传完成: {mp3_key}")

        if os.path.exists(lrc_file):
            s3_client.upload_file(lrc_file, BUCKET_NAME, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            print(f"   🚀 R2 歌词上传完成: {lrc_key}")

    # 4. 提交第三季全专 D1 批量标准化点亮
    print("\n⚡ 提交第三季 13 首全量标准编码批量点亮...")
    enc_artist = urllib.parse.quote("我是歌手")
    enc_album = urllib.parse.quote(aname)

    fresh_detail = safe_api_get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}").json()
    fresh_songs = fresh_detail.get("data", {}).get("songs", [])

    updates = []
    for s in fresh_songs:
        sid = s["id"]
        mp3_url = f"{PUBLIC_BASE}/music/{enc_artist}/{enc_album}/s_{sid}.mp3"
        lrc_url = f"{PUBLIC_BASE}/lyrics/{enc_artist}/{enc_album}/s_{sid}.lrc"
        updates.append({"id": sid, "file_path": mp3_url, "lrc_path": lrc_url})

    res_lit = safe_api_post(f"{API_BASE}/api/admin/songs/batch-light", json_data={"updates": updates})
    print(f"   • batch-light 响应: {res_lit.status_code} | {res_lit.text}")

    # 5. 第三季终验
    print("\n🔍 正在对第三季 13 首进行生产端 1:1 物理字节审计...")
    all_pass = True
    final_detail = safe_api_get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}").json()
    final_songs = final_detail.get("data", {}).get("songs", [])

    for s in sorted(final_songs, key=lambda x: x["track_index"]):
        sid = s["id"]
        title = s["title"]
        tidx = s["track_index"]
        fpath = s.get("file_path")
        lpath = s.get("lrc_path")

        r_mp3 = None
        for _ in range(2):
            try:
                r_mp3 = session.head(fpath, headers=HEADERS, timeout=10)
                if r_mp3.status_code == 200: break
            except Exception: pass
        mp3_len = int(r_mp3.headers.get("content-length", 0)) if (r_mp3 and r_mp3.status_code == 200) else 0

        r_lrc = None
        for _ in range(2):
            try:
                r_lrc = session.head(lpath, headers=HEADERS, timeout=10)
                if r_lrc.status_code == 200: break
            except Exception: pass
        lrc_len = int(r_lrc.headers.get("content-length", 0)) if (r_lrc and r_lrc.status_code == 200) else 0

        ok = (r_mp3 and r_mp3.status_code == 200 and mp3_len > 1000000 and r_lrc and r_lrc.status_code == 200 and lrc_len > 100)
        if not ok: all_pass = False

        status = "✅ PASS" if ok else "❌ FAIL"
        c_m = r_mp3.status_code if r_mp3 else 0
        c_l = r_lrc.status_code if r_lrc else 0
        print(f"Track {tidx:2d} | [{sid}] {title:<40} | {status} | MP3: {mp3_len/1024/1024:.2f}MB (HTTP {c_m}) | LRC: {lrc_len}B (HTTP {c_l})")

    print(f"\n第三季验收: {'🎉 100% 满格通过！' if all_pass else '⚠️ 存在未通过项！'}")
    return all_pass

def main():
    print("=" * 80)
    print("🌟 开始执行《我是歌手》第二季与第三季高可用补齐流水线")
    print("=" * 80)

    s2_ok = process_season_2()
    s3_ok = process_season_3()

    print("\n" + "=" * 80)
    print(f"终极验收汇报: 第二季通过={s2_ok}, 第三季通过={s3_ok}")
    print("=" * 80)

if __name__ == "__main__":
    main()
