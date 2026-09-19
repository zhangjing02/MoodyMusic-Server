import os
import sys
import json
import subprocess
import tempfile
import requests

GROQ_API_KEY = "GROQ_KEY_REMOVED"
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
PROXIES = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}

def transcribe_audio(file_path):
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    with open(file_path, "rb") as f:
        files = {"file": ("tail.mp3", f, "audio/mpeg")}
        data = {"model": "whisper-large-v3", "language": "zh"}
        resp = requests.post(GROQ_API_URL, headers=headers, files=files, data=data, proxies=PROXIES, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
        else:
            return f"ERR_{resp.status_code}: {resp.text}"

# 获取刀郎所有歌曲
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

print(f"刀郎共有 {len(songs)} 首已点亮歌曲待排查")

# 关键词列表
KEYWORDS = ["点赞", "观看", "关注", "视频", "下期", "谢谢观看", "感谢观看", "投币", "转发", "订阅", "频道"]

# 逐一排查后 15 秒
for idx, (alb, title, path) in enumerate(songs, 1):
    # 转换为绝对可播放URL
    if not path.startswith("http"):
        # 兼容相对路径
        url = f"https://pub-3507a1a1bc4b4ac3a3340833031078c2.r2.dev{path}"
    else:
        url = path
        
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # 使用 ffmpeg 截取最后 15 秒: 先获取时长
        # 为提高速度，直接使用 ffmpeg sseof 截取最后 15 秒
        cmd = [
            "ffmpeg", "-y", "-sseof", "-15", "-i", url,
            "-ac", "1", "-ar", "16000", "-b:a", "32k",
            tmp_path
        ]
        ret = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if ret.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1000:
            text = transcribe_audio(tmp_path)
            # 检查是否有口播关键词
            hit = [kw for kw in KEYWORDS if kw in text]
            if hit:
                print(f"🚨 命中口播! [{idx}/{len(songs)}] 《{alb}》- 《{title}》: {text} (命中: {hit})")
                print(f"   URL: {url}")
            else:
                if "感谢" in text or "观看" in text or "视频" in text:
                    print(f"⚠️ 疑似口播: [{idx}/{len(songs)}] 《{alb}》- 《{title}》: {text}")
                else:
                    if idx % 10 == 0:
                        print(f"[{idx}/{len(songs)}] 进度正常: 《{title}》 -> 尾音: {text[:20]}...")
        else:
            pass
    except Exception as e:
        # print(f"Err on {title}: {e}")
        pass
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

print("排查完毕。")
