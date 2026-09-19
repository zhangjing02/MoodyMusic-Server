import os
import sys
import json
import subprocess
import requests
import boto3
from botocore.config import Config

PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
GROQ_API_KEY = "GROQ_KEY_REMOVED"

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

artist = "五月天"
album = "五月天第一張創作專輯"

# 1. 验证 24211《瘋狂世界》在 40~65 秒（人声副歌部分）到底是谁唱的
crazy_world_url = f"{public_base}/music/五月天/五月天第一張創作專輯/s_24211.mp3"
subprocess.run(['ffmpeg', '-y', '-ss', '40', '-t', '25', '-i', crazy_world_url, '-ac', '1', '-ar', '16000', '/tmp/crazy_vocal.mp3'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
curl_cmd = [
    'curl', '-s', '-x', 'http://127.0.0.1:7890',
    'https://api.groq.com/openai/v1/audio/transcriptions',
    '-H', f'Authorization: Bearer {GROQ_API_KEY}',
    '-F', 'file=@/tmp/crazy_vocal.mp3',
    '-F', 'model=whisper-large-v3-turbo'
]
res = json.loads(subprocess.check_output(curl_cmd).decode())
print(f"🎧 24211《瘋狂世界》(40-65s) 人声听音: '{res.get('text', '')}'")

# 2. 攻坚 24214《生活》与 24222《風若吹》
targets = [
    (24214, "生活", "五月天 - Topic 生活"),
    (24222, "風若吹", "五月天 - Topic 風若吹")
]

updates = []
for sid, title, query in targets:
    print(f"\n🎸 重新采录 [{sid}] 《{title}》...")
    raw = f"/tmp/raw_{sid}.webm"
    mp3 = f"/tmp/s_{sid}_clean.mp3"
    lrc = f"/tmp/s_{sid}.lrc"
    
    cmd_dl = [
        "yt-dlp", "--proxy", "http://127.0.0.1:7890",
        "--no-playlist", "-f", "ba",
        "-o", raw, f"ytsearch3:{query}"
    ]
    subprocess.run(cmd_dl, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(raw):
        # 降级备用关键词
        subprocess.run(["yt-dlp", "--proxy", "http://127.0.0.1:7890", "--no-playlist", "-f", "ba", "-o", raw, f"ytsearch3:Mayday 五月天 {title} 音频"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(raw):
        subprocess.run(["ffmpeg", "-y", "-i", raw, "-af", "loudnorm=I=-14:LRA=11:TP=-1.5", "-b:a", "160k", "-ar", "44100", "-ac", "2", mp3], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 歌词
        try:
            import syncedlyrics
            lrc_text = syncedlyrics.search(f"五月天 {title}")
            if lrc_text:
                with open(lrc, "w", encoding="utf-8") as f:
                    f.write(lrc_text)
                lrc_key = f"lyrics/{artist}/{album}/s_{sid}.lrc"
                s3_client.upload_file(lrc, bucket_name, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
        except Exception:
            pass
            
        mp3_key = f"music/{artist}/{album}/s_{sid}.mp3"
        s3_client.upload_file(mp3, bucket_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        new_url = f"{public_base}/{mp3_key}"
        print(f"  🚀 音频已上传: {new_url}")
        
        # 校验副歌人声
        subprocess.run(['ffmpeg', '-y', '-ss', '30', '-t', '25', '-i', mp3, '-ac', '1', '-ar', '16000', f'/tmp/clip_{sid}.mp3'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        c_cmd = [
            'curl', '-s', '-x', 'http://127.0.0.1:7890',
            'https://api.groq.com/openai/v1/audio/transcriptions',
            '-H', f'Authorization: Bearer {GROQ_API_KEY}',
            '-F', f'file=@/tmp/clip_{sid}.mp3',
            '-F', 'model=whisper-large-v3-turbo'
        ]
        t_res = json.loads(subprocess.check_output(c_cmd).decode())
        print(f"  🎧 AI听辨: '{t_res.get('text', '')}'")
        updates.append({"id": sid, "file_path": new_url})

if updates:
    r = requests.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json={"updates": updates}, proxies=PROXIES, timeout=30)
    print(f"D1 补齐结果: HTTP {r.status_code}, {r.text}")
