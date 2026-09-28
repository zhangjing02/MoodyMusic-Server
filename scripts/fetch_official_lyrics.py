#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高保真歌词下载与清洗模块 (酷狗官方高保真源 + 标准请求头)
"""
import requests
import base64
import json

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.kugou.com/'
}

def fetch_clean_lrc(artist: str, title: str) -> str:
    """
    通过酷狗高保真接口获取动力火车正版原唱歌词，过滤脏标签
    """
    try:
        # 1. 搜索歌曲 hash
        search_url = f"http://mobilecdn.kugou.com/api/v3/search/song?keyword={artist} {title}&page=1&pagesize=5"
        r = requests.get(search_url, headers=HEADERS, timeout=8).json()
        info_list = r.get("data", {}).get("info", [])
        if not info_list:
            return None

        # 优先匹配原唱歌手
        chosen_hash = None
        for item in info_list:
            singer = item.get("singername", "")
            if artist in singer:
                chosen_hash = item.get("hash")
                break
        if not chosen_hash and info_list:
            chosen_hash = info_list[0].get("hash")

        if not chosen_hash:
            return None

        # 2. 获取 LRC 候选
        lrc_search_url = f"http://lyrics.kugou.com/search?ver=1&man=yes&client=pc&keyword={artist} {title}&hash={chosen_hash}&album_audio_id=0"
        res = requests.get(lrc_search_url, headers=HEADERS, timeout=8).json()
        candidates = res.get('candidates', [])
        if not candidates:
            return None

        cand = candidates[0]
        # 3. 下载 LRC 内容
        dl_url = f"http://lyrics.kugou.com/download?ver=1&client=pc&id={cand['id']}&accesskey={cand['accesskey']}&fmt=lrc&charset=utf8"
        dr = requests.get(dl_url, headers=HEADERS, timeout=8).json()
        raw_b64 = dr.get("content", "")
        if not raw_b64:
            return None

        content = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
        content = content.replace('\ufeff', '').strip()

        # 4. 清洗垃圾私有标签
        clean_lines = []
        for line in content.split("\n"):
            l_str = line.strip()
            if any(l_str.startswith(tag) for tag in ["[qq:", "[id:", "[hash:", "[sign:", "[offset:", "[by:酷狗", "[by:kugou"]):
                continue
            clean_lines.append(line)

        cleaned = "\n".join(clean_lines).strip()
        if len(cleaned) > 50:
            return cleaned
    except Exception as e:
        print(f"[歌词抓取异常] {artist} - {title}: {e}")
    return None

if __name__ == "__main__":
    import sys
    tit = sys.argv[1] if len(sys.argv) > 1 else "还隐隐作痛"
    art = sys.argv[2] if len(sys.argv) > 2 else "动力火车"
    lrc = fetch_clean_lrc(art, tit)
    if lrc:
        print("抓取成功! 歌词前 200 字:")
        print(lrc[:200])
    else:
        print("未抓取到歌词!")
