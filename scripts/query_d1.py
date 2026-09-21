#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import json

import os
account_id = "0bd18c2b8609958f139bed5fdbe6b3f5"
db_id = "a9591a5a-1c83-4c27-ad19-70a3aa4f11fc"
token = os.environ.get("CF_TOKEN", "")
url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{db_id}/query"

sql = """
SELECT s.id, s.title, a.title as album, art.name as artist, s.file_path
FROM songs s
JOIN albums a ON s.album_id = a.id
JOIN artists art ON a.artist_id = art.id
WHERE art.name = 'Beyond' AND a.title = '真的見証'
"""

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

r = requests.post(url, headers=headers, json={"sql": sql}, timeout=15)
res = r.json()
print("Cloudflare D1 REST API 响应:")
if res.get("success"):
    results = res.get("result", [])[0].get("results", [])
    for row in results:
        sid = row.get("id")
        title = row.get("title")
        path = row.get("file_path")
        print(f"ID: {sid:<6} | 歌名: {title:<15} | Path: {path}")
else:
    print("Error:", res.get("errors"))
