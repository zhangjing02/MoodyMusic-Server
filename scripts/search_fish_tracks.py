import subprocess
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

cmd = ['yt-dlp', '--proxy', 'http://127.0.0.1:10090', '--dump-json', 'ytsearch5:梁靜茹 我和自己的約會 Sunrise 我喜歡']
res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
if res.stdout:
    for line in res.stdout.strip().split('\n'):
        if line.strip():
            d = json.loads(line)
            print(f"{d.get('id')} | {d.get('title')} | {d.get('channel')} | {d.get('duration')}s | {d.get('album')}")
