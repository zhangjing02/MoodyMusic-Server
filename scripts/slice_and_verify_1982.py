import os
import sys
import subprocess
import json
import requests

sys.stdout.reconfigure(encoding='utf-8')

full_audio = "backend/tmp/luo_1982_full.webm"
out_dir = "backend/tmp/luo_1982_tracks"
os.makedirs(out_dir, exist_ok=True)

TRACKS = [
    {"index": 1, "id": 27012, "title": "鹿港小镇", "start": 1, "end": 284, "dur": 283},
    {"index": 2, "id": 27013, "title": "恋曲1980", "start": 284, "end": 485, "dur": 201},
    {"index": 3, "id": 27014, "title": "童年", "start": 485, "end": 720, "dur": 235},
    {"index": 4, "id": 27015, "title": "错误", "start": 720, "end": 1028, "dur": 308},
    {"index": 5, "id": 27016, "title": "摇篮曲", "start": 1028, "end": 1229, "dur": 201},
    {"index": 6, "id": 27017, "title": "之乎者也", "start": 1229, "end": 1474, "dur": 245},
    {"index": 7, "id": 27018, "title": "乡愁四韵", "start": 1474, "end": 1832, "dur": 358},
    {"index": 8, "id": 27019, "title": "将进酒", "start": 1832, "end": 2096, "dur": 264},
    {"index": 9, "id": 27020, "title": "光阴的故事", "start": 2096, "end": 2300, "dur": 204},
    {"index": 10, "id": 27021, "title": "蒲公英", "start": 2300, "end": 2490, "dur": 190}
]

key = os.environ.get('GROQ_API_KEY')
proxies = {'http': 'http://127.0.0.1:10090', 'https': 'http://127.0.0.1:10090'}

print("=== 开始切片 1982《之乎者也》全专辑 10 首曲目并听音质检 ===")

for t in TRACKS:
    idx = t["index"]
    sid = t["id"]
    title = t["title"]
    st = t["start"]
    duration = t["dur"]
    
    raw_track_mp3 = os.path.join(out_dir, f"s_{sid}_raw.mp3")
    
    # 提取切片
    cmd = [
        "ffmpeg", "-y", "-ss", str(st), "-i", full_audio,
        "-t", str(duration),
        "-c:a", "libmp3lame", "-b:a", "320k",
        raw_track_mp3
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    
    # 获取真实时长
    out_dur = subprocess.check_output([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", raw_track_mp3
    ]).decode().strip()
    
    # 截取中段人声测试
    clip_p = os.path.join(out_dir, f"s_{sid}_clip.mp3")
    subprocess.run(["ffmpeg", "-y", "-ss", "30", "-i", raw_track_mp3, "-t", "20", "-c", "copy", clip_p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    heard = ""
    try:
        with open(clip_p, "rb") as fp:
            r = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": ("clip.mp3", fp, "audio/mpeg"), "model": (None, "whisper-large-v3"), "temperature": (None, "0.0")},
                proxies=proxies,
                timeout=20
            )
            if r.ok:
                heard = r.json().get("text", "")
    except Exception as e:
        heard = str(e)
        
    print(f"[{idx:02d}] ID:{sid} 《{title}》 | 切片时长: {float(out_dur):.1f}s | 试听: {heard[:50]}")

print("=== 10 首曲目初步切片质检完毕 ===")
