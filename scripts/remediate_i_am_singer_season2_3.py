#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
《我是歌手》第二季 (2014) 与第三季 (2015) 核心首秀曲目全量归正与点亮流水线
==============================================================================
1. 第二季 (2014) [共 12 首]:
   - 剔除王菲《你在终点等我》跨年代假歌，纠偏邓紫棋非首秀重复曲目；
   - 规范首发 7 人 + 补位 5 人（韩磊、韦唯、张宇、周笔畅、罗琦、曹格、邓紫棋、张杰、品冠、茜拉、满文军、动力火车）；
2. 第三季 (2015) [共 13 首]:
   - 纠偏非首秀曲目（饿狼传说、袖手旁观、父亲）；
   - 规范首发 7 人 + 踢馆/补位 6 人（韩红、孙楠、张靓颖、A-Lin、古巨基、胡彦斌、陈洁仪、李荣浩、李健、谭维维、郑淳元、李佳薇、萧煌奇）；
3. 采录官方 Live 母带与单曲纯享，EBU R128 (-14 LUFS) 响度标准化，160k CBR 压制，上传 R2 account_12；
4. D1 批处理更新、新增与点亮，标准 URL 百分号编码，1:1 HTTP HEAD 终验。
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

# R2 客户端 (account_12)
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
session.trust_env = False  # 避免本地代理影响与 Worker API 的直连

# ==============================================================================
# 第二季 (2014) 目标配置 (12 首)
# ==============================================================================
SEASON_2_PLAN = {
    "album_id": 1946,
    "album_name": "第二季 (2014)",
    # 既有 7 首复用与重排
    "reuse_updates": [
        {"id": 27625, "track_index": 1, "title": "等待 - 韩磊", "keep_audio": True},
        {"id": 27627, "track_index": 2, "title": "恋寻 - 韦唯", "keep_audio": False, "yt_id": "JAvAbDmz_II", "lrc_query": "韦唯 恋寻"},
        {"id": 27626, "track_index": 3, "title": "月亮惹的祸 - 张宇", "keep_audio": True},
        {"id": 27628, "track_index": 4, "title": "别爱我，像爱个朋友 + 解脱 - 周笔畅", "keep_audio": False, "yt_id": "vuRfdpxsFNY", "lrc_query": "周笔畅 别爱我像爱个朋友"},
        {"id": 27629, "track_index": 5, "title": "随心所欲 - 罗琦", "keep_audio": False, "yt_id": "W9bBAoy4DMo", "lrc_query": "罗琦 随心所欲"},
        {"id": 27630, "track_index": 6, "title": "背叛 - 曹格", "keep_audio": False, "yt_id": "1A9fhciGxEM", "lrc_query": "曹格 背叛"},
        {"id": 27624, "track_index": 7, "title": "泡沫 - 邓紫棋", "keep_audio": True}
    ],
    # 新增插入 5 首
    "insert_tracks": [
        {"track_index": 8, "title": "勿忘心安 - 张杰", "yt_id": "jJFJkKulRws", "lrc_query": "张杰 勿忘心安"},
        {"track_index": 9, "title": "掌心 - 品冠", "yt_id": "saekI9QZEq0", "lrc_query": "品冠 掌心"},
        {"track_index": 10, "title": "想你的夜 - 茜拉", "yt_id": "t-2DPNfGyLQ", "lrc_query": "茜拉 想你的夜"},
        {"track_index": 11, "title": "我需要你 - 满文军", "yt_id": "4ioskB0br7Q", "lrc_query": "满文军 我需要你"},
        {"track_index": 12, "title": "当 - 动力火车", "yt_id": "2YSs10xvA8c", "lrc_query": "动力火车 当"}
    ]
}

