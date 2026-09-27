import subprocess, json, sys
sys.stdout.reconfigure(encoding='utf-8')

tracks = [
    ("其实你不懂我的心", 195),
    ("让生命等候", 257),
    ("明天你是否依然爱我", 256),
    ("飞雪", 301),
    ("别离歌", 233),
    ("忘不了", 254),
    ("干燥花", 215),
    ("永远不要说放弃", 263),
    ("看不清的未来", 298),
    ("爱,让世界更美", 226),
    ("扑克先生", 259),
    ("灯", 214)
]

for title, exp_dur in tracks:
    q = f"童安格 {title} 1989"
    cmd = ['yt-dlp', '--proxy', 'http://127.0.0.1:10090', '--dump-json', f'ytsearch2:{q}']
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(f"=== {title} (预计 {exp_dur}s) ===")
    if res.stdout:
        for line in res.stdout.strip().split('\n'):
            if line.strip():
                try:
                    d = json.loads(line)
                    print(f"  {d.get('id')} | {d.get('title')} | {d.get('duration')}s")
                except Exception:
                    pass
