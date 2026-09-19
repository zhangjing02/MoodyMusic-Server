import json
import subprocess
import tempfile
import os
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

with open('/tmp/mayday_all_songs.json', 'r', encoding='utf-8') as f:
    all_songs = json.load(f)

# 挑选代表性主打歌曲
sample_targets = [
    ("愛情萬歲", "溫柔"),
    ("愛情萬歲", "終結孤單"),
    ("人生海海", "人生海海"),
    ("人生海海", "純真"),
    ("時光機", "時光機"),
    ("時光機", "恆星的恆心"),
    ("神的孩子都在跳舞", "倔強"),
    ("神的孩子都在跳舞", "孫悟空"),
    ("知足 just my pride 最真傑作選", "知足"),
    ("知足 just my pride 最真傑作選", "戀愛ing"),
    ("為愛而生", "天使"),
    ("為愛而生", "為愛而生"),
    ("離開地球表面", "離開地球表面"),
    ("離開地球表面", "私奔到月球"),
    ("後青春期的詩", "突然好想你"),
    ("後青春期的詩", "你不是真正的快樂"),
    ("第二人生 (明日版)", "星空"),
    ("第二人生 (明日版)", "諾亞方舟"),
    ("自传", "派對動物"),
    ("自传", "後來的我們")
]

target_map = {}
for s in all_songs:
    k = (s['album'], s['title'])
    target_map[k] = s

print(f"🔍 开始抽样探测 {len(sample_targets)} 首五月天核心主打歌曲...")

for alb, title in sample_targets:
    item = target_map.get((alb, title))
    if not item:
        # 模糊匹配
        for (a, t), v in target_map.items():
            if alb in a and title in t:
                item = v
                break
    if not item:
        print(f"⚠️ 未找到: 《{alb}》- 《{title}》")
        continue

    path = item['path']
    if not path.startswith('http'):
        url = f"https://m-api.changgepd.ccwu.cc/storage/{path.lstrip('/')}"
    else:
        url = path

    # 1. 截取前奏 (0~25s) 检查是否有观众尖叫、现场欢呼、报幕
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_head:
        p_head = tmp_head.name
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_vocal:
        p_vocal = tmp_vocal.name

    try:
        subprocess.run(['ffmpeg', '-y', '-ss', '0', '-t', '20', '-i', url, '-ac', '1', '-ar', '16000', p_head], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
        subprocess.run(['ffmpeg', '-y', '-ss', '35', '-t', '25', '-i', url, '-ac', '1', '-ar', '16000', p_vocal], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)

        # 听辨前奏
        curl_cmd1 = [
            'curl', '-s', '-x', 'http://127.0.0.1:7890',
            'https://api.groq.com/openai/v1/audio/transcriptions',
            '-H', f'Authorization: Bearer {GROQ_API_KEY}',
            '-F', f'file=@{p_head}',
            '-F', 'model=whisper-large-v3-turbo'
        ]
        res1 = json.loads(subprocess.check_output(curl_cmd1).decode()).get('text', '').strip()

        # 听辨人声
        curl_cmd2 = [
            'curl', '-s', '-x', 'http://127.0.0.1:7890',
            'https://api.groq.com/openai/v1/audio/transcriptions',
            '-H', f'Authorization: Bearer {GROQ_API_KEY}',
            '-F', f'file=@{p_vocal}',
            '-F', 'model=whisper-large-v3-turbo'
        ]
        res2 = json.loads(subprocess.check_output(curl_cmd2).decode()).get('text', '').strip()

        is_live = any(w in res1 for w in ["尖叫", "欢呼", "掌声", "现场", "大家", "晚安", "Live", "live", "演唱会"]) or \
                  any(w in res2 for w in ["尖叫", "欢呼", "掌声", "现场", "大家", "一起唱", "后面的朋友"])
        
        is_wrong_artist = "李宗盛" in res1 or "李宗盛" in res2

        status_tag = "✅ 正常录音室"
        if is_wrong_artist:
            status_tag = "🚨 严重错误(李宗盛)"
        elif is_live:
            status_tag = "⚠️ 疑似演唱会Live版"

        print(f"{status_tag} | 《{alb}》- 《{title}》")
        print(f"   前奏听音: '{res1[:40]}'")
        print(f"   人声听音: '{res2[:50]}'")
    except Exception as e:
        print(f"❌ 探测出错 《{title}》: {e}")
    finally:
        if os.path.exists(p_head): os.remove(p_head)
        if os.path.exists(p_vocal): os.remove(p_vocal)

