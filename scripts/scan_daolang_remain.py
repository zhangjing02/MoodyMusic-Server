import os
import sys
import subprocess
import tempfile
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

GROQ_API_KEY = "GROQ_KEY_REMOVED"
PROXIES = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}

r = requests.get('https://m-api.changgepd.ccwu.cc/api/songs?artist=刀郎', timeout=20)
data = r.json().get('data', [])
songs = []
for art in data:
    if art['name'] == '刀郎':
        for alb in art.get('albums', []):
            alb_name = alb.get('title')
            for s in alb.get('songs', []):
                if s.get('path'):
                    songs.append((alb_name, s.get('title'), s.get('path')))

# 仅检查后半部分 (index 94 ~ 171)
target_songs = songs[94:]
print(f"剩余 {len(target_songs)} 首待并发扫描...")

KEYWORDS = ["点赞", "观看", "关注", "视频", "下期", "谢谢观看", "感谢观看", "投币", "转发", "订阅", "频道", "优优独播"]

def check_one(item):
    alb, title, path = item
    url = path if path.startswith("http") else f"https://pub-3507a1a1bc4b4ac3a3340833031078c2.r2.dev{path}"
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cmd = ["ffmpeg", "-y", "-sseof", "-15", "-i", url, "-ac", "1", "-ar", "16000", "-b:a", "32k", tmp_path]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1000:
            curl_cmd = [
                'curl', '-s', '-x', 'http://127.0.0.1:7890',
                'https://api.groq.com/openai/v1/audio/transcriptions',
                '-H', f'Authorization: Bearer {GROQ_API_KEY}',
                '-F', f'file=@{tmp_path}',
                '-F', 'model=whisper-large-v3-turbo'
            ]
            res = json.loads(subprocess.check_output(curl_cmd).decode())
            text = res.get('text', '')
            hit = [kw for kw in KEYWORDS if kw in text]
            if hit:
                return (True, f"🚨 命中口播! 《{alb}》- 《{title}》: {text} (命中: {hit})", path)
            elif any(k in text for k in ["感谢", "观看", "视频"]):
                return (True, f"⚠️ 疑似口播! 《{alb}》- 《{title}》: {text}", path)
            return (False, f"✅ 《{title}》正常", path)
    except Exception as e:
        return (False, f"Err {title}: {e}", path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

with ThreadPoolExecutor(max_workers=5) as ex:
    futures = [ex.submit(check_one, s) for s in target_songs]
    for f in as_completed(futures):
        hit, msg, path = f.result()
        if hit:
            print(msg)
