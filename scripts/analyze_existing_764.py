import os
import sys
import subprocess
import json
import requests

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

key = os.environ.get('GROQ_API_KEY')
proxies = {'http': 'http://127.0.0.1:10090', 'https': 'http://127.0.0.1:10090'}

print("=== 正在对当前 10 首曲目进行深度质检与版本分析 ===")

for sid, title in songs:
    mp3_p = f'backend/tmp/inspect_764/s_{sid}.mp3'
    if not os.path.exists(mp3_p):
        continue
    
    # 截取前 30s 与中间 30s
    clip_start = f'backend/tmp/inspect_764/s_{sid}_start.mp3'
    clip_mid = f'backend/tmp/inspect_764/s_{sid}_mid.mp3'
    
    subprocess.run(['ffmpeg', '-y', '-ss', '0', '-i', mp3_p, '-t', '25', '-c', 'copy', clip_start], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['ffmpeg', '-y', '-ss', '60', '-i', mp3_p, '-t', '25', '-c', 'copy', clip_mid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 调用 Whisper
    def whisper_text(clip):
        try:
            with open(clip, 'rb') as fp:
                r = requests.post(
                    'https://api.groq.com/openai/v1/audio/transcriptions',
                    headers={'Authorization': f'Bearer {key}'},
                    files={'file': ('clip.mp3', fp, 'audio/mpeg'), 'model': (None, 'whisper-large-v3'), 'temperature': (None, '0.0')},
                    proxies=proxies,
                    timeout=20
                )
                if r.ok:
                    return r.json().get('text', '')
        except Exception as e:
            return str(e)
        return ""

    t_start = whisper_text(clip_start)
    t_mid = whisper_text(clip_mid)
    print(f"[{sid}] 《{title}》:")
    print(f"   前奏/开唱 (0-25s): {t_start}")
    print(f"   中段人声 (60-85s): {t_mid}")
