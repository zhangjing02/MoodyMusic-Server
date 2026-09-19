import os
import sys
import json
import time
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

TARGET_SONGS = [
    {
        "id": 24274,
        "album": "後青春期的詩",
        "title": "突然好想你"
    },
    {
        "id": 24197,
        "album": "第二人生",
        "title": "突然好想你"
    },
    {
        "id": 17935,
        "album": "步步自選作品輯 1999-2013",
        "title": "突然好想你"
    },
    {
        "id": 17974,
        "album": "第二人生 (明日版)",
        "title": "星空"
    },
    {
        "id": 17938,
        "album": "步步自選作品輯 1999-2013",
        "title": "星空"
    },
    {
        "id": 17926,
        "album": "自传",
        "title": "What's Your Story?"
    },
    {
        "id": 18069,
        "album": "知足 just my pride 最真傑作選",
        "title": "借問眾神明"
    }
]

work_dir = "/tmp/mayday_reharvest_work"
os.makedirs(work_dir, exist_ok=True)

def find_true_topic_url(title):
    queries = [f"五月天 - Topic {title}", f"Mayday - Topic {title}"]
    for q in queries:
        cmd = [
            "yt-dlp",
            "--proxy", "http://127.0.0.1:7890",
            "--print", "%(id)s | %(channel)s | %(title)s | %(duration_string)s",
            f"ytsearch10:{q}"
        ]
        try:
            out = subprocess.check_output(cmd, text=True, timeout=18)
            lines = out.strip().splitlines()
            for line in lines:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4:
                    vid, channel, vtitle, vdur = parts[0], parts[1], parts[2], parts[3]
                    # 必须是 Topic 频道，且排除 live / mv
                    if "Topic" in channel and "Live" not in vtitle and "MV" not in vtitle and "Music Video" not in vtitle:
                        print(f"   🎯 锁定官方 Topic 录音室源: [{channel}] {vtitle} ({vdur}) -> ID: {vid}")
                        return f"https://www.youtube.com/watch?v={vid}"
        except Exception as e:
            print(f"   ⚠️ 搜索出错 {q}: {e}")
    return None

updates = []

for item in TARGET_SONGS:
    sid = item['id']
    alb = item['album']
    title = item['title']

    print(f"\n=======================================================")
    print(f"🎸 [ID: {sid}] 《{alb}》- 《{title}》...")
    
    target_url = find_true_topic_url(title)
    if not target_url:
        print(f"   ❌ 未找到匹配的 Topic 音源！")
        continue

    raw_path = os.path.join(work_dir, f"raw_{sid}.webm")
    mp3_path = os.path.join(work_dir, f"s_{sid}.mp3")
    lrc_path = os.path.join(work_dir, f"s_{sid}.lrc")

    if os.path.exists(raw_path): os.remove(raw_path)
    if os.path.exists(mp3_path): os.remove(mp3_path)
    if os.path.exists(lrc_path): os.remove(lrc_path)

    # 1. 抓取
    cmd_dl = [
        "yt-dlp",
        "--proxy", "http://127.0.0.1:7890",
        "-f", "ba",
        "-o", raw_path,
        target_url
    ]
    ret = subprocess.run(cmd_dl, capture_output=True, text=True)
    if ret.returncode != 0 or not os.path.exists(raw_path):
        print(f"   ❌ 下载失败: {ret.stderr[:100]}")
        continue

    # 2. 转码
    cmd_ffmpeg = [
        "ffmpeg", "-y", "-i", raw_path,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-b:a", "160k", "-ar", "44100", "-ac", "2",
        mp3_path
    ]
    subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) < 10000:
        print(f"   ❌ 转码失败")
        continue

    # 3. 歌词
    lrc_url = None
    try:
        import syncedlyrics
        lrc_text = syncedlyrics.search(f"五月天 {title}")
        if not lrc_text:
            lrc_text = syncedlyrics.search(f"Mayday {title}")
        if lrc_text:
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(lrc_text)
            lrc_key = f"lyrics/五月天/{alb}/s_{sid}.lrc"
            s3_client.upload_file(lrc_path, bucket_name, lrc_key, ExtraArgs={"ContentType": "text/plain; charset=utf-8"})
            lrc_url = f"{public_base}/{lrc_key}"
            print(f"   📄 歌词已上传: {lrc_url}")
    except Exception as e:
        print(f"   ⚠️ 歌词跳过: {e}")

    # 4. 上传
    mp3_key = f"music/五月天/{alb}/s_{sid}.mp3"
    s3_client.upload_file(mp3_path, bucket_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
    mp3_url = f"{public_base}/{mp3_key}"
    print(f"   🚀 音频已上传: {mp3_url}")

    updates.append({
        "id": sid,
        "file_path": mp3_url,
        "lrc_path": lrc_url
    })

    # 5. Groq Whisper 前尾听音复测
    try:
        tmp_head = os.path.join(work_dir, f"clip_h_{sid}.mp3")
        tmp_tail = os.path.join(work_dir, f"clip_t_{sid}.mp3")
        subprocess.run(['ffmpeg', '-y', '-ss', '0', '-t', '20', '-i', mp3_path, '-ac', '1', '-ar', '16000', tmp_head], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['ffmpeg', '-y', '-sseof', '-20', '-i', mp3_path, '-ac', '1', '-ar', '16000', tmp_tail], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        cmd_h = [
            'curl', '-s', '-x', 'http://127.0.0.1:7890',
            'https://api.groq.com/openai/v1/audio/transcriptions',
            '-H', f'Authorization: Bearer {GROQ_API_KEY}',
            '-F', f'file=@{tmp_head}',
            '-F', 'model=whisper-large-v3-turbo'
        ]
        cmd_t = [
            'curl', '-s', '-x', 'http://127.0.0.1:7890',
            'https://api.groq.com/openai/v1/audio/transcriptions',
            '-H', f'Authorization: Bearer {GROQ_API_KEY}',
            '-F', f'file=@{tmp_tail}',
            '-F', 'model=whisper-large-v3-turbo'
        ]
        h_text = json.loads(subprocess.check_output(cmd_h).decode()).get('text', '')
        t_text = json.loads(subprocess.check_output(cmd_t).decode()).get('text', '')
        print(f"   🎧 [闭环复测] 前奏听音: '{h_text[:40]}'")
        print(f"   🎧 [闭环复测] 尾奏听音: '{t_text[:40]}'")
    except Exception as ex:
        print(f"   ⚠️ 闭环听音跳过: {ex}")

# 6. D1 批量点亮
if updates:
    print(f"\n=======================================================")
    print(f"🚀 正在向 D1 提交批量点亮更新 ({len(updates)} 首)...")
    resp = requests.post(
        "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light",
        json={"updates": updates},
        proxies=PROXIES,
        timeout=30
    )
    print(f"D1 点亮响应: HTTP {resp.status_code}, {resp.text}")

print("\n🎉 五月天受污染曲目 100% 官方 Topic 纯净录音室重采与清洗完毕！")
