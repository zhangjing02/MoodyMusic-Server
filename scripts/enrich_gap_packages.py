#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为三组残缺补齐曲目注入原汁原味的华语标准 search_title 映射
"""

import json

SEARCH_MAPPING = {
    # Package A
    "乾杯": "干杯",
    "我不願讓你一個人": "我不愿让你一个人",
    "三個傻瓜": "三个傻瓜",
    "諾亞方舟": "诺亚方舟",
    "我的自由式 (Alive!)": "我的自由式",
    "嘆服": "叹服",
    
    # Package B
    "Don't Cry (My Love)": "别哭",
    "I Am Free": "任逍遥",
    "Forever": "永远",
    "Far Away Place": "在那遥远的地方",
    "坏x5 (坏坏坏坏坏)": "坏x5",
    "絲路": "丝路",
    "我還記得": "我还记得",
    "下一秒鐘": "下一秒钟",
    "親親": "亲亲",
    "飛魚": "飞鱼",
    "憨過頭": "憨过头",
    
    # Package C
    "夢見鐵達尼": "梦见铁达尼",
    "當我開始偷偷地想你": "当我开始偷偷地想你",
    "愛 什麼稀罕": "爱什么稀罕",
    "好膽你就來": "好胆你就来",
    "相愛後動物感傷": "相爱后动物感伤",
    "未出現的愛": "未出现的爱",
    "飛機上": "飞机上",
    "無理取鬧": "无理取闹",
    "夜半狂飆": "夜半狂飙",
    "從下世紀欣賞我": "从下世纪欣赏我",
    "從明日開始": "从明日开始",
    "Going Nowhere": "没有管理员的公寓",
    "I Didn't Think I'm in Love with You": "我想我不会爱你",
    "Missing You": "寂寞寂寞就好",
    "The Most Important Thing in Life": "终身大事",
    "Learning From Drunk": "不醉不会",
    "Subconscious": "潜意识",
    "My Figure At the Age of Seven": "七岁的影子",
    "At a Deadlock": "僵局"
}

for p in ['reports/gap_package_a.json', 'reports/gap_package_b.json', 'reports/gap_package_c.json']:
    with open(p, 'r', encoding='utf-8') as f:
        items = json.load(f)
    for it in items:
        t = it['title']
        it['search_title'] = SEARCH_MAPPING.get(t, t)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Enriched {p} ({len(items)} tracks)")
