import boto3
import json
import sys
from botocore.config import Config

sys.stdout.reconfigure(encoding='utf-8')

with open('backend/r2_config.json', 'r', encoding='utf-8') as f:
    cfg = json.load(f)['buckets']

key_mp3 = 'music/梁静茹/Sunrise 我喜欢/s_26503.mp3'
key_lrc = 'lyrics/梁静茹/Sunrise 我喜欢/s_26503.lrc'

for b_id, b_info in cfg.items():
    try:
        s3 = boto3.client(
            's3',
            endpoint_url=b_info['endpoint_url'],
            aws_access_key_id=b_info['access_key_id'],
            aws_secret_access_key=b_info['secret_access_key'],
            config=Config(signature_version='s3v4')
        )
        try:
            head_mp3 = s3.head_object(Bucket=b_info['name'], Key=key_mp3)
            print(f"[MP3 Found] {b_id} ({b_info['name']}): {head_mp3.get('ContentLength')} bytes, Domain: {b_info.get('public_domain')}")
        except Exception:
            pass

        try:
            head_lrc = s3.head_object(Bucket=b_info['name'], Key=key_lrc)
            print(f"[LRC Found] {b_id} ({b_info['name']}): {head_lrc.get('ContentLength')} bytes")
        except Exception:
            pass
    except Exception as e:
        print(f"Error checking {b_id}: {e}")

print("Done scanning R2 buckets.")
