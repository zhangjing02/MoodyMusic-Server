import os
import sys
import json
import subprocess
import tempfile
import requests
import boto3
from botocore.config import Config

PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

with open("MoodyMusic-Server/r2_config.json", "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]["account_07"]

s3_client = boto3.client(
    service_name="s3",
    endpoint_url=r2_cfg["endpoint_url"],
    aws_access_key_id=r2_cfg["access_key_id"],
    aws_secret_access_key=r2_cfg["secret_access_key"],
    region_name="auto",
    config=Config(s3={"addressing_style": "path"}, proxies=PROXIES, connect_timeout=15, read_timeout=30)
)
bucket_name = r2_cfg["name"]
public_base = r2_cfg["public_url"]

print(f"目标桶: {bucket_name}, Public: {public_base}")

# 1. 抓取王菲《無奈那天》
artist = "王菲"
album = "王靖雯"
song = "無奈那天"
song_id = 23999

work_dir = tempfile.mkdtemp()
raw_audio = os.path.join(work_dir, "raw.webm")
norm_mp3 = os.path.join(work_dir, f"s_{song_id}.mp3")
lrc_file = os.path.join(work_dir, f"s_{song_id}.lrc")

query = f"ytsearch3:王菲 無奈那天 官方音源"
cmd = [
    "yt-dlp",
    "--proxy", "http://127.0.0.1:7890",
    "--no-playlist",
    "-f", "ba",
    "--default-search", "ytsearch",
    "-o", raw_audio,
    query
]
print(f"正在下载: {artist} - {song}...")
ret = subprocess.run(cmd, capture_output=True, text=True)
if ret.returncode != 0:
    print(f"下载失败: {ret.stderr}")
    sys.exit(1)

# 转码 160k loudnorm
cmd_ffmpeg = [
    "ffmpeg", "-y", "-i", raw_audio,
    "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
    "-b:a", "160k", "-ar", "44100", "-ac", "2",
    norm_mp3
]
subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f"转码完成: {os.path.getsize(norm_mp3)} bytes")

# 抓取歌词
try:
    import syncedlyrics
    lrc_text = syncedlyrics.search(f"{artist} {song}", proxies={"https": "http://127.0.0.1:7890"})
    if not lrc_text:
        lrc_text = syncedlyrics.search(f"{artist} 无奈那天", proxies={"https": "http://127.0.0.1:7890"})
    if lrc_text:
        with open(lrc_file, "w", encoding="utf-8") as f:
            f.write(lrc_text)
        print(f"歌词获取成功: {len(lrc_text)} chars")
    else:
        lrc_file = None
except Exception as e:
    print(f"歌词获取异常: {e}")
    lrc_file = None

# 上传到 account_07
mp3_key = f"music/{artist}/{album}/s_{song_id}.mp3"
s3_client.upload_file(norm_mp3, bucket_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
mp3_url = f"{public_base}/{mp3_key}"
print(f"MP3 已上传: {mp3_url}")

lrc_url = None
if lrc_file and os.path.exists(lrc_file):
    lrc_key = f"lyrics/{artist}/{album}/s_{song_id}.lrc"
    s3_client.upload_file(lrc_file, bucket_name, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
    lrc_url = f"{public_base}/{lrc_key}"
    print(f"LRC 已上传: {lrc_url}")

# 更新 D1 数据库
payload = {
    "updates": [
        {
            "id": song_id,
            "file_path": mp3_url,
            "lrc_path": lrc_url
        }
    ]
}
resp = requests.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json=payload, proxies=PROXIES, timeout=30)
print(f"D1 点亮返回: HTTP {resp.status_code}, {resp.text}")

# AI 听音验证
with open(norm_mp3, "rb") as f:
    files = {"file": ("check.mp3", f, "audio/mpeg")}
    data = {"model": "whisper-large-v3", "language": "zh"}
    r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", 
                      headers={"Authorization": f"Bearer {GROQ_API_KEY}"}, 
                      files=files, data=data, proxies=PROXIES, timeout=30)
    if r.status_code == 200:
        print("🎧 AI 识别前 100 字:", r.json().get("text", "")[:100])
    else:
        print("AI 识别错误:", r.text)

print("王菲首曲重采上传完毕！")
