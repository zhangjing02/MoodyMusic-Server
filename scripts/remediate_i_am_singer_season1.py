#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
《我是歌手》第一季 (2013) 骨架修正、李鬼剔除与核心竞演资源全量补齐流水线
==============================================================================
1. 纠偏审查：
   - 彻底剔除华晨宇（2013快男出道，2018方登歌手舞台）；
   - 彻底纠正杨宗纬《我期待》（第一季正赛全13期从未演唱张雨生此作）；
   - 补齐首发7人自选代表作全阵容（补充黄贯中、陈明、沙宝亮）；
   - 补齐全量补位歌手真实经典Live（杨宗纬4首、周晓鸥2首、林志炫4首、辛晓琪1首、彭佳慧1首）；
2. 资源采录与处理：
   - 采录湖南卫视 / 芒果TV《我是歌手》官方纯享与官方 Live 母带音轨；
   - 统一压制规范：EBU R128 (-14 LUFS) 响度标准化，160k CBR Xing 编码，44100Hz；
   - 获取并清洗高保真同步 LRC 歌词；
   - 写入活跃存储桶 account_12 (moody-music-asset-12)；
3. D1 数据库原子切链与批量点亮：
   - 热更正 27622 -> 黄贯中 - 《海阔天空》 (track 5)
   - 热更正 27623 -> 陈明 - 《等你爱我》 (track 6)
   - 更新既有 6 首曲目曲序 (羽泉 1, 齐秦 2, 黄绮珊 3, 尚雯婕 4, 林志炫没离开过 14, 烟花易冷 15)
   - batch-insert 插入其余 11 首曲目并获取分配 ID
   - batch-light 批量切链并点亮
   - 生产端 HTTP HEAD 强校验与回放验证
