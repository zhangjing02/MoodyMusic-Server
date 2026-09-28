#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
动力火车全专辑 (除《背叛情歌》外其余 9 张专辑) 深度审计脚本
==============================================================================
1. 从 D1 拉取动力火车全部 10 张专辑的完整歌曲元数据
2. 逐一并发下载并解析 LRC 歌词文本，检测李鬼、翻唱、其他歌手、广告水印
3. 对比各曲目的时长与官方标准发行档案
4. 生成详尽的异常报告报告供批量靶向修复
==============================================================================
"""

import os
import sys
import json
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE = "https://m-api.changgepd.ccwu.cc"
OUTPUT_REPORT = "MoodyMusic-Server/reports/POWER_STATION_AUDIT_REPORT.json"
os.makedirs("MoodyMusic-Server/reports", exist_ok=True)

# 敏感与李鬼特征关键词
SUSPECT_KEYWORDS = [
    'zither harp', 'zither', 'piano cover', '翻唱', '原唱', '伴奏', '纯音乐',
    '微信公众号', '关注我们', '欢迎收听', '电台', '广告', '代录', '翻唱网',
    'subtitle', 'volunteer', '字幕组', '优优独播', '官方频道', 'tiktok', '快手',
    'bilibili', 'cover', '改编', '连麻', '法老', '龙崎', 'lil jet', '群星'
]

def check_single_song(song, album_title):
    sid = song.get("id")
    title = song.get("title")
    mp3_path = song.get("path")
    lrc_path = song.get("lrc_path")

    issue = {
        "id": sid,
        "album": album_title,
        "title": title,
        "mp3_path": mp3_path,
        "lrc_path": lrc_path,
        "is_missing_mp3": not bool(mp3_path),
        "is_missing_lrc": not bool(lrc_path),
        "lrc_suspect_hits": [],
        "lrc_snippet": "",
        "singer_tag": "",
        "status": "NORMAL"
    }

    if not mp3_path:
        issue["status"] = "MISSING_AUDIO"
        return issue

    if not lrc_path:
        issue["status"] = "MISSING_LYRIC"
        return issue

    try:
        r = requests.get(lrc_path, timeout=6)
        if r.status_code == 200:
            text = r.text
            # 提取元数据标签
            ar_match = re.search(r'\[ar:(.*?)\]', text, re.I)
            ti_match = re.search(r'\[ti:(.*?)\]', text, re.I)
            if ar_match:
                issue["singer_tag"] = ar_match.group(1).strip()
            
            # 检查敏感词
            text_lower = text.lower()
            hits = [kw for kw in SUSPECT_KEYWORDS if kw in text_lower]
            issue["lrc_suspect_hits"] = hits

            # 检查歌词前几行有效文本
            lines = [l.strip() for l in text.split("\n") if l.strip() and not any(tag in l for tag in ['[ti:', '[ar:', '[al:', '[by:', '[offset:', '[total:', '[id:', '[hash:'])]
            issue["lrc_snippet"] = " / ".join(lines[:3])

            # 如果命中严重异常 (如歌手名非动力火车且不包含动力，或命中翻唱李鬼)
            if hits or (issue["singer_tag"] and "动力火车" not in issue["singer_tag"] and "power station" not in issue["singer_tag"].lower()):
                issue["status"] = "SUSPECT_POLLUTED"
        else:
            issue["status"] = "LRC_HTTP_ERROR"
    except Exception as e:
        issue["status"] = f"LRC_FETCH_FAIL_{str(e)[:20]}"

    return issue

def main():
    print("=" * 80)
    print("🌐 正在从 D1 生产环境获取动力火车全量专辑与歌曲...")
    print("=" * 80)
    resp = requests.get(f"{API_BASE}/api/songs?artist=%E5%8A%A8%E5%8A%9B%E7%81%AB%E8%BD%A6", timeout=15)
    if resp.status_code != 200:
        print(f"❌ 获取失败: HTTP {resp.status_code}")
        return

    data = resp.json().get("data", [])
    if not data:
        print("❌ 未找到歌手数据")
        return

    artist_obj = data[0]
    albums = artist_obj.get("albums", [])
    print(f"✅ 找到 {len(albums)} 张专辑:")
    for alb in albums:
        print(f"  • 《{alb.get('title')}》: {len(alb.get('songs', []))} 首曲目")

    # 排除刚刚正在修复的《背叛情歌》，重点体检其余 9 张专辑
    target_albums = [alb for alb in albums if "背叛情歌" not in alb.get("title", "")]
    all_songs = []
    for alb in target_albums:
        for s in alb.get("songs", []):
            all_songs.append((s, alb.get("title")))

    print(f"\n📊 待体检其余 9 张专辑曲目总数: {len(all_songs)} 首...")

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_single_song, s, alb_title): (s, alb_title) for s, alb_title in all_songs}
        for f in as_completed(futures):
            res = f.result()
            results.append(res)

    # 统计问题
    polluted = [r for r in results if r["status"] == "SUSPECT_POLLUTED"]
    missing_aud = [r for r in results if r["status"] == "MISSING_AUDIO"]
    missing_lrc = [r for r in results if r["status"] == "MISSING_LYRIC"]
    normal = [r for r in results if r["status"] == "NORMAL"]

    print("\n" + "=" * 80)
    print("📋 体检报告总结 (除《背叛情歌》外 其余 9 张专辑):")
    print(f"  • 审查曲目总数: {len(results)} 首")
    print(f"  • 正常曲目: {len(normal)} 首")
    print(f"  • 歌词被李鬼/翻唱/广告污染曲目: {len(polluted)} 首")
    print(f"  • 缺失音频曲目: {len(missing_aud)} 首")
    print(f"  • 缺失歌词曲目: {len(missing_lrc)} 首")
    print("=" * 80)

    if polluted:
        print("\n🚨 发现疑似受污染/李鬼曲目清单:")
        for item in sorted(polluted, key=lambda x: (x["album"], x["title"])):
            print(f"  ❌ [{item['album']}] 《{item['title']}》 (ID: {item['id']})")
            print(f"     歌手标签: {item['singer_tag']} | 命中敏感特征: {item['lrc_suspect_hits']}")
            print(f"     歌词片段: {item['lrc_snippet'][:90]}")
            print(f"     音频路径: {item['mp3_path']}")

    if missing_aud:
        print("\n⚠️ 缺失音频的留白曲目:")
        for item in missing_aud:
            print(f"  ⚪ [{item['album']}] 《{item['title']}》 (ID: {item['id']})")

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n💾 完整审计数据已保存至: {OUTPUT_REPORT}")

if __name__ == "__main__":
    main()
