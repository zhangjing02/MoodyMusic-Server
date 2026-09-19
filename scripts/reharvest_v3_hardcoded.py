#!/usr/bin/env python3
"""
五月天污染歌曲精准重采 v3（硬编码版）
- 直接使用已确认的 YouTube 视频 ID，跳过搜索步骤
- 突然好想你 x3 => Mayday - Topic: 3VfoPoGfZuQ
- 星空 x2       => Mayday - Topic: FZDMPzZKtdg
- 借問眾神明     => 滾石官方 MV: 4vZMeHykGlk (尾奏已验证干净)
- What's Your Story => 跳过（无完整版）
"""

import subprocess, json, os, sys, time, boto3, requests, tempfile, shutil
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
API_BASE = "https://m-api.changgepd.ccwu.cc"
PROXY = "http://127.0.0.1:7890"
GROQ_KEY = os.environ.get("GROQ_API_KEY")
R2_CFG = json.load(open("/Users/apple/Desktop/moodyimusic/MoodyMusic-Server/r2_config.json"))
BUCKET_CFG = R2_CFG["buckets"]["account_07"]
PUBLIC_PREFIX = BUCKET_CFG["public_url"]
BUCKET_NAME   = BUCKET_CFG["name"]
WORK_DIR = "/tmp/reharvest_v3_work"
os.makedirs(WORK_DIR, exist_ok=True)

# ── 硬编码任务表 ───────────────────────────────────────
TASKS = [
    {"id": 24274, "album": "後青春期的詩",           "title": "突然好想你", "yt_id": "3VfoPoGfZuQ"},
    {"id": 24197, "album": "第二人生",               "title": "突然好想你", "yt_id": "3VfoPoGfZuQ"},
    {"id": 17935, "album": "步步自選作品輯 1999-2013","title": "突然好想你", "yt_id": "3VfoPoGfZuQ"},
    {"id": 17974, "album": "第二人生 (明日版)",       "title": "星空",       "yt_id": "FZDMPzZKtdg"},
    {"id": 17938, "album": "步步自選作品輯 1999-2013","title": "星空",       "yt_id": "FZDMPzZKtdg"},
    {"id": 18069, "album": "知足 just my pride 最真傑作選", "title": "借問眾神明", "yt_id": "4vZMeHykGlk"},
    # ID:17926 What's Your Story? — 无完整版，跳过
]

# ── R2 客户端 ──────────────────────────────────────────
s3 = boto3.client(
    "s3",
    endpoint_url=BUCKET_CFG["endpoint_url"],
    aws_access_key_id=BUCKET_CFG["access_key_id"],
    aws_secret_access_key=BUCKET_CFG["secret_access_key"],
    region_name="auto"
)

def download_audio(yt_id: str, out_path: str) -> bool:
    url = f"https://www.youtube.com/watch?v={yt_id}"
    cmd = [
        "yt-dlp", "--proxy", PROXY,
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "-o", out_path, url
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    return r.returncode == 0 and os.path.exists(out_path)

def fetch_lrc(title: str, artist: str = "五月天") -> str | None:
    try:
        import syncedlyrics
        lrc = syncedlyrics.search(f"{artist} {title}")
        return lrc
    except Exception as e:
        print(f"   ⚠️  歌词获取失败: {e}")
        return None

def upload_r2(local_path: str, r2_key: str, content_type: str = "audio/mpeg") -> str:
    s3.upload_file(local_path, BUCKET_NAME, r2_key,
                   ExtraArgs={"ContentType": content_type})
    return f"{PUBLIC_PREFIX}/{r2_key}"

def whisper_check(mp3_path: str, segment: str = "head") -> str:
    """提取前/后 20 秒并转写"""
    seg_path = mp3_path + f"_{segment}.mp3"
    if segment == "head":
        ffcmd = ["ffmpeg", "-y", "-i", mp3_path, "-t", "20",
                 "-acodec", "libmp3lame", "-q:a", "5", seg_path]
    else:
        ffcmd = ["ffmpeg", "-y", "-i", mp3_path, "-ss", "-20",
                 "-acodec", "libmp3lame", "-q:a", "5", seg_path]
    subprocess.run(ffcmd, capture_output=True, timeout=30)
    if not os.path.exists(seg_path):
        return ""
    with open(seg_path, "rb") as f:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            data={"model": "whisper-large-v3-turbo", "response_format": "json", "language": "zh"},
            files={"file": ("seg.mp3", f, "audio/mpeg")},
            timeout=30
        )
    return resp.json().get("text", "") if resp.ok else ""

