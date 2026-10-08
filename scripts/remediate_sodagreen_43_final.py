#!/usr/bin/env python3
"""
苏打绿剩余 43 首精准别名与复刻母带终极点亮脚本
(remediate_sodagreen_43_final.py)
"""

import os, sys, json, time, re, subprocess, requests, boto3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CACHE_DIR = Path("/tmp/sodagreen_final_cache")
CACHE_DIR.mkdir(exist_ok=True)

PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}

with open(BASE_DIR / "r2_config.json") as f:
    cfg = json.load(f)

acct12 = cfg['buckets']['account_12']
s3 = boto3.client(
    's3',
    endpoint_url=acct12['endpoint_url'],
    aws_access_key_id=acct12['access_key_id'],
    aws_secret_access_key=acct12['secret_access_key'],
    region_name='auto'
)
bucket_name = acct12['name']
public_base = acct12['public_url']

# 43 首曲目真实 ID 与精准检索词字典 (id, album, title, [keywords])
TASKS = [
    (15106, '夏 / 狂熱', '口白 - 英文詩 1', ['sodagreen 英文詩 1', '蘇打綠 英文詩 1', 'sodagreen Summer Fever']),
    (15110, '夏 / 狂熱', '口白 - 英文詩 2', ['sodagreen 英文詩 2', '蘇打綠 英文詩 2', 'sodagreen Summer Fever']),
    (15034, '冬 未了', '第二樂章/慢板(取材自〈回車諾比的夢〉與〈下雨的夜晚〉) (feat. Budapest Art Orchestra)', ['sodagreen 冬之頌 第二樂章', 'Budapest Art Orchestra sodagreen', '冬之頌 第二樂章']),
    (15035, '冬 未了', '第三樂章/活潑的快板(取材自〈他舉起右手點名〉) (feat. Budapest Art Orchestra)', ['sodagreen 冬之頌 第三樂章', 'Budapest Art Orchestra sodagreen', '冬之頌 第三樂章']),
    (15036, '冬 未了', '第四樂章/有精神的快板—莊嚴的快板(取材自〈痛快的哀艷〉) (feat. Budapest Art Orchestra)', ['sodagreen 冬之頌 第四樂章', 'Budapest Art Orchestra sodagreen', '冬之頌 第四樂章']),
    (15037, '冬 未了', 'Cold Star (feat. Budapest Art Orchestra)', ['Cold Star sodagreen', 'sodagreen Cold Star Budapest']),
    (15038, '冬 未了', 'Weird Cat (feat. Budapest Art Orchestra)', ['Weird Cat sodagreen', 'sodagreen Weird Cat Budapest']),
    (15039, '冬 未了', 'Four Season (feat. Budapest Art Orchestra)', ['Four Season sodagreen', 'sodagreen Four Season Budapest']),
    (14952, 'Spring · Daylight (sodagreen Version)', '. .', ['sodagreen 春 日光 苏打绿版', 'sodagreen Spring Daylight']),
    (14955, 'Spring · Daylight (sodagreen Version)', '海洋 (Live in summer)', ['sodagreen Ocean (Live in summer)', 'Ocean (Live in summer) sodagreen']),
    (14956, 'Spring · Daylight (sodagreen Version)', '月亮使者 (Live in summer)', ['sodagreen Moon Envoy (Live in summer)', 'Moon Envoy (Live in summer) sodagreen']),
    (14957, 'Spring · Daylight (sodagreen Version)', '原谅 (Live in summer)', ['sodagreen Forgive (Live in summer)', 'Forgive (Live in summer) sodagreen']),
    (14958, 'Spring · Daylight (sodagreen Version)', 'わすれない (Live in summer)', ['sodagreen わすれない (Live in summer)', 'わすれない sodagreen']),
    (14959, 'Spring · Daylight (sodagreen Version)', '九月 (Live in summer)', ['sodagreen September (Live in summer)', 'September (Live in summer) sodagreen']),
    (14961, 'Spring · Daylight (sodagreen Version)', '天地记 (Live in summer)', ['sodagreen Record of Heaven and Earth (Live in summer)', 'Record of Heaven and Earth sodagreen']),
    (14962, 'Spring · Daylight (sodagreen Version)', 'The Rose (Live in summer)', ['sodagreen The Rose (Live in summer)', 'The Rose (Live in summer) sodagreen']),
    (14963, 'Spring · Daylight (sodagreen Version)', 'Love Is Everything (Live in summer)', ['sodagreen Love Is Everything (Live in summer)', 'Love Is Everything (Live in summer) sodagreen']),
    (14966, 'Autumn: Stories (sodagreen Version)', ':', ['sodagreen 秋 故事 苏打绿版', 'sodagreen Autumn Stories']),
    (14980, 'Autumn: Stories (sodagreen Version)', '安静在沸腾 (Live in summer)', ['sodagreen Quietly Boiling (Live in summer)', 'Quietly Boiling (Live in summer) sodagreen']),
    (14981, 'Autumn: Stories (sodagreen Version)', 'Where Have All The Cowboys Gone? (Live in summer)', ['sodagreen Where Have All The Cowboys Gone? (Live in summer)', 'Where Have All The Cowboys Gone? sodagreen']),
    (14984, 'Autumn: Stories (sodagreen Version)', '百年孤寂 (Live in summer)', ['sodagreen One Hundred Years of Solitude (Live in summer)', 'One Hundred Years of Solitude sodagreen']),
    (14985, 'Autumn: Stories (sodagreen Version)', '影子 (Live in summer)', ['sodagreen Shadow (Live in summer)', 'Shadow (Live in summer) sodagreen']),
    (15004, 'Summer / Fever (sodagreen Version)', '我在欧洲打电话给你 (Live in summer)', ['sodagreen Calling You From Europe (Live in summer)', 'Calling You From Europe sodagreen']),
    (15007, 'Summer / Fever (sodagreen Version)', 'Smells Like Teen Spirit (Live in summer)', ['sodagreen Smells Like Teen Spirit (Live in summer)', 'Smells Like Teen Spirit sodagreen']),
    (15008, 'Summer / Fever (sodagreen Version)', 'Don\'t Break My Heart (Live in summer)', ['sodagreen Don\'t Break My Heart (Live in summer)', 'Don\'t Break My Heart sodagreen']),
    (15009, 'Summer / Fever (sodagreen Version)', '花房姑娘 (Live in summer)', ['sodagreen Girl in the Greenhouse (Live in summer)', 'Girl in the Greenhouse sodagreen']),
    (14880, 'Winter Endless (sodagreen Version)', '冬之颂：第一乐章 适度的快板', ['sodagreen 冬之颂 第一乐章', '冬之颂 第一乐章 sodagreen']),
    (14881, 'Winter Endless (sodagreen Version)', '冬之颂：第二乐章 慢板', ['sodagreen 冬之颂 第二乐章', '冬之颂 第二乐章 sodagreen']),
    (14882, 'Winter Endless (sodagreen Version)', '冬之颂：第三乐章 活泼的快板', ['sodagreen 冬之颂 第三乐章', '冬之颂 第三乐章 sodagreen']),
    (14883, 'Winter Endless (sodagreen Version)', '冬之颂：第四乐章 有精神的快板-庄严的快板', ['sodagreen 冬之颂 第四乐章', '冬之颂 第四乐章 sodagreen']),
    (14884, 'Winter Endless (sodagreen Version)', '哼唱光年：第一乐章 穿梭', ['sodagreen 哼唱光年 第一乐章', '哼唱光年 第一乐章 sodagreen']),
    (14886, 'Winter Endless (sodagreen Version)', '哼唱光年：第三乐章 梦境', ['sodagreen 哼唱光年 第三乐章', '哼唱光年 第三乐章 sodagreen']),
    (14887, 'Winter Endless (sodagreen Version)', '哼唱光年：第四乐章 在我们之间', ['sodagreen 哼唱光年 第四乐章', '哼唱光年 第四乐章 sodagreen']),
    (14903, '20 Special Moments', '漂白 (Live)', ['sodagreen 漂白 20 Special Moments', '漂白 sodagreen']),
    (14904, '20 Special Moments', 'To You (Live)', ['sodagreen To You 20 Special Moments', 'To You sodagreen']),
    (14907, '20 Special Moments', '应许 (Live)', ['sodagreen 应许 20 Special Moments', '应许 sodagreen']),
    (14908, '20 Special Moments', '饥饿再生 (Live)', ['sodagreen 饥饿再生 20 Special Moments', '饥饿再生 sodagreen']),
    (14911, '20 Special Moments', '旅人 (Live)', ['sodagreen 旅人 20 Special Moments', '旅人 sodagreen']),
    (14912, '20 Special Moments', '夜来疯 (Live)', ['sodagreen 夜来疯 20 Special Moments', '夜来疯 sodagreen']),
    (14913, '20 Special Moments', '悬丝傀儡 (Live)', ['sodagreen 悬丝傀儡 20 Special Moments', '悬丝傀儡 sodagreen']),
    (14914, '20 Special Moments', 'Let\'s Dream About Love (feat. GermanPops Orchestra) [Live]', ['sodagreen Let\'s Dream About Love GermanPops', 'Let\'s Dream About Love sodagreen']),
    (14915, '20 Special Moments', '生命乐章 (feat. 佐藤芳明) [Live]', ['sodagreen 生命乐章 佐藤芳明', '生命乐章 sodagreen']),
    (14916, '20 Special Moments', '只有可以 (Live)', ['sodagreen 只有可以 20 Special Moments', '只有可以 sodagreen'])
]

