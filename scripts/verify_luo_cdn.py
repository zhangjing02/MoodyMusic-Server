import requests
import sys
import urllib.parse

sys.stdout.reconfigure(encoding='utf-8')

b10_domain = 'https://pub-9e5d39f15e4a40dfb886ecb275551c90.r2.dev'

TRACKS = [
    (27012, '鹿港小镇'), (27013, '恋曲1980'), (27014, '童年'), (27015, '错误'), (27016, '摇篮曲'),
    (27017, '之乎者也'), (27018, '乡愁四韵'), (27019, '将进酒'), (27020, '光阴的故事'), (27021, '蒲公英')
]

print("=== 抽验 1982《之乎者也》全专辑 10 首曲目公网 CDN 直链 ===")
all_ok = True
for sid, title in TRACKS:
    key_mp3 = f"music/罗大佑/之乎者也/s_{sid}.mp3"
    key_lrc = f"lyrics/罗大佑/之乎者也/s_{sid}.lrc"
    
    url_mp3 = f"{b10_domain}/{urllib.parse.quote(key_mp3)}"
    url_lrc = f"{b10_domain}/{urllib.parse.quote(key_lrc)}"
    
    r_mp3 = requests.head(url_mp3, headers={'User-Agent': 'Mozilla/5.0'}, proxies={'http': None, 'https': None}, timeout=10)
    r_lrc = requests.get(url_lrc, headers={'User-Agent': 'Mozilla/5.0'}, proxies={'http': None, 'https': None}, timeout=10)
    
    mp3_ok = (r_mp3.status_code == 200)
    lrc_ok = (r_lrc.status_code == 200)
    if not (mp3_ok and lrc_ok):
        all_ok = False
        
    mp3_len = r_mp3.headers.get("Content-Length", "0")
    first_line = r_lrc.text.splitlines()[0] if r_lrc.ok and r_lrc.text.splitlines() else ""
    print(f"[{sid}] 《{title}》 | MP3: {r_mp3.status_code} ({mp3_len} bytes) | LRC: {r_lrc.status_code} ({len(r_lrc.content)} bytes) | 首行: {first_line}")

print(f"\n全部 10 首曲目 CDN 校验结果: {'SUCCESS' if all_ok else 'FAILED'}")