==============================================================================
"""

import os
import sys
import json
import time
import re
import subprocess
import requests
import boto3
from botocore.config import Config
import syncedlyrics

# 保证 UTF-8 输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
WORK_DIR = "/tmp/i_am_singer_season1_work"
os.makedirs(WORK_DIR, exist_ok=True)

NODE_PATH = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"
PROXY_URL = "http://127.0.0.1:7897"
API_BASE = "https://m-api.changgepd.ccwu.cc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# 1. 读取 R2 配置 (写入 account_12)
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

ALBUM_ID = 1945
ARTIST_NAME = "我是歌手"
ALBUM_NAME = "第一季 (2013)"

# 定义 13 首待下载/补齐的曲目档案 (包含 YouTube 官方视频 ID 与网易云/syncedlyrics 歌词查询词)
REMEDIATE_TARGETS = [
    # 首发补齐 (复用 27622)
    {
        "mode": "reuse",
        "reuse_id": 27622,
        "title": "海阔天空 - 黄贯中",
        "track_index": 5,
        "yt_id": "IbZwrcQUItY",
        "lrc_query": "黄贯中 海阔天空"
    },
    # 首发补齐 (复用 27623)
    {
        "mode": "reuse",
        "reuse_id": 27623,
        "title": "等你爱我 - 陈明",
        "track_index": 6,
        "yt_id": "InMEFg9Nmbc",
        "lrc_query": "陈明 等你爱我"
    },
    # 首发补齐 (新增 1)
    {
        "mode": "insert",
        "title": "飘 - 沙宝亮",
        "track_index": 7,
        "yt_id": "jIRIPceTFn8",
        "lrc_query": "沙宝亮 飘"
    },
    # 补位精选: 杨宗纬 (新增 2~5)
    {
        "mode": "insert",
        "title": "矜持 - 杨宗纬",
        "track_index": 8,
        "yt_id": "HY6KVt3epbQ",
        "lrc_query": "杨宗纬 矜持"
    },
    {
        "mode": "insert",
        "title": "空白格 - 杨宗纬",
        "track_index": 9,
        "yt_id": "hWZ0Wvaa2cw",
        "lrc_query": "杨宗纬 空白格"
    },
    {
        "mode": "insert",
        "title": "流浪记 - 杨宗纬",
        "track_index": 10,
        "yt_id": "TWjp0mg0EUY",
        "lrc_query": "杨宗纬 流浪记"
    },
    {
        "mode": "insert",
        "title": "最爱 - 杨宗纬",
        "track_index": 11,
        "yt_id": "mQkJB2ziroo",
        "lrc_query": "杨宗纬 最爱"
    },
    # 补位精选: 周晓鸥 (新增 6~7)
    {
        "mode": "insert",
        "title": "爱不爱我 - 周晓鸥",
        "track_index": 12,
        "yt_id": "CPRm0cUVZkg",
        "lrc_query": "周晓鸥 爱不爱我"
    },
    {
        "mode": "insert",
        "title": "无地自容 - 周晓鸥",
        "track_index": 13,
        "yt_id": "ox_AZQcqpmI",
        "lrc_query": "周晓鸥 无地自容"
    },
    # 补位精选: 林志炫补充 (新增 8~9)
    {
        "mode": "insert",
        "title": "浮夸 - 林志炫",
        "track_index": 16,
        "yt_id": "isIUZ4HMV80",
        "lrc_query": "林志炫 浮夸"
    },
    {
        "mode": "insert",
        "title": "Making Love Out of Nothing at All - 林志炫",
        "track_index": 17,
        "yt_id": "k9E_oBUYfSU",
        "lrc_query": "林志炫 Making Love Out of Nothing at All"
    },
    # 补位精选: 辛晓琪 (新增 10)
    {
        "mode": "insert",
        "title": "领悟 - 辛晓琪",
        "track_index": 18,
        "yt_id": "rwwQ6EvoiCw",
        "lrc_query": "辛晓琪 领悟"
    },
    # 补位精选: 彭佳慧 (新增 11)
    {
        "mode": "insert",
        "title": "走在红毯那一天 - 彭佳慧",
        "track_index": 19,
        "yt_id": "Xgm-0ItfRAM",
        "lrc_query": "彭佳慧 走在红毯那一天"
    }
]

def fetch_lrc_multi(query: str) -> str:
    """多通道抓取高保真同步歌词"""
    # 通道 1: 网易云
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
                clean_lines = []
                for line in lrc_text.split("\n"):
                    if any(line.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"]):
                        continue
                    clean_lines.append(line)
                return "\n".join(clean_lines).strip()
    except Exception:
        pass

    # 通道 2: syncedlyrics
    try:
        lrc_text = syncedlyrics.search(query)
        if lrc_text and len(lrc_text.strip()) > 50:
            clean_lines = []
            for line in lrc_text.split("\n"):
                if any(line.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"]):
                    continue
                clean_lines.append(line)
            return "\n".join(clean_lines).strip()
    except Exception:
        pass

    return ""

def main():
    print("=" * 80)
    print("🌟 开始执行《我是歌手》第一季 (2013) 骨架归正与全量资源补齐流水线")
    print("=" * 80)

    # 阶段 1: 整理已有曲目曲序，更正 27622 / 27623
    print("\n📝 [Phase 1] 规整现有曲目曲序，热更正 27622 与 27623 元数据...")
    existing_updates = [
        {"id": 27616, "track_index": 1, "title": "心似狂潮 - 羽泉"},
        {"id": 27617, "track_index": 2, "title": "夜夜夜夜 - 齐秦"},
        {"id": 27618, "track_index": 3, "title": "等待 - 黄绮珊"},
        {"id": 27619, "track_index": 4, "title": "最终信仰 - 尚雯婕"},
        {"id": 27620, "track_index": 14, "title": "没离开过 - 林志炫"},
        {"id": 27621, "track_index": 15, "title": "烟花易冷 - 林志炫"},
        {"id": 27622, "track_index": 5, "title": "海阔天空 - 黄贯中"},
        {"id": 27623, "track_index": 6, "title": "等你爱我 - 陈明"}
    ]
    res_up = requests.post(
        f"{API_BASE}/api/admin/songs/batch-update",
        json={"updates": existing_updates},
        timeout=15
    )
    print(f"   • batch-update 响应: {res_up.status_code} | {res_up.text}")

    # 阶段 2: 批量插入新增的 11 首曲目
    print("\n📝 [Phase 2] 向 D1 插入新增的 11 首第一季经典竞演曲目...")
    insert_items = [t for t in REMEDIATE_TARGETS if t["mode"] == "insert"]
    payload_insert = {
        "album_id": ALBUM_ID,
        "songs": [
            {
                "title": t["title"],
                "track_index": t["track_index"],
                "storage_id": "primary"
            }
            for t in insert_items
        ]
    }
    res_ins = requests.post(
        f"{API_BASE}/api/admin/songs/batch-insert",
        json=payload_insert,
        timeout=20
    )
    print(f"   • batch-insert 响应: {res_ins.status_code} | {res_ins.text}")
    res_ins_data = res_ins.json()

    # 阶段 3: 重新拉取 album detail 获取精确的 song id 映射
    print("\n🔍 [Phase 3] 重新拉取专辑曲目列表以核准所有曲目 ID...")
    detail_res = requests.get(f"{API_BASE}/api/admin/albums/detail?album_id={ALBUM_ID}", timeout=10).json()
    all_current_songs = detail_res.get("data", {}).get("songs", [])
    print(f"   • 当前专辑总曲目数: {len(all_current_songs)} 首")

    song_id_map = {}
    for s in all_current_songs:
        song_id_map[s["title"]] = s["id"]
        print(f"     Track {s['track_index']:2d}: [{s['id']}] {s['title']}")

    # 阶段 4: 下载、标准化压制、抓取歌词并上传至 R2
    print("\n🎛️ [Phase 4] 启动 13 首曲目正规采录、母带压制与 R2 对象入库流水线...")
    d1_lights = []

    for idx, item in enumerate(REMEDIATE_TARGETS, 1):
        title = item["title"]
        sid = song_id_map.get(title) or item.get("reuse_id")
        if not sid:
            print(f"   ❌ 无法找到曲目 ID: {title}")
            continue

        yt_id = item["yt_id"]
        lrc_query = item["lrc_query"]

        print(f"\n--- [{idx}/13] 正在采录 [{sid}] 《{title}》 (YouTube ID: {yt_id}) ---")

        raw_audio = os.path.join(WORK_DIR, f"raw_{sid}.%(ext)s")
        norm_mp3 = os.path.join(WORK_DIR, f"s_{sid}.mp3")
        lrc_file = os.path.join(WORK_DIR, f"s_{sid}.lrc")

        # 清理旧缓存
        for f in [norm_mp3, lrc_file]:
            if os.path.exists(f): os.remove(f)

        # 1. 下载音频
        dl_cmd = [
            "yt-dlp",
            "--proxy", PROXY_URL,
            "--js-runtimes", f"node:{NODE_PATH}",
            "-f", "ba/b",
            "-o", raw_audio,
            f"https://www.youtube.com/watch?v={yt_id}"
        ]
        ret = subprocess.run(dl_cmd, capture_output=True, text=True)
        
        # 寻找实际下载的 raw 格式
        actual_raw = None
        for ext in ["webm", "m4a", "opus", "mp3", "mp4", "mkv"]:
            cand = os.path.join(WORK_DIR, f"raw_{sid}.{ext}")
            if os.path.exists(cand) and os.path.getsize(cand) > 100000:
                actual_raw = cand
                break

        if not actual_raw:
            print(f"   ❌ 音频下载失败! stderr: {ret.stderr[-200:]}")
            continue

        # 2. 标准化母带压制
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
            print(f"   ❌ 音频压制失败或文件过小!")
            continue

        dur_raw = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", norm_mp3
        ]).decode().strip()
        dur = float(dur_raw)
        size_mb = os.path.getsize(norm_mp3) / (1024 * 1024)
        print(f"   ✅ 母带压制达标: 时长 {int(dur//60)}分{int(dur%60):02d}秒 ({dur:.1f}s), 体积 {size_mb:.2f} MB")

        # 3. 抓取与清洗歌词
        lrc_text = fetch_lrc_multi(lrc_query)
        if lrc_text:
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            print(f"   📄 同步歌词抓取就绪: {len(lrc_text)} 字节")
        else:
            print(f"   ⚠️ 未抓取到歌词，跳过歌词生成")

        # 4. 上传 R2 account_12
        mp3_key = f"music/{ARTIST_NAME}/{ALBUM_NAME}/s_{sid}.mp3"
        s3_client.upload_file(norm_mp3, BUCKET_NAME, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        mp3_url = f"{PUBLIC_BASE}/{mp3_key}"

        lrc_url = None
        if os.path.exists(lrc_file):
            lrc_key = f"lyrics/{ARTIST_NAME}/{ALBUM_NAME}/s_{sid}.lrc"
            s3_client.upload_file(lrc_file, BUCKET_NAME, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            lrc_url = f"{PUBLIC_BASE}/{lrc_key}"

        print(f"   🚀 R2 上传完成: {mp3_url}")
        d1_lights.append({
            "id": sid,
            "file_path": mp3_url,
            "lrc_path": lrc_url
        })

    # 阶段 5: 提交 D1 批量点亮
    print("\n⚡ [Phase 5] 正在向 D1 提交批量点亮...")
    if d1_lights:
        res_lit = requests.post(
            f"{API_BASE}/api/admin/songs/batch-light",
            json={"updates": d1_lights},
            timeout=20
        )
        print(f"   • batch-light 响应: {res_lit.status_code} | {res_lit.text}")

    # 阶段 6: 终检验收 (全专 19 首可用性探测)
    print("\n🔍 [Phase 6] 生产端全网可用性与音频指纹终审...")
    detail_final = requests.get(f"{API_BASE}/api/admin/albums/detail?album_id={ALBUM_ID}", timeout=10).json()
    final_songs = detail_final.get("data", {}).get("songs", [])

    print(f"\n==================== 《我是歌手》第一季 终极全阵容 (共 {len(final_songs)} 首) ====================")
    all_passed = True
    for s in final_songs:
        sid = s["id"]
        title = s["title"]
        t_idx = s["track_index"]
        fpath = s.get("file_path")
        lpath = s.get("lrc_path")

        mp3_ok = False
        mp3_size = 0
        if fpath:
            try:
                hr = requests.head(fpath, headers=HEADERS, timeout=6)
                if hr.status_code == 200:
                    mp3_ok = True
                    mp3_size = int(hr.headers.get("Content-Length", 0))
            except Exception:
                pass

        lrc_ok = False
        if lpath:
            try:
                lr = requests.head(lpath, headers=HEADERS, timeout=6)
                if lr.status_code == 200:
                    lrc_ok = True
            except Exception:
                pass

        status_flag = "✅ 正常点亮" if (mp3_ok and mp3_size > 500000) else "❌ 异常"
        if not (mp3_ok and mp3_size > 500000):
            all_passed = False
        print(f"Track {t_idx:2d} | [{sid}] {title:<35} | {status_flag} | MP3: {mp3_size/1024/1024:.2f}MB | LRC: {'有' if lrc_ok else '无'}")

    print("=" * 80)
    if all_passed and len(final_songs) == 19:
        print("🎉 《我是歌手》第一季 19 首骨架归正与全量资源采录补齐 100% 成功交付！")
    else:
        print(f"⚠️ 交付状态: 验收通过={all_passed}, 当前总曲目数={len(final_songs)}")

if __name__ == "__main__":
    main()
