#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 1 Verification Script: Worker Obfuscated Gateway & Strict Anti-Hotlink
Validates 4 core dimensions:
1. Web client receives signed stream gateway URL (hidden R2 origin)
2. Android client receives direct absolute CDN URL (zero breaking change)
3. Direct/Unauthorized requests to stream gateway return HTTP 403 Forbidden
4. Authorized Web requests (with allowed Referer) stream audio successfully (HTTP 200/206)
"""

import sys
import requests

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = "https://m-api.changgepd.ccwu.cc"
PROXIES = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}

def run_tests():
    print("=" * 60)
    print("🚀 开始阶段一验收测试：混淆短链网关与防盗链四维指标")
    print("=" * 60)

    # 1. Web 客户端请求 /api/songs
    print("\n[测试 1] 模拟 Web 浏览器请求 /api/songs...")
    web_res = requests.get(
        f"{BASE_URL}/api/songs?artist=Beyond&limit=1",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        proxies=PROXIES,
        timeout=15
    )
    if web_res.status_code != 200:
        print(f"❌ Web 请求失败，状态码: {web_res.status_code}")
        return False
    web_data = web_res.json()
    web_song = web_data.get("data", [{}])[0].get("albums", [{}])[0].get("songs", [{}])[0]
    web_path = web_song.get("path", "")
    print(f"Web 返回歌曲: {web_song.get('title')}")
    print(f"Web 返回路径: {web_path}")

    is_gateway = "/api/media/stream?" in web_path
    if is_gateway:
        print("✅ 指标 1 通过：Web 端成功下发混淆签名网关短链，R2 物理物理源站完全隐藏！")
    else:
        print("❌ 指标 1 失败：Web 端返回的仍是物理直链，网关代码未生效或未部署！")
        return False

    # 2. Android 客户端请求 /api/songs
    print("\n[测试 2] 模拟 Android App 请求 /api/songs...")
    app_res = requests.get(
        f"{BASE_URL}/api/songs?artist=Beyond&limit=1",
        headers={
            "User-Agent": "moodymusic-android/1.0.0",
            "x-app-platform": "android"
        },
        proxies=PROXIES,
        timeout=15
    )
    if app_res.status_code != 200:
        print(f"❌ App 请求失败，状态码: {app_res.status_code}")
        return False
    app_data = app_res.json()
    app_song = app_data.get("data", [{}])[0].get("albums", [{}])[0].get("songs", [{}])[0]
    app_path = app_song.get("path", "")
    print(f"App 返回歌曲: {app_song.get('title')}")
    print(f"App 返回路径: {app_path}")

    if "r2.dev" in app_path or "changgepd.ccwu.cc" in app_path and "/api/media/stream" not in app_path:
        print("✅ 指标 2 通过：Android 客户端原样保留绝对 CDN 直链，App 体验与离线缓存 100% 零侵入！")
    else:
        print(f"❌ 指标 2 失败：Android 收到非直链地址: {app_path}")
        return False

    # 3. 裸请求/非法 Referer 请求网关
    print("\n[测试 3] 安全拦截校验：非法盗链请求测试...")
    # 3a. 裸爬虫 (无 Referer)
    naked_res = requests.get(web_path, proxies=PROXIES, timeout=10)
    print(f"裸请求（无 Referer）状态码: {naked_res.status_code}")
    # 3b. 恶意第三方网站 Referer
    evil_res = requests.get(web_path, headers={"Referer": "https://evil-crawler.com/steal"}, proxies=PROXIES, timeout=10)
    print(f"恶意 Referer 状态码: {evil_res.status_code}")

    if naked_res.status_code == 403 and evil_res.status_code == 403:
        print("✅ 指标 3 通过：裸请求与非法盗链均被 Worker 网关严格阻断 (HTTP 403 Forbidden)！")
    else:
        print(f"❌ 指标 3 失败：防盗链未拦截！naked={naked_res.status_code}, evil={evil_res.status_code}")
        return False

    # 4. 合法 Web 播放与预加载流式请求 (带合法 Referer 与 Range)
    print("\n[测试 4] 合法 Web 播放与 Audio Blob 预加载校验...")
    valid_res = requests.get(
        web_path,
        headers={
            "Referer": "https://music.changgepd.ccwu.cc/",
            "Range": "bytes=0-102400"  # 模拟前 100KB 流式缓冲
        },
        proxies=PROXIES,
        timeout=15
    )
    print(f"合法 Web 请求状态码: {valid_res.status_code}")
    print(f"响应 Content-Type: {valid_res.headers.get('Content-Type')}")
    print(f"响应 Content-Range: {valid_res.headers.get('Content-Range')}")
    print(f"接收数据长度: {len(valid_res.content)} 字节")

    if valid_res.status_code in [200, 206] and len(valid_res.content) > 0:
        print("✅ 指标 4 通过：合法 Web Referer 正常拉取音频流，预加载与分片缓冲完美畅通！")
    else:
        print(f"❌ 指标 4 失败：合法请求未能成功获取音频数据，状态码: {valid_res.status_code}")
        return False

    print("\n" + "=" * 60)
    print("🎉 阶段一：混淆网关与防盗链全量测试通过！")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
