import requests
import sys
import urllib.parse
import subprocess
import os

sys.stdout.reconfigure(encoding='utf-8')

songs = [
    (27012, '鹿港小镇'),
    (27013, '恋曲1980'),
    (27014, '童年'),
    (27015, '错误'),
    (27016, '摇篮曲'),
    (27017, '之乎者也'),
    (27018, '乡愁四韵'),
    (27019, '将进酒'),
    (27020, '光阴的故事'),
    (27021, '蒲公英')
]

domain = 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev'
os.makedirs('backend/tmp/inspect_764', exist_ok=True)

for sid, title in songs:
    key = f'music/罗大佑/之乎者也/s_{sid}.mp3'
    enc_key = urllib.parse.quote(key)
    url = f'{domain}/{enc_key}'
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            tmp_p = f'backend/tmp/inspect_764/s_{sid}.mp3'
            with open(tmp_p, 'wb') as fp:
                fp.write(r.content)
            # ffprobe duration
            out = subprocess.check_output(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', tmp_p]).decode().strip()
            dur = float(out)
            print(f"[{sid}] 《{title}》: {len(r.content)} bytes, 时长: {dur:.2f}s ({dur/60:.2f}min)")
        else:
            print(f"[{sid}] 《{title}》: HTTP {r.status_code}")
    except Exception as e:
        print(f"[{sid}] 《{title}》: Err {e}")
