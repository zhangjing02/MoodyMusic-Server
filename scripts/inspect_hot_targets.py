# -*- coding: utf-8 -*-
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
with open('backend/scripts/configs/priority_hot_targets.json', encoding='utf-8') as f:
    d = json.load(f)
print("大热优先曲目总数:", len(d))
for item in d[:3]:
    print(f"  - [{item['artist_name']}] 《{item['album_title']}》 - {item['title']} (SongID: {item['song_id']})")