def search_and_download(queries: list, out_file: str) -> bool:
    for q in queries:
        cmd = [
            "yt-dlp", "--proxy", "http://127.0.0.1:7897",
            "--dump-json", "--flat-playlist", "--no-playlist",
            f"ytsearch3:{q}"
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=18)
            best_vid = None
            for line in r.stdout.splitlines():
                if not line.strip(): continue
                d = json.loads(line)
                vid = d.get("id")
                dur = d.get("duration", 0)
                if dur > 10:
                    best_vid = vid
                    break
            if best_vid:
                dl_cmd = [
                    "yt-dlp", "--proxy", "http://127.0.0.1:7897",
                    "-f", "bestaudio/best",
                    "-o", out_file,
                    f"https://www.youtube.com/watch?v={best_vid}"
                ]
                subprocess.run(dl_cmd, capture_output=True, timeout=90)
                if os.path.exists(out_file) and os.path.getsize(out_file) > 50000:
                    return True
        except Exception:
            pass
    return False

def normalize(in_file: str, out_file: str) -> float | None:
    cmd = [
        "ffmpeg", "-y", "-i", in_file,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-b:a", "320k", "-ar", "44100",
        out_file
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
        if os.path.exists(out_file) and os.path.getsize(out_file) > 50000:
            p_res = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_entries", "format=duration", out_file
            ], capture_output=True, text=True)
            return float(json.loads(p_res.stdout).get("format", {}).get("duration", 0))
    except Exception:
        pass
    return None

