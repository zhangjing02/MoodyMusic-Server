import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

songs = [
    ("相对的失去 (钢琴版)", "江美琪 相对的失去 钢琴版"),
    ("I'm O.K.谢谢", "江美琪 I'm O.K. 谢谢"),
    ("你不公平", "江美琪 你不公平"),
    ("黑色的翅膀", "江美琪 黑色的翅膀"),
    ("朋友的朋友", "江美琪 朋友的朋友"),
    ("You're In Love", "江美琪 You're In Love"),
    ("退一步伤心", "江美琪 退一步伤心"),
    ("紫色蝴蝶", "江美琪 紫色蝴蝶"),
    ("相对的失去 (吉他版)", "江美琪 相对的失去 吉他版"),
    ("就这样一辈子", "江美琪 就这样一辈子"),
    ("少林传奇", "江美琪 少林传奇")
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
