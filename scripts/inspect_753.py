import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

domain = 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev'

print('=== 检查专辑 753《恋曲2000》(1994) 当前音频 ===')
songs_753 = [
    (27053, '东风'), (27054, '就这么样吧'), (27055, '五十块钱'), (27056, '情丝'),
    (27057, '上海之夜'), (27058, '蓝'), (27059, '台北红玫瑰'), (27060, '天雨'),
    (27061, '倒影'), (27062, '恋曲2000')
]
for sid, t in songs_753:
    url = f'{domain}/music/%E7%BD%97%E5%A4%A7%E4%BD%91/%E6%81%8B%E6%9B%B22000/s_{sid}.mp3'
    try:
        r = requests.head(url, timeout=5)
        cl = r.headers.get("Content-Length", "0")
        print(f"  [{sid}] 《{t}》: HTTP {r.status_code} | {cl} bytes")
    except Exception as e:
        print(f"  [{sid}] 《{t}》: {e}")
