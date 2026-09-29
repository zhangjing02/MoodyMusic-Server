#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MOODY 早期曲库治理 - 阶段 2C：28 首非官方幽灵虚假曲目规范下架与熄灭
=============================================================================
下架对象：
- S.H.E《沙漠之鷹》 (武器解说短视频掉包，官方 Discography 查无此歌)
- 汪峰《也许我可以无视死亡》、《果岭里29号》虚拟专辑内劣质影视压制切片
- 电视剧片头台词与杂乱同名音频
=============================================================================
"""

import os
import sys
import json
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_FILE = os.path.join(BASE_DIR, "reports", "TASK_UNLIGHT_28_GHOST_SONGS.json")
LOG_DIR = os.path.join(BASE_DIR, "reports")
D1_UNLIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-unlight"

def main():
    print("=" * 80)
    print("🚀 启动 MOODY 早期曲库治理 - 阶段 2C：28 首幽灵虚假曲目规范下架熄灭")
    print("=" * 80)

    if not os.path.exists(TASK_FILE):
        print(f"❌ 任务文件不存在: {TASK_FILE}")
        sys.exit(1)

    with open(TASK_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    song_ids = [item["song_id"] for item in tasks]
    print(f"📋 待下架幽灵假歌数量: {len(song_ids)} 首")

    for t in tasks:
        print(f"  • [下架] [{t['artist']}] 《{t['title']}》 (ID: {t['song_id']}, 专辑: 《{t['album']}》)")

    payload = {"song_ids": song_ids}
    try:
        r = requests.post(D1_UNLIGHT_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        print(f"\n📡 D1 网关响应状态码: {r.status_code}")
        resp_json = r.json()
        print(f"📡 D1 网关响应内容: {resp_json}")
        
        if r.status_code == 200 and resp_json.get("code") == 200:
            print("✅ 28 首幽灵虚假歌曲已全部成功从 D1 数据库下架熄灭！")
            record_file = os.path.join(LOG_DIR, "STAGE_2C_UNLIGHT_LOG.json")
            with open(record_file, "w", encoding="utf-8") as f:
                json.dump({
                    "action": "BATCH_UNLIGHT",
                    "count": len(song_ids),
                    "song_ids": song_ids,
                    "details": tasks,
                    "d1_response": resp_json
                }, f, ensure_ascii=False, indent=2)
            print(f"📜 下架记录已归档至: {record_file}")
        else:
            print("❌ 下架请求失败！")
    except Exception as e:
        print(f"❌ 请求异常: {e}")

if __name__ == "__main__":
    main()
