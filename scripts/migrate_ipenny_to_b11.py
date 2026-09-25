import boto3
from botocore.config import Config
import json
import urllib.parse
import urllib.request
import requests
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = 'e:/Workspace/AI-Project/MoodyMusic-Workspace'
CONFIG_PATH = f'{BASE_DIR}/backend/r2_config.json'
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    cfg = json.load(f)['buckets']

s3_02 = boto3.client(
    's3',
    endpoint_url=cfg['account_02']['endpoint_url'],
    aws_access_key_id=cfg['account_02']['access_key_id'],
    aws_secret_access_key=cfg['account_02']['secret_access_key'],
    config=Config(signature_version='s3v4')
)

s3_09 = boto3.client(
    's3',
    endpoint_url=cfg['account_09']['endpoint_url'],
    aws_access_key_id=cfg['account_09']['access_key_id'],
    aws_secret_access_key=cfg['account_09']['secret_access_key'],
    config=Config(signature_version='s3v4')
)

s3_11 = boto3.client(
    's3',
    endpoint_url=cfg['account_11']['endpoint_url'],
    aws_access_key_id=cfg['account_11']['access_key_id'],
    aws_secret_access_key=cfg['account_11']['secret_access_key'],
    config=Config(signature_version='s3v4')
)

b02_name = cfg['account_02']['name']
b09_name = cfg['account_09']['name']
b11_name = cfg['account_11']['name']
b11_domain = cfg['account_11']['public_domain'].rstrip('/')

print("=== Step 1: Streaming objects from B02/B09 to Bucket 11 ===")
updates = []
for sid in range(5135, 5145):
    key_mp3 = f"music/戴佩妮/iPenny/s_{sid}.mp3"
    key_lrc = f"lyrics/戴佩妮/iPenny/s_{sid}.lrc"

    # 1. MP3
    try:
        head_11_mp3 = s3_11.head_object(Bucket=b11_name, Key=key_mp3)
        print(f"  • Already uploaded MP3: {key_mp3} ({head_11_mp3['ContentLength']} bytes)")
    except Exception:
        obj_mp3 = s3_02.get_object(Bucket=b02_name, Key=key_mp3)
        data_mp3 = obj_mp3['Body'].read()
        s3_11.put_object(
            Bucket=b11_name,
            Key=key_mp3,
            Body=data_mp3,
            ContentType='audio/mpeg'
        )
        head_11_mp3 = s3_11.head_object(Bucket=b11_name, Key=key_mp3)
        assert head_11_mp3['ContentLength'] == len(data_mp3), f"Size mismatch for {key_mp3}"
        print(f"  • Uploaded MP3: {key_mp3} ({len(data_mp3)} bytes)")

    # 2. LRC
    try:
        head_11_lrc = s3_11.head_object(Bucket=b11_name, Key=key_lrc)
        print(f"  • Already uploaded LRC: {key_lrc} ({head_11_lrc['ContentLength']} bytes)")
    except Exception:
        obj_lrc = s3_09.get_object(Bucket=b09_name, Key=key_lrc)
        data_lrc = obj_lrc['Body'].read()
        s3_11.put_object(
            Bucket=b11_name,
            Key=key_lrc,
            Body=data_lrc,
            ContentType='text/plain; charset=utf-8'
        )
        head_11_lrc = s3_11.head_object(Bucket=b11_name, Key=key_lrc)
        assert head_11_lrc['ContentLength'] == len(data_lrc), f"Size mismatch for {key_lrc}"
        print(f"  • Uploaded LRC: {key_lrc} ({len(data_lrc)} bytes)")

    # Standard percent-encoded CDN URLs
    enc_artist = urllib.parse.quote("戴佩妮")
    cdn_mp3 = f"{b11_domain}/music/{enc_artist}/iPenny/s_{sid}.mp3"
    cdn_lrc = f"{b11_domain}/lyrics/{enc_artist}/iPenny/s_{sid}.lrc"

    updates.append({
        "id": sid,
        "file_path": cdn_mp3,
        "lrc_path": cdn_lrc,
        "is_lit": 1
    })

print("\n=== Step 2: Verifying CDN Public Endpoints ===")
for u in updates:
    # Check MP3 with retry
    for attempt in range(5):
        try:
            req = urllib.request.Request(u["file_path"], headers={'User-Agent': 'Mozilla/5.0', 'Origin': 'https://changgepd.ccwu.cc'})
            with urllib.request.urlopen(req) as resp:
                if resp.status == 200:
                    cors = resp.headers.get('Access-Control-Allow-Origin')
                    cl = resp.headers.get('Content-Length')
                    print(f"  Verified CDN MP3 s_{u['id']}: 200 OK, Content-Length: {cl}, CORS: {cors}")
                    break
        except Exception as e:
            if attempt == 4:
                raise e
            time.sleep(1.5)

    # Check LRC with retry
    for attempt in range(5):
        try:
            req_lrc = urllib.request.Request(u["lrc_path"], headers={'User-Agent': 'Mozilla/5.0', 'Origin': 'https://changgepd.ccwu.cc'})
            with urllib.request.urlopen(req_lrc) as resp_lrc:
                if resp_lrc.status == 200:
                    cl_lrc = resp_lrc.headers.get('Content-Length')
                    print(f"  Verified CDN LRC s_{u['id']}: 200 OK, Content-Length: {cl_lrc}")
                    break
        except Exception as e:
            if attempt == 4:
                raise e
            time.sleep(1.5)

print("\n=== Step 3: Updating Cloudflare D1 via batch-light ===")
res = requests.post(
    D1_LIGHT_URL,
    json={"updates": updates},
    proxies={'http': None, 'https': None},
    timeout=15
)
print(f"D1 response: {res.status_code}, {res.text}")
assert res.status_code == 200 and ('"code":200' in res.text or '"code": 200' in res.text)

print("\n=== Step 4: Updating Local catalog_sync.db ===")
conn = sqlite3.connect(f'{BASE_DIR}/backend/database/catalog_sync.db')
c = conn.cursor()
for u in updates:
    c.execute("UPDATE songs SET file_path = ?, lrc_path = ? WHERE id = ?", (u["file_path"], u["lrc_path"], u["id"]))

# Also sync the other 6 Penny albums into catalog_sync.db so local matches cloud exactly
res_all = requests.get('https://m-api.changgepd.ccwu.cc/api/songs?artistId=17', proxies={'http': None, 'https': None}, timeout=15)
cloud_data = res_all.json()
for art in cloud_data.get('data', []):
    for alb in art.get('albums', []):
        for s in alb.get('songs', []):
            if s.get('path'):
                c.execute("""
                    UPDATE songs 
                    SET file_path = ?, lrc_path = ?
                    WHERE artist_id = 17 AND title = ? AND (file_path IS NULL OR file_path = '')
                """, (s.get('path'), s.get('lrc_path'), s.get('title')))

conn.commit()
conn.close()
print("Local database updated successfully!")

print("\n=== Step 5: Deleting old MP3s from Bucket 02 ===")
for sid in range(5135, 5145):
    key_mp3 = f"music/戴佩妮/iPenny/s_{sid}.mp3"
    s3_02.delete_object(Bucket=b02_name, Key=key_mp3)
    print(f"  • Deleted old object from B02: {key_mp3}")

print("\n✅ Migration of iPenny to Bucket 11 completed 100% flawlessly!")
