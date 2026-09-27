import os
import sys
import requests
import subprocess

sys.stdout.reconfigure(encoding='utf-8')
mp3_path = 'backend/tmp/fish_date_raw.mp3'

for start in [20, 24, 27, 28]:
    clip = f'backend/tmp/test_{start}.mp3'
    subprocess.run(['ffmpeg', '-y', '-ss', str(start), '-i', mp3_path, '-t', '6', '-c', 'copy', clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(clip, 'rb') as f:
        r = requests.post(
            'https://api.groq.com/openai/v1/audio/transcriptions',
            headers={'Authorization': f'Bearer {os.environ.get("GROQ_API_KEY")}'},
            files={'file': ('clip.mp3', f, 'audio/mpeg'), 'model': (None, 'whisper-large-v3'), 'temperature': (None, '0.0')},
            proxies={'http': 'http://127.0.0.1:10090', 'https': 'http://127.0.0.1:10090'},
            timeout=30
        )
    print(f'Start at {start}s (6s long):', r.json().get('text') if r.ok else r.text)
