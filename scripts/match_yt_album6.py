import subprocess
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

songs = [
    ("娃娃", "江美琪 娃娃 恋人心中有一首诗"),
    ("晴天娃娃", "江美琪 晴天娃娃"),
    ("Changll", "江美琪 Chagall"),
    ("我爱夏卡尔", "江美琪 我爱夏卡尔"),
    ("情书", "江美琪 情书 恋人心中有一首诗"),
    ("那年的情书", "江美琪 那年的情书"),
    ("谁还相信", "江美琪 谁还相信"),
    ("是否这就是爱情", "江美琪 是否这就是爱情"),
    ("不辣", "江美琪 不辣 恋人心中有一首诗"),
    ("芥末不辣", "江美琪 芥末不辣")
]

results = []
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
        print(f"MATCH: {title} -> https://www.youtube.com/watch?v={vid_id} | {vid_title}")
        results.append((title, f"https://www.youtube.com/watch?v={vid_id}"))
    else:
        print(f"FAILED: {title} -> {res.stderr[:200]}")

print("\n--- JSON OUTPUT ---")
print(json.dumps(results, ensure_ascii=False, indent=2))
