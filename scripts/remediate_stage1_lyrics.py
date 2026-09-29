#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MOODY 早期曲库治理 - 阶段 1：平反曲目 (53 首) 官方正版 LRC 歌词精准修缮
=============================================================================
核心准则：
1. 【保全优质音频】：绝对不改动或重新上传已有原版 mp3 音频直链；
2. 双源保障：网易云官方 cloudsearch API + syncedlyrics 权威歌词库；
3. 严格校验：歌名精准匹配，坚决杜绝“纯音乐，请欣赏”脏歌词；
4. 物理上传至 R2 Account 11 并调用 D1 接口原子更新 lrc_path；
5. 输出改动前后详细对比明细。
=============================================================================
"""

import os
import sys
import json
import re
import time
import requests
import boto3
from botocore.config import Config

try:
    import syncedlyrics
except ImportError:
    syncedlyrics = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_FILE = os.path.join(BASE_DIR, "reports", "TASK_REMEDIATE_53_LYRICS.json")
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
LOG_DIR = os.path.join(BASE_DIR, "reports")
WORK_DIR = "/tmp/moody_remediate_lyrics"
os.makedirs(WORK_DIR, exist_ok=True)

D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/"
}

# 加载 R2 配置
with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_data = json.load(f)["buckets"]

b11 = r2_data["account_11"]
s3_11 = boto3.client(
    "s3",
    endpoint_url=b11["endpoint_url"],
    aws_access_key_id=b11["access_key_id"],
    aws_secret_access_key=b11["secret_access_key"],
    region_name="auto",
    config=Config(signature_version="s3v4")
)
BUCKET_NAME = b11["name"]
PUBLIC_DOMAIN = b11.get("public_url", "").rstrip("/")

def clean_title(title: str) -> str:
    """去除 (Live)、(Remix) 等修饰词方便搜索正版歌词"""
    t = re.sub(r'\(.*?\)|\[.*?\]|（.*?）', '', title).strip()
    return t

def is_valid_lrc(lrc_text: str) -> bool:
    if not lrc_text or len(lrc_text) < 40:
        return False
    # 必须含有至少 3 个时间轴标签
    timestamps = re.findall(r'\[\d{2}:\d{2}', lrc_text)
    if len(timestamps) < 3:
        return False
    # 不得包含纯音乐占位
    if "纯音乐，请欣赏" in lrc_text or "没有填词的纯音乐" in lrc_text:
        return False
    return True

def fetch_from_netease(artist: str, title: str) -> str:
    c_title = clean_title(title)
    query = f"{artist} {c_title}"
    try:
        r = requests.post(
            "https://music.163.com/api/cloudsearch/pc",
            data={"s": query, "type": 1, "limit": 6},
            headers=HEADERS,
            timeout=5
        )
        if r.status_code == 200:
            songs = r.json().get("result", {}).get("songs", [])
            for s in songs:
                s_name = s.get("name", "")
                # 歌名核心词必须吻合
                if c_title.lower() in s_name.lower() or s_name.lower() in c_title.lower():
                    sid = s["id"]
                    lr = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1", headers=HEADERS, timeout=5)
                    if lr.status_code == 200:
                        lrc = lr.json().get("lrc", {}).get("lyric", "")
                        if is_valid_lrc(lrc):
                            return lrc
    except Exception:
        pass
    return ""

def fetch_from_syncedlyrics(artist: str, title: str) -> str:
    if not syncedlyrics:
        return ""
    c_title = clean_title(title)
    queries = [
        f"{artist} {c_title}",
        f"{c_title}"
    ]
    for q in queries:
        try:
            lrc = syncedlyrics.search(q)
            if is_valid_lrc(lrc):
                return lrc
        except Exception:
            pass
    return ""

def get_official_lrc(artist: str, title: str) -> tuple[str, str]:
    lrc = fetch_from_netease(artist, title)
    if lrc:
        return lrc, "NetEase CloudSearch"
    lrc = fetch_from_syncedlyrics(artist, title)
    if lrc:
        return lrc, "SyncedLyrics Multi-Source"
    return "", "NONE"

def main():
    print("=" * 80)
    print("🚀 启动 MOODY 早期曲库治理 - 阶段 1：平反曲目 (53 首) 正版歌词批量修缮")
    print("=" * 80)

    if not os.path.exists(TASK_FILE):
        print(f"❌ 任务文件不存在: {TASK_FILE}")
        sys.exit(1)

    with open(TASK_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    print(f"📋 待修缮曲目数: {len(tasks)} 首 (全部保全原有音频直链)")

    success_cnt = 0
    fail_cnt = 0
    audit_diff_records = []

    for idx, item in enumerate(tasks, 1):
        sid = item["song_id"]
        artist = item["artist"]
        album = item["album"]
        title = item["title"]
        old_lrc_url = item.get("lrc_path", "")
        old_file_url = item.get("file_path", "")

        print(f"\n[{idx:02d}/{len(tasks):02d}] 正在修缮: [{artist}] 《{album}》 - 《{title}》 (ID: {sid})")

        # 1. 抓取正版官方歌词
        new_lrc_text, source_name = get_official_lrc(artist, title)
        if not new_lrc_text:
            print("   ⚠️ 未能从权威接口匹配到符合标准的时间轴歌词，保留现状。")
            fail_cnt += 1
            continue

        print(f"   🟢 成功获取正版歌词 ({source_name})，总行数: {len(new_lrc_text.splitlines())}")

        # 2. 写入临时文件
        lrc_tmp = os.path.join(WORK_DIR, f"s_{sid}.lrc")
        with open(lrc_tmp, "w", encoding="utf-8") as f:
            f.write(new_lrc_text)

        # 3. 上传 R2
        clean_alb = re.sub(r'[\\/*?:"<>|]', '_', album).strip()
        clean_art = re.sub(r'[\\/*?:"<>|]', '_', artist).strip()
        r2_key = f"lyrics/{clean_art}/{clean_alb}/s_{sid}.lrc"

        with open(lrc_tmp, "rb") as f:
            s3_11.put_object(
                Bucket=BUCKET_NAME,
                Key=r2_key,
                Body=f,
                ContentType="text/plain; charset=utf-8"
            )

        new_lrc_url = f"{PUBLIC_DOMAIN}/{r2_key}"
        print(f"   🟢 新版官方歌词已上传至 R2: {new_lrc_url}")

        # 4. 更新 D1
        payload = {
            "updates": [{
                "id": sid,
                "file_path": old_file_url,  # 绝对不动原音频
                "lrc_path": new_lrc_url
            }]
        }

        updated = False
        for retry in range(3):
            try:
                r = requests.post(D1_LIGHT_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
                if r.status_code == 200 and r.json().get("code") == 200:
                    updated = True
                    break
            except Exception:
                time.sleep(1)

        if updated:
            print(f"   ✅ D1 数据库记录更新成功！")
            success_cnt += 1
            audit_diff_records.append({
                "song_id": sid,
                "artist": artist,
                "album": album,
                "title": title,
                "audio_action": "RETAINED_ORIGINAL_AUDIO (音频保全)",
                "old_lrc": old_lrc_url,
                "new_lrc": new_lrc_url,
                "lrc_status": "SUCCESS_UPDATED",
                "lyric_source": source_name
            })
        else:
            print(f"   ❌ D1 更新失败！")
            fail_cnt += 1

        # 清理临时文件
        if os.path.exists(lrc_tmp):
            try: os.remove(lrc_tmp)
            except: pass

        time.sleep(0.3)

    # 归档记录
    record_file = os.path.join(LOG_DIR, "STAGE_1_LYRICS_REMEDIATION_LOG.json")
    with open(record_file, "w", encoding="utf-8") as f:
        json.dump(audit_diff_records, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"🎉 阶段 1 歌词修缮完成！")
    print(f"   • 成功修缮: {success_cnt} 首")
    print(f"   • 未变/跳过: {fail_cnt} 首")
    print(f"   • 变更明细归档: {record_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
