import os
import sys
import json
import time
import requests
import sqlite3
import subprocess
import boto3

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts')
from r2_safety_guard import safe_r2_put_object, get_r2_config

GROQ_KEY = os.environ.get('GROQ_API_KEY')
TMP_DIR = r'G:\music-backup\tmp\remediate_bili'
os.makedirs(TMP_DIR, exist_ok=True)

# 7 validated Bilibili targets
bili_targets = [
    {
        "id": 14227,
        "artist": "容祖儿",
        "album": "Me, Re-Do (Deluxe Version)",
        "title": "天然呆 (KTV 版)",
        "bvid": "BV18Y4114792",
        "expected_dur": 235
    },
    {
        "id": 14283,
        "artist": "容祖儿",
        "album": "小日子 (特別版)",
        "title": "小日子",
        "bvid": "BV1ou2sBjE4i",
        "expected_dur": 255
    },
    {
        "id": 14730,
        "artist": "容祖儿",
        "album": "Something About You",
        "title": "一面之緣(清仔Q版)",
        "bvid": "BV1zg411F79X",
        "expected_dur": 189
    },
    {
        "id": 22549,
        "artist": "周华健",
        "album": "小天堂",
        "title": "摆渡人的歌",
        "bvid": "BV1km421g7uN",
        "expected_dur": 161
    },
    {
        "id": 23750,
        "artist": "齐秦",
        "album": "无情的雨无情的你",
        "title": "边界",
        "bvid": "BV193eYzXEZW",
        "expected_dur": 325
    },
    {
        "id": 14301,
        "artist": "容祖儿",
        "album": "小日子 (特別版)",
        "title": "另眼相看 (iTunes Session)",
        "bvid": "BV1tZ421M7Rp",
        "expected_dur": 224
    },
    {
        "id": 14645,
        "artist": "容祖儿",
        "album": "Show Up",
        "title": "Show Up!",
        "bvid": "BV1KdexecEab",
        "expected_dur": 269
    }
]

cfg = get_r2_config()
acc_key = 'account_13'
acc = cfg['buckets'][acc_key]

s3 = boto3.client(
    's3',
    endpoint_url=f"https://{acc['account_id']}.r2.cloudflarestorage.com",
    aws_access_key_id=acc['access_key_id'],
    aws_secret_access_key=acc['secret_access_key'],
    region_name='auto'
)

conn = sqlite3.connect(r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\database\catalog_sync.db')
cur = conn.cursor()

print("🚀 开始通过 Bilibili 高清母带采录修复 7 首遗珠曲目...")
success = 0

for t in bili_targets:
    sid = t['id']
    artist = t['artist']
    album = t['album']
    title = t['title']
    bvid = t['bvid']
    
    print(f"\n--- 正在处理 ID {sid}: [{artist}] 《{title}》 ({bvid}) ---")
    raw_path = os.path.join(TMP_DIR, f"bili_{sid}.mp3")
    opt_path = os.path.join(TMP_DIR, f"bili_opt_{sid}.mp3")
    
    for p in [raw_path, opt_path]:
        if os.path.exists(p): os.remove(p)
        
    cmd_dl = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "-o", raw_path,
        f"https://www.bilibili.com/video/{bvid}"
    ]
    res_dl = subprocess.run(cmd_dl, capture_output=True)
    if not os.path.exists(raw_path) or os.path.getsize(raw_path) < 500000:
        print(f"  ❌ 下载失败: {res_dl.stderr.decode('utf-8', errors='replace')[-200:]}")
        continue
        
    print(f"  📥 下载成功 ({os.path.getsize(raw_path)//1024} KB)")
    
    # 压制标准化 (loudnorm, 160k CBR)
    cmd_ff = [
        "ffmpeg", "-y", "-i", raw_path,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-codec:a", "libmp3lame", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        opt_path
    ]
    subprocess.run(cmd_ff, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    
    # ffprobe Accurate Duration
    cmd_probe = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", opt_path]
    probe_res = subprocess.run(cmd_probe, capture_output=True)
    data = json.loads(probe_res.stdout.decode('utf-8', errors='replace'))
    dur = int(float(data['format']['duration']))
    print(f"  🎵 标准化压制完成: 时长 {dur} 秒, 160k CBR")
    
    # R2 Upload via Guard
    with open(opt_path, "rb") as f:
        audio_data = f.read()
        
    r2_key = f"music/{artist}/{album}/s_{sid}.mp3"
    safe_r2_put_object(
        s3_client=s3,
        bucket_name=acc['name'],
        account_key=acc_key,
        key=r2_key,
        body=audio_data,
        content_type='audio/mpeg'
    )
    
    cdn_url = f"{acc['public_domain']}/{r2_key}"
    
    # Verify HTTP 200
    chk = requests.head(cdn_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
    if chk.status_code != 200:
        print(f"  ❌ CDN 校验失败: HTTP {chk.status_code}")
        continue
    print(f"  ☁️ R2 写入成功 & CDN 200 OK: {cdn_url}")
    
    # Update D1
    cmd_d1 = [
        'npx', 'wrangler', 'd1', 'execute', 'moody-d1-test', '--remote',
        f"--command=UPDATE songs SET file_path = '{cdn_url}', duration = {dur} WHERE id = {sid};"
    ]
    subprocess.run(cmd_d1, cwd='backend', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
    
    # Update Local DB
    cur.execute("UPDATE songs SET file_path = ?, duration = ? WHERE id = ?", (cdn_url, dur, sid))
    conn.commit()
    
    # Update progress
    with open('backend/scripts/remediate_progress.json', 'r', encoding='utf-8') as f:
        prog = json.load(f)
    if sid not in prog['completed']:
        prog['completed'].append(sid)
    with open('backend/scripts/remediate_progress.json', 'w', encoding='utf-8') as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)
        
    print(f"  🎉 修复成功: ID {sid} 正版已入库！")
    success += 1
    
    for p in [raw_path, opt_path]:
        if os.path.exists(p): os.remove(p)

print(f"\n==========================================")
print(f"Bilibili 补充治理完成: 成功 {success} / {len(bili_targets)} 首！")
print(f"==========================================")
