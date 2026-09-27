import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

domain = 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev'

print('=== 检查专辑 745《家》(1984) ===')
songs_745 = [
    (27032, '吾乡印象'), (27033, '家 (I)'), (27034, '超级市民'), (27035, '青蚵嫂'),
    (27036, '家 (II)'), (27037, '我所不能了解的事'), (27038, '穿过你的黑发的我的手'),
    (27039, 'Mysterious Eyes'), (27040, '耶稣的另一个名字')
]
for sid, t in songs_745:
    url = f'{domain}/music/%E7%BD%97%E5%A4%A7%E4%BD%91/%E5%AE%B6/s_{sid}.mp3'
    try:
        r = requests.head(url, timeout=5)
        cl = r.headers.get("Content-Length", "0")
        print(f"  [{sid}] 《{t}》: HTTP {r.status_code} | {cl} bytes")
    except Exception as e:
        print(f"  [{sid}] 《{t}》: {e}")

print('\n=== 检查专辑 759《爱人同志》(1988) ===')
songs_759 = [
    (10393, '暗恋'), (10394, '恋曲1990'), (10395, '爱人同志'), (10396, '你的样子'),
    (10397, '梦'), (10398, '黄色脸孔'), (10399, '京城夜'), (10400, '明天的太阳'),
    (10401, '游戏规则'), (10402, '不变的结局')
]
for sid, t in songs_759:
    url = f'{domain}/music/%E7%BD%97%E5%A4%A7%E4%BD%91/%E6%84%9B%E4%BA%BA%E5%90%8C%E5%BF%97/s_{sid}.mp3'
    try:
        r = requests.head(url, timeout=5)
        cl = r.headers.get("Content-Length", "0")
        print(f"  [{sid}] 《{t}》: HTTP {r.status_code} | {cl} bytes")
    except Exception as e:
        print(f"  [{sid}] 《{t}》: {e}")
