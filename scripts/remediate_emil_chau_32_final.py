#!/usr/bin/env python3
"""
周华健剩余 32 首历史断链与别名曲目终极精准点亮脚本
(remediate_emil_chau_32_final.py)
"""

import os, sys, json, time, re, subprocess, requests, boto3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
CACHE_DIR = Path("/tmp/emil_chau_final_cache")
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

# 32 首精准别名与母体对应表 (title, album) -> (search_keyword, fallback_id)
MAPPING = {
    ("永远的宝贝", "有弦相聚"): ("周华健 永远的宝贝", 22625),
    ("其实我不想放弃", "我願意去等"): ("周华健 其实我不想放弃", 22606),
    ("寡妇村传奇", "我願意去等"): ("周华健 寡妇村传奇", 22602),
    ("花心", "小天堂"): ("周华健 花心 小天堂", 22567),
    ("你现在还好吗", "小天堂"): ("周华健 你现在还好吗 小天堂", 22573),
    ("棋子", "愛的光"): ("周华健 棋子", 22583),
    ("问情剑", "愛的光"): ("周华健 问情剑", 22587),
    ("寡妇村传奇", "光陰似健1987-1997"): ("周华健 寡妇村传奇", 22513),
    ("孤枕难眠", "光陰似健1987-1997"): ("周华健 孤枕难眠", 22512),
    ("花心", "光陰似健1987-1997"): ("周华健 花心", 22511),
    ("爱相随", "光陰似健1987-1997"): ("周华健 爱相随", 22514),
    ("後序", "光陰似健1987-1997"): ("周华健 後序", 22519),
    ("如果我现在 (Acid Version)", "現在"): ("周华健 如果我现在", 22467),
    ("别傻了", "一起吃苦的幸福"): ("任贤齐 周华健 别傻了", 22357),
    ("The Widow Village", "周而復始"): ("周华健 寡妇村传奇", 22360),
    ("How Are You Getting Along", "周而復始"): ("周华健 你现在还好吗", 22361),
    ("The Flowery Heart", "周而復始"): ("周华健 花心", 22363),
    ("How Many Will You Like", "周而復始"): ("周华健 你喜欢的会有几个", 22362),
    ("Love Follows Us", "周而復始"): ("周华健 爱相随", 22364),
    ("A Man With Stories", "周而復始"): ("周华健 有故事的人", 22367),
    ("Day Lilies", "周而復始"): ("周华健 忘忧草", 22368),
    ("Any Songs Remind You of Me?", "周而復始"): ("周华健 有没有一首歌会让你想起我", 22369),
    ("Separate Lives", "周而復始"): ("周华健 Separate Lives", 22396),
    ("寂寞難耐", "男人三十"): ("周华健 寂寞难耐", 22338),
    ("言之尚早", "雨人"): ("周华健 言之尚早", 22330),
    ("林秀偉談上梁山", "水滸三部曲 (原創音樂選輯)"): ("林秀偉談上梁山 周华健", 22262),
    ("九天玄女1", "水滸三部曲 (原創音樂選輯)"): ("九天玄女 周华健", 22256),
    ("九天玄女2", "水滸三部曲 (原創音樂選輯)"): ("九天玄女 周华健", 22250),
    ("佛洛伊德惹的祸", "少年"): ("周华健 佛洛伊德惹的祸", 22204),
    ("在世界毁灭之前", "少年"): ("周华健 在世界毁灭之前", 22206),
    ("我把人生唱成一首给你的歌", "少年"): ("周华健 我把人生唱成一首给你的歌", 22208),
    ("遇树临风", "少年"): ("周华健 遇树临风", 22212)
}

