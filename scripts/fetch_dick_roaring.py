import sys
import json
import requests
import subprocess
import os

sys.stdout.reconfigure(encoding='utf-8')

roaring_tracks = [
    {"id": 28648, "title": "爱如潮水", "r2_key": "music/迪克牛仔/咆哮/s_28648.mp3"},
    {"id": 28649, "title": "酒干倘卖无", "r2_key": "music/迪克牛仔/咆哮/s_28649.mp3"},
    {"id": 28650, "title": "哭不出来", "r2_key": "music/迪克牛仔/咆哮/s_28650.mp3"},
    {"id": 28651, "title": "梦醒时分", "r2_key": "music/迪克牛仔/咆哮/s_28651.mp3"},
    {"id": 28652, "title": "吻别", "r2_key": "music/迪克牛仔/咆哮/s_28652.mp3"},
    {"id": 28653, "title": "无力去爱谁", "r2_key": "music/迪克牛仔/咆哮/s_28653.mp3"},
    {"id": 28654, "title": "想说", "r2_key": "music/迪克牛仔/咆哮/s_28654.mp3"},
    {"id": 28655, "title": "一言难尽", "r2_key": "music/迪克牛仔/咆哮/s_28655.mp3"},
    {"id": 28656, "title": "原来你什么都不要", "r2_key": "music/迪克牛仔/咆哮/s_28656.mp3"},
    {"id": 28657, "title": "值得", "r2_key": "music/迪克牛仔/咆哮/s_28657.mp3"},
]

def search_and_download(title, temp_raw):
    # 1. Kuwo
    url_kw = f"http://search.kuwo.cn/r.s?client=kt&all=迪克牛仔+{title}&ft=music&cluster=0&strategy=2012&encoding=utf8&rformat=json&vipver=1&issubtitle=1&show_copyright_off=1&pn=0&rn=10"
    try:
        r = requests.get(url_kw, timeout=6)
        d = json.loads(r.text.replace("'", '"'))
        for item in d.get('abslist', []):
            art = item.get('ARTIST', '')
            alb = item.get('ALBUM', '')
            rid = item.get('DC_TARGETID', '')
            if '迪克牛仔' in art:
                # get download url
                anti_url = f"http://antiserver.kuwo.cn/anti.s?type=convert_url&rid={rid}&format=mp3&response=url"
                r_dl = requests.get(anti_url, timeout=5)
                if r_dl.text.startswith('http'):
                    audio_res = requests.get(r_dl.text, stream=True, timeout=15)
                    with open(temp_raw, 'wb') as f:
                        for c in audio_res.iter_content(65536):
                            if c: f.write(c)
                    if os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 500000:
                        print(f"  • Kuwo 命中: {art} - {item.get('SONGNAME')} (Album: {alb}) [RID: {rid}]")
                        return True
    except Exception as e:
        print(f"  Kuwo error for {title}: {e}")

    # 2. NetEase
    url_ne = f"https://music.163.com/api/search/get/web?s=迪克牛仔+{title}&type=1&limit=5"
    try:
        r = requests.get(url_ne, headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)
        for s in r.json().get('result', {}).get('songs', []):
            s_art = s.get('artists', [{}])[0].get('name', '')
            if '迪克牛仔' in s_art:
                sid = s.get('id')
                mp3_url = f"https://music.163.com/song/media/outer/url?id={sid}.mp3"
                head = requests.head(mp3_url, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True, timeout=5)
                if head.status_code == 200 and int(head.headers.get('Content-Length', 0)) > 500000:
                    audio_res = requests.get(mp3_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=15)
                    with open(temp_raw, 'wb') as f:
                        for c in audio_res.iter_content(65536):
                            if c: f.write(c)
                    if os.path.exists(temp_raw) and os.path.getsize(temp_raw) > 500000:
                        print(f"  • NetEase 命中: {s_art} - {s.get('name')} (ID: {sid})")
                        return True
    except Exception as e:
        print(f"  NetEase error for {title}: {e}")

    return False

for t in roaring_tracks:
    raw_path = f"scratch/dick_{t['id']}.raw.mp3"
    print(f"Finding 迪克牛仔 version for: 《{t['title']}》...")
    ok = search_and_download(t['title'], raw_path)
    if ok:
        print(f"  ✅ 成功下载实体音频: {os.path.getsize(raw_path)} 字节")
    else:
        print(f"  ❌ 未找到纯净版本")
