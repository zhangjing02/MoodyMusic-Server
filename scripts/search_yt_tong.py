import subprocess
import json

def search_yt(query, limit=5):
    print(f"=== Searching: {query} ===")
    cmd = ['yt-dlp', '--proxy', 'http://127.0.0.1:10090', '--dump-json', '--flat-playlist', f'ytsearch{limit}:{query}']
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    for line in res.stdout.strip().split('\n'):
        if line:
            try:
                data = json.loads(line)
                print(f"  {data.get('id')} | {data.get('title')} | {data.get('duration')}s | {data.get('uploader')}")
            except Exception as e:
                pass

if __name__ == '__main__':
    search_yt("童安格 花瓣雨 专辑", 5)
    search_yt("童安格 把根留住 官方", 3)
    search_yt("童安格 梦开始的地方 专辑", 5)
    search_yt("童安格 耶利亚女郎 官方", 3)
