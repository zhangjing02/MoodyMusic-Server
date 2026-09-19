import requests
import subprocess
import tempfile
import os

url = "https://m-api.changgepd.ccwu.cc/storage/music/五月天/後青春期的詩/s_17961.mp3"

# 1. 取文件大小
h = requests.head(url, timeout=10)
cl = int(h.headers.get('Content-Length', 0))
print(f"Content-Length: {cl} bytes")

# 2. 取前 400KB (大约前 20~25 秒)
r_head = requests.get(url, headers={'Range': 'bytes=0-409600'}, timeout=10)
with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
    f.write(r_head.content)
    p_head = f.name

# 3. 转码成 16k mono wav/mp3 并转写
with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f2:
    p_clip = f2.name

subprocess.run(['ffmpeg', '-y', '-i', p_head, '-t', '20', '-ac', '1', '-ar', '16000', p_clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sz = os.path.getsize(p_clip)
print(f"Clip created: {sz} bytes")

import json
GROQ_API_KEY = "GROQ_KEY_REMOVED"
cmd = [
    'curl', '-s', '-x', 'http://127.0.0.1:7890',
    'https://api.groq.com/openai/v1/audio/transcriptions',
    '-H', f'Authorization: Bearer {GROQ_API_KEY}',
    '-F', f'file=@{p_clip}',
    '-F', 'model=whisper-large-v3-turbo'
]
res = subprocess.check_output(cmd).decode()
print("Range fetch 转写结果:", res)

os.remove(p_head)
os.remove(p_clip)