# ==============================================================================
# 第三季 (2015) 目标配置 (13 首)
# ==============================================================================
SEASON_3_PLAN = {
    "album_id": 1947,
    "album_name": "第三季 (2015)",
    # 既有 7 首复用与重排
    "reuse_updates": [
        {"id": 27631, "track_index": 1, "title": "天亮了 - 韩红", "keep_audio": True},
        {"id": 27636, "track_index": 2, "title": "是否爱过我 - 孙楠", "keep_audio": False, "yt_id": "XbScXJHZYuo", "lrc_query": "孙楠 是否爱过我"},
        {"id": 27632, "track_index": 3, "title": "我用所有报答爱 - 张靓颖", "keep_audio": False, "yt_id": "vHqyG6M4b6g", "lrc_query": "张靓颖 我用所有报答爱"},
        {"id": 27635, "track_index": 4, "title": "给我一个理由忘记 - A-Lin", "keep_audio": True},
        {"id": 27634, "track_index": 5, "title": "爱与诚 - 古巨基", "keep_audio": False, "yt_id": "LgajARxwfzE", "lrc_query": "古巨基 爱与诚"},
        {"id": 27637, "track_index": 8, "title": "模特 - 李荣浩", "keep_audio": True},
        {"id": 27633, "track_index": 9, "title": "贝加尔湖畔 - 李健", "keep_audio": True}
    ],
    # 新增插入 6 首
    "insert_tracks": [
        {"track_index": 6, "title": "山丘 - 胡彦斌", "yt_id": "Bxv-S-LodmQ", "lrc_query": "胡彦斌 山丘"},
        {"track_index": 7, "title": "心动 - 陈洁仪", "yt_id": "YkLrZASoJmc", "lrc_query": "陈洁仪 心动"},
        {"track_index": 10, "title": "灯塔 - 谭维维", "yt_id": "niLRCMmvAE0", "lrc_query": "谭维维 灯塔"},
        {"track_index": 11, "title": "那个男人 - 郑淳元", "yt_id": "fvPfjGgjTXc", "lrc_query": "郑淳元 那个男人"},
        {"track_index": 12, "title": "煎熬 - 李佳薇", "yt_id": "LJd5xIjvMCg", "lrc_query": "李佳薇 煎熬"},
        {"track_index": 13, "title": "你是我的眼 - 萧煌奇", "yt_id": "X1mAQeVKqPg", "lrc_query": "萧煌奇 你是我的眼"}
    ]
}

