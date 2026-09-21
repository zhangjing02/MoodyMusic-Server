#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第一战役：批量热更正被暴力直译为英文的华语经典歌名
包含：范玮琪 (18首)、郁可唯 (54首)、萧亚轩 (10首) 共 82 首歌曲
调用 Worker 生产路由：POST /api/admin/ops/songs/batch-update
"""

import requests
import json
import time

WORKER_BASE = "https://m-api.changgepd.ccwu.cc"
PROXIES = {"http": "http://127.0.0.1:7898", "https": "http://127.0.0.1:7898"}

RECTIFY_TASKS = [
    # 1. 范玮琪 - 《范范的感恩節》 (2016)
    {
        "artist_name": "范玮琪",
        "album_title": "范范的感恩節",
        "updates": [
            {"old_title": "Etude", "new_title": "练习曲"},
            {"old_title": "My Thanksgiving", "new_title": "感恩节"},
            {"old_title": "Some Time After", "new_title": "很久很久以后"},
            {"old_title": "How Have You Been", "new_title": "别来无恙"},
            {"old_title": "Left Alone", "new_title": "落单"},
            {"old_title": "That Morning", "new_title": "那个早晨"},
            {"old_title": "With One Eye", "new_title": "一只眼睛"},
            {"old_title": "Meant To Be", "new_title": "最好的安排"},
            {"old_title": "Perfect Match", "new_title": "吻合"},
            {"old_title": "Big Wind Blows", "new_title": "大风吹"}
        ]
    },
    # 2. 范玮琪 - 《恰如其分的自己》 (2022)
    {
        "artist_name": "范玮琪",
        "album_title": "恰如其分的自己",
        "updates": [
            {"old_title": "Solitary Moment", "new_title": "独到"},
            {"old_title": "Heliophobia", "new_title": "畏光"},
            {"old_title": "Kingdom", "new_title": "王国的城堡"},
            {"old_title": "Self-edited Diary", "new_title": "自编自导自演"},
            {"old_title": "Laugh It Off", "new_title": "一笑置之"},
            {"old_title": "Happy Therapy", "new_title": "快乐的治疗"},
            {"old_title": "Que Sera Sera", "new_title": "Que Sera, Sera"},
            {"old_title": "Forget Me Not", "new_title": "勿忘我"}
        ]
    },
    # 3. 郁可唯 - 《失戀事小》 (2012)
    {
        "artist_name": "郁可唯",
        "album_title": "失戀事小",
        "updates": [
            {"old_title": "Flower", "new_title": "花散"},
            {"old_title": "Miss", "new_title": "想念"},
            {"old_title": "Bad Habit", "new_title": "坏习惯"},
            {"old_title": "No Match", "new_title": "不是不适合"},
            {"old_title": "Can't Forgot", "new_title": "忘不了"},
            {"old_title": "Skirt", "new_title": "裙摆"},
            {"old_title": "Lost Love", "new_title": "失恋事小"},
            {"old_title": "Always", "new_title": "一直"},
            {"old_title": "Love Back", "new_title": "白日梦"},
            {"old_title": "Sun Shine", "new_title": "暖阳"}
        ]
    },
    # 4. 郁可唯 - 《00:00》 (2016)
    {
        "artist_name": "郁可唯",
        "album_title": "00:00",
        "updates": [
            {"old_title": "Revert", "new_title": "倒流"},
            {"old_title": "Solitude Again", "new_title": "寂寞更寂寞"},
            {"old_title": "Love Passing By", "new_title": "风筝"},
            {"old_title": "First Snow", "new_title": "初雪"},
            {"old_title": "We Loved", "new_title": "我们都爱过"},
            {"old_title": "Oh Why", "new_title": "Oh Why"},
            {"old_title": "No Time for Being Alone", "new_title": "没空寂寞"},
            {"old_title": "21 Days", "new_title": "21天"},
            {"old_title": "Amber", "new_title": "琥珀"},
            {"old_title": "My Style", "new_title": "个人品味"}
        ]
    },
    # 5. 郁可唯 - 《路過人間》 (2019)
    {
        "artist_name": "郁可唯",
        "album_title": "路過人間",
        "updates": [
            {"old_title": "Walking by the world", "new_title": "路过人间"},
            {"old_title": "Intersection of 30", "new_title": "三十而立"},
            {"old_title": "Evolve", "new_title": "进化"},
            {"old_title": "As You Know", "new_title": "你知道"},
            {"old_title": "Hate", "new_title": "恨爱"},
            {"old_title": "One Decade As One Day", "new_title": "十年如一日"},
            {"old_title": "Who", "new_title": "是谁"},
            {"old_title": "Godless", "new_title": "没有神仙"},
            {"old_title": "Missed Call", "new_title": "未接来电"},
            {"old_title": "Still Early", "new_title": "为时尚早"}
        ]
    },
    # 6. 郁可唯 - 《Dear Life》 (2022)
    {
        "artist_name": "郁可唯",
        "album_title": "Dear Life",
        "updates": [
            {"old_title": "Seek For", "new_title": "寻"},
            {"old_title": "Dear Life", "new_title": "Dear Life"},
            {"old_title": "Let You Go", "new_title": "放过自己"},
            {"old_title": "Romance", "new_title": "浪漫远行"},
            {"old_title": "Living My Way Loving You", "new_title": "我行我素我爱你"},
            {"old_title": "Painful Delight", "new_title": "痛快"},
            {"old_title": "Life Is Like a Firework", "new_title": "烟花"},
            {"old_title": "What If Flowers...", "new_title": "如果花"},
            {"old_title": "Eager to Love", "new_title": "渴望"},
            {"old_title": "A Seat", "new_title": "一个座位"},
            {"old_title": "Bookmark", "new_title": "书签"},
            {"old_title": "Midnight Wanderer", "new_title": "夜行者"},
            {"old_title": "Reverie", "new_title": "白日梦"}
        ]
    },
    # 7. 郁可唯 - 《How Weird of Me》 (2024)
    {
        "artist_name": "郁可唯",
        "album_title": "How Weird of Me",
        "updates": [
            {"old_title": "How Weird of Me", "new_title": "我有多怪"},
            {"old_title": "Utopia of Love", "new_title": "爱的乌托邦"},
            {"old_title": "My Inner Me", "new_title": "心里的自己"},
            {"old_title": "The Way I Live", "new_title": "活着的滋味"},
            {"old_title": "Undying Days", "new_title": "未尽之日"},
            {"old_title": "Narcissus", "new_title": "水仙"},
            {"old_title": "Back to Dream", "new_title": "重返梦境"},
            {"old_title": "Gone with time", "new_title": "随时间而去"},
            {"old_title": "Best Wishes", "new_title": "最好的祝愿"},
            {"old_title": "Think of Us", "new_title": "想想我们"},
            {"old_title": "Lullaby", "new_title": "摇篮曲"}
        ]
    },
    # 8. 萧亚轩 - 《Naked Truth赤裸真相》 (2020)
    {
        "artist_name": "萧亚轩",
        "album_title": "Naked Truth赤裸真相",
        "updates": [
            {"old_title": "Lonely 911", "new_title": "Lonely 911"},
            {"old_title": "Celebrate Everyday", "new_title": "当爱是个玩笑"},
            {"old_title": "In a Heartbeat", "new_title": "当你和心跳一起出现"},
            {"old_title": "Naked Truth", "new_title": "赤裸真相"},
            {"old_title": "So Good", "new_title": "So Good"},
            {"old_title": "Blame It on Me", "new_title": "不如先庆祝"},
            {"old_title": "Driving Away", "new_title": "不如先庆祝 (Club Remix)"},
            {"old_title": "Say the Words", "new_title": "说实话"},
            {"old_title": "My Little Soldier", "new_title": "我的小小士兵"},
            {"old_title": "In a Heartbeat (Tropical Remix)", "new_title": "当你和心跳一起出现 (Tropical Remix)"}
        ]
    }
]

def main():
    print("================================================================")
    print("🚀 第一战役启动：批量热更正被暴力直译的华语经典歌名")
    print(f"📊 待处理专辑数: {len(RECTIFY_TASKS)} 张 | 目标曲目数: {sum(len(t['updates']) for t in RECTIFY_TASKS)} 首")
    print("================================================================\n")

    total_success = 0
    total_failed = 0

    for task in RECTIFY_TASKS:
        art = task["artist_name"]
        alb = task["album_title"]
        upd = task["updates"]
        print(f"▶ 正在处理: 【{art}】 - 《{alb}》 (共 {len(upd)} 首歌)...")

        payload = {
            "artist_name": art,
            "album_title": alb,
            "updates": upd,
            "dry_run": False
        }

        try:
            r = requests.post(
                f"{WORKER_BASE}/api/admin/ops/songs/batch-update",
                json=payload,
                proxies=PROXIES,
                timeout=20
            )
            res = r.json()
            if r.status_code == 200 and res.get("code") == 200:
                updated_count = res.get("data", {}).get("updated_count", len(upd))
                print(f"   🟢 [更正成功] 成功热更正 {updated_count} 首曲目为官方中文名！")
                total_success += updated_count
            else:
                print(f"   ❌ [更正失败] 状态码: {r.status_code}, 详情: {res}")
                total_failed += len(upd)
        except Exception as e:
            print(f"   ❌ [请求异常] {e}")
            total_failed += len(upd)
        
        time.sleep(0.5)

    print("\n================================================================")
    print(f"🎉 第一战役执行完毕！成功更正: {total_success} 首 | 失败: {total_failed} 首")
    print("================================================================\n")

if __name__ == "__main__":
    main()
