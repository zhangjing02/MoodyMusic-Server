import os
import sys
import syncedlyrics
import requests
import urllib.parse
import base64

sys.stdout.reconfigure(encoding='utf-8')

TRACKS_1767 = [
    {"id": 27022, "title": "诞生"},
    {"id": 27023, "title": "亚细亚的孤儿"},
    {"id": 27024, "title": "现象七十二变"},
    {"id": 27025, "title": "牧童"},
    {"id": 27026, "title": "未来的主人翁"},
    {"id": 27027, "title": "青春舞曲"},
    {"id": 27028, "title": "爱的箴言"},
    {"id": 27029, "title": "小妹"},
    {"id": 27030, "title": "盲聋"},
    {"id": 27031, "title": "稻草人"}
]

out_dir = "backend/tmp/luo_1767_tracks"
os.makedirs(out_dir, exist_ok=True)
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

for t in TRACKS_1767:
    sid = t["id"]
    title = t["title"]
    lrc_f = os.path.join(out_dir, f"s_{sid}.lrc")
    
    # 特例处理纯音乐或短引子《诞生》
    if title == "诞生":
        # 《诞生》是开场交响/摇篮纯音乐或引子
        content = "[00:00.00]诞生 (纯音乐) - 罗大佑\n[00:01.00]曲：罗大佑\n[00:05.00]编曲：罗大佑\n[00:10.00] (音乐演奏)\n"
        with open(lrc_f, "w", encoding="utf-8") as fp:
            fp.write(content)
        print(f"[{sid}] 《{title}》: 纯音乐引子歌词写入成功")
        continue

    q = f"罗大佑 {title}"
    lrc_text = ""
    try:
        res = syncedlyrics.search(q, providers=['NetEase', 'Kugou', 'Lrclib'])
        if res and len(res.strip()) > 30 and ("[" in res):
            lrc_text = res
    except Exception:
        pass
        
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
                    if content and len(content.strip()) > 30 and ("[" in content):
                        lrc_text = content
                        break
        except Exception:
            pass
            
    if lrc_text:
        with open(lrc_f, "w", encoding="utf-8") as fp:
            fp.write(lrc_text)
        print(f"[{sid}] 《{title}》: 歌词抓取成功 ({len(lrc_text.splitlines())} 行)")
    else:
        print(f"[{sid}] 《{title}》: ⚠️ 未能抓取歌词")

print("=== 1767 歌词准备完毕 ===")