def fetch_lrc_multi(query: str) -> str:
    """多渠道提取高保真 LRC 歌词"""
    # 渠道 1: 网易云
    try:
        r = requests.get(
            f"https://music.163.com/api/search/get/web?s={query}&type=1&limit=3",
            headers=HEADERS,
            timeout=5
        ).json()
        songs = r.get("result", {}).get("songs", [])
        if songs:
            sid = songs[0]["id"]
            lr = requests.get(
                f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1",
                headers=HEADERS,
                timeout=5
            ).json()
            lrc_text = lr.get("lrc", {}).get("lyric", "")
            if lrc_text and len(lrc_text.strip()) > 50:
                clean_lines = [l for l in lrc_text.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
                return "\n".join(clean_lines).strip()
    except Exception:
        pass

    # 渠道 2: syncedlyrics
    try:
        lrc_text = syncedlyrics.search(query)
        if lrc_text and len(lrc_text.strip()) > 50:
            clean_lines = [l for l in lrc_text.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
            return "\n".join(clean_lines).strip()
    except Exception:
        pass

    return ""

def process_single_season(plan: dict):
    aid = plan["album_id"]
    aname = plan["album_name"]
    print("\n" + "=" * 80)
    print(f"🚀 开始执行《我是歌手》{aname} (ID: {aid}) 归正与点亮流水线")
    print("=" * 80)

    # 1. 批量更正/规整既有曲目元数据
    print(f"\n📝 [Step 1] 更新并重整既有曲目元数据与曲序...")
    updates_payload = [
        {"id": u["id"], "track_index": u["track_index"], "title": u["title"]}
        for u in plan["reuse_updates"]
    ]
    res_up = session.post(f"{API_BASE}/api/admin/songs/batch-update", json={"updates": updates_payload}, timeout=15)
    print(f"   • batch-update 响应: {res_up.status_code} | {res_up.text}")

    # 2. 插入新增曲目
    print(f"\n📝 [Step 2] 向 D1 专辑插入缺失的 {len(plan['insert_tracks'])} 首首秀曲目...")
    insert_payload = {
        "album_id": aid,
        "songs": [
            {"title": t["title"], "track_index": t["track_index"], "storage_id": "primary"}
            for t in plan["insert_tracks"]
        ]
    }
    res_ins = session.post(f"{API_BASE}/api/admin/songs/batch-insert", json=insert_payload, timeout=20)
    print(f"   • batch-insert 响应: {res_ins.status_code} | {res_ins.text}")

    # 3. 重新拉取曲目以绑定 ID
    print(f"\n🔍 [Step 3] 拉取当前专辑曲目列表以核定各曲目 ID...")
    detail = session.get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}", timeout=15).json()
    all_songs = detail.get("data", {}).get("songs", [])
    print(f"   • 专辑现有总曲目数: {len(all_songs)} 首")

    song_id_map = {s["title"]: s["id"] for s in all_songs}

    # 整理需要采录下载的曲目清单
    tasks = []
    # 从复用曲目中挑出需要重新采录的（keep_audio 为 False）
    for u in plan["reuse_updates"]:
        if not u["keep_audio"]:
            tasks.append({
                "id": u["id"],
                "title": u["title"],
                "yt_id": u["yt_id"],
                "lrc_query": u["lrc_query"]
            })
    # 从新增曲目中加入所有新增的
    for ins in plan["insert_tracks"]:
        sid = song_id_map.get(ins["title"])
        if sid:
            tasks.append({
                "id": sid,
                "title": ins["title"],
                "yt_id": ins["yt_id"],
                "lrc_query": ins["lrc_query"]
            })

    print(f"\n🎛️ [Step 4] 启动 {len(tasks)} 首需采录曲目的官方 Live 母带压制与上传...")

    for idx, t in enumerate(tasks, 1):
        sid = t["id"]
        title = t["title"]
        yt_id = t["yt_id"]
        lrc_query = t["lrc_query"]

        print(f"\n--- [{idx}/{len(tasks)}] 采录 [{sid}] 《{title}》 (YouTube ID: {yt_id}) ---")

        raw_audio = os.path.join(WORK_DIR, f"raw_{sid}.%(ext)s")
        norm_mp3 = os.path.join(WORK_DIR, f"s_{sid}.mp3")
        lrc_file = os.path.join(WORK_DIR, f"s_{sid}.lrc")

        for f in [norm_mp3, lrc_file]:
            if os.path.exists(f): os.remove(f)

        dl_cmd = [
            "yt-dlp",
            "--proxy", PROXY_URL,
            "--js-runtimes", f"node:{NODE_PATH}",
            "-f", "ba/b",
            "-o", raw_audio,
            f"https://www.youtube.com/watch?v={yt_id}"
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
            "-vn",
            "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-c:a", "libmp3lame",
            "-b:a", "160k",
            "-write_xing", "1",
            "-ar", "44100",
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
        size_mb = os.path.getsize(norm_mp3) / (1024 * 1024)
        print(f"   ✅ 母带压制达标: 时长 {int(dur//60)}分{int(dur%60):02d}秒 ({dur:.1f}s), 体积 {size_mb:.2f} MB")

        lrc_text = fetch_lrc_multi(lrc_query)
        if lrc_text:
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            print(f"   📄 同步歌词就绪: {len(lrc_text)} 字节")

        # 上传 R2 account_12
        mp3_key = f"music/我是歌手/{aname}/s_{sid}.mp3"
        s3_client.upload_file(norm_mp3, BUCKET_NAME, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        print(f"   🚀 R2 音频上传完成: {mp3_key}")

        if os.path.exists(lrc_file):
            lrc_key = f"lyrics/我是歌手/{aname}/s_{sid}.lrc"
            s3_client.upload_file(lrc_file, BUCKET_NAME, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            print(f"   🚀 R2 歌词上传完成: {lrc_key}")

    # 4. 全专标准 URL 百分号编码并点亮
    print(f"\n⚡ [Step 5] 构造标准 URL 编码并向 D1 提交全专批量点亮...")
    enc_artist = urllib.parse.quote("我是歌手")
    enc_album = urllib.parse.quote(aname)

    # 重新拉取以确保完整
    fresh_detail = session.get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}", timeout=15).json()
    fresh_songs = fresh_detail.get("data", {}).get("songs", [])

    d1_lights = []
    for s in fresh_songs:
        sid = s["id"]
        mp3_url = f"{PUBLIC_BASE}/music/{enc_artist}/{enc_album}/s_{sid}.mp3"
        lrc_url = f"{PUBLIC_BASE}/lyrics/{enc_artist}/{enc_album}/s_{sid}.lrc"
        d1_lights.append({
            "id": sid,
            "file_path": mp3_url,
            "lrc_path": lrc_url
        })

    res_lit = session.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": d1_lights}, timeout=25)
    print(f"   • batch-light 响应: {res_lit.status_code} | {res_lit.text}")

    # 5. 验收
    print(f"\n🔍 [Step 6] 生产端全网 1:1 可用性校验 ({aname})...")
    final_detail = session.get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}", timeout=15).json()
    final_songs = final_detail.get("data", {}).get("songs", [])

    all_pass = True
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
        print(f"Track {tidx:2d} | [{sid}] {title:<38} | {status} | MP3: {mp3_len/1024/1024:.2f}MB (HTTP {c_m}) | LRC: {lrc_len}B (HTTP {c_l})")

    print(f"\n{aname} 验收结果: {'🎉 100% 满格通过！' if all_pass else '⚠️ 存在未通过项！'}")
    return all_pass

def main():
    print("=" * 80)
    print("🌟 开始《我是歌手》第二季 (2014) 与第三季 (2015) 核心阵容全量补齐")
    print("=" * 80)

    s2_ok = process_single_season(SEASON_2_PLAN)
    s3_ok = process_single_season(SEASON_3_PLAN)

    print("\n" + "=" * 80)
    print(f"终极汇总: 第二季通过={s2_ok}, 第三季通过={s3_ok}")
    print("=" * 80)

if __name__ == "__main__":
    main()
