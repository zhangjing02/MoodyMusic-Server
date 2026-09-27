import requests, boto3, json
from botocore.config import Config

with open('backend/r2_config.json', 'r', encoding='utf-8') as f:
    cfg = json.load(f)['buckets']['account_10']

s3 = boto3.client(
    's3',
    endpoint_url=cfg['endpoint_url'],
    aws_access_key_id=cfg['access_key_id'],
    aws_secret_access_key=cfg['secret_access_key'],
    config=Config(signature_version='s3v4')
)
bname = cfg['name']
bdomain = cfg['public_domain'].rstrip('/')

# 1. Artist Photo
artist_pic = 'https://p2.music.126.net/R-Whzktk38cF_bwQxHnzyg==/109951172174207103.jpg'
r_art = requests.get(artist_pic, headers={'User-Agent': 'Mozilla/5.0'}).content
key_art = 'covers/artists/a_tong_an_ge.jpg'
s3.put_object(Bucket=bname, Key=key_art, Body=r_art, ContentType='image/jpeg')
cdn_art = f"{bdomain}/{key_art}"
print(f"Artist photo uploaded: {cdn_art} ({len(r_art)} bytes)")

# 2. Album Cover (其实你不懂我的心)
album_pic = 'https://p1.music.126.net/adpk3YWadGHzcFz9Rd_EeA==/109951164843924659.jpg'
r_alb = requests.get(album_pic, headers={'User-Agent': 'Mozilla/5.0'}).content
key_alb = 'covers/albums/c_qi_shi_ni_bu_dong_wo_de_xin.jpg'
s3.put_object(Bucket=bname, Key=key_alb, Body=r_alb, ContentType='image/jpeg')
cdn_alb = f"{bdomain}/{key_alb}"
print(f"Album cover uploaded: {cdn_alb} ({len(r_alb)} bytes)")
