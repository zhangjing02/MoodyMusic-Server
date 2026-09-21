#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过 /api/admin/albums/detail 直接解析莫文蔚与萧亚轩未点亮曲目的 Song ID
"""

import requests
import json
import time

WORKER = "https://m-api.changgepd.ccwu.cc"
PROXIES = {"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}

def main():
    print("================================================================")
    print("🔍 正在拉取莫文蔚与萧亚轩在 Cloudflare D1 中的精确曲目与 ID...")
    print("================================================================")

    resolved = []

    # 1. 获取歌手所有专辑的真实 album_id
    for art in ["莫文蔚", "萧亚轩"]:
        r = requests.get(f"{WORKER}/api/songs?artist={art}", proxies=PROXIES)
        artist_obj = r.json().get("data", [])[0]
        
        # 通过查询平铺数据获取每个 album_title 对应的真实 album_id
        # 我们直接调用 /api/admin/albums/detail 遍历
        # 先获取该歌手名下的全部专辑
        print(f"\n▶ 正在扫描歌手: 【{art}】...")
        for alb in artist_obj.get("albums", []):
            atitle = alb["title"]
            unlit_songs = [s for s in alb.get("songs", []) if not s.get("path")]
            if not unlit_songs:
                continue
                
            print(f"   💿 检查残缺专辑: 《{atitle}》 (未点亮 {len(unlit_songs)} 首)")

            # 用关键词搜 album
            try:
                r_s = requests.get(
                    f"{WORKER}/api/admin/albums/search",
                    params={"keyword": atitle},
                    proxies=PROXIES,
                    timeout=10
                )
                res_data = r_s.json().get("data", [])
            except Exception as e:
                res_data = []

            aid = None
            if isinstance(res_data, list):
                for item in res_data:
                    if isinstance(item, dict) and item.get("artist_name") == art:
                        if item.get("title") == atitle or atitle in item.get("title") or item.get("title") in atitle:
                            aid = item.get("id")
                            break
            
            if not aid:
                print(f"      ⚠️ 未搜到 album_id，尝试备用探测...")
                continue

            # 获取详情
            try:
                r_d = requests.get(
                    f"{WORKER}/api/admin/albums/detail",
                    params={"album_id": aid},
                    proxies=PROXIES,
                    timeout=10
                )
                det_songs = r_d.json().get("data", {}).get("songs", [])
            except Exception as e:
                det_songs = []

            for u_s in unlit_songs:
                tit = u_s["title"]
                sid = None
                for ds in det_songs:
                    if ds.get("title") == tit or ds.get("title", "").strip().lower() == tit.strip().lower():
                        sid = ds.get("id")
                        break
                if not sid:
                    for ds in det_songs:
                        if tit in ds.get("title", "") or ds.get("title", "") in tit:
                            sid = ds.get("id")
                            break

                if sid:
                    search_t = tit
                    if "Karen獨唱版" in search_t:
                        search_t = "色情男女 莫文蔚"
                    elif "淘宝" in search_t:
                        search_t = "淘宝 莫文蔚"
                    elif "对谁都好" in search_t or "對誰都好" in search_t:
                        search_t = "对谁都好 萧亚轩"
                    elif "天雷地火" in search_t:
                        search_t = "天雷地火 萧亚轩"
                    
                    resolved.append({
                        "id": sid,
                        "artist": art,
                        "album": atitle,
                        "title": tit,
                        "search_title": search_t
                    })
                    print(f"      ✅ [绑定成功] 《{tit}》 -> ID: {sid} (检索词: '{search_t}')")
                else:
                    print(f"      ❌ 未能匹配到 Song ID: 《{tit}》")

            time.sleep(0.05)

    print("\n================================================================")
    print(f"🎉 第二战役已成功解析绑定 {len(resolved)} 首曲目！")
    print("================================================================\n")

    with open("sparse_karen_elva_resolved.json", "w", encoding="utf-8") as f:
        json.dump(resolved, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