def main():
    print("==================================================")
    print(" 苏打绿剩余 43 首精准别名与复刻母带终极点亮流水线")
    print("==================================================")
    sess = requests.Session()
    sess.trust_env = False
    
    success_count = 0
    for idx, (sid, alb, tit, qlist) in enumerate(TASKS, 1):
        print(f"[{idx}/43] 正在处理: 《{tit}》[{alb}] (主键 ID: {sid})...")
        raw_tmp = str(CACHE_DIR / f"raw_soda_{sid}.webm")
        norm_mp3 = str(CACHE_DIR / f"norm_soda_{sid}.mp3")
        
        ok = search_and_download(qlist, raw_tmp)
        if not ok:
            print(f"  ❌ 采录失败")
            continue
            
        dur = normalize(raw_tmp, norm_mp3)
        if not dur:
            print(f"  ❌ 压制失败")
            if os.path.exists(raw_tmp): os.unlink(raw_tmp)
            continue
            
        r2_k = f"music/苏打绿/{alb}/s_{sid}.mp3"
        try:
            with open(norm_mp3, "rb") as mf:
                s3.put_object(
                    Bucket=bucket_name,
                    Key=r2_k,
                    Body=mf,
                    ContentType="audio/mpeg"
                )
            pub_audio = f"{public_base}/{r2_k}"
            d1_payload = {"updates": [{
                "id": int(sid),
                "file_path": pub_audio
            }]}
            r_d1 = sess.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json=d1_payload, timeout=12)
            if r_d1.status_code == 200:
                print(f"  🌟 点亮成功: 时长 {dur:.1f}s -> {pub_audio}")
                success_count += 1
            else:
                print(f"  ⚠️ D1 点亮响应: {r_d1.status_code} | {r_d1.text[:60]}")
        except Exception as e:
            print(f"  ❌ 推流入库异常: {e}")
        finally:
            if os.path.exists(raw_tmp): os.unlink(raw_tmp)
            if os.path.exists(norm_mp3): os.unlink(norm_mp3)
            
    print(f"\n苏打绿 43 首处理完成: 成功 {success_count}/43 首！")

if __name__ == "__main__":
    main()
