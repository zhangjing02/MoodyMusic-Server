#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查《明天的明天的明天》官方 YouTube 音源
"""
import subprocess
import json

PROXY_URL = "http://127.0.0.1:7897"
NODE_PATH = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"

TRACKS = [
    "梨山痴情花",
    "我不知道",
    "明天的明天的明天",
    "Don't break my heart",
    "因为心碎所以喝醉",
    "你不在我身边好冷",
    "最后一种快乐",
    "刺猬",
    "单程车票",
    "让我哭",
    "我知道你要的是什么",
    "翅膀之歌"
]

results = []
for idx, tit in enumerate(TRACKS, 1):
    q = f"ytsearch1:動力火車 {tit} 官方"
    cmd = [
        "yt-dlp",
        "--proxy", PROXY_URL,
        "--js-runtimes", f"node:{NODE_PATH}",
        "--extractor-args", "youtube:player_client=ios,web,mweb",
        q,
        "--get-title", "--get-id", "--get-duration"
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip().split("\n")
        if len(out) >= 3:
            v_title, v_id, v_dur = out[0], out[1], out[2]
            results.append({"track": idx, "title": tit, "yt_id": v_id, "yt_title": v_title, "dur": v_dur})
            print(f"[{idx}/12] 《{tit}》: {v_id} | {v_title} ({v_dur})", flush=True)
    except Exception as e:
        print(f"[{idx}/12] 《{tit}》: Failed {e}", flush=True)

with open("/tmp/dongli_mingtian_sources.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