def search_and_download(q: str, out_file: str) -> bool:
    cmd = [
        "yt-dlp", "--proxy", "http://127.0.0.1:7897",
        "--dump-json", "--flat-playlist", "--no-playlist",
        f"ytsearch5:{q}"
    ]
    best_vid = None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        for line in r.stdout.splitlines():
            if not line.strip(): continue
            d = json.loads(line)
            vid = d.get("id")
            tit = d.get("title", "")
            if any(kw in tit.lower() for kw in ["live", "演唱会", "伴奏", "karaoke"]):
                continue
            best_vid = vid
            break
        if not best_vid and r.stdout.splitlines():
            # 允许 fallback
            d = json.loads(r.stdout.splitlines()[0])
            best_vid = d.get("id")
    except Exception as e:
        print(f"  ⚠️ 检索异常: {e}")
        return False
        
    if not best_vid:
        return False
        
    dl_cmd = [
        "yt-dlp", "--proxy", "http://127.0.0.1:7897",
        "-f", "bestaudio/best",
        "-o", out_file,
        f"https://www.youtube.com/watch?v={best_vid}"
    ]
    try:
        subprocess.run(dl_cmd, capture_output=True, timeout=90)
        return os.path.exists(out_file) and os.path.getsize(out_file) > 100000
    except Exception:
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
        if os.path.exists(out_file) and os.path.getsize(out_file) > 100000:
            p_res = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_entries", "format=duration", out_file
            ], capture_output=True, text=True)
            return float(json.loads(p_res.stdout).get("format", {}).get("duration", 0))
    except Exception:
        pass
    return None

def fetch_lrc(q: str) -> str:
    try:
        url = f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={requests.utils.quote(q)}&page=1&pagesize=3"
        r = requests.get(url, timeout=5).json()
        songs = r.get("data", {}).get("info", [])
        if songs:
            dur = songs[0].get("duration", 0)
            h = songs[0].get("hash", "")
            lr_search = f"http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword={requests.utils.quote(q)}&duration={dur*1000}&hash={h}"
            cd = requests.get(lr_search, timeout=5).json().get("candidates", [])
            if cd:
                cid, akey = cd[0].get("id"), cd[0].get("accesskey")
                dl = requests.get(f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cid}&accesskey={akey}&fmt=lrc&charset=utf8", timeout=5).json()
                if dl.get("content"):
                    import base64
                    return base64.b64decode(dl["content"]).decode("utf-8")
    except:
        pass
    return ""

def main():
    print("==================================================")
    print(" 周华健剩余 32 首历史断链终极点亮流水线")
    print("==================================================")
    
    sess = requests.Session()
    sess.trust_env = False
    
    success_count = 0
    for idx, ((tit, alb), (kw, sid)) in enumerate(MAPPING.items(), 1):
        print(f"[{idx}/32] 正在处理: 《{tit}》[{alb}] (主键 ID: {sid}, 搜索词: '{kw}')...")
        raw_tmp = str(CACHE_DIR / f"raw_{sid}.webm")
        norm_mp3 = str(CACHE_DIR / f"norm_{sid}.mp3")
        
        ok = search_and_download(kw, raw_tmp)
        if not ok:
            print(f"  ❌ 采录失败")
            continue
            
        dur = normalize(raw_tmp, norm_mp3)
        if not dur:
            print(f"  ❌ 压制失败")
            if os.path.exists(raw_tmp): os.unlink(raw_tmp)
            continue
            
        r2_audio_key = f"music/周华健/{alb}/s_{sid}.mp3"
        r2_lrc_key = f"music/周华健/{alb}/s_{sid}.lrc"
        try:
            with open(norm_mp3, "rb") as mf:
                s3.put_object(
                    Bucket=bucket_name,
                    Key=r2_audio_key,
                    Body=mf,
                    ContentType="audio/mpeg"
                )
            pub_audio = f"{public_base}/{r2_audio_key}"
            
            lrc_txt = fetch_lrc(kw)
            pub_lrc = None
            if lrc_txt and len(lrc_txt) > 30:
                s3.put_object(
                    Bucket=bucket_name,
                    Key=r2_lrc_key,
                    Body=lrc_txt.encode("utf-8"),
                    ContentType="text/plain; charset=utf-8"
                )
                pub_lrc = f"{public_base}/{r2_lrc_key}"
                
            # D1 原子点亮
            d1_payload = {"updates": [{
                "id": int(sid),
                "file_path": pub_audio,
                "lrc_path": pub_lrc
            }]}
            r_d1 = sess.post("https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light", json=d1_payload, timeout=12)
            if r_d1.status_code == 200:
                print(f"  🌟 点亮成功: 时长 {dur:.1f}s -> {pub_audio}")
                success_count += 1
            else:
                print(f"  ⚠️ D1 响应: {r_d1.status_code} | {r_d1.text[:60]}")
        except Exception as e:
            print(f"  ❌ 推流入库异常: {e}")
        finally:
            if os.path.exists(raw_tmp): os.unlink(raw_tmp)
            if os.path.exists(norm_mp3): os.unlink(norm_mp3)
            
    print(f"\n32 首处理完成: 成功 {success_count}/32 首！")

if __name__ == "__main__":
    main()
