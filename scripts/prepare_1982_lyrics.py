import os
import sys
import syncedlyrics
import requests
import urllib.parse
import base64
import re

sys.stdout.reconfigure(encoding='utf-8')

TRACKS = [
    {"index": 1, "id": 27012, "title": "鹿港小镇"},
    {"index": 2, "id": 27013, "title": "恋曲1980"},
    {"index": 3, "id": 27014, "title": "童年"},
    {"index": 4, "id": 27015, "title": "错误"},
    {"index": 5, "id": 27016, "title": "摇篮曲"},
    {"index": 6, "id": 27017, "title": "之乎者也"},
    {"index": 7, "id": 27018, "title": "乡愁四韵"},
    {"index": 8, "id": 27019, "title": "将进酒"},
    {"index": 9, "id": 27020, "title": "光阴的故事"},
    {"index": 10, "id": 27021, "title": "蒲公英"}
]

out_dir = "backend/tmp/luo_1982_tracks"
os.makedirs(out_dir, exist_ok=True)

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

for t in TRACKS:
    sid = t["id"]
    title = t["title"]
    lrc_path = os.path.join(out_dir, f"s_{sid}.lrc")
    
    # 优先搜索 罗大佑 歌名
    q = f"罗大佑 {title}"
    lrc_text = ""
    
    # 1. 尝试 syncedlyrics
    try:
        res = syncedlyrics.search(q, providers=['NetEase', 'Kugou', 'Lrclib'])
        if res and len(res.strip()) > 30:
            lrc_text = res
    except Exception:
        pass
        
    # 2. 尝试酷狗高精度源
    if not lrc_text:
        try:
            url = f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={urllib.parse.quote(q)}&page=1&pagesize=5"
            r = requests.get(url, headers=headers, timeout=5).json()
            for s in r.get("data", {}).get("info", []):
                h = s.get("hash")
                dur = s.get("duration", 0)
                lrc_url = f"http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword={urllib.parse.quote(s.get('songname'))}&duration={dur}000&hash={h}"
                lr = requests.get(lrc_url, timeout=5).json()
                candidates = lr.get("candidates", [])
                if candidates:
                    cand = candidates[0]
                    dl_url = f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cand['id']}&accesskey={cand['accesskey']}&fmt=lrc&charset=utf8"
                    dr = requests.get(dl_url, timeout=5).json()
                    content = base64.b64decode(dr.get("content", "")).decode("utf-8", errors="ignore")
                    if content and len(content.strip()) > 30:
                        lrc_text = content
                        break
        except Exception:
            pass
            
    if lrc_text:
        with open(lrc_path, "w", encoding="utf-8") as fp:
            fp.write(lrc_text)
        print(f"[{t['index']}] ID:{sid} 《{title}》 -> 歌词抓取成功 ({len(lrc_text.splitlines())} 行)")
    else:
        print(f"[{t['index']}] ID:{sid} 《{title}》 -> ⚠️ 未抓取到歌词")

print("=== 歌词预备完成 ===")
