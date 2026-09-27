import subprocess
import json

tracks_meng = [
    ("梦开始的地方", 1895403097, 286),
    ("借我一点爱", 1895402346, 237),
    ("水中的颜", 1895402347, 252),
    ("不要分离", 1895402348, 239),
    ("耶利亚女郎", 1895403098, 274),
    ("等我一起入梦", 1895402349, 336),
    ("今天的我", 1895402350, 246),
    ("给你一份惊喜", 1895403099, 263),
    ("日落之处", 1895403100, 258),
    ("我有多想你", 1895403101, 281)
]

for t, nid, exp_dur in tracks_meng:
    query = f"ytsearch1:童安格 {t}"
    cmd = ['yt-dlp', '--proxy', 'http://127.0.0.1:10090', '--dump-json', '--flat-playlist', query]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    line = res.stdout.strip()
    if line:
        try:
            data = json.loads(line)
            y_id = data.get('id')
            dur = data.get('duration')
            title = data.get('title')
            print(f'{{"title": "{t}", "yt_id": "{y_id}", "netease_id": {nid}, "exp_dur": {exp_dur}}},  # {title} ({dur}s)')
        except Exception:
            print(f'# Parse error for {t}')
    else:
        print(f'# {t} Not found')
