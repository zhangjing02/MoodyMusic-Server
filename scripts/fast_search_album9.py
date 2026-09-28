import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

songs = [
    ("陀螺", "江美琪 陀螺 官方"),
    ("成为我自己", "江美琪 成为我自己"),
    ("家珍", "江美琪 家珍"),
    ("三明治女孩", "江美琪 三明治女孩"),
    ("怎么了吗", "江美琪 怎么了吗"),
    ("不是时候", "江美琪 不是时候"),
    ("我们都是有歌的人", "江美琪 我们都是有歌的人 官方"),
    ("好胜心", "江美琪 好胜心"),
    ("遇不到 (Live)", "江美琪 遇不到 Live"),
    ("没有不可能 (Live)", "江美琪 没有不可能 Live")
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
