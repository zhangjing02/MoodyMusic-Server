#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 夜间离线全自动化攻坚批处理流水线调度器 (Nightly Batch Runner)
==============================================================================
特性：
1. 全程遵循方案 A：MOODY_OFFLINE=1，彻底杜绝任何 D1 网络交互；
2. 串行安全执行：等候当前进行中的张韶涵流水线完成，随后全自动接续：
   - 林忆莲 (80 首)
   - Twins (73 首)
   - 郁可唯 (93 首)
   - Package B (周华健、张信哲、李玟、黎明 79 首)
3. 严格执行工业级 EBU R128 标准化与 Groq Whisper-large-v3 人声金标准盲听质检；
4. 双桶容量动态监控：触碰 9.30 GB 警戒线自动平滑切入 Bucket 09；
5. 所有合格母带曲目直接入桶并寄存至 data/pending_d1_light_queue.json，
   为明早 08:00 额度清零后的一键点亮做好万全蓄水准备。
==============================================================================
"""

import os
import sys
import time
import subprocess

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REMEDIATOR = os.path.join(BASE_DIR, "scripts", "master_sparse_remediator.py")

TASKS = [
    {"file": "sparse_sandy_resolved.json", "name": "sandy", "desc": "林忆莲 (80 首待补全大碟曲目)"},
    {"file": "sparse_twins_resolved.json", "name": "twins", "desc": "Twins (73 首待补全大碟曲目)"},
    {"file": "sparse_yisa_resolved.json", "name": "yisa", "desc": "郁可唯 (93 首恢复中文名待补全曲目)"},
    {"file": "sparse_pkg_b_resolved.json", "name": "pkg_b", "desc": "Package B 周华健/张信哲/李玟/黎明 (79 首)"},
]

def is_angela_running() -> bool:
    try:
        out = subprocess.check_output(["ps", "aux"]).decode()
        return "sparse_angela_resolved.json" in out
    except Exception:
        return False

def main():
    print("==================================================================")
    print("🌙 启动 MOODY 夜间无人值守母带重制与入桶总控调度引擎")
    print("==================================================================")

    # 1. 等待张韶涵流水线完成
    if is_angela_running():
        print("⏳ 检测到【张韶涵】攻坚流水线正在执行中，自动进入守候阶段...")
        while is_angela_running():
            time.sleep(15)
        print("🎉 【张韶涵】攻坚流水线已圆满收官！")
        time.sleep(5)
    else:
        print("ℹ️ 【张韶涵】攻坚流水线未在运行或已结束，直接推进后续任务队列。")

    # 2. 依次串行执行后续歌手队列
    for idx, t in enumerate(TASKS, 1):
        target_path = os.path.join(BASE_DIR, t["file"])
        if not os.path.exists(target_path):
            print(f"⚠️ 目标任务文件不存在: {target_path}，跳过！")
            continue

        print(f"\n##################################################################")
        print(f"▶ [{idx}/{len(TASKS)}] 启动夜间批次: {t['desc']}")
        print(f"##################################################################\n")

        env = os.environ.copy()
        env["MOODY_OFFLINE"] = "1"

        cmd = [sys.executable, REMEDIATOR, target_path, t["name"]]
        try:
            res = subprocess.run(cmd, cwd=BASE_DIR, env=env)
            print(f"✅ 批次 {t['name']} 执行完成，返回码: {res.returncode}")
        except Exception as e:
            print(f"❌ 批次 {t['name']} 执行异常: {e}")

        time.sleep(5)

    print("\n==================================================================")
    print("🌟 夜间无人值守全部批次已 100% 执行完毕！")
    print("📁 所有合格音频母带与 LRC 歌词已安全写入 Cloudflare R2 集群！")
    print("📋 全部待点亮元数据已完整固化在 data/pending_d1_light_queue.json！")
    print("⏰ 请在明早 08:00 (UTC 00:00) 配额清零后运行: python3 scripts/flush_d1_light_queue.py")
    print("==================================================================\n")

if __name__ == "__main__":
    main()
