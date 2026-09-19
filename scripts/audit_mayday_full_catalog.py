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

INPUT_JSON = '/tmp/mayday_all_songs.json'
OUTPUT_REPORT = '/tmp/mayday_audit_report.json'
OUTPUT_POLLUTED = '/tmp/mayday_polluted_songs.json'

with open(INPUT_JSON, 'r', encoding='utf-8') as f:
    all_songs = json.load(f)

print(f"🚀 启动五月天全量 {len(all_songs)} 首歌曲并发现场版/微电影对白审计...")

def audit_single_song(song):
    album = song['album']
    title = song['title']
    path = song['path']
    song_id = song.get('id')
    if not song_id and 's_' in path:
        try:
            song_id = int(path.split('s_')[-1].split('.')[0])
        except Exception:
            song_id = None

    if path.startswith('http'):
        url = path
    else:
        url = f"https://m-api.changgepd.ccwu.cc/storage/{path.lstrip('/')}"

    res_item = {
        "id": song_id,
        "album": album,
        "title": title,
        "path": path,
        "url": url,
        "head_text": "",
        "tail_text": "",
        "is_polluted": False,
        "pollute_reasons": []
    }

    head_clip = None
    tail_clip = None
    try:
        # 1. HEAD 请求探测 Content-Length
        try:
            h = requests.head(url, timeout=8, proxies=PROXIES if 'r2.dev' in url else None)
            cl = int(h.headers.get('content-length', 0))
        except Exception:
            cl = 0

        # 2. HTTP Range 取前 350KB
        r_head = requests.get(url, headers={'Range': 'bytes=0-358400'}, timeout=10, proxies=PROXIES if 'r2.dev' in url else None)
        if r_head.status_code in [200, 206] and len(r_head.content) > 5000:
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f_head_raw:
                f_head_raw.write(r_head.content)
                raw_head_path = f_head_raw.name

            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f_head_clip:
                head_clip = f_head_clip.name

            subprocess.run(['ffmpeg', '-y', '-i', raw_head_path, '-t', '18', '-ac', '1', '-ar', '16000', head_clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(raw_head_path):
                os.remove(raw_head_path)

            if os.path.exists(head_clip) and os.path.getsize(head_clip) > 1000:
                cmd = [
                    'curl', '-s', '--max-time', '15', '-x', 'http://127.0.0.1:7890',
                    'https://api.groq.com/openai/v1/audio/transcriptions',
                    '-H', f'Authorization: Bearer {GROQ_API_KEY}',
                    '-F', f'file=@{head_clip}',
                    '-F', 'model=whisper-large-v3-turbo'
                ]
                curl_out = subprocess.check_output(cmd).decode()
                res_item['head_text'] = json.loads(curl_out).get('text', '').strip()

        # 3. HTTP Range 取尾奏 350KB (若文件够大)
        if cl > 700000:
            start_b = max(0, cl - 358400)
            r_tail = requests.get(url, headers={'Range': f'bytes={start_b}-{cl-1}'}, timeout=10, proxies=PROXIES if 'r2.dev' in url else None)
            if r_tail.status_code in [200, 206] and len(r_tail.content) > 5000:
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f_tail_raw:
                    f_tail_raw.write(r_tail.content)
                    raw_tail_path = f_tail_raw.name

                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f_tail_clip:
                    tail_clip = f_tail_clip.name

                subprocess.run(['ffmpeg', '-y', '-i', raw_tail_path, '-ac', '1', '-ar', '16000', tail_clip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(raw_tail_path):
                    os.remove(raw_tail_path)

                if os.path.exists(tail_clip) and os.path.getsize(tail_clip) > 1000:
                    cmd_tail = [
                        'curl', '-s', '--max-time', '15', '-x', 'http://127.0.0.1:7890',
                        'https://api.groq.com/openai/v1/audio/transcriptions',
                        '-H', f'Authorization: Bearer {GROQ_API_KEY}',
                        '-F', f'file=@{tail_clip}',
                        '-F', 'model=whisper-large-v3-turbo'
                    ]
                    curl_out_tail = subprocess.check_output(cmd_tail).decode()
                    res_item['tail_text'] = json.loads(curl_out_tail).get('text', '').strip()

        # 4. 特征词匹配与污染判定
        ht = res_item['head_text']
        tt = res_item['tail_text']

        live_kw = ["尖叫", "欢呼", "掌声", "现场", "大家一起", "晚安", "Live", "live", "演唱会", "后面的朋友", "双手借给我"]
        mv_dialog_kw = ["相遇了", "面对着你们", "小时候妈妈说", "我是阿信", "我是怪兽", "电影院", "请看下集", "微电影"]

        # 前奏现场判断
        for kw in live_kw:
            if kw in ht:
                res_item['pollute_reasons'].append(f"前奏Live现场音({kw})")
                res_item['is_polluted'] = True
                break
        
        # 尾奏现场判断
        for kw in live_kw:
            if kw in tt:
                res_item['pollute_reasons'].append(f"尾奏Live现场音({kw})")
                res_item['is_polluted'] = True
                break

        # MV台词独白判断
        for kw in mv_dialog_kw:
            if kw in ht or kw in tt:
                res_item['pollute_reasons'].append(f"MV/微电影对白污染({kw})")
                res_item['is_polluted'] = True
                break

        # 长台词判断（前奏出现超过 25 字的陈述句，且不是歌词）
        if len(ht) > 25 and any(w in ht for w in ["于是我们", "那年", "时候", "我们开始", "记得"]):
            if "MV/微电影对白污染" not in str(res_item['pollute_reasons']):
                res_item['pollute_reasons'].append("疑似前奏剧情对白")
                res_item['is_polluted'] = True

    except Exception as e:
        res_item['error'] = str(e)
    finally:
        if head_clip and os.path.exists(head_clip): os.remove(head_clip)
        if tail_clip and os.path.exists(tail_clip): os.remove(tail_clip)

    return res_item

results = []
polluted = []

start_t = time.time()
with ThreadPoolExecutor(max_workers=6) as executor:
    futures = {executor.submit(audit_single_song, s): s for s in all_songs}
    completed_cnt = 0
    for fut in as_completed(futures):
        completed_cnt += 1
        res = fut.result()
        results.append(res)
        tag = "✅ 正常"
        if res['is_polluted']:
            polluted.append(res)
            tag = f"🚨 污染 ({','.join(res['pollute_reasons'])})"
        print(f"[{completed_cnt}/{len(all_songs)}] {tag} | 《{res['album']}》- 《{res['title']}》 (ID: {res['id']})")
        if res['head_text']:
            print(f"    前奏: '{res['head_text'][:40]}'")
        if res['tail_text']:
            print(f"    尾奏: '{res['tail_text'][:40]}'")

cost = time.time() - start_t
print("\n" + "=" * 80)
print(f"🎉 审计完成！共普查 {len(results)} 首，用时 {cost:.1f} 秒")
print(f"📊 发现污染音源: {len(polluted)} 首 (占比 {len(polluted)/len(results)*100:.1f}%)")
print("=" * 80)

with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

with open(OUTPUT_POLLUTED, 'w', encoding='utf-8') as f:
    json.dump(polluted, f, ensure_ascii=False, indent=2)

print(f"📁 报告已生成: {OUTPUT_REPORT}")
print(f"📁 待重采污染清单已写入: {OUTPUT_POLLUTED}")
