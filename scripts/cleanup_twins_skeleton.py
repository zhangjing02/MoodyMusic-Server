#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twins 专辑骨架清洗与正名脚本
- 热更正 4 首历史骨架曲名错别字
- 剔除 12 首非 Twins 本人跨歌手/幽灵骨架曲目
- 输出改动前后（Before / After）严密对比
"""

import sys
import json
import socket
import requests

# Cloudflare IP Pinning
_orig_getaddrinfo = socket.getaddrinfo
def _custom_getaddrinfo(host, port, *args, **kwargs):
    if host == "m-api.changgepd.ccwu.cc":
        return _orig_getaddrinfo("172.67.199.94", port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = _custom_getaddrinfo

BASE_URL = "https://m-api.changgepd.ccwu.cc"

# Twins 的真实专辑 ID 列表 (1993 ~ 2000)
TWINS_ALBUM_IDS = [1993, 1994, 1995, 1996, 1997, 1998, 1999, 2000]

# 1. 待正名曲目映射 (ID -> 正式名称)
TITLE_UPDATES = [
    {"id": 28092, "title": "流金搖擺", "old_title": "流金歲月"},
    {"id": 28093, "title": "一時無倆", "old_title": "一時倦了"},
    {"id": 28036, "title": "快熟時代", "old_title": "快過戰車"},
    {"id": 28040, "title": "換季", "old_title": "跩跩"},
]

# 2. 待清理的李鬼曲目清单 (真实底表 album_id)
GHOST_SONGS_BY_ALBUM = {
    1995: {
        "album_title": "Touch of Love",
        "song_ids": [28054, 28055, 28056],
        "details": {
            28054: "盲愛 (刘德华/郑秀文)",
            28055: "難忘的星期天 (杂录)",
            28056: "我的驕傲 (容祖儿)"
        }
    },
    1996: {
        "album_title": "Evolution",
        "song_ids": [28063, 28064, 28065, 28067],
        "details": {
            28063: "拖男帶女 (方大同)",
            28064: "純屬玩笑 (陈慧琳)",
            28065: "雙重打擊 (容祖儿)",
            28067: "快樂的眼淚 (童亦桦)"
        }
    },
    1997: {
        "album_title": "Magic",
        "song_ids": [28075],
        "details": {
            28075: "人生漫遊 (非正式专辑曲目)"
        }
    },
    1999: {
        "album_title": "八十塊環遊世界",
        "song_ids": [28094, 28098],
        "details": {
            28094: "怎麼開心怎麼過 (杨顺高)",
            28098: "純屬玩笑 (陈慧琳)"
        }
    },
    2000: {
        "album_title": "桐話妍語",
        "song_ids": [28107],
        "details": {
            28107: "雙重打擊 (容祖儿)"
        }
    },
    1994: {
        "album_title": "雙生兒",
        "song_ids": [28044],
        "details": {
            28044: "No. 1 (非正式专辑曲目)"
        }
    }
}

def get_album_details(album_id):
    """获取单个专辑及其曲目列表"""
    url = f"{BASE_URL}/api/admin/albums/detail?album_id={album_id}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("data", {})
    return data

def main():
    print("=" * 80)
    print("🚀 开始执行 Twins 骨架清洗与正名操作")
    print("=" * 80)

    # 1. 抓取执行前状态
    print("📡 正在获取清洗前 (Before) 状态...")
    before_state = {}
    for aid in TWINS_ALBUM_IDS:
        before_state[aid] = get_album_details(aid)
    
    total_before = sum(len(before_state[aid].get("songs", [])) for aid in TWINS_ALBUM_IDS)
    lit_before = sum(sum(1 for s in before_state[aid].get("songs", []) if s.get("file_path")) for aid in TWINS_ALBUM_IDS)
    print(f"📊 清洗前现状: 全库 8 张专辑，总计 {total_before} 首，已点亮 {lit_before} 首，未点亮 {total_before - lit_before} 首")

    # 2. 执行 4 首歌名热更正
    print("\n" + "=" * 80)
    print("📝 Step 1: 执行 4 首曲名热更正 (batch-update)")
    print("=" * 80)
    update_payload = {
        "updates": [{"id": item["id"], "title": item["title"]} for item in TITLE_UPDATES]
    }
    update_url = f"{BASE_URL}/api/admin/songs/batch-update"
    r_up = requests.post(update_url, json=update_payload, timeout=15)
    print(f"响应码: {r_up.status_code}, 内容: {r_up.text}")
    if r_up.status_code != 200:
        print("❌ 歌名更正失败！")
        sys.exit(1)
    print("✅ 4 首曲名热更正完成！")

    # 3. 执行 12 首李鬼曲目物理剔除
    print("\n" + "=" * 80)
    print("🗑️ Step 2: 执行 12 首李鬼曲目剔除 (cleanup-duplicates)")
    print("=" * 80)
    cleanup_url = f"{BASE_URL}/api/admin/albums/cleanup-duplicates"
    deleted_total = 0

    for alb_id, info in GHOST_SONGS_BY_ALBUM.items():
        alb_title = info["album_title"]
        song_ids = info["song_ids"]
        print(f"\n🎯 正在处理专辑 [{alb_id}] 《{alb_title}》: 剔除 {len(song_ids)} 首幽灵曲目 {song_ids}")
        for sid in song_ids:
            print(f"   - 待删 ID {sid}: {info['details'].get(sid)}")
        
        payload = {
            "album_id": alb_id,
            "song_ids": song_ids
        }
        r_del = requests.post(cleanup_url, json=payload, timeout=15)
        print(f"   响应: {r_del.status_code} - {r_del.text}")
        if r_del.status_code != 200:
            print(f"❌ 专辑 [{alb_id}] 清理失败！")
            sys.exit(1)
        else:
            deleted_total += len(song_ids)

    print(f"\n✅ 李鬼曲目物理清理完成，累计成功剔除: {deleted_total} 首")

    # 4. 抓取执行后状态并验证对比
    print("\n" + "=" * 80)
    print("🔍 Step 3: 抓取清洗后 (After) 状态并验证对比")
    print("=" * 80)
    after_state = {}
    for aid in TWINS_ALBUM_IDS:
        after_state[aid] = get_album_details(aid)

    total_after = sum(len(after_state[aid].get("songs", [])) for aid in TWINS_ALBUM_IDS)
    lit_after = sum(sum(1 for s in after_state[aid].get("songs", []) if s.get("file_path")) for aid in TWINS_ALBUM_IDS)
    unlit_after = total_after - lit_after

    print("\n" + "=" * 95)
    print(f"{'专辑名称':<20} | {'清洗前曲目':>10} | {'清洗后曲目':>10} | {'已点亮':>6} | {'未点亮':>6} | {'完成率':>8}")
    print("-" * 95)

    for aid in TWINS_ALBUM_IDS:
        b_data = before_state[aid]
        b_title = b_data.get("album", {}).get("title", f"专辑 {aid}")
        b_count = len(b_data.get("songs", []))

        a_data = after_state[aid]
        a_songs = a_data.get("songs", [])
        a_count = len(a_songs)
        a_lit = sum(1 for s in a_songs if s.get("file_path"))
        a_unlit = a_count - a_lit
        pct = (a_lit / a_count * 100) if a_count > 0 else 0
        tag = "🏆 100%" if a_unlit == 0 else f"⚠️ 缺 {a_unlit}"

        print(f"{b_title:<20} | {b_count:>10} | {a_count:>10} | {a_lit:>6} | {a_unlit:>6} | {tag:>8}")

    print("-" * 95)
    print(f"{'全库合计 (8张专辑)':<20} | {total_before:>10} | {total_after:>10} | {lit_after:>6} | {unlit_after:>6} | {lit_after/total_after*100:.1f}%")
    print("=" * 95)

    # 检查 4 首更名结果
    print("\n🔎 核验 4 首曲目更名落地情况:")
    all_after_songs = {}
    for aid in TWINS_ALBUM_IDS:
        for s in after_state[aid].get("songs", []):
            all_after_songs[s["id"]] = s["title"]
    
    for item in TITLE_UPDATES:
        sid = item["id"]
        current_title = all_after_songs.get(sid, "不存在")
        status = "✅ 成功更正" if current_title == item["title"] else f"❌ 异常 (当前: {current_title})"
        print(f" - ID [{sid}] 原名: 《{item['old_title']}》 -> 新名: 《{current_title}》 [{status}]")

    # 检查 12 首李鬼是否已彻底不复存在
    print("\n🔎 核验 12 首李鬼曲目剔除情况:")
    ghost_leak_count = 0
    for aid, info in GHOST_SONGS_BY_ALBUM.items():
        for sid in info["song_ids"]:
            if sid in all_after_songs:
                print(f" ⚠️ 警告: 李鬼曲目 ID [{sid}] 《{all_after_songs[sid]}》 仍残留于底表！")
                ghost_leak_count += 1
            else:
                print(f" ✅ ID [{sid}] {info['details'].get(sid)} 已彻底从 D1 剔除")
    
    if ghost_leak_count == 0:
        print("\n🎉 12 首李鬼曲目已全部彻底剔除！D1 底表骨架 100% 纯净正品！")
    else:
        print(f"\n❌ 发现 {ghost_leak_count} 首李鬼曲目未成功剔除！")

if __name__ == "__main__":
    main()
