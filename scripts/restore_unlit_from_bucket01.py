#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
精准复原第一存储桶中被误置灰的全部真实物理资产
原则：
1. 仅针对当前 Cloudflare D1 中处于置灰状态（path 为 None）的曲目进行复原点亮；
2. 若某曲目当前已在更高版本桶（如 Bucket 07/08）点亮，坚决不降级覆盖；
3. 统一使用绝对 CDN 公网直链（https://r2.changgepd.ccwu.cc/...），确保全端（Android / Web）秒级起播，无 404 隐患。
"""

import json
import time
import requests

D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
ASSETS_PATH = "reports/bucket01_verified_assets.json"

sess = requests.Session()
sess.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})

print("1. 拉取 D1 生产环境当前全部歌曲状态...", flush=True)
resp = sess.get(D1_SONGS_URL, timeout=30)
d1_artists = resp.json().get("data", [])

# 提取当前 D1 中已点亮的歌曲 ID
currently_lit_ids = set()
all_d1_songs = {}
for art in d1_artists:
    for alb in art.get("albums", []):
        for s in alb.get("songs", []):
            sid = s.get("id")
            if not sid and s.get("path"):
                import re
                m = re.search(r's_(\d+)\.(mp3|m4a)', s.get("path"))
                if m: sid = int(m.group(1))
            if sid:
                all_d1_songs[sid] = s
                if s.get("path"):
                    currently_lit_ids.add(sid)

print(f"   • D1 总收录曲目: {len(all_d1_songs)}")
print(f"   • 当前已点亮曲目: {len(currently_lit_ids)}")
print(f"   • 当前置灰曲目: {len(all_d1_songs) - len(currently_lit_ids)}")

print("\n2. 读取第一存储桶已核验的物理资产清单...", flush=True)
with open(ASSETS_PATH, "r", encoding="utf-8") as f:
    verified_data = json.load(f)["found_songs"]

print(f"   • 第一存储桶真实物理存在: {len(verified_data)} 首")

# 筛选需要复原点亮的曲目（当前置灰但第一桶存在）
to_restore = []
for s in verified_data:
    sid = s["id"]
    if sid not in currently_lit_ids:
        # 构造更新 payload
        update_item = {
            "id": sid,
            "file_path": s["file_path"],
            "is_lit": 1
        }
        if s.get("lrc_path"):
            update_item["lrc_path"] = s["lrc_path"]
        to_restore.append((update_item, s["artist"], s["album"], s["title"]))

print(f"\n3. 精准匹配结果: 共有 {len(to_restore)} 首被误置灰的曲目需要复原点亮！")

# 统计各歌手待复原数量
by_artist = {}
for item, art, alb, title in to_restore:
    by_artist.setdefault(art, []).append((alb, title))

for art, tracklist in sorted(by_artist.items(), key=lambda x: -len(x[1])):
    print(f"   • {art:<12}: 待复原 {len(tracklist):>3} 首")

# 分批调用 batch-light 提交 D1
chunk_size = 50
success_cnt = 0
updates_only = [item for item, _, _, _ in to_restore]

print(f"\n4. 开始分批向 D1 网关提交复原点亮 (每批 {chunk_size} 首)...", flush=True)
for i in range(0, len(updates_only), chunk_size):
    chunk = updates_only[i:i + chunk_size]
    for retry in range(3):
        try:
            r = sess.post(D1_LIGHT_URL, json={"updates": chunk}, timeout=25)
            if r.status_code == 200:
                success_cnt += len(chunk)
                print(f"   ✅ 批次 [{min(i + chunk_size, len(updates_only))}/{len(updates_only)}] 成功! (累积复原: {success_cnt})")
                break
            else:
                print(f"   ⚠️ 批次 [{i}] HTTP {r.status_code}: {r.text}")
        except Exception as e:
            print(f"   ⚠️ 批次 [{i}] 异常重试: {e}")
            time.sleep(1)

print(f"\n=======================================================")
print(f"🎉 批量复原完成! 成功点亮: {success_cnt} / {len(to_restore)} 首")
print(f"=======================================================\n")
