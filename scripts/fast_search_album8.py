import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

songs = [
    ("房间", "江美琪 房间 2012 官方"),
    ("爱笑的你", "江美琪 爱笑的你"),
    ("完美分手", "江美琪 完美分手"),
    ("你是爱我的", "江美琪 你是爱我的 房间"),
    ("晴空", "江美琪 晴空"),
    ("在一起多好", "江美琪 在一起多好"),
    ("爱情的重量", "江美琪 爱情的重量"),
    ("后天再说我爱你", "江美琪 后天再说我爱你"),
    ("月光下", "江美琪 月光下 房间")
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
