#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探查《都是因为爱》与《结伴》官方 YouTube 音源
"""
import subprocess
import json

PROXY_URL = "http://127.0.0.1:7897"
NODE_PATH = "/Users/apple/.nvm/versions/node/v24.18.0/bin/node"

TARGETS = [
    # 《都是因为爱》 (Album ID 345)
    {"album": "都是因为爱", "title": "I'll Be Back"},
    {"album": "都是因为爱", "title": "我很好骗"},
    {"album": "都是因为爱", "title": "救世主"},
    {"album": "都是因为爱", "title": "我陪你面对"},
    {"album": "都是因为爱", "title": "远远的泪"},
    {"album": "都是因为爱", "title": "不必说哈啰"},
    {"album": "都是因为爱", "title": "完美遗憾"},
    {"album": "都是因为爱", "title": "跳上车子离开伤心的台北"},
    {"album": "都是因为爱", "title": "谢谢别再联络"},
    {"album": "都是因为爱", "title": "如果海能够"},
    {"album": "都是因为爱", "title": "二月"},
    # 《结伴》 (Album ID 343)
    {"album": "结伴", "title": "嗨歌万万岁"},
    {"album": "结伴", "title": "俯冲的灵魂"},
    {"album": "结伴", "title": "催眠"},
    {"album": "结伴", "title": "趁少年"},
    {"album": "结伴", "title": "看着你看着他"},
    {"album": "结伴", "title": "我不该哭"},
    {"album": "结伴", "title": "摇滚区"},
    {"album": "结伴", "title": "到底我算什么"},
    {"album": "结伴", "title": "你骂的都对"},
    {"album": "结伴", "title": "一直都在那里"}
]

results = []
for idx, item in enumerate(TARGETS, 1):
    alb = item["album"]
    tit = item["title"]
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
            results.append({"album": alb, "title": tit, "yt_id": v_id, "yt_title": v_title, "dur": v_dur})
            print(f"[{idx}/{len(TARGETS)}] [{alb}] 《{tit}》: {v_id} | {v_title} ({v_dur})", flush=True)
    except Exception as e:
        print(f"[{idx}/{len(TARGETS)}] [{alb}] 《{tit}》: Failed {e}", flush=True)

with open("/tmp/dongli_ai_jieban_sources.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
