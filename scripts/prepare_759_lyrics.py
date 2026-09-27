import os
import sys
import syncedlyrics
import requests
import urllib.parse
import base64

sys.stdout.reconfigure(encoding='utf-8')

TRACKS_759 = [
    {"id": 10393, "title": "暗恋"},
    {"id": 10394, "title": "恋曲1990"},
    {"id": 10395, "title": "爱人同志"},
    {"id": 10396, "title": "你的样子"},
    {"id": 10397, "title": "梦"},
    {"id": 10398, "title": "黄色脸孔"},
    {"id": 10399, "title": "京城夜"},
    {"id": 10400, "title": "明天的太阳"},
    {"id": 10401, "title": "游戏规则"},
    {"id": 10402, "title": "不变的结局"}
]

out_dir = "backend/tmp/luo_759_tracks"
os.makedirs(out_dir, exist_ok=True)
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

for t in TRACKS_759:
    sid = t["id"]
    title = t["title"]
    lrc_f = os.path.join(out_dir, f"s_{sid}.lrc")
    
    queries = [f"罗大佑 {title}", title]
    lrc_text = ""
    for q in queries:
        try:
            res = syncedlyrics.search(q, providers=['NetEase', 'Kugou', 'Lrclib'])
            if res and len(res.strip()) > 30 and ("[" in res):
                lrc_text = res
                break
        except Exception:
            pass
            
    if not lrc_text:
        for q in queries:
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
                        if content and len(content.strip()) > 30 and ("[" in content):
                            lrc_text = content
                            break
                if lrc_text:
                    break
            except Exception:
                pass
                
    if lrc_text:
        with open(lrc_f, "w", encoding="utf-8") as fp:
            fp.write(lrc_text)
        print(f"[{sid}] 《{title}》: 歌词抓取成功 ({len(lrc_text.splitlines())} 行)")
    else:
        print(f"[{sid}] 《{title}》: ⚠️ 未能抓取歌词")

print("=== 759 歌词准备完毕 ===")
