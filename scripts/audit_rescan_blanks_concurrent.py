import os
import sys
import json
import time
import requests
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
GROQ_API_KEY = "GROQ_KEY_REMOVED"

with open('/tmp/mayday_audit_report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)

blanks = [r for r in report if not r.get('head_text') and not r.get('tail_text')]
print(f"🚀 启动 4 线程并发复核 {len(blanks)} 首空白曲目...")

def check_song(item):
    url = item['url']
    sid = item['id']
    alb = item['album']
    title = item['title']
    
    # 截取前 400KB
    head_clip = f"/tmp/cf_head_{sid}.mp3"
    raw_head = f"/tmp/cf_raw_{sid}.mp3"
    
    ht = ""
    try:
        r = requests.get(url, headers={'Range': 'bytes=0-409600'}, timeout=8, proxies=PROXIES if 'r2.dev' in url else None)
        if r.status_code in [200, 206] and len(r.content) > 5000:
            with open(raw_head, 'wb') as f:
                f.write(r.content)
            subprocess.run(['ffmpeg', '-y', '-i', raw_head, '-t', '18', '-ac', '1', '-ar', '16000', head_clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(head_clip) and os.path.getsize(head_clip) > 1000:
                cmd = [
                    'curl', '-s', '--max-time', '15', '-x', 'http://127.0.0.1:7890',
                    'https://api.groq.com/openai/v1/audio/transcriptions',
                    '-H', f'Authorization: Bearer {GROQ_API_KEY}',
                    '-F', f'file=@{head_clip}',
                    '-F', 'model=whisper-large-v3-turbo'
                ]
                for attempt in range(3):
                    out = subprocess.check_output(cmd).decode()
                    data = json.loads(out)
                    if 'error' in data:
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    ht = data.get('text', '').strip()
                    break
    except Exception:
        pass
    finally:
        if os.path.exists(head_clip): os.remove(head_clip)
        if os.path.exists(raw_head): os.remove(raw_head)

    # 判定污染
    is_pol = False
    reasons = []
    for w in ['小时候妈妈说', '相遇了', '面对着你们', '我愿意', '动新闻', '台北报道', '记者', '幸福的方向', '对不起啊', '没关系啊']:
        if w in ht:
            is_pol = True
            reasons.append(f"剧情/台词({w})")
    for w in ['尖叫', '欢呼', '现场', '晚安', '演唱会', '大家一起', '后面的朋友']:
        if w in ht:
            is_pol = True
            reasons.append(f"现场音({w})")

    return {
        "id": sid,
        "album": alb,
        "title": title,
        "url": url,
        "path": item['path'],
        "head_text": ht,
        "is_polluted": is_pol,
        "pollute_reasons": reasons
    }

results = []
polluted = []

with ThreadPoolExecutor(max_workers=4) as pool:
    futs = {pool.submit(check_song, b): b for b in blanks}
    done = 0
    for f in as_completed(futs):
        done += 1
        res = f.result()
        results.append(res)
        if res['is_polluted']:
            polluted.append(res)
            print(f"[{done}/{len(blanks)}] 🚨 污染发现！《{res['album']}》- 《{res['title']}》 (ID: {res['id']}): {res['pollute_reasons']} | 听音: '{res['head_text'][:40]}'")
        else:
            if done % 10 == 0 or done == len(blanks):
                print(f"[{done}/{len(blanks)}] 进度更新... 最近: 《{res['album']}》- 《{res['title']}》: '{res['head_text'][:20]}'")

print("\n" + "=" * 80)
print(f"🎉 并发复核完成！复核曲目: {len(results)} 首，新增污染: {len(polluted)} 首")
for p in polluted:
    print(f"  - 《{p['album']}》- 《{p['title']}》 (ID: {p['id']}): {p['pollute_reasons']}")
print("=" * 80)

with open('/tmp/mayday_concurrent_polluted.json', 'w', encoding='utf-8') as f:
    json.dump(polluted, f, ensure_ascii=False, indent=2)
