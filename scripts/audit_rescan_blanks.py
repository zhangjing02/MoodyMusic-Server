import os
import sys
import json
import time
import requests
import subprocess
import tempfile

PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
GROQ_API_KEY = "GROQ_KEY_REMOVED"

with open('/tmp/mayday_audit_report.json', 'r', encoding='utf-8') as f:
    report = json.load(f)

# 找出 head_text 为空的曲目
blanks = [r for r in report if not r.get('head_text') and not r.get('tail_text')]
print(f"🔍 待复核曲目: 共 {len(blanks)} 首...")

def transcribe_with_retry(clip_path):
    cmd = [
        'curl', '-s', '--max-time', '20', '-x', 'http://127.0.0.1:7890',
        'https://api.groq.com/openai/v1/audio/transcriptions',
        '-H', f'Authorization: Bearer {GROQ_API_KEY}',
        '-F', f'file=@{clip_path}',
        '-F', 'model=whisper-large-v3-turbo'
    ]
    for _ in range(3):
        out = subprocess.check_output(cmd).decode()
        data = json.loads(out)
        if 'error' in data:
            time.sleep(1.5)
            continue
        return data.get('text', '').strip()
    return ''

new_polluted = []

for idx, item in enumerate(blanks, 1):
    url = item['url']
    alb = item['album']
    title = item['title']
    sid = item['id']

    print(f"[{idx}/{len(blanks)}] 正在复核: 《{alb}》- 《{title}》 (ID: {sid})...")
    
    # 截取前 20 秒
    head_clip = f"/tmp/re_head_{sid}.mp3"
    tail_clip = f"/tmp/re_tail_{sid}.mp3"
    
    ht = ""
    tt = ""
    try:
        # 用 ffmpeg 直接抓前 20 秒
        subprocess.run(['ffmpeg', '-y', '-ss', '0', '-t', '20', '-i', url, '-ac', '1', '-ar', '16000', head_clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if os.path.exists(head_clip) and os.path.getsize(head_clip) > 1000:
            ht = transcribe_with_retry(head_clip)

        # 检查是否包含台词/新闻/现场
        time.sleep(0.5)
    except Exception as e:
        print(f"   ⚠️ 探测异常: {e}")
    finally:
        if os.path.exists(head_clip): os.remove(head_clip)
        if os.path.exists(tail_clip): os.remove(tail_clip)

    item['head_text'] = ht
    
    is_pol = False
    reasons = []
    # 关键词匹配
    for w in ['小时候妈妈说', '相遇了', '面对着你们', '我愿意', '动新闻', '台北报道', '记者', '幸福的方向']:
        if w in ht:
            is_pol = True
            reasons.append(f"台词/播报({w})")
    for w in ['尖叫', '欢呼', '现场', '晚安', '演唱会']:
        if w in ht:
            is_pol = True
            reasons.append(f"现场音({w})")

    if is_pol:
        item['is_polluted'] = True
        item['pollute_reasons'] = reasons
        new_polluted.append(item)
        print(f"   🚨 发现污染！{reasons} | 听音: '{ht[:45]}'")
    else:
        print(f"   ✅ 正常 | 前奏听音: '{ht[:30]}'")

print(f"\n🎉 复核完成！新增污染曲目: {len(new_polluted)} 首")
with open('/tmp/mayday_rescan_polluted.json', 'w', encoding='utf-8') as f:
    json.dump(new_polluted, f, ensure_ascii=False, indent=2)