def batch_light(updates: list[dict]) -> bool:
    resp = requests.post(
        f"{API_BASE}/api/admin/songs/batch-light",
        json={"updates": updates},
        timeout=15
    )
    return resp.ok

# ── 主流程 ─────────────────────────────────────────────
print("🚀 五月天污染歌曲精准重采 v3（硬编码版）\n")
updates = []

for task in TASKS:
    song_id = task["id"]
    album   = task["album"]
    title   = task["title"]
    yt_id   = task["yt_id"]
    print(f"{'='*60}")
    print(f"🎸 [ID:{song_id}] 《{album}》- 《{title}》")
    print(f"   ▶ YouTube ID: {yt_id}")

    mp3_path = os.path.join(WORK_DIR, f"s_{song_id}.mp3")
    # 如已下载则跳过
    if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 100_000:
        print(f"   ✅ 本地已有音频，跳过下载")
    else:
        print(f"   ⬇️  下载中...")
        ok = download_audio(yt_id, mp3_path)
        if not ok:
            print(f"   ❌ 下载失败，跳过")
            continue
        print(f"   ✅ 下载完成: {os.path.getsize(mp3_path)/1024/1024:.1f} MB")

    # 闭环听音检测（前20秒 + 后20秒）
    print(f"   🎧 闭环听音检测中...")
    head_text = whisper_check(mp3_path, "head")
    tail_text = whisper_check(mp3_path, "tail")
    print(f"   🔊 前奏: {head_text[:80]}")
    print(f"   🔊 尾奏: {tail_text[:80]}")

    # 简单污染检测
    POLLUTION_KEYWORDS = ["那年", "台北", "报道", "幸福的方向", "小时候妈妈", "播报"]
    head_clean = not any(kw in head_text for kw in POLLUTION_KEYWORDS)
    tail_clean  = not any(kw in tail_text  for kw in POLLUTION_KEYWORDS)

    if not (head_clean and tail_clean):
        print(f"   ⚠️  闭环检测仍发现污染！跳过上传")
        continue

    # 上传音频
    r2_audio_key = f"music/五月天/{album}/s_{song_id}.mp3"
    audio_url = upload_r2(mp3_path, r2_audio_key, "audio/mpeg")
    print(f"   🚀 音频上传: {audio_url}")

    # 获取歌词
    lrc_content = fetch_lrc(title)
    lrc_url = None
    if lrc_content:
        lrc_path = os.path.join(WORK_DIR, f"s_{song_id}.lrc")
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        r2_lrc_key = f"lyrics/五月天/{album}/s_{song_id}.lrc"
        lrc_url = upload_r2(lrc_path, r2_lrc_key, "text/plain")
        print(f"   📄 歌词上传: {lrc_url}")
    else:
        print(f"   ⚠️  歌词未找到，跳过歌词上传")

    updates.append({
        "id": song_id,
        "file_path": r2_audio_key,
        "lrc_path": r2_lrc_key if lrc_url else None
    })
    print(f"   ✅ ID:{song_id} 准备写入 D1")

# ── D1 批量点亮 ────────────────────────────────────────
print(f"\n{'='*60}")
if updates:
    print(f"📡 批量写入 D1，共 {len(updates)} 首...")
    ok = batch_light(updates)
    if ok:
        print(f"✅ D1 批量点亮成功！")
        for u in updates:
            print(f"   - ID:{u['id']} => {u['file_path']}")
    else:
        print(f"❌ D1 写入失败，手动提交 payload:")
        print(json.dumps({"updates": updates}, ensure_ascii=False, indent=2))
else:
    print("⚠️  没有成功处理的曲目，跳过 D1 写入")

print(f"\n🎉 完成！处理了 {len(updates)}/{len(TASKS)} 首（跳过 What's Your Story）")
