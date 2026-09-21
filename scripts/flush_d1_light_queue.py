#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY D1 离线点亮队列刷新与全量点亮工具 (Flush D1 Light Queue)
==============================================================================
作用：
在每日行读配额重置（每天 00:00:00 UTC / 北京时间 08:00:00）后执行，
将方案 A 在夜间先行采录入桶并保存在 data/pending_d1_light_queue.json 的所有曲目，
以分块批处理方式（每批 20 首）一键毫秒级点亮！
==============================================================================
"""

import os
import sys
import json
import time
import requests

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
QUEUE_FILE = os.path.join(BASE_DIR, "data", "pending_d1_light_queue.json")
WORKER_URL = "https://m-api.changgepd.ccwu.cc"
LIGHT_URL = f"{WORKER_URL}/api/admin/songs/batch-light"
PROXY_URL = "http://127.0.0.1:7898"
PROXIES = {"http": PROXY_URL, "https": PROXY_URL}

def flush_queue():
    if not os.path.exists(QUEUE_FILE):
        print(f"⚠️ 队列文件不存在: {QUEUE_FILE}")
        return

    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        queue = json.load(f)

    if not queue:
        print("✅ 待点亮队列为空，无需操作！")
        return

    print("==================================================================")
    print(f"🚀 启动 D1 待点亮队列批量入库: 共 {len(queue)} 首曲目")
    print("==================================================================")

    batch_size = 20
    success_count = 0
    failed_items = []

    for i in range(0, len(queue), batch_size):
        batch = queue[i:i + batch_size]
        print(f"\n▶ 正在提交批次 [{i + 1} ~ {min(i + batch_size, len(queue))}] ({len(batch)} 首)...")
        
        req_body = {"updates": batch}
        success = False
        
        # 1. 优先直连 CDN
        try:
            r = requests.post(LIGHT_URL, json=req_body, timeout=15)
            if r.status_code == 200 and r.json().get("code") == 200:
                success = True
                print(f"   🟢 直连点亮成功: {r.json().get('message')}")
            else:
                print(f"   ⚠️ 直连响应: {r.status_code} - {r.text[:100]}")
        except Exception as e:
            print(f"   ⚠️ 直连超时或异常: {e}，尝试代理...")

        # 2. 代理回退
        if not success:
            try:
                r = requests.post(LIGHT_URL, json=req_body, proxies=PROXIES, timeout=20)
                if r.status_code == 200 and r.json().get("code") == 200:
                    success = True
                    print(f"   🟢 代理点亮成功: {r.json().get('message')}")
                else:
                    print(f"   ❌ 代理点亮失败: {r.status_code} - {r.text[:100]}")
            except Exception as e:
                print(f"   ❌ 代理请求异常: {e}")

        if success:
            success_count += len(batch)
        else:
            failed_items.extend(batch)

        time.sleep(0.1)

    print("\n==================================================================")
    print(f"🎉 队列处理完毕！成功点亮: {success_count} 首 | 失败: {len(failed_items)} 首")
    print("==================================================================")

    # 如果有失败的，回写队列文件供下次重试
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(failed_items, f, ensure_ascii=False, indent=2)

    if not failed_items:
        print(f"✨ 队列已彻底清空并闭环！所有歌曲已 100% 正式上线！\n")
    else:
        print(f"⚠️ 剩余 {len(failed_items)} 首失败曲目已保留在队列中。\n")

if __name__ == "__main__":
    flush_queue()
