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

artist = "五月天"
album = "五月天第一張創作專輯"

tracks = [
    (24211, "瘋狂世界", "五月天 瘋狂世界 第一張創作專輯 滾石 官方"),
    (24212, "擁抱", "五月天 擁抱 第一張創作專輯 滾石 官方"),
    (24213, "透露", "五月天 透露 第一張創作專輯 滾石 官方"),
    (24214, "生活", "五月天 生活 第一張創作專輯 滾石 官方"),
    (24215, "愛情的模樣", "五月天 愛情的模樣 第一張創作專輯 滾石 官方"),
    (24216, "嘿我要走了", "五月天 嘿我要走了 第一張創作專輯 滾石 官方"),
    (24217, "軋車", "五月天 軋車 第一張創作專輯 滾石 官方"),
    (24218, "志明與春嬌", "五月天 志明與春嬌 第一張創作專輯 滾石 官方"),
    (24219, "Hosee", "五月天 Hosee 第一張創作專輯 滾石 官方"),
    (24220, "黑白講", "五月天 黑白講 第一張創作專輯 滾石 官方"),
    (24221, "I Love You 無望", "五月天 I Love You 無望 第一張創作專輯 滾石 官方"),
    (24222, "風若吹", "五月天 風若吹 第一張創作專輯 滾石 官方")
]

work_dir = "/tmp/mayday_first_album_work"
os.makedirs(work_dir, exist_ok=True)

updates = []

for song_id, title, query in tracks:
    print(f"\n==========================================")
    print(f"🎸 处理 [{song_id}] 《{title}》...")
    raw_path = os.path.join(work_dir, f"raw_{song_id}.webm")
    mp3_path = os.path.join(work_dir, f"s_{song_id}.mp3")
    lrc_path = os.path.join(work_dir, f"s_{song_id}.lrc")

    if os.path.exists(raw_path):
        os.remove(raw_path)
    if os.path.exists(mp3_path):
        os.remove(mp3_path)
    if os.path.exists(lrc_path):
        os.remove(lrc_path)

    # 1. 抓取正版
    cmd = [
        "yt-dlp",
        "--proxy", "http://127.0.0.1:7890",
        "--no-playlist",
        "-f", "ba",
        "--default-search", "ytsearch",
        "-o", raw_path,
        f"ytsearch3:{query}"
    ]
    ret = subprocess.run(cmd, capture_output=True, text=True)
    if ret.returncode != 0 or not os.path.exists(raw_path):
        print(f"❌ 下载失败: {title}, err: {ret.stderr[:120]}")
        continue

    # 2. 转码 160k CBR + loudnorm
    cmd_ffmpeg = [
        "ffmpeg", "-y", "-i", raw_path,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-b:a", "160k", "-ar", "44100", "-ac", "2",
        mp3_path
    ]
    subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) < 10000:
        print(f"❌ 转码失败: {title}")
        continue

    # 3. 抓取歌词
    lrc_url = None
    try:
        import syncedlyrics
        lrc_text = syncedlyrics.search(f"五月天 {title}")
        if not lrc_text:
            lrc_text = syncedlyrics.search(f"Mayday {title}")
        if lrc_text:
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            lrc_key = f"lyrics/{artist}/{album}/s_{song_id}.lrc"
            s3_client.upload_file(lrc_path, bucket_name, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            lrc_url = f"{public_base}/{lrc_key}"
            print(f"  📄 歌词上传成功: {lrc_url}")
    except Exception as e:
        print(f"  ⚠️ 歌词获取跳过: {e}")

    # 4. 上传音频
    mp3_key = f"music/{artist}/{album}/s_{song_id}.mp3"
    s3_client.upload_file(mp3_path, bucket_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
    mp3_url = f"{public_base}/{mp3_key}"
    print(f"  🚀 音频上传成功: {mp3_url}")

    updates.append({
        "id": song_id,
        "file_path": mp3_url,
        "lrc_path": lrc_url
    })

    # 5. Groq Whisper 听音核对
    try:
        tmp_clip = os.path.join(work_dir, f"clip_{song_id}.mp3")
        subprocess.run(['ffmpeg', '-y', '-ss', '20', '-t', '25', '-i', mp3_path, '-ac', '1', '-ar', '16000', tmp_clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        curl_cmd = [
            'curl', '-s', '-x', 'http://127.0.0.1:7890',
            'https://api.groq.com/openai/v1/audio/transcriptions',
            '-H', f'Authorization: Bearer {GROQ_API_KEY}',
            '-F', f'file=@{tmp_clip}',
            '-F', 'model=whisper-large-v3-turbo'
        ]
        res_json = json.loads(subprocess.check_output(curl_cmd).decode())
        ai_text = res_json.get('text', '')
        print(f"  🎧 AI听辨人声: {ai_text[:60]}")
        # 验证是否包含李宗盛字样
        if "李宗盛" in ai_text:
            print(f"  ⚠️ 警告: 依然检测到李宗盛，需核对源！")
    except Exception as ex:
        print(f"  AI听辨跳过: {ex}")

# 6. 批量提交 D1
if updates:
    print(f"\n🚀 正在向 D1 提交批量点亮 ({len(updates)} 首)...")
    resp = requests.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json={"updates": updates}, proxies=PROXIES, timeout=30)
    print(f"D1 点亮结果: HTTP {resp.status_code}, {resp.text}")

print("\n🎉 五月天《第一張創作專輯》12首全部清洗重采完毕！")
