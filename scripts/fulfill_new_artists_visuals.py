# -*- coding: utf-8 -*-
"""
fulfill_new_artists_visuals.py
专项补全新歌手头像、海报图及专辑封面：
1. 覆盖 10 位新歌手（童安格、阿雅、大张伟、金海心、老狼、娃娃、杨乃文、张宇、郑秀文、江美琪）
2. 彻底解决 NetEase 原始文件伪装（PNG 伪装成 .jpg）与大图传输瓶颈，统一 LANCZOS 精准面部裁切至 600x600 纯正 JPEG (40~65KB)
3. 强力破除客户端/CDN 30 天缓存毒化：上传 artist_{aid}_v2.jpg 并原子更新 D1 artists.photo_url，同时覆盖历史 artist_{aid}.jpg
4. 修复郑秀文 5 张核心大碟封面缺失（2184, 2185, 2186, 2187, 2188），上传 R2 并更新 D1 albums.cover_url
5. 同步写入 Web 本地静态资源目录以支持离线/备用 Fallback
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
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com'
}

# 10 位歌手高清写真配置（经人工眼动视觉校验与面部定位）
ARTIST_CONFIGS = [
    {
        "id": 169,
        "name": "童安格",
        "file": "tmp/audit_avatars/169_童安格.jpg",
        "crop_mode": "top_center",
        "face_top_ratio": 0.12
    },
    {
        "id": 174,
        "name": "阿雅",
        "file": "tmp/audit_avatars/174_阿雅.jpg",
        "crop_mode": "top_center",
        "face_top_ratio": 0.05
    },
    {
        "id": 175,
        "name": "大张伟",
        "file": "tmp/audit_avatars/175_大张伟.jpg",
        "crop_mode": "center",
        "face_top_ratio": 0.08
    },
    {
        "id": 171,
        "name": "金海心",
        "file": "tmp/audit_avatars/171_金海心.jpg",
        "crop_mode": "top_center",
        "face_top_ratio": 0.15
    },
    {
        "id": 172,
        "name": "老狼",
        "file": "tmp/audit_avatars/172_老狼.jpg",
        "crop_mode": "center",
        "face_top_ratio": 0.05
    },
    {
        "id": 177,
        "name": "娃娃",
        "file": "tmp/audit_avatars/177_娃娃_final.jpg",
        "crop_mode": "direct_square",
        "face_top_ratio": 0
    },
    {
        "id": 173,
        "name": "杨乃文",
        "file": "tmp/audit_avatars/173_杨乃文.jpg",
        "crop_mode": "top_center",
        "face_top_ratio": 0.10
    },
    {
        "id": 167,
        "name": "张宇",
        "file": "tmp/audit_avatars/167_张宇.jpg",
        "crop_mode": "top_center",
        "face_top_ratio": 0.10
    },
    {
        "id": 168,
        "name": "郑秀文",
        "file": "tmp/audit_avatars/168_郑秀文.jpg",
        "crop_mode": "top_center",
        "face_top_ratio": 0.08
    },
    {
        "id": 176,
        "name": "江美琪",
        "file": "tmp/audit_avatars/176_江美琪.jpg",
        "crop_mode": "top_center",
        "face_top_ratio": 0.12
    }
]

# 郑秀文 5 张专辑封面配置
SAMMI_ALBUMS = [
    {
        "id": 2184,
        "title": "值得",
        "file": "tmp/audit_avatars/sammi_2184_值得.jpg"
    },
    {
        "id": 2185,
        "title": "眉飞色舞",
        "file": "tmp/audit_avatars/sammi_2185_眉飞色舞.jpg"
    },
    {
        "id": 2186,
        "title": "去爱吧",
        "file": "tmp/audit_avatars/sammi_2186_去爱吧.jpg"
    },
    {
        "id": 2187,
        "title": "完整",
        "file": "tmp/audit_avatars/sammi_2187_完整.jpg"
    },
    {
        "id": 2188,
        "title": "Sammi 经典粤语白金极选",
        "file": "tmp/audit_avatars/sammi_2188_白金极选.jpg"
    }
]

# 本地 Web assets 路径
WEB_AVATAR_DIR = "MoodyMusic-Web/src/assets/images/avatars/artists"
WEB_COVER_DIR = "MoodyMusic-Web/src/assets/images/covers"

def optimize_image_square(src_path, target_size=600, top_ratio=0.1, crop_mode="top_center"):
    im = Image.open(src_path).convert('RGB')
    w, h = im.size
    min_dim = min(w, h)
    
    if crop_mode == "direct_square" and w == h:
        cropped = im
    else:
        left = (w - min_dim) // 2
        top = int((h - min_dim) * top_ratio) if h > w else 0
        if top + min_dim > h:
            top = h - min_dim
        cropped = im.crop((left, top, left + min_dim, top + min_dim))
        
    resized = cropped.resize((target_size, target_size), Image.Resampling.LANCZOS)
    
    out_buf = BytesIO()
    resized.save(out_buf, format='JPEG', quality=88, optimize=True)
    return out_buf.getvalue(), resized

def process_artists():
    print("=" * 80)
    print("🚀 开始处理 10 位歌手高清头像与海报视觉资产...")
    print("=" * 80)
    
    os.makedirs(WEB_AVATAR_DIR, exist_ok=True)
    
    for cfg in ARTIST_CONFIGS:
        aid = cfg['id']
        name = cfg['name']
        src_file = cfg['file']
        top_ratio = cfg.get('face_top_ratio', 0.1)
        crop_mode = cfg.get('crop_mode', 'top_center')
        
        print(f"\n🎨 优化中 [{name}] (ID: {aid})...")
        jpeg_bytes, pil_img = optimize_image_square(src_file, target_size=600, top_ratio=top_ratio, crop_mode=crop_mode)
        print(f"   ✨ 优化规格: 600x600 纯正 JPEG，体积: {len(jpeg_bytes)} 字节")
        
        # 1. 保存本地 Web Fallback 资产 (artist_{aid}.jpg)
        local_web_path = os.path.join(WEB_AVATAR_DIR, f"artist_{aid}.jpg")
        with open(local_web_path, 'wb') as f:
            f.write(jpeg_bytes)
        print(f"   💾 [本地 Web 资产就绪] -> {local_web_path}")
        
        # 2. 上传至 R2 v2 版本并原子更新 D1 artists.photo_url
        v2_filename = f"artist_{aid}_v2.jpg"
        files_v2 = {'file': (v2_filename, jpeg_bytes, 'image/jpeg')}
        data_v2 = {'category': 'artists', 'artist_id': str(aid), 'filename': v2_filename}
        up_v2 = requests.post(ASSET_UPLOAD_URL, files=files_v2, data=data_v2, timeout=20)
        if up_v2.status_code == 200:
            print(f"   ✅ [R2 V2 上传成功] D1 绑定 -> artists/{v2_filename}")
        else:
            print(f"   ❌ [R2 V2 上传失败] HTTP {up_v2.status_code}: {up_v2.text}")
            
        # 3. 同步覆盖旧文件名 artist_{aid}.jpg 以维持历史直链与各端平滑兼容
        v1_filename = f"artist_{aid}.jpg"
        files_v1 = {'file': (v1_filename, jpeg_bytes, 'image/jpeg')}
        data_v1 = {'category': 'artists', 'filename': v1_filename}
        up_v1 = requests.post(ASSET_UPLOAD_URL, files=files_v1, data=data_v1, timeout=20)
        if up_v1.status_code == 200:
            print(f"   ✅ [R2 V1 历史兼容覆盖成功] -> artists/{v1_filename}")
        else:
            print(f"   ⚠️ [R2 V1 历史兼容覆盖告警] HTTP {up_v1.status_code}")
            
        time.sleep(0.3)

def process_sammi_albums():
    print("\n" + "=" * 80)
    print("💿 开始处理郑秀文 5 张核心录音室大碟封面资产...")
    print("=" * 80)
    
    os.makedirs(WEB_COVER_DIR, exist_ok=True)
    
    for alb in SAMMI_ALBUMS:
        albid = alb['id']
        title = alb['title']
        src_file = alb['file']
        
        print(f"\n🎵 处理大碟 《{title}》 (Album ID: {albid})...")
        jpeg_bytes, pil_img = optimize_image_square(src_file, target_size=600, top_ratio=0, crop_mode="direct_square")
        print(f"   ✨ 优化规格: 600x600 纯正 JPEG，体积: {len(jpeg_bytes)} 字节")
        
        cover_filename = f"c_{albid}.jpg"
        
        # 1. 保存本地 Web Covers
        local_cover_path = os.path.join(WEB_COVER_DIR, cover_filename)
        with open(local_cover_path, 'wb') as f:
            f.write(jpeg_bytes)
        print(f"   💾 [本地 Web 封面就绪] -> {local_cover_path}")
        
        # 2. 上传至 R2 covers/albums 并原子更新 D1 albums.cover_url
        files = {'file': (cover_filename, jpeg_bytes, 'image/jpeg')}
        data = {'category': 'albums', 'album_id': str(albid), 'filename': cover_filename}
        up = requests.post(ASSET_UPLOAD_URL, files=files, data=data, timeout=20)
        if up.status_code == 200:
            res_json = up.json()
            r2_url = res_json.get('data', {}).get('files', [{}])[0].get('url', '')
            print(f"   ✅ [R2 封面上传成功] D1 绑定 -> covers/albums/{cover_filename} ({r2_url})")
        else:
            print(f"   ❌ [R2 封面上传失败] HTTP {up.status_code}: {up.text}")
            
        time.sleep(0.3)

def verify_all_results():
    print("\n" + "=" * 80)
    print("🔍 验证 D1 骨架下发最新头像与海报数据 (破缓存模式):")
    print("=" * 80)
    
    r = requests.get(f"{API_BASE}/api/skeleton?nocache={int(time.time())}", timeout=15).json()
    artists = r.get('data', {}).get('artists', [])
    art_map = {}
    for a in artists:
        aid_str = a.get('id', '').replace('db_', '')
        if aid_str.isdigit():
            art_map[int(aid_str)] = a
            
    for cfg in ARTIST_CONFIGS:
        aid = cfg['id']
        name = cfg['name']
        info = art_map.get(aid)
        if not info:
            print(f"❌ 未在骨架中找到: {name} ({aid})")
            continue
        av_url = info.get('avatar', '')
        if not av_url or 'default.png' in av_url:
            print(f"❌ {name:<6} (ID: {aid:<3}) -> 仍为默认头像: {av_url}")
            continue
        try:
            head = requests.head(av_url, timeout=10)
            print(f"✅ {name:<6} (ID: {aid:<3}) -> HTTP {head.status_code} | {head.headers.get('content-length')} 字节 | {av_url}")
        except Exception as e:
            print(f"⚠️ {name:<6} (ID: {aid:<3}) -> 请求失败: {e}")
            
    print("\n" + "=" * 80)
    print("🔍 验证郑秀文专辑详情封面数据:")
    print("=" * 80)
    r_sammi = requests.get(f"{API_BASE}/api/songs?artistId=168&artist=郑秀文&nocache={int(time.time())}", timeout=15).json()
    sammi_albs = r_sammi.get('data', [{}])[0].get('albums', [])
    for alb in sammi_albs:
        cov = alb.get('cover', '')
        try:
            head = requests.head(cov, timeout=10)
            print(f"✅ 《{alb.get('title'):<16}》 -> HTTP {head.status_code} | {cov}")
        except Exception as e:
            print(f"⚠️ 《{alb.get('title'):<16}》 -> 探测异常: {cov} ({e})")

if __name__ == '__main__':
    process_artists()
    process_sammi_albums()
    verify_all_results()
