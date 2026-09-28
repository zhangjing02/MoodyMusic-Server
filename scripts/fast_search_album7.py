import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

songs = [
    ("May I", "江美琪 May I"),
    ("不速之客", "江美琪 不速之客"),
    ("爱哭鬼", "江美琪 爱哭鬼"),
    ("妹妹", "江美琪 妹妹 爱哭鬼"),
    ("生日快乐", "江美琪 生日快乐"),
    ("你呀...你呀", "江美琪 你呀你呀"),
    ("塔罗牌恋人", "江美琪 塔罗牌恋人"),
    ("路人", "江美琪 路人"),
    ("我的他", "江美琪 我的他"),
    ("对你有感觉", "江美琪 光良 对你有感觉")
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
