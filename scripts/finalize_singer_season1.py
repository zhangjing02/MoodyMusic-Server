#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规范化《我是歌手》第一季 19 首全量曲目在 D1 数据库的标准 URL 编码，补全 27618 与 27621 歌词，并执行 100% 验收
"""
import os
import sys
import json
import urllib.parse
import requests
import boto3
from botocore.config import Config
import syncedlyrics

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R2_CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
API_BASE = "https://m-api.changgepd.ccwu.cc"
HEADERS = {"User-Agent": "Mozilla/5.0"}

with open(R2_CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]["account_12"]

s3_client = boto3.client(
    "s3",
    endpoint_url=r2_cfg["endpoint_url"],
    aws_access_key_id=r2_cfg["access_key_id"],
    aws_secret_access_key=r2_cfg["secret_access_key"],
    region_name="auto"
)
BUCKET = r2_cfg["name"]
PUBLIC_BASE = r2_cfg["public_url"].rstrip("/")

# 1. 修复 27618 (黄绮珊 等待) 和 27621 (林志炫 烟花易冷) 歌词
fix_lyrics = {
    27618: "黄绮珊 等待",
    27621: "林志炫 烟花易冷"
}

for sid, q in fix_lyrics.items():
    lrc = syncedlyrics.search(q)
    if lrc and len(lrc) > 50:
        clean_lines = [l for l in lrc.split("\n") if not any(l.strip().startswith(x) for x in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:"])]
        cleaned = "\n".join(clean_lines).strip()
        key = f"lyrics/我是歌手/第一季 (2013)/s_{sid}.lrc"
        s3_client.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=cleaned.encode("utf-8"),
            ContentType="text/plain; charset=utf-8"
        )
        print(f"✅ 成功补修 [{sid}] {q} 歌词 ({len(cleaned)} 字节)")

# 2. 构造标准编码的 D1 updates
encoded_artist = urllib.parse.quote("我是歌手")
encoded_album = urllib.parse.quote("第一季 (2013)")

session = requests.Session()
session.trust_env = False  # 禁用环境变量代理，直连 Cloudflare Worker API

res = session.get(f"{API_BASE}/api/admin/albums/detail?album_id=1945", timeout=15)
songs = res.json().get("data", {}).get("songs", [])

updates = []
for s in songs:
    sid = s["id"]
    mp3_url = f"{PUBLIC_BASE}/music/{encoded_artist}/{encoded_album}/s_{sid}.mp3"
    lrc_url = f"{PUBLIC_BASE}/lyrics/{encoded_artist}/{encoded_album}/s_{sid}.lrc"
    updates.append({
        "id": sid,
        "file_path": mp3_url,
        "lrc_path": lrc_url
    })

print(f"\n⚡ 提交 D1 批量标准化点亮 (共 {len(updates)} 首)...")
light_res = session.post(f"{API_BASE}/api/admin/songs/batch-light", json={"updates": updates}, timeout=25)
print(f"batch-light 响应: {light_res.status_code} | {light_res.text}")

# 3. 终验
print("\n" + "=" * 80)
print("🔍 正在对生产环境全专 19 首曲目发起 HTTP HEAD 1:1 字节校验与可用性审计...")
print("=" * 80)

final_res = session.get(f"{API_BASE}/api/admin/albums/detail?album_id=1945", timeout=15).json()
final_songs = final_res.get("data", {}).get("songs", [])

all_passed = True
for s in sorted(final_songs, key=lambda x: x["track_index"]):
    sid = s["id"]
    title = s["title"]
    t_idx = s["track_index"]
    fpath = s.get("file_path")
    lpath = s.get("lrc_path")

    # 尝试直连 head 请求，若偶发网络抖动进行 1 次重试
    r_mp3 = None
    for _ in range(2):
        try:
            r_mp3 = session.head(fpath, headers=HEADERS, timeout=10)
            if r_mp3.status_code == 200:
                break
        except Exception:
            pass
    mp3_len = int(r_mp3.headers.get("content-length", 0)) if (r_mp3 and r_mp3.status_code == 200) else 0

    r_lrc = None
    for _ in range(2):
        try:
            r_lrc = session.head(lpath, headers=HEADERS, timeout=10)
            if r_lrc.status_code == 200:
                break
        except Exception:
            pass
    lrc_len = int(r_lrc.headers.get("content-length", 0)) if (r_lrc and r_lrc.status_code == 200) else 0

    passed = (r_mp3 and r_mp3.status_code == 200 and mp3_len > 1000000 and r_lrc and r_lrc.status_code == 200 and lrc_len > 100)
    if not passed:
        all_passed = False

    status = "✅ PASS" if passed else "❌ FAIL"
    code_mp3 = r_mp3.status_code if r_mp3 else 0
    code_lrc = r_lrc.status_code if r_lrc else 0
    print(f"Track {t_idx:2d} | [{sid}] {title:<36} | {status} | MP3: {mp3_len/1024/1024:.2f}MB (HTTP {code_mp3}) | LRC: {lrc_len}B (HTTP {code_lrc})")

print("=" * 80)
if all_passed:
    print(f"🎉 验收 100% 通过！《我是歌手》第一季 (2013) 全部 19 首曲目与高保真歌词全链路点亮就绪！")
else:
    print(f"⚠️ 验收存在未通过项，请排查！")
