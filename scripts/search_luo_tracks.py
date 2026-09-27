import subprocess
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

songs = [
    '鹿港小鎮', '戀曲1980', '童年', '錯誤', '搖籃曲',
    '之乎者也', '鄉愁四韻', '將進酒', '光陰的故事', '蒲公英'
]

for s in songs:
    cmd = ['yt-dlp', '--proxy', 'http://127.0.0.1:10090', '--dump-json', f'ytsearch3:羅大佑 {s} 滾石唱片 Official']
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f"=== {s} ===")
    if res.stdout:
        for line in res.stdout.strip().split('\n'):
            if line.strip():
                try:
                    d = json.loads(line)
                    title = d.get('title')
                    channel = d.get('channel')
                    dur = d.get('duration')
                    vid = d.get('id')
                    print(f"  [{vid}] {dur}s | {channel} | {title}")
                except:
                    pass
