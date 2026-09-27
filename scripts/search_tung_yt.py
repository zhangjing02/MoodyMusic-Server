import subprocess, json, sys
sys.stdout.reconfigure(encoding='utf-8')

queries = [
    '童安格 其实你不懂我的心 完整专辑 1989',
    '童安格 花瓣雨 完整专辑 1990',
    '童安格 梦开始的地方 完整专辑 1989',
    '童安格 一世情缘 完整专辑 1991',
    '童安格 其实你不懂我的心 专辑 全碟',
    '童安格 花瓣雨 专辑 全碟',
    '童安格 经典 专辑 宝丽金'
]

for q in queries:
    print(f"=== Query: {q} ===")
    cmd = ['yt-dlp', '--proxy', 'http://127.0.0.1:10090', '--dump-json', f'ytsearch3:{q}']
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if res.stdout:
        for line in res.stdout.strip().split('\n'):
            if line.strip():
                try:
                    d = json.loads(line)
                    print(f"  {d.get('id')} | {d.get('title')} | {d.get('duration')}s")
                except Exception:
                    pass
