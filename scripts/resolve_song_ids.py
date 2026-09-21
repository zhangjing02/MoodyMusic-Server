#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动解析并关联未点亮歌曲在 Cloudflare D1 中的精确 Song ID 与 Album ID
同时注入高质量华语录音室母带真实检索词 (search_title)
"""

import json
import time
import urllib.parse
import subprocess

# 权威中英文真实歌名映射字典
ENGLISH_TO_CHINESE_SEARCH = {
    # 苏慧伦
    "Tender Foolishness": "溫柔的傻事",
    "The Tenderest Bondage": "最溫柔的牽絆",
    "My Tears Are Shaking": "我的眼淚在顫抖",
    # 周华健
    "A Hard Scripture To Read": "难念的经",
    "The Flowery Heart": "花心",
    "How Are You Getting Along": "过得好不好",
    "Sword of Love": "刀剑如梦",
    "Chessmen": "棋子",
    "Laughter and Cry": "笑与哭",
    "Heart From the Past": "昨晚的梦到明天",
    "Beloved Baby Forever": "永远的宝贝",
    "Forsaken You, Please Stay": "舍不得你",
    "Happiness": "快乐",
    "Momentary Love": "爱冒险的梦",
    "A Man With Stories": "有故事的人",
    "Feel Troubled": "烦",
    "Who's Coming To Dinner": "谁来晚餐",
    "Show Your Smile": "让我欢喜让我忧",
    "Separate Lives": "爱一个人恨一个人",
    "Walk You Home": "送你回家",
    "If Now": "如果现在",
    "We Don't Cry": "我们不哭",
    "So Happy I Want to Cry": "好想哭",
    "Too Early to Tell": "说谎",
    "I Truly Give My Love": "我付出我的真爱",
    "Lonely Eyes": "寂寞的眼",
    "Never Miss the Target": "百发百中",
    "Blame It on Myself": "自责",
    "Silent Night, Holy Night": "平安夜",
    # 李玟
    "In My Mind": "愛我久一點",
    "If I Rely On You": "如果依賴",
    "The Best Of Love": "最好的愛",
    "Wo Men Shuo Hao": "我們說好",
    "Every Moments of Love": "愛的每一刻",
    "The Answer": "答案",
    "I'm Still Your Lover": "我依然是你的情人",
    "How Could U let Me be in Sorrows": "你怎麼捨得我難過",
    "I am Truly Hurt": "我是真的受傷了",
    "Stuck On U": "著迷",
    "Could it be": "會不會",
    # 黎明
    "Don't Know What to Say": "不知所謂",
    # Beyond
    "遥かなるゆめに～Far away": "海闊天空",
    "係要聽ROCK N' ROLL": "係要聽ROCK N ROLL",
    "谁来主宰": "誰來主宰",
    "完全的拥有": "完全的擁有"
}

def fetch_album_detail(album_title, artist_name):
    # 对专辑名称进行清洗（去除括号中多余注释进行搜索）
    clean_alb = album_title.split('(')[0].split('（')[0].strip()
    encoded_alb = urllib.parse.quote(clean_alb)
    url_search = f"https://m-api.changgepd.ccwu.cc/api/admin/albums/search?keyword={encoded_alb}"
    
    try:
        cmd = ["curl", "-s", url_search]
        r = subprocess.check_output(cmd, timeout=10).decode("utf-8")
        data = json.loads(r).get("data", {}).get("albums", [])
        matched_album = None
        for a in data:
            if a.get("artist_name") == artist_name and a.get("title") == album_title:
                matched_album = a
                break
        if not matched_album and data:
            for a in data:
                if a.get("artist_name") == artist_name:
                    matched_album = a
                    break
        if not matched_album:
            return None
            
        aid = matched_album["id"]
        url_detail = f"https://m-api.changgepd.ccwu.cc/api/admin/albums/detail?album_id={aid}"
        r_det = subprocess.check_output(["curl", "-s", url_detail], timeout=10).decode("utf-8")
        det_data = json.loads(r_det).get("data", {})
        return det_data
    except Exception as e:
        print(f"Error fetching album {album_title}: {e}")
        return None

def resolve_package(pkg_path, out_path):
    print(f"\n========================================================")
    print(f"正在为 {pkg_path} 解析并关联真实 Song ID 与搜索关键词...")
    print(f"========================================================")
    with open(pkg_path, "r", encoding="utf-8") as f:
        items = json.load(f)
        
    resolved_items = []
    album_cache = {}
    
    for idx, it in enumerate(items, 1):
        art = it["artist"]
        alb = it["album"]
        tit = it["title"]
        
        cache_key = f"{art}_{alb}"
        if cache_key not in album_cache:
            time.sleep(0.05)
            album_cache[cache_key] = fetch_album_detail(alb, art)
            
        alb_info = album_cache[cache_key]
        song_id = None
        if alb_info:
            for s in alb_info.get("songs", []):
                # 1. 精准匹配
                if s.get("title") == tit:
                    song_id = s.get("id")
                    break
            # 2. 忽略大小写及空白
            if not song_id:
                for s in alb_info.get("songs", []):
                    if s.get("title", "").strip().lower() == tit.strip().lower():
                        song_id = s.get("id")
                        break
            # 3. 包含匹配
            if not song_id:
                for s in alb_info.get("songs", []):
                    s_t = s.get("title", "")
                    if tit in s_t or s_t in tit:
                        song_id = s.get("id")
                        break
                        
        it["id"] = song_id
        # 智能匹配 search_title
        if tit in ENGLISH_TO_CHINESE_SEARCH:
            it["search_title"] = ENGLISH_TO_CHINESE_SEARCH[tit]
        else:
            it["search_title"] = tit
            
        if song_id:
            resolved_items.append(it)
            print(f"  [{idx:>2}/{len(items)}] ✅ 匹配: ID {song_id:<6} | [{art}] 《{alb[:15]}》 - 《{tit}》 (检索词: '{it['search_title']}')")
        else:
            print(f"  [{idx:>2}/{len(items)}] ⚠️ 无法定位 ID: [{art}] 《{alb[:15]}》 - 《{tit}》")
            
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resolved_items, f, ensure_ascii=False, indent=2)
    print(f"\n🎉 完成！已解析并绑定 {len(resolved_items)} / {len(items)} 首歌曲，保存至 {out_path}\n")

if __name__ == "__main__":
    resolve_package("sparse_pkg_a.json", "sparse_pkg_a_resolved.json")
    resolve_package("sparse_pkg_b.json", "sparse_pkg_b_resolved.json")
