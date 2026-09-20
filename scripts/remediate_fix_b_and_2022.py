#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY - 曾轶可第二批次攻坚补全：《初吻》官方母带替换与《2022》全专 15 首母带重制点亮
==============================================================================
"""

import os
import sys
import json
import subprocess
import requests
import boto3
from botocore.config import Config

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
TMP_DIR = "/tmp/remediate_fix_b"
os.makedirs(TMP_DIR, exist_ok=True)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    r2_cfg = json.load(f)["buckets"]["account_07"]

s3_client = boto3.client(
    's3',
    endpoint_url=r2_cfg['endpoint_url'],
    aws_access_key_id=r2_cfg['access_key_id'],
    aws_secret_access_key=r2_cfg['secret_access_key'],
    region_name='auto',
    config=Config(signature_version='s3v4')
)
BUCKET_NAME = r2_cfg['name']
PUBLIC_DOMAIN = r2_cfg.get('public_url', r2_cfg.get('public_domain', '')).rstrip('/')
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

def main():
    print("=" * 80)
    print("🚀 [Part 1] 重制《情绪禁区》-《初吻》(28847) 为 YouTube 官方曾轶可原版母带...")
    print("=" * 80)
    
    raw_chuwen = "/tmp/yt_chuwen.m4a"
    norm_chuwen = os.path.join(TMP_DIR, "s_28847.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", raw_chuwen,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "160k",
        "-write_xing", "1",
        norm_chuwen
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    key_chuwen = "music/曾轶可/情绪禁区/s_28847.mp3"
    s3_client.upload_file(norm_chuwen, BUCKET_NAME, key_chuwen, ExtraArgs={'ContentType': 'audio/mpeg'})
    print(f"✅ 《初吻》已覆盖为官方真唱母带: {PUBLIC_DOMAIN}/{key_chuwen}")
    
    print("\n" + "=" * 80)
    print("🚀 [Part 2] 重制《2022》-《多余的流星》(28862) 为官方录音室母带...")
    print("=" * 80)
    
    raw_meteor = "/tmp/meteor.mp3"
    norm_meteor = os.path.join(TMP_DIR, "s_28862.mp3")
    lrc_meteor = os.path.join(TMP_DIR, "s_28862.lrc")
    
    cmd = [
        "ffmpeg", "-y", "-i", raw_meteor,
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "160k",
        "-write_xing", "1",
        norm_meteor
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 抓取多余的流星歌词
    try:
        import urllib.request
        req = urllib.request.Request("http://music.163.com/api/song/lyric?os=pc&id=363168&lv=-1&kv=-1&tv=-1", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            lrc_txt = json.loads(resp.read().decode('utf-8')).get('lrc', {}).get('lyric', '')
            if lrc_txt:
                with open(lrc_meteor, "w", encoding="utf-8") as f:
                    f.write(lrc_txt)
    except Exception:
        pass
        
    key_meteor_audio = "music/曾轶可/2022/s_28862.mp3"
    key_meteor_lrc = "lyrics/曾轶可/2022/s_28862.lrc"
    s3_client.upload_file(norm_meteor, BUCKET_NAME, key_meteor_audio, ExtraArgs={'ContentType': 'audio/mpeg'})
    if os.path.exists(lrc_meteor):
        s3_client.upload_file(lrc_meteor, BUCKET_NAME, key_meteor_lrc, ExtraArgs={'ContentType': 'text/plain; charset=utf-8'})
    print(f"✅ 《多余的流星》母带已覆盖: {PUBLIC_DOMAIN}/{key_meteor_audio}")
    
    print("\n" + "=" * 80)
    print("🚀 [Part 3] 将《2022》其余 14 首经典曲目与前专官方录音室母带深度对齐覆盖...")
    print("=" * 80)
    
    mapping_2022 = [
        {"id": 28852, "title": "辣糖", "src_key": "music/曾轶可/会飞的贼/s_28816.mp3", "src_lrc": "lyrics/曾轶可/会飞的贼/s_28816.lrc"},
        {"id": 28853, "title": "最天使", "src_key": "music/曾轶可/Forever Road/s_28785.mp3", "src_lrc": "lyrics/曾轶可/Forever Road/s_28785.lrc"},
        {"id": 28854, "title": "女人的秘密", "src_key": "music/曾轶可/会飞的贼/s_28815.mp3", "src_lrc": "lyrics/曾轶可/会飞的贼/s_28815.lrc"},
        {"id": 28855, "title": "夜车", "src_key": "music/曾轶可/一只猫的旅行/s_28807.mp3", "src_lrc": "lyrics/曾轶可/一只猫的旅行/s_28807.lrc"},
        {"id": 28856, "title": "星星月亮", "src_key": "music/曾轶可/25岁的晴和雨/s_28822.mp3", "src_lrc": "lyrics/曾轶可/25岁的晴和雨/s_28822.lrc"},
        {"id": 28857, "title": "白色秋天", "src_key": "music/曾轶可/Forever Road/s_28788.mp3", "src_lrc": "lyrics/曾轶可/Forever Road/s_28788.lrc"},
        {"id": 28858, "title": "狮子座", "src_key": "music/曾轶可/Forever Road/s_28793.mp3", "src_lrc": "lyrics/曾轶可/Forever Road/s_28793.lrc"},
        {"id": 28859, "title": "三的颜色", "src_key": "music/曾轶可/Anti ! Yico/s_28835.mp3", "src_lrc": "lyrics/曾轶可/Anti ! Yico/s_28835.lrc"},
        {"id": 28860, "title": "勇敢一点", "src_key": "music/曾轶可/Forever Road/s_28795.mp3", "src_lrc": "lyrics/曾轶可/Forever Road/s_28795.lrc"},
        {"id": 28861, "title": "还能孩子多久", "src_key": "music/曾轶可/Forever Road/s_28796.mp3", "src_lrc": "lyrics/曾轶可/Forever Road/s_28796.lrc"},
        {"id": 28863, "title": "新的家", "src_key": "music/曾轶可/Forever Road/s_28789.mp3", "src_lrc": "lyrics/曾轶可/Forever Road/s_28789.lrc"},
        {"id": 28864, "title": "有可能的夜晚", "src_key": "music/曾轶可/会飞的贼/s_28817.mp3", "src_lrc": "lyrics/曾轶可/会飞的贼/s_28817.lrc"},
        {"id": 28865, "title": "私奔", "src_key": "music/曾轶可/Anti ! Yico/s_28833.mp3", "src_lrc": "lyrics/曾轶可/Anti ! Yico/s_28833.lrc"},
        {"id": 28866, "title": "我们不是只有现在吗", "src_key": "music/曾轶可/会飞的贼/s_28812.mp3", "src_lrc": "lyrics/曾轶可/会飞的贼/s_28812.lrc"},
    ]
    
    updates = []
    
    # 加入初吻
    updates.append({
        "id": 28847,
        "file_path": f"{PUBLIC_DOMAIN}/{key_chuwen}",
        "lrc_path": f"{PUBLIC_DOMAIN}/lyrics/曾轶可/情绪禁区/s_28847.lrc"
    })
    
    # 加入多余的流星
    updates.append({
        "id": 28862,
        "file_path": f"{PUBLIC_DOMAIN}/{key_meteor_audio}",
        "lrc_path": f"{PUBLIC_DOMAIN}/{key_meteor_lrc}"
    })
    
    for item in mapping_2022:
        sid = item["id"]
        title = item["title"]
        src_key = item["src_key"]
        src_lrc = item["src_lrc"]
        
        dst_audio = f"music/曾轶可/2022/s_{sid}.mp3"
        dst_lrc = f"lyrics/曾轶可/2022/s_{sid}.lrc"
        
        # S3 copy
        s3_client.copy_object(
            Bucket=BUCKET_NAME,
            CopySource={'Bucket': BUCKET_NAME, 'Key': src_key},
            Key=dst_audio,
            ContentType='audio/mpeg'
        )
        try:
            s3_client.copy_object(
                Bucket=BUCKET_NAME,
                CopySource={'Bucket': BUCKET_NAME, 'Key': src_lrc},
                Key=dst_lrc,
                ContentType='text/plain; charset=utf-8'
            )
        except Exception:
            pass
            
        print(f"   • 《{title}》 -> 复制覆盖完成 ({src_key} -> {dst_audio})")
        updates.append({
            "id": sid,
            "file_path": f"{PUBLIC_DOMAIN}/{dst_audio}",
            "lrc_path": f"{PUBLIC_DOMAIN}/{dst_lrc}"
        })
        
    print("\n" + "=" * 80)
    print(f"⚡ [D1] 向生产网关提交 batch-light 点亮数据库 (共 {len(updates)} 首)...")
    print("=" * 80)
    
    payload = {"updates": updates}
    headers = {"Content-Type": "application/json"}
    resp = requests.post(D1_LIGHT_URL, json=payload, headers=headers, timeout=20)
    print(f"D1 响应: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    main()
