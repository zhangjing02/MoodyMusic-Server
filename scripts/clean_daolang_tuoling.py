import os
import sys
import json
import subprocess
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

raw_url = 'https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/2002年的第一场雪/s_5415.mp3'
clean_mp3 = '/tmp/s_5415_clean.mp3'

# 裁切最后 7.9 秒，并在 276.5s 开始做 1.5s 淡出
print("✂️ 正在精密切割《驼铃》片尾口播并做自然淡出...")
cmd = [
    "ffmpeg", "-y", "-t", "278.0", "-i", raw_url,
    "-af", "afade=t=out:st=276.5:d=1.5",
    "-b:a", "160k", "-ar", "44100", "-ac", "2",
    clean_mp3
]
subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f"清洗完成: {os.path.getsize(clean_mp3)} bytes")

# 上传到 account_07
mp3_key = "music/刀郎/2002年的第一场雪/s_5415.mp3"
s3_client.upload_file(clean_mp3, bucket_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
mp3_url = f"{public_base}/{mp3_key}"
print(f"清洗后音频已上传: {mp3_url}")

# 更新 D1 数据库
payload = {
    "updates": [
        {
            "id": 5415,
            "file_path": mp3_url,
            "lrc_path": "https://pub-383b876c0bb840f6b852946604275232.r2.dev/lyrics/刀郎/2002年的第一场雪/s_5415.lrc"
        }
    ]
}
resp = requests.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json=payload, proxies=PROXIES, timeout=30)
print(f"D1 点亮更新结果: HTTP {resp.status_code}, {resp.text}")

# 验证清洗后最后 10 秒
subprocess.run(['ffmpeg', '-y', '-sseof', '-10', '-i', clean_mp3, '-ac', '1', '-ar', '16000', '/tmp/tuoling_clean_tail.mp3'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
curl_cmd = [
    'curl', '-s', '-x', 'http://127.0.0.1:7890',
    'https://api.groq.com/openai/v1/audio/transcriptions',
    '-H', f'Authorization: Bearer {GROQ_API_KEY}',
    '-F', 'file=@/tmp/tuoling_clean_tail.mp3',
    '-F', 'model=whisper-large-v3-turbo'
]
res = json.loads(subprocess.check_output(curl_cmd).decode())
print(f"🎧 清洗后最后10秒 AI 听音: '{res.get('text', '')}'")
