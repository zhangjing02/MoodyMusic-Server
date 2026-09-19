import os
import sys
import json
import subprocess
import tempfile
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

artist = "曲婉婷"
album = "LLL"

tracks = [
    (27397, "为此曲而歌 (Make Love To This Song)", "Wanting Qu - Make Love To This Song (Official Audio)"),
    (27398, "分散你的注意力 (Distract You)", "Wanting Qu - Distract You (Official Audio)"),
    (27399, "再见月球 (Moon And Back)", "Wanting Qu - Moon And Back (Official Audio)"),
    (27400, "亲吻天堂 (Kissing Paradise)", "Wanting Qu - Kissing Paradise (Official Audio)"),
    (27401, "余晖 (Afterglow)", "Wanting Qu - Afterglow (Official Audio)"),
    (27402, "不能再伤害我 (You Can't Hurt Me Anymore)", "Wanting Qu - You Can't Hurt Me Anymore (Official Audio)"),
    (27403, "让你自由 (Set You Free)", "Wanting Qu - Set You Free (Official Audio)"),
    (27404, "难道不好吗 (Wouldn't It Be Nice)", "Wanting Qu - Wouldn't It Be Nice (Official Audio)"),
    (27405, "你的女孩 (Your Girl)", "Wanting Qu - Your Girl (Official Audio)"),
    (27406, "狂野的心 (Wild Heart)", "Wanting Qu - Wild Heart (Official Audio)"),
    (27407, "最好的安排", "曲婉婷 最好的安排 官方音源")
]

work_dir = "/tmp/quwanting_lll_work"
os.makedirs(work_dir, exist_ok=True)

updates = []

for song_id, title, query in tracks:
    print(f"\n==========================================")
    print(f"🎵 处理 [{song_id}] 《{title}》...")
    raw_path = os.path.join(work_dir, f"raw_{song_id}.webm")
    mp3_path = os.path.join(work_dir, f"s_{song_id}.mp3")
    lrc_path = os.path.join(work_dir, f"s_{song_id}.lrc")

    if os.path.exists(raw_path):
        os.remove(raw_path)
    if os.path.exists(mp3_path):
        os.remove(mp3_path)
    if os.path.exists(lrc_path):
        os.remove(lrc_path)

    # 1. 下载
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

    # 3. 获取歌词
    lrc_url = None
    try:
        import syncedlyrics
        # 英文歌名搜索
        clean_name = title.split('(')[-1].replace(')', '').strip()
        lrc_text = syncedlyrics.search(f"Wanting {clean_name}")
        if not lrc_text:
            lrc_text = syncedlyrics.search(f"曲婉婷 {clean_name}")
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

    # 5. 快速 Groq 听音校验
    try:
        tmp_clip = os.path.join(work_dir, f"clip_{song_id}.mp3")
        subprocess.run(['ffmpeg', '-y', '-ss', '20', '-t', '20', '-i', mp3_path, '-ac', '1', '-ar', '16000', tmp_clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        curl_cmd = [
            'curl', '-s', '-x', 'http://127.0.0.1:7890',
            'https://api.groq.com/openai/v1/audio/transcriptions',
            '-H', f'Authorization: Bearer {GROQ_API_KEY}',
            '-F', f'file=@{tmp_clip}',
            '-F', 'model=whisper-large-v3-turbo'
        ]
        res_json = json.loads(subprocess.check_output(curl_cmd).decode())
        print(f"  🎧 AI听辨: {res_json.get('text', '')[:60]}")
    except Exception as ex:
        print(f"  AI听辨跳过: {ex}")

# 6. 批量调用 D1 点亮
if updates:
    print(f"\n🚀 正在向 D1 提交批量点亮 ({len(updates)} 首)...")
    resp = requests.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json={"updates": updates}, proxies=PROXIES, timeout=30)
    print(f"D1 点亮结果: HTTP {resp.status_code}, {resp.text}")

print("\n🎉 曲婉婷《LLL》全专重采与点亮完成！")
