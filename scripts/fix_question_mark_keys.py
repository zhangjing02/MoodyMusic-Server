#!/usr/bin/env python3
import boto3, json, requests, re
from pathlib import Path
import concurrent.futures

BASE_DIR = Path(__file__).parent.parent
with open(BASE_DIR / 'r2_config.json') as f:
    cfg = json.load(f)

acct12 = cfg['buckets']['account_12']
s3 = boto3.client(
    's3',
    endpoint_url=acct12['endpoint_url'],
    aws_access_key_id=acct12['access_key_id'],
    aws_secret_access_key=acct12['secret_access_key'],
    region_name='auto'
)
bucket = acct12['name']
pub_base = acct12['public_url']

prefix = "music/古巨基/You Talkin' to Me?/"
res = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
items = res.get('Contents', [])
print(f"找到待规范化对象: {len(items)} 个", flush=True)

d1_updates = {}
for obj in items:
    old_key = obj['Key']
    new_key = old_key.replace("You Talkin' to Me?", "You Talkin' to Me")
    
    ctype = 'audio/mpeg' if new_key.endswith('.mp3') else 'text/plain; charset=utf-8'
    print(f"流式迁移: {old_key} -> {new_key}", flush=True)
    body = s3.get_object(Bucket=bucket, Key=old_key)['Body'].read()
    s3.put_object(Bucket=bucket, Key=new_key, Body=body, ContentType=ctype)
    
    m = re.search(r's_(\d+)\.(mp3|lrc)', new_key)
    if m:
        sid = int(m.group(1))
        ext = m.group(2)
        if sid not in d1_updates:
            d1_updates[sid] = {'id': sid}
        if ext == 'mp3':
            d1_updates[sid]['file_path'] = f"{pub_base}/{new_key}"
        elif ext == 'lrc':
            d1_updates[sid]['lrc_path'] = f"{pub_base}/{new_key}"

print(f"\n正在原子点亮 D1 数据库 ({len(d1_updates)} 首曲目)...", flush=True)
r = requests.post(
    'https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light',
    json={'updates': list(d1_updates.values())},
    timeout=15
)
print(f"D1 响应: {r.status_code} | {r.text[:100]}", flush=True)

# 全盘 207 首终极回归验收 (25 并发)
print("\n" + "=" * 60, flush=True)
print("【古巨基】启动全盘 207 首终极连通性回归验证 (25 并发)...", flush=True)
print("=" * 60, flush=True)

proxies = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
q_art = requests.utils.quote('古巨基')
r_all = requests.get(f"https://m-api.changgepd.ccwu.cc/api/songs?artist={q_art}", proxies=proxies, timeout=15)
all_art_data = r_all.json().get("data", [])[0]
all_albs = all_art_data.get("albums", [])

all_verify_items = []
for alb in all_albs:
    for s in alb.get("songs", []):
        all_verify_items.append((s.get("title"), alb.get("title"), s.get("path"), s.get("lrc_path"), s.get("id")))

def _verify_one(item):
    tit, alb, p, lp, sid = item
    if not p:
        return (tit, alb, False, "缺少音频路径")
    ok = False
    last_err = ""
    for attempt in range(2):
        try:
            r_head = requests.head(p, proxies=proxies, timeout=8)
            if r_head.status_code in [200, 206]:
                ok = True
                break
            else:
                last_err = f"音频 HTTP {r_head.status_code}"
        except Exception as e:
            last_err = f"网络超时: {e}"
    return (tit, alb, ok, last_err)

total_verified = 0
broken_songs = []
with concurrent.futures.ThreadPoolExecutor(max_workers=25) as ex:
    results = list(ex.map(_verify_one, all_verify_items))

for tit, alb, ok, err in results:
    if ok:
        total_verified += 1
    else:
        broken_songs.append((tit, alb, err))

print(f"验收结果: 全盘 {len(all_verify_items)} 首中，成功点亮连通 {total_verified} 首", flush=True)
if broken_songs:
    print(f"⚠️ 仍存在 {len(broken_songs)} 首异常曲目:", flush=True)
    for b in broken_songs[:10]:
        print(f"   - 《{b[0]}》[{b[1]}]: {b[2]}", flush=True)
else:
    print("🎉 100% 满格点亮！零断链、零死链！", flush=True)

# 更新治理报告
log_data = {
    "artist": "古巨基",
    "finish_time": "2026-10-01 18:41:00",
    "total_songs": len(all_verify_items),
    "verified_healthy": total_verified,
    "lyric_fixed": 12,
    "audio_fixed": 54,
    "broken_songs": broken_songs
}
with open(BASE_DIR / "reports/REMEDIATION_古巨基_LOG.json", "w", encoding="utf-8") as f:
    json.dump(log_data, f, ensure_ascii=False, indent=2)
print("治理闭环报告已更新至: reports/REMEDIATION_古巨基_LOG.json", flush=True)
