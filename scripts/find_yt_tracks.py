import subprocess
import json

tracks_hua = [
    ("花瓣雨", 150895, 202),
    ("你我的爱只能擦肩而过", 150898, 251),
    ("晚归的丈夫", 150900, 248),
    ("那一段日子", 150902, 214),
    ("把根留住", 150467, 280),
    ("尘埃", 150907, 232),
    ("爱情终究是一场难圆的梦", 150910, 245),
    ("无所谓的歌", 150913, 289),
    ("香水城", 150916, 237),
    ("爱的主题曲", 150918, 211),
    ("跨过彩虹", 150920, 238)
]

for t, nid, exp_dur in tracks_hua:
    query = f"ytsearch1:童安格 {t}"
    cmd = ['yt-dlp', '--proxy', 'http://127.0.0.1:10090', '--dump-json', '--flat-playlist', query]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    line = res.stdout.strip()
    if line:
        data = json.loads(line)
        y_id = data.get('id')
        dur = data.get('duration')
        title = data.get('title')
        print(f'{{"title": "{t}", "yt_id": "{y_id}", "netease_id": {nid}, "exp_dur": {exp_dur}}},  # {title} ({dur}s)')
    else:
        print(f'# {t} Not found')
