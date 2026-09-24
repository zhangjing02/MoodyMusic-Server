#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周杰伦 14 首置换曲目 Bucket 01 (moody-music-asset) 旧脏音频物理清除脚本
使用 wrangler CLI 直接与 Cloudflare 远程 R2 通信，彻底释放存储容量，确保零空间膨胀。
"""

import os
import subprocess
import time

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WRANGLER_BIN = os.path.join(BASE_DIR, "cloudflare-worker", "node_modules", ".bin", "wrangler")
CWD = os.path.join(BASE_DIR, "cloudflare-worker")

TARGET_FILES = [
    (23291, "周杰伦", "Jay", "可爱女人"),
    (23312, "周杰伦", "八度空间", "半岛铁盒"),
    (23313, "周杰伦", "八度空间", "暗号"),
    (23317, "周杰伦", "八度空间", "爷爷泡的茶"),
    (23324, "周杰伦", "叶惠美", "三年二班"),
    (23335, "周杰伦", "七里香", "外婆"),
    (23349, "周杰伦", "十一月的萧邦", "逆鳞"),
    (23359, "周杰伦", "依然范特西", "红模仿"),
    (23367, "周杰伦", "我很忙", "阳光宅男"),
    (23369, "周杰伦", "我很忙", "无双"),
    (23371, "周杰伦", "我很忙", "扯"),
    (23390, "周杰伦", "跨时代", "雨下一整晚"),
    (23403, "周杰伦", "惊叹号", "水手怕水"),
    (23434, "周杰伦", "周杰伦的床边故事", "前世情人"),
]

def cleanup_old_files():
    print("=" * 80)
    print("🧹 启动 Bucket 01 (moody-music-asset) 旧脏音频物理清除工作")
    print("=" * 80)

    for sid, artist, album, title in TARGET_FILES:
        r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
        print(f"正在物理删除: moody-music-asset/{r2_key} ({title})...")
        cmd = [WRANGLER_BIN, "r2", "object", "delete", f"moody-music-asset/{r2_key}", "--remote"]
        try:
            res = subprocess.run(cmd, cwd=CWD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
            if res.returncode == 0:
                print(f"  ✅ 成功释放: {r2_key}")
            else:
                print(f"  ⚠️ 删除输出: {res.stdout.strip()} {res.stderr.strip()}")
        except Exception as e:
            print(f"  ❌ 删除失败: {e}")
        time.sleep(0.5)

    print("\n🎉 Bucket 01 物理清除执行完毕！")

if __name__ == "__main__":
    cleanup_old_files()
