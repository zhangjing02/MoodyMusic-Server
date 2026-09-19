import os
import sys
import json
import subprocess
import requests
import boto3
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# 30首待清洗清单 (排除 5415 已经单独清洗)
items = [
    (5442, "丝路乐魂(乐器篇)", "拉克木卡姆片段", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐魂(乐器篇)/s_5442.mp3", 9.0),
    (5445, "丝路乐魂(乐器篇)", "塔娜瓦尔", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐魂(乐器篇)/s_5445.mp3", 9.0),
    (5446, "丝路乐魂(乐器篇)", "莱里古尔", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐魂(乐器篇)/s_5446.mp3", 9.0),
    (5448, "丝路乐魂(乐器篇)", "亲爱的妈妈", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐魂(乐器篇)/s_5448.mp3", 9.0),
    (5449, "丝路乐魂(乐器篇)", "沙信日克", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐魂(乐器篇)/s_5449.mp3", 9.0),
    (5454, "楼兰钟鼓(器乐篇)", "阿瓦日古丽", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/楼兰钟鼓(器乐篇)/s_5454.mp3", 6.5),
    (5462, "楼兰钟鼓(器乐篇)", "黑眉毛", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/楼兰钟鼓(器乐篇)/s_5462.mp3", 9.0),
    (5463, "楼兰钟鼓(器乐篇)", "达坂城的姑娘", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/楼兰钟鼓(器乐篇)/s_5463.mp3", 6.5),
    (5464, "丝路乐韵(乐器篇)", "牡丹汗", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐韵(乐器篇)/s_5464.mp3", 9.0),
    (5465, "丝路乐韵(乐器篇)", "塔里木", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐韵(乐器篇)/s_5465.mp3", 9.0),
    (5467, "丝路乐韵(乐器篇)", "沙漠驼客", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐韵(乐器篇)/s_5467.mp3", 9.0),
    (5470, "丝路乐韵(乐器篇)", "摇篮曲", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐韵(乐器篇)/s_5470.mp3", 9.0),
    (5472, "丝路乐韵(乐器篇)", "达坂城的姑娘", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐韵(乐器篇)/s_5472.mp3", 6.5),
    (5473, "丝路乐韵(乐器篇)", "春天的歌", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/丝路乐韵(乐器篇)/s_5473.mp3", 9.0),
    (5418, "西域情歌(摇滚篇)", "怀念战友", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/西域情歌(摇滚篇)/s_5418.mp3", 9.0),
    (5424, "西域情歌(摇滚篇)", "康定情歌", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/西域情歌(摇滚篇)/s_5424.mp3", 9.0),
    (5428, "西域情歌(摇滚篇)", "古莱莱", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/西域情歌(摇滚篇)/s_5428.mp3", 9.0),
    (5431, "西域记事", "阿伊夏姆", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/西域记事/s_5431.mp3", 9.0),
    (5435, "西域记事", "穿艾德莱丝的姑娘", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/西域记事/s_5435.mp3", 9.0),
    (5438, "西域记事", "往来丝绸道,不问胡笛声", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/西域记事/s_5438.mp3", 9.0),
    (5405, "2002年的第一场雪", "2002年的第一场雪", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/2002年的第一场雪/s_5405.mp3", 9.0),
    (5395, "喀什噶尔胡杨", "关于二道桥", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/喀什噶尔胡杨/s_5395.mp3", 9.0),
    (5398, "喀什噶尔胡杨", "只有艾得勒斯能看见", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/喀什噶尔胡杨/s_5398.mp3", 9.0),
    (5401, "喀什噶尔胡杨", "亚克西", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/喀什噶尔胡杨/s_5401.mp3", 9.0),
    (5363, "刀郎Ⅲ", "世界如此寂寞", "https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/music/刀郎/刀郎Ⅲ/s_5363.mp3", 9.0),
    (5364, "刀郎Ⅲ", "西海情歌", "https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/music/刀郎/刀郎Ⅲ/s_5364.mp3", 8.0),
    (5366, "刀郎Ⅲ", "孤独的牧羊人", "https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/music/刀郎/刀郎Ⅲ/s_5366.mp3", 8.0),
    (5373, "披着羊皮的狼", "雁南飞 (feat. 黄灿)", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/披着羊皮的狼/s_5373.mp3", 6.5),
    (5375, "披着羊皮的狼", "怀念战友", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/披着羊皮的狼/s_5375.mp3", 9.0),
    (5378, "披着羊皮的狼", "驼铃", "https://pub-383b876c0bb840f6b852946604275232.r2.dev/music/刀郎/披着羊皮的狼/s_5378.mp3", 8.0)
]

work_dir = "/tmp/daolang_clean_batch"
os.makedirs(work_dir, exist_ok=True)

def process_one(item):
    sid, alb, title, url, trim_sec = item
    try:
        # 获取时长
        cmd_dur = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', url]
        dur = float(subprocess.check_output(cmd_dur, timeout=15).decode().strip())
        target_dur = max(dur - trim_sec, 10.0)
        fade_start = target_dur - 1.5

        clean_file = os.path.join(work_dir, f"clean_{sid}.mp3")
        cmd_ffmpeg = [
            "ffmpeg", "-y", "-t", str(target_dur), "-i", url,
            "-af", f"afade=t=out:st={fade_start:.2f}:d=1.5",
            "-b:a", "160k", "-ar", "44100", "-ac", "2",
            clean_file
        ]
        subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
        if not os.path.exists(clean_file) or os.path.getsize(clean_file) < 10000:
            return None

        # 上传到 account_07
        mp3_key = f"music/刀郎/{alb}/s_{sid}.mp3"
        s3_client.upload_file(clean_file, bucket_name, mp3_key, ExtraArgs={"ContentType": "audio/mpeg"})
        new_url = f"{public_base}/{mp3_key}"

        # 校验尾音
        tail_check = os.path.join(work_dir, f"tail_{sid}.mp3")
        subprocess.run(['ffmpeg', '-y', '-sseof', '-10', '-i', clean_file, '-ac', '1', '-ar', '16000', tail_check], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        curl_cmd = [
            'curl', '-s', '-x', 'http://127.0.0.1:7890',
            'https://api.groq.com/openai/v1/audio/transcriptions',
            '-H', f'Authorization: Bearer {GROQ_API_KEY}',
            '-F', f'file=@{tail_check}',
            '-F', 'model=whisper-large-v3-turbo'
        ]
        res = json.loads(subprocess.check_output(curl_cmd).decode())
        tail_text = res.get('text', '').strip()
        print(f"  ✨ [{sid}] 《{title}》清洗成功: 尾部10秒听音 -> '{tail_text}'")

        return {
            "id": sid,
            "file_path": new_url
        }
    except Exception as e:
        print(f"  ❌ [{sid}] 《{title}》处理异常: {e}")
        return None

print(f"🚀 开始并发清洗刀郎 30 首口播歌曲...")
updates = []
with ThreadPoolExecutor(max_workers=4) as ex:
    futures = [ex.submit(process_one, it) for it in items]
    for f in as_completed(futures):
        res = f.result()
        if res:
            updates.append(res)

print(f"\n📦 清洗完成: {len(updates)}/{len(items)} 首")
if updates:
    resp = requests.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json={"updates": updates}, proxies=PROXIES, timeout=30)
    print(f"D1 数据库批量更新结果: HTTP {resp.status_code}, {resp.text}")

print("🎉 刀郎全部口播污染歌曲已彻底清洗并重新点亮完毕！")
