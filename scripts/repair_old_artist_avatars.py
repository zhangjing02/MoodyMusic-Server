# -*- coding: utf-8 -*-
"""
repair_old_artist_avatars.py
专项修复老歌手高清头像：
1. 迪克牛仔 (ID: 154) - 重新覆盖之前损坏的 213 字节文本文件
2. 李克勤 (ID: 160) - 补全头像并绑定 D1
3. 谭咏麟 (ID: 82) - 确保高清头像在 R2 且 D1 正确关联
4. 蔡琴 (ID: 159) - 补全头像并绑定 D1
5. 许茹芸 (ID: 161) - 补全头像并绑定 D1
6. 陈小春 (ID: 136) - 补全头像并绑定 D1
7. 宋冬野 (ID: 137) - 补全头像并绑定 D1
"""
import requests
import json
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

API_BASE = "https://m-api.changgepd.ccwu.cc"
ASSET_UPLOAD_URL = f"{API_BASE}/api/admin/assets/upload"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/'
}

# 预先经过严密校验的高清真头像来源（网易云无损 CDN 高清图 640x640+）
TARGET_ARTISTS = [
    {
        "id": 154,
        "name": "迪克牛仔",
        "url": "http://p1.music.126.net/EVRNHbTelaeRpaD2PFGnYw==/109951168896254251.jpg"
    },
    {
        "id": 160,
        "name": "李克勤",
        "url": "http://p1.music.126.net/a9ekQj9SfOujRMk6h6IIUA==/109951168299155350.jpg"
    },
    {
        "id": 82,
        "name": "谭咏麟",
        "url": "http://p2.music.126.net/wpQIDNXCXbhmhBT5JtDTMQ==/109951168274716128.jpg"
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
        "id": 136,
        "name": "陈小春",
        "url": "http://p1.music.126.net/MyK0_930LX6q0fD2Bcp_vg==/109951169164945697.jpg"
    },
    {
        "id": 137,
        "name": "宋冬野",
        # 经精准抓取得到的宋冬野官方高清写真
        "url": "https://p2.music.126.net/6y-UleORITEDbvrOLAssGQ==/109951168705646193.jpg"
    }
]

def upload_avatar(artist_id, artist_name, img_url):
    print(f"🔄 正在处理艺人 [{artist_name}] (ID: {artist_id})...")
    resp = requests.get(img_url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        print(f"❌ 下载原图失败: HTTP {resp.status_code}")
        return False
    
    img_data = resp.content
    print(f"   下载成功，体积: {len(img_data)} 字节")

    filename = f"artist_{artist_id}.jpg"
    files = {
        'file': (filename, img_data, 'image/jpeg')
    }
    data = {
        'category': 'artists',
        'artist_id': str(artist_id),
        'filename': filename
    }

    up_resp = requests.post(ASSET_UPLOAD_URL, files=files, data=data, timeout=20)
    if up_resp.status_code == 200:
        res_json = up_resp.json()
        print(f"   ✅ 上传并更新 D1 成功: {res_json.get('message')}")
        results = res_json.get('data', {}).get('files', [])
        if results:
            print(f"   直链/访问地址: {results[0].get('url')}")
        return True
    else:
        print(f"   ❌ 上传失败: HTTP {up_resp.status_code}, {up_resp.text}")
        return False

def verify_all():
    print("\n🔍 正在通过 /api/skeleton 验证所有修复艺人头像状态...")
    r = requests.get(f"{API_BASE}/api/skeleton", timeout=15).json()
    artists = r.get('data', {}).get('artists', [])
    art_map = {a.get('id'): a for a in artists}

    for item in TARGET_ARTISTS:
        key = f"db_{item['id']}"
        info = art_map.get(key)
        if not info:
            print(f"⚠️ 未在骨架中找到 {key} ({item['name']})")
            continue
        avatar = info.get('avatar')
        print(f"[{item['name']}] Avatar URL: {avatar}")
        if avatar and avatar.startswith('http'):
            try:
                head_resp = requests.head(avatar, timeout=10)
                print(f"   -> HTTP {head_resp.status_code}, Content-Length: {head_resp.headers.get('content-length')} 字节")
            except Exception as e:
                print(f"   -> 探测异常: {e}")

if __name__ == '__main__':
    for item in TARGET_ARTISTS:
        upload_avatar(item['id'], item['name'], item['url'])
        time.sleep(0.5)
    verify_all()
