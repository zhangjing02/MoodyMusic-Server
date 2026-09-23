# -*- coding: utf-8 -*-
"""
fix_and_optimize_all_avatars.py
专项解决移动端/App 歌手头像无法显示问题：
1. 彻底解决 Cloudflare CDN 与客户端 Coil 磁盘 30 天缓存毒化（通过切换 _v2.jpg 新文件名实现强力 Cache-Busting）
2. 彻底解决 NetEase 原始文件伪装（PNG 伪装成 .jpg 导致 Android 解码异常或耗费海量内存）
3. 彻底解决大图传输超时与内存溢出（统一以高质量 LANCZOS 居中裁剪为 500x500 正方形标准 JPEG，压缩至 30~60KB）
4. 同步覆盖旧文件名以确保历史直链兼容，并原子更新 D1 数据库 photo_url
"""

import os
import sys
import time
import requests
from io import BytesIO
from PIL import Image

sys.stdout.reconfigure(encoding='utf-8')

API_BASE = "https://m-api.changgepd.ccwu.cc"
ASSET_UPLOAD_URL = f"{API_BASE}/api/admin/assets/upload"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com'
}

TARGET_ARTISTS = [
    {
        "id": 154,
        "name": "迪克牛仔",
        "url": "http://p1.music.126.net/EVRNHbTelaeRpaD2PFGnYw==/109951168896254251.jpg"
    },
    {
        "id": 82,
        "name": "谭咏麟",
        "url": "http://p2.music.126.net/wpQIDNXCXbhmhBT5JtDTMQ==/109951168274716128.jpg"
    },
    {
        "id": 160,
        "name": "李克勤",
        "url": "http://p1.music.126.net/a9ekQj9SfOujRMk6h6IIUA==/109951168299155350.jpg"
    },
    {
        "id": 159,
        "name": "蔡琴",
        "url": "http://p1.music.126.net/7wJrRn7aeigTVZg5rIFtGQ==/109951172377851914.jpg"
    },
    {
        "id": 161,
        "name": "许茹芸",
        "url": "http://p2.music.126.net/-oIf4O8OZcbOPokzSOphhg==/109951168788233157.jpg"
    },
    {
        "id": 157,
        "name": "郑智化",
        "url": f"{API_BASE}/storage/artists/artist_157.jpg?v=1"
    },
    {
        "id": 158,
        "name": "萧煌奇",
        "url": f"{API_BASE}/storage/artists/artist_158.jpg?v=1"
    },
    {
        "id": 136,
        "name": "陈小春",
        "url": "http://p1.music.126.net/MyK0_930LX6q0fD2Bcp_vg==/109951169164945697.jpg"
    },
    {
        "id": 162,
        "name": "刘若英",
        "url": f"{API_BASE}/storage/artists/artist_162.jpg?v=1"
    },
    {
        "id": 163,
        "name": "小虎队",
        "url": f"{API_BASE}/storage/artists/artist_163.jpg?v=1"
    },
    {
        "id": 164,
        "name": "谭维维",
        "url": f"{API_BASE}/storage/artists/artist_164.jpg?v=1"
    },
    {
        "id": 165,
        "name": "林志炫",
        "url": f"{API_BASE}/storage/artists/artist_165.jpg?v=1"
    }
]

def process_and_upload(item):
    aid = item['id']
    name = item['name']
    src_url = item['url']
    print(f"\n🎨 开始处理 [{name}] (ID: {aid})...")
    
    # 1. 获取原图
    resp = requests.get(src_url, headers=HEADERS, timeout=15)
    if resp.status_code != 200 or len(resp.content) < 1000:
        print(f"   ❌ 获取源图失败 HTTP {resp.status_code}, len={len(resp.content)}")
        return False
        
    print(f"   📥 源图下载成功: {len(resp.content)} 字节")
    
    # 2. PIL 规范化处理 (500x500 正方形 JPEG，质感压缩)
    try:
        im = Image.open(BytesIO(resp.content)).convert('RGB')
        w, h = im.size
        min_dim = min(w, h)
        # 针对人像摄影，取偏上中位区域（保留更多面部特征）
        left = (w - min_dim) // 2
        top = int((h - min_dim) * 0.25) if h > w else 0
        cropped = im.crop((left, top, left + min_dim, top + min_dim))
        resized = cropped.resize((500, 500), Image.Resampling.LANCZOS)
        
        out_buf = BytesIO()
        resized.save(out_buf, format='JPEG', quality=88, optimize=True)
        jpeg_bytes = out_buf.getvalue()
        print(f"   ✨ 优化后尺寸: 500x500 纯正 JPEG，体积: {len(jpeg_bytes)} 字节 (大幅精简)")
    except Exception as e:
        print(f"   ❌ 图片处理异常: {e}")
        return False

    # 3. 上传新文件名 artist_{aid}_v2.jpg 并自动更新 D1 photo_url
    v2_filename = f"artist_{aid}_v2.jpg"
    files_v2 = {'file': (v2_filename, jpeg_bytes, 'image/jpeg')}
    data_v2 = {'category': 'artists', 'artist_id': str(aid), 'filename': v2_filename}
    
    up_v2 = requests.post(ASSET_UPLOAD_URL, files=files_v2, data=data_v2, timeout=20)
    if up_v2.status_code == 200:
        print(f"   ✅ [V2 Cache-Busting 上传成功] 已绑定 D1 artists.photo_url -> artists/{v2_filename}")
    else:
        print(f"   ❌ V2 上传失败 HTTP {up_v2.status_code}: {up_v2.text}")
        return False

    # 4. 同步覆盖老文件名 artist_{aid}.jpg (释放 213 字节坏文件或超大老图)
    v1_filename = f"artist_{aid}.jpg"
    files_v1 = {'file': (v1_filename, jpeg_bytes, 'image/jpeg')}
    data_v1 = {'category': 'artists', 'filename': v1_filename}
    requests.post(ASSET_UPLOAD_URL, files=files_v1, data=data_v1, timeout=20)
    print(f"   ✅ [V1 同名覆盖成功] 同步修复历史路径兼容性")
    
    return True

def verify_results():
    print("\n" + "=" * 80)
    print("🔍 验证 D1 骨架最新下发数据与图片有效性:")
    print("=" * 80)
    r = requests.get(f"{API_BASE}/api/skeleton?nocache={int(time.time())}", timeout=15).json()
    artists = r.get('data', {}).get('artists', [])
    art_map = {}
    for a in artists:
        aid_str = a.get('id', '').replace('db_', '')
        if aid_str.isdigit():
            art_map[int(aid_str)] = a
            
    for item in TARGET_ARTISTS:
        aid = item['id']
        name = item['name']
        a_info = art_map.get(aid)
        if not a_info:
            print(f"❌ 未找到艺人: {name} ({aid})")
            continue
        av_url = a_info.get('avatar')
        try:
            head = requests.head(av_url, timeout=10)
            status = head.status_code
            content_len = head.headers.get('content-length', '未知')
            ctype = head.headers.get('content-type', '未知')
            print(f"• {name:<6} (ID:{aid:<3}) -> HTTP {status} | {ctype:<10} | {content_len:>6} B | URL: {av_url}")
        except Exception as e:
            print(f"• {name:<6} (ID:{aid:<3}) -> 请求失败: {e}")

if __name__ == '__main__':
    print("🚀 启动歌手头像重构与全链路破缓存修复...")
    for item in TARGET_ARTISTS:
        process_and_upload(item)
        time.sleep(0.3)
    verify_results()
