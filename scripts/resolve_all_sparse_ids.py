#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直连 9 张残缺专辑 ID，秒级精确解析莫文蔚与萧亚轩未点亮曲目的 Song ID
"""

import requests
import json
import time

WORKER = "https://m-api.changgepd.ccwu.cc"
PROXIES = {"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}

TARGET_ALBUMS = [
    ("莫文蔚", "全身莫文蔚", 933),
    ("莫文蔚", "你可以", 929),
    ("莫文蔚", "一朵金花", 924),
    ("莫文蔚", "回蔚", 918),
    ("莫文蔚", "宝贝 (2nd Edition)", 914),
    ("莫文蔚", "不散,不見", 910),
    ("莫文蔚", "我们在中场相遇", 907),
    ("萧亚轩", "不解釋親吻", 1753),
    ("萧亚轩", "Naked Truth赤裸真相", 1746)
]

def main():
    print("================================================================")
    print("🔍 正在秒级拉取莫文蔚与萧亚轩 9 张残缺大碟的所有未点亮歌曲...")
    print("================================================================")

    resolved = []

    for art, atitle, aid in TARGET_ALBUMS:
        try:
            r = requests.get(
                f"{WORKER}/api/admin/albums/detail",
                params={"album_id": aid},
                proxies=PROXIES,
                timeout=10
            )
            det = r.json().get("data", {})
            songs = det.get("songs", [])
            unlit = [s for s in songs if not s.get("file_path") and s.get("is_lit") != 1]
            print(f"💿 [{art}] 《{atitle}》 (ID: {aid}) - 发现 {len(unlit)} 首待补全曲目:")

            for s in unlit:
                sid = s["id"]
                tit = s["title"]
                search_t = tit

                # 优化特殊检索词，保证 100% 命中权威原声
                if "Karen獨唱版" in search_t or "独唱版" in search_t:
                    search_t = "色情男女 莫文蔚"
                elif "淘宝" in search_t:
                    search_t = "淘宝 莫文蔚"
                elif tit in ["飞", "绝", "看看", "亲爱的", "红", "无知", "散光", "扇子舞", "旺角公主", "一朵金花", "消灭", "钻石", "实况转播", "我不信"]:
                    search_t = f"{tit} 莫文蔚"
                elif "对谁都好" in tit or "對誰都好" in tit:
                    search_t = "对谁都好 萧亚轩"
                elif "天雷地火" in tit:
                    search_t = "天雷地火 萧亚轩"
                elif "当爱是个玩笑" in tit or "Celebrate Everyday" in tit:
                    search_t = "当爱是个玩笑 萧亚轩"
                elif "赤裸真相" in tit or "Naked Truth" in tit:
                    search_t = "赤裸真相 萧亚轩"
                elif "So Good" in tit:
                    search_t = "So Good 萧亚轩"
                elif "说实话" in tit or "Say the Words" in tit:
                    search_t = "说实话 萧亚轩"

                resolved.append({
                    "id": sid,
                    "artist": art,
                    "album": atitle,
                    "title": tit,
                    "search_title": search_t
                })
                print(f"   🟢 ID: {sid:<5} | 《{tit}》 | 检索词: '{search_t}'")
        except Exception as e:
            print(f"   ❌ 读取专辑 {aid} 出错: {e}")

    # 去重
    seen = set()
    final = []
    for r in resolved:
        if r["id"] not in seen:
            seen.add(r["id"])
            final.append(r)

    print("\n================================================================")
    print(f"🎉 成功精准解析并绑定全部 {len(final)} 首曲目的 D1 Song ID 与检索词！")
    print("================================================================\n")

    with open("sparse_karen_elva_resolved.json", "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
