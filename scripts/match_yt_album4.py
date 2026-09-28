import subprocess
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

songs = [
    ("夜的诗人", "江美琪 夜的诗人"),
    ("再一次也好 (Romantic 浪漫版)", "江美琪 再一次也好 浪漫版"),
    ("挥霍爱人的耐性", "江美琪 挥霍爱人的耐性"),
    ("留在谁的心里", "江美琪 留在谁的心里"),
    ("缓慢的爱", "江美琪 缓慢的爱"),
    ("再一次也好 (Acoustic 纯情版)", "江美琪 再一次也好 纯情版"),
    ("东京铁塔的幸福", "江美琪 东京铁塔的幸福"),
    ("对你而言", "江美琪 对你而言"),
    ("海角天涯", "江美琪 海角天涯"),
    ("别在我离开你之前离开我", "江美琪 别在我离开你之前离开我"),
    ("Love Love", "江美琪 Love Love")
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
