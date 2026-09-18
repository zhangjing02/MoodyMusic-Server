import sys
if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import boto3
from botocore.config import Config
import requests

with open('backend/r2_config.json', 'r', encoding='utf-8') as f:
    cfg = json.load(f)

b4 = cfg['buckets']['account_04']
s3 = boto3.client(
    service_name='s3',
    endpoint_url=b4['endpoint_url'],
    aws_access_key_id=b4['access_key_id'],
    aws_secret_access_key=b4['secret_access_key'],
    region_name='auto',
    config=Config(s3={'addressing_style': 'path'})
)

test_key = "music/test_connection.txt"
test_body = "Moody Music Connection Test OK"

print("Uploading test object to moody-music-asset-04...")
s3.put_object(
    Bucket=b4['name'],
    Key=test_key,
    Body=test_body.encode('utf-8'),
    ContentType='text/plain; charset=utf-8'
)
print("Upload successful!")

cdn_url = f"{b4['public_domain']}/{test_key}"
print(f"Testing CDN access: {cdn_url}")
r = requests.get(cdn_url, timeout=10)
print(f"CDN Status: {r.status_code}, Content: {r.text}")

# Clean up test object
s3.delete_object(Bucket=b4['name'], Key=test_key)
print("Test object deleted from R2.")
