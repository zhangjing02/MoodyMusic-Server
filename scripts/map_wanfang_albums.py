#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import sqlite3
import requests
import json
import zhconv

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
DB_PATH = os.path.join(WORKSPACE, "backend", "database", "catalog_sync.db")

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT al.id, al.title 
        FROM albums al 
        JOIN songs s ON al.id = s.album_id 
        JOIN artists ar ON al.artist_id = ar.id 
        WHERE ar.name = '万芳' 
        ORDER BY al.id
    """)
    albums = cur.fetchall()

    album_mappings = {}

    for alb_id, alb_title in albums:
        simp_title = zhconv.convert(alb_title, 'zh-cn')
        # 去除特殊标点便于搜索
        clean_search = alb_title.replace('.....', '').replace('1 - ', '').strip()
        url = f"https://music.163.com/api/search/get/web?s=万芳 {clean_search}&type=10&limit=5"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        cands = r.get('result', {}).get('albums', [])
        best = None
        for c in cands:
            art_name = c.get('artist', {}).get('name', '')
            if '万芳' in art_name:
                best = c
                break
        if best:
            netease_id = best['id']
            netease_name = best['name']
            album_mappings[alb_id] = {
                'local_id': alb_id,
                'local_title': alb_title,
                'netease_id': netease_id,
                'netease_name': netease_name
            }
            print(f"✅ [{alb_id:5d}] {alb_title:<25} -> 163 ID: {netease_id:<8} ({netease_name})")
        else:
            print(f"❌ [{alb_id:5d}] {alb_title:<25} -> 未找到对应网易云专辑")

    out_file = os.path.join(WORKSPACE, "backend", "database", "wanfang_album_map.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(album_mappings, f, ensure_ascii=False, indent=2)
    print(f"\n已保存专辑映射至: {out_file}")

if __name__ == "__main__":
    main()
