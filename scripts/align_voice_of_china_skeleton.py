#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国好声音（第一季~第四季）曲库骨架权威对齐脚本
依据官方盲选首秀标准，重构四大黄金赛季盲选核心歌单（共 53 首）
"""
import os
import sys
import json
import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

API_BASE = "https://m-api.changgepd.ccwu.cc"
session = requests.Session()
session.trust_env = False

# 权威盲选目标清单
TARGET_SEASONS = {
    1941: {
        "title": "第一季 (2012)",
        "songs": [
            (1, "梁博", "长安 长安"),
            (2, "吴莫愁", "Price Tag"),
            (3, "吉克隽逸", "i feel good"),
            (4, "金志文", "为爱痴狂"),
            (5, "李代沫", "我的歌声里"),
            (6, "张玮", "High歌"),
            (7, "丁丁", "爱要坦荡荡"),
            (8, "平安", "我爱你中国"),
            (9, "多亮", "小情歌"),
            (10, "张赫宣", "你是我心爱的姑娘"),
            (11, "关喆", "领悟"),
            (12, "袁娅维", "弯弯的月亮"),
            (13, "王韵壹", "被遗忘的时光"),
            (14, "徐海星", "自己"),
            (15, "郑虹", "Someone Like You"),
            (16, "金池", "夜夜夜夜"),
        ]
    },
    1942: {
        "title": "第二季 (2013)",
        "songs": [
            (1, "李琦", "趁早"),
            (2, "张恒远", "无法逃脱"),
            (3, "萱萱", "残酷月光"),
            (4, "金润吉", "When A Man Loves A Woman"),
            (5, "姚贝娜", "也许明天"),
            (6, "毕夏", "像梦一样自由"),
            (7, "朱克", "离不开你"),
            (8, "孟楠", "领悟"),
            (9, "塔斯肯", "三百六十五里路"),
            (10, "侯磊", "味道"),
            (11, "蘑菇兄弟", "睫毛弯弯"),
            (12, "刘雅婷", "I Wanna Rock"),
            (13, "钟伟强", "Rolling in the deep"),
        ]
    },
    1943: {
        "title": "第三季 (2014)",
        "songs": [
            (1, "张碧晨", "她说"),
            (2, "帕尔哈提", "你怎么舍得我难过"),
            (3, "余枫", "有多少爱可以重来"),
            (4, "秦宇子", "I Love Rock 'N Roll"),
            (5, "周深", "欢颜"),
            (6, "陈冰", "盛夏光年"),
            (7, "陈乐基", "月半小夜曲"),
            (8, "刘明湘", "漂洋过海来看你"),
            (9, "李嘉格", "普通朋友"),
            (10, "耿斯汉", "美丽世界的孤儿"),
            (11, "魏雪漫", "我是真的爱你"),
            (12, "张心杰", "大惊小怪"),
        ]
    },
    1944: {
        "title": "第四季 (2015)",
        "songs": [
            (1, "张磊", "南山南"),
            (2, "陈梓童", "双截棍"),
            (3, "谭轩辕", "Still Loving You"),
            (4, "贝贝", "花火"),
            (5, "李安", "逝去的爱"),
            (6, "赵大格", "我在人民广场吃炸鸡"),
            (7, "关诗敏", "晴天"),
            (8, "朗嘎拉姆", "千言万语"),
            (9, "黄霄雲", "你"),
            (10, "长宇", "氧气"),
            (11, "马吟吟", "海上花"),
            (12, "刘伟男", "Lemon Tree"),
        ]
    }
}

# 既有 33 首在各专辑的映射重用分配
# (album_id, song_id) -> (target_track_index, target_title)
MAPPING_REUSE = {
    # 第一季 (1941)
    (1941, 27591): (1, "长安 长安 - 梁博"),
    (1941, 27586): (2, "Price Tag - 吴莫愁"),
    (1941, 27588): (4, "为爱痴狂 - 金志文"),
    (1941, 27585): (5, "我的歌声里 - 李代沫"),
    (1941, 27583): (6, "High歌 - 张玮"),
    (1941, 27592): (8, "我爱你中国 - 平安"),
    (1941, 27590): (9, "小情歌 - 多亮"),
    (1941, 27593): (10, "你是我心爱的姑娘 - 张赫宣"),
    (1941, 27587): (12, "弯弯的月亮 - 袁娅维"),
    (1941, 27584): (14, "自己 - 徐海星"),
    (1941, 27589): (15, "Someone Like You - 郑虹"),
    # 第二季 (1942)
    (1942, 27594): (1, "趁早 - 李琦"),
    (1942, 27596): (2, "无法逃脱 - 张恒远"),
    (1942, 27597): (3, "残酷月光 - 萱萱"),
    (1942, 27599): (4, "When A Man Loves A Woman - 金润吉"),
    (1942, 27595): (5, "也许明天 - 姚贝娜"),
    (1942, 27598): (6, "像梦一样自由 - 毕夏"),
    (1942, 27600): (7, "离不开你 - 朱克"),
    # 第三季 (1943)
    (1943, 27601): (1, "她说 - 张碧晨"),
    (1943, 27603): (2, "你怎么舍得我难过 - 帕尔哈提"),
    (1943, 27608): (3, "有多少爱可以重来 - 余枫"),
    (1943, 27605): (4, "I Love Rock 'N Roll - 秦宇子"),
    (1943, 27607): (5, "欢颜 - 周深"),
    (1943, 27602): (6, "盛夏光年 - 陈冰"),
    (1943, 27606): (7, "月半小夜曲 - 陈乐基"),
    (1943, 27604): (8, "漂洋过海来看你 - 刘明湘"),
    # 第四季 (1944)
    (1944, 27612): (1, "南山南 - 张磊"),
    (1944, 27609): (2, "双截棍 - 陈梓童"),
    (1944, 27610): (3, "Still Loving You - 谭轩辕"),
    (1944, 27613): (4, "花火 - 贝贝"),
    (1944, 27614): (5, "逝去的爱 - 李安"),
    (1944, 27615): (6, "我在人民广场吃炸鸡 - 赵大格"),
    (1944, 27611): (7, "晴天 - 关诗敏"),
}

def main():
    print("=" * 80)
    print("🚀 开始执行《中国好声音》全四赛季骨架对齐工程")
    print("=" * 80)

    # 1. 批量更新既有 33 首
    print("\n[Phase 1] 批量更新既有 33 首曲目标题与曲序...")
    updates = []
    for (aid, sid), (t_idx, title) in MAPPING_REUSE.items():
        updates.append({
            "id": sid,
            "title": title,
            "track_index": t_idx
        })

    res_up = session.post(f"{API_BASE}/api/admin/songs/batch-update", json={"updates": updates}, timeout=20)
    print(f"   • batch-update 响应: {res_up.status_code} | {res_up.text}")
    if res_up.status_code != 200:
        print("❌ 批量更新失败，终止流程")
        return

    # 2. 批量新增 20 首空缺曲目
    print("\n[Phase 2] 批量插入 20 首空缺盲选经典曲目...")
    # 提取各专辑中未被既有 ID 覆盖的目标曲目
    covered_tracks = {}
    for (aid, sid), (t_idx, title) in MAPPING_REUSE.items():
        covered_tracks.setdefault(aid, set()).add(t_idx)

    for aid, season_info in TARGET_SEASONS.items():
        new_songs = []
        for t_idx, singer, song_name in season_info["songs"]:
            if t_idx not in covered_tracks.get(aid, set()):
                formatted_title = f"{song_name} - {singer}"
                new_songs.append({
                    "title": formatted_title,
                    "track_index": t_idx
                })

        if new_songs:
            print(f"   • 专辑 {aid} ({season_info['title']}) 增量插入 {len(new_songs)} 首...")
            res_ins = session.post(
                f"{API_BASE}/api/admin/songs/batch-insert",
                json={"album_id": aid, "songs": new_songs},
                timeout=20
            )
            print(f"     响应: {res_ins.status_code} | {res_ins.text}")
            if res_ins.status_code != 200:
                print(f"❌ 专辑 {aid} 插入失败！")
                return

    # 3. 验证 D1 生产库对齐情况
    print("\n[Phase 3] 校验生产端 D1 数据库四赛季对齐结果...")
    all_matched = True
    season_results = {}

    for aid, season_info in TARGET_SEASONS.items():
        res = session.get(f"{API_BASE}/api/admin/albums/detail?album_id={aid}", timeout=15)
        data = res.json().get("data", {})
        songs = data.get("songs", [])
        season_results[aid] = songs
        target_len = len(season_info["songs"])
        print(f"\n--- {season_info['title']} (Album ID: {aid}) --- 当前曲目数: {len(songs)} / 期望: {target_len}")

        sorted_songs = sorted(songs, key=lambda x: (x.get("track_index", 0), x["id"]))
        for s in sorted_songs:
            sid = s["id"]
            t_idx = s.get("track_index", 0)
            title = s["title"]
            print(f"  Track {t_idx:2d} | [{sid}] {title}")

        if len(songs) != target_len:
            print(f"❌ 曲目数不匹配: 实测 {len(songs)} vs 期望 {target_len}")
            all_matched = False

    if all_matched:
        print("\n🎉 生产端 D1 四赛季 53 首骨架全部成功对齐！")
    else:
        print("\n⚠️ 生产端有部分未对齐，请排查！")

if __name__ == "__main__":
    main()
