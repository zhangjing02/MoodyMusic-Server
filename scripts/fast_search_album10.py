import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

songs = [
    ("伤心唱出来就没事了", "江美琪 伤心唱出来就没事了"),
    ("圆的圆的", "江美琪 圆的圆的"),
    ("天真有爱", "江美琪 天真有爱"),
    ("走到哪都下着雨 (feat. 郑兴)", "江美琪 郑兴 走到哪都下着雨"),
    ("坏习惯", "江美琪 坏习惯 2024"),
    ("关于失去", "江美琪 关于失去"),
    ("低速公路", "江美琪 低速公路"),
    ("鱼缸 (feat. 椅子乐团)", "江美琪 椅子乐团 鱼缸"),
    ("白饭", "江美琪 白饭 官方"),
    ("幸福有如平常一日", "江美琪 幸福有如平常一日")
]

for title, q in songs:
    cmd = [
        "yt-dlp",
        "--js-runtimes", r"node:D:\DevelopeTools\Node\node.exe",
        f"ytsearch1:{q}",
        "--get-id",
        "--get-title"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    lines = [l.strip() for l in res.stdout.strip().split('\n') if l.strip()]
    if len(lines) >= 2:
        vid_id = lines[1]
        vid_title = lines[0]
        print(f"'{title}': 'https://www.youtube.com/watch?v={vid_id}', # {vid_title}", flush=True)
    elif len(lines) == 1:
        print(f"'{title}': 'https://www.youtube.com/watch?v={lines[0]}',", flush=True)
    else:
        print(f"FAILED: {title}", flush=True)
