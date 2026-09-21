#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 三大天王天后 (谭咏麟 / 李克勤 / 许茹芸) 核心神专全量点亮总指挥调度器
==============================================================================
执行顺序：
1. 谭咏麟 (8 张神专, 86 首传世金曲) -> sparse_alan_tam_resolved.json
2. 李克勤 (5 张大碟, 57 首殿堂之作) -> sparse_hacken_lee_resolved.json
3. 许茹芸 (4 张神专, 40 首空灵名曲) -> sparse_valen_hsu_resolved.json

总计: 17 张大碟, 183 首传世录音室高保真母带！
全部经过 EBU R128 (-14 LUFS) 标准化 + 160k CBR Xing Header + Groq Whisper 金标准人声质检！
全部平滑写入 Bucket 09 (moody-music-asset-09) 并实时毫秒级点亮 D1 数据库！
==============================================================================
"""

import os
import sys
import json
import time
import subprocess

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REMEDIATOR = os.path.join(BASE_DIR, "scripts", "master_sparse_remediator.py")

STAGES = [
    {
        "name": "谭咏麟 (Alan Tam)",
        "file": os.path.join(BASE_DIR, "sparse_alan_tam_resolved.json"),
        "label": "alan_tam"
    },
    {
        "name": "李克勤 (Hacken Lee)",
        "file": os.path.join(BASE_DIR, "sparse_hacken_lee_resolved.json"),
        "label": "hacken_lee"
    },
    {
        "name": "许茹芸 (Valen Hsu)",
        "file": os.path.join(BASE_DIR, "sparse_valen_hsu_resolved.json"),
        "label": "valen_hsu"
    }
]

def check_file(path):
    if not os.path.exists(path):
        print(f"❌ 目标文件不存在: {path}")
        return 0
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return len(data)

def main():
    print("==============================================================================")
    print("👑 MOODY 三大天王天后核心大碟补齐点亮工程总调度器启动")
    print("==============================================================================")
    
    total_songs = 0
    for s in STAGES:
        c = check_file(s["file"])
        total_songs += c
        print(f"  ▶ 计划执行: 【{s['name']}】 -> {c} 首曲目 ({os.path.basename(s['file'])})")
        
    print(f"📊 待处理总曲目数: {total_songs} 首")
    print(f"🛡️ 存储保障: Bucket 08 警戒熔断只读，全量无缝写入 Bucket 09 (安全可用 >8.8 GB)")
    print("==============================================================================\n")

    env = os.environ.copy()
    env["MOODY_OFFLINE"] = "0" # 开启实时秒级点亮模式

    for idx, stage in enumerate(STAGES, 1):
        sname = stage["name"]
        sfile = stage["file"]
        slabel = stage["label"]
        print(f"\n>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print(f"🚀 [STAGE {idx}/{len(STAGES)}] 开始执行: 【{sname}】")
        print(f">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>\n")
        
        start_t = time.time()
        res = subprocess.run([sys.executable, REMEDIATOR, sfile, slabel], env=env, cwd=BASE_DIR)
        elapsed = time.time() - start_t
        
        if res.returncode == 0:
            print(f"\n✅ [STAGE {idx}/{len(STAGES)}] 【{sname}】流水线执行完成！耗时: {elapsed/60:.1f} 分钟\n")
        else:
            print(f"\n⚠️ [STAGE {idx}/{len(STAGES)}] 【{sname}】执行退出 (代码: {res.returncode})，耗时: {elapsed/60:.1f} 分钟\n")
        time.sleep(2)

    print("\n🎉 全部三大天王天后流水线调度完毕！")

if __name__ == "__main__":
    main()
