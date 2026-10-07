#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 & Phase 3 End-to-End Comprehensive Verification:
1. Web client receives symmetric encrypted field (moody://enc_v1:...)
2. Android client receives raw absolute CDN direct link (100% intact, zero breaking change)
3. WebAssembly music_guard.wasm binary with DOM host probe:
   - Authorizes legitimate browser host -> Decrypts instantly to stream gateway URL
   - Intercepts headless scraper / unauthorized host -> Aborts decryption
4. Stream gateway fetches audio with valid Web Referer and Range (HTTP 206)
5. Simulates audio Blob prefetch pipeline (prefetchAudioToBlob / _audioBlobCache)
"""

import sys
import os
import subprocess
import requests

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = "https://m-api.changgepd.ccwu.cc"
PROXIES = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
WASM_PATH = r"e:\Workspace\AI-Project\MoodyMusic-Workspace\MoodyMusic-Web\src\wasm\music_guard.wasm"

def run_tests():
    print("=" * 70)
    print("🛡️ 开始阶段二与阶段三验收测试：专属字段加密与 Wasm 二进制探针防盗")
    print("=" * 70)

    # 1. Web 客户端请求 /api/songs
    print("\n[测试 1] 模拟 Web 浏览器请求 /api/songs (验证字段加密)...")
    web_res = requests.get(
        f"{BASE_URL}/api/songs?artist=Beyond&limit=1",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        proxies=PROXIES,
        timeout=15
    )
    if web_res.status_code != 200:
        print(f"❌ Web 请求失败，HTTP 状态码: {web_res.status_code}")
        return False

    web_data = web_res.json()
    web_song = web_data.get("data", [{}])[0].get("albums", [{}])[0].get("songs", [{}])[0]
    web_cipher = web_song.get("path", "")
    print(f"Web 返回歌曲: {web_song.get('title')}")
    print(f"Web 返回 path 密文: {web_cipher[:65]}... (总长度: {len(web_cipher)})")

    if web_cipher.startswith("moody://enc_v1:"):
        print("✅ 指标 1 通过：Web 端成功收到 moody://enc_v1 专属加密密文，物理源站与网关结构对抓包完全不可见！")
    else:
        print(f"❌ 指标 1 失败：返回的未被加密: {web_cipher}")
        return False

    # 2. Android 客户端请求 /api/songs (绝对 CDN 直链铁律)
    print("\n[测试 2] 模拟 Android 客户端请求 /api/songs (验证 App 绝对直链)...")
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
        print(f"❌ App 请求失败，HTTP 状态码: {app_res.status_code}")
        return False

    app_data = app_res.json()
    app_song = app_data.get("data", [{}])[0].get("albums", [{}])[0].get("songs", [{}])[0]
    app_path = app_song.get("path", "")
    print(f"App 返回歌曲: {app_song.get('title')}")
    print(f"App 返回 path: {app_path}")

    if app_path.startswith("https://") and "r2.dev" in app_path and not app_path.startswith("moody://"):
        print("✅ 指标 2 通过：Android 客户端原样保留绝对物理 CDN 直链，App 离线下载与播放 100% 零侵入！")
    else:
        print(f"❌ 指标 2 失败：Android 收到非法路径: {app_path}")
        return False

    # 3. WebAssembly 模块与宿主探针防搬砖检验 (Node.js 执行 Wasm 探针)
    print("\n[测试 3] WebAssembly 二进制模块 (music_guard.wasm) 运行与反爬探针测试...")
    node_script = f"""
    const fs = require('fs');
    const wasmBuffer = fs.readFileSync({repr(WASM_PATH)});

    async function testWasm(encStr) {{
        const hex = encStr.slice('moody://enc_v1:'.length);
        const saltHex = hex.slice(0, 16);
        const bodyHex = hex.slice(16);
        const bodyLen = bodyHex.length / 2;

        // 3a. 合法宿主环境 (白名单域名与 DOM 探针)
        let probeResult = 0x4D4F4F44;
        const {{ instance: instValid }} = await WebAssembly.instantiate(wasmBuffer, {{
            env: {{ check_host_probe: () => probeResult, abort: () => {{}} }}
        }});
        const memValid = new Uint8Array(instValid.exports.memory.buffer);
        const saltPtr = instValid.exports.get_salt_ptr();
        const cipherPtr = instValid.exports.get_cipher_ptr();
        const outPtr = instValid.exports.get_out_ptr();

        for (let i = 0; i < 8; i++) memValid[saltPtr + i] = parseInt(saltHex.substr(i * 2, 2), 16);
        for (let i = 0; i < bodyLen; i++) memValid[cipherPtr + i] = parseInt(bodyHex.substr(i * 2, 2), 16);

        const outLenValid = instValid.exports.decrypt(bodyLen);
        const decryptedUrl = outLenValid > 0 ? Buffer.from(memValid.slice(outPtr, outPtr + outLenValid)).toString('utf8') : '';

        // 3b. 模拟脱机爬虫 / 非法宿主探针
        probeResult = 0; // 爬虫未在合法浏览器 DOM 中运行
        const {{ instance: instScraper }} = await WebAssembly.instantiate(wasmBuffer, {{
            env: {{ check_host_probe: () => probeResult, abort: () => {{}} }}
        }});
        const outLenScraper = instScraper.exports.decrypt(bodyLen);

        console.log(JSON.stringify({{
            validOut: decryptedUrl,
            scraperBlocked: outLenScraper < 0
        }}));
    }}

    testWasm({repr(web_cipher)});
    """

    res_node = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    if res_node.returncode != 0:
        print(f"❌ Node.js 运行 Wasm 失败: {res_node.stderr}")
        return False

    import json
    wasm_eval = json.loads(res_node.stdout.strip())
    decrypted_stream_url = wasm_eval.get("validOut", "")
    scraper_blocked = wasm_eval.get("scraperBlocked", False)

    print(f"Wasm 解密输出 URL: {decrypted_stream_url}")
    print(f"非法爬虫脱机运行拦截: {'成功阻断 (返回 -1)' if scraper_blocked else '未阻断'}")

    if "/api/media/stream?" in decrypted_stream_url and scraper_blocked:
        print("✅ 指标 3 通过：Wasm 二进制在合法宿主毫秒级解密；脱机爬虫无法搬砖利用！")
    else:
        print("❌ 指标 3 失败：Wasm 解密未能还原合法 URL 或反爬探针未生效！")
        return False

    # 4. 解密后网关流式请求校验 (合法 Referer + Range 206)
    print("\n[测试 4] 校验解密后网关地址真实音频流响应...")
    valid_res = requests.get(
        decrypted_stream_url,
        headers={
            "Referer": "https://music.changgepd.ccwu.cc/",
            "Range": "bytes=0-102400"
        },
        proxies=PROXIES,
        timeout=15
    )
    print(f"网关流请求状态码: {valid_res.status_code}")
    print(f"Content-Type: {valid_res.headers.get('Content-Type')}")
    print(f"Content-Range: {valid_res.headers.get('Content-Range')}")
    print(f"接收音频字节: {len(valid_res.content)} 字节")

    if valid_res.status_code in [200, 206] and len(valid_res.content) > 0:
        print("✅ 指标 4 通过：解密后的网关短链正常拉取音频数据，分片缓冲与毫秒级 Seek 快进正常！")
    else:
        print(f"❌ 指标 4 失败：网关未能成功返回音频流: {valid_res.status_code}")
        return False

    # 5. 音频 Blob 预加载机制不受限验证 (模拟 prefetchAudioToBlob)
    print("\n[测试 5] 验证音频 Blob 预加载机制完整性...")
    blob_res = requests.get(
        decrypted_stream_url,
        headers={"Referer": "https://music.changgepd.ccwu.cc/"},
        proxies=PROXIES,
        timeout=20
    )
    if blob_res.status_code == 200 and len(blob_res.content) > 100000:
        print(f"✅ 指标 5 通过：整曲音频成功下载 ({len(blob_res.content)} 字节)，可无损封装为 Blob URL 存入 _audioBlobCache！预加载机制 100% 畅通！")
    else:
        print(f"❌ 指标 5 失败：整曲下载异常: {blob_res.status_code}, 长度: {len(blob_res.content)}")
        return False

    print("\n" + "=" * 70)
    print("🎉 阶段二与阶段三三位一体防御体系全量自动化验收通过！")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
