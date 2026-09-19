#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import sqlite3

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
DB_PATH = os.path.join(WORKSPACE, "backend", "database", "catalog_sync.db")
CFG_PATH = os.path.join(WORKSPACE, "backend", "r2_config.json")

def check():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    with open(CFG_PATH, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    print("=" * 80)
    print("📦 存储桶水位监控 (9.50 GB 熔断警戒线)")
    print("=" * 80)
    max_safe = 9.50 * (1024**3)
    for acc, b in cfg['buckets'].items():
        cur.execute("""
            SELECT COALESCE(SUM(file_size), 0), COUNT(song_id)
            FROM tracks_sync_state
            WHERE status = 'D1_LIT' AND (r2_mp3_key LIKE ? OR r2_mp3_key LIKE ?)
        """, (f"%{b['name']}%", f"%{b.get('public_domain', 'NONEXIST')}%"))
        bsize, bcount = cur.fetchone()
        if acc == 'account_07':
            bsize += 5638278316
        gb = bsize / (1024**3)
        pct = (bsize / max_safe) * 100
        status_flag = "🟢 安全" if gb < 9.0 else ("🟡 预警" if gb < 9.5 else "🔴 熔断保护")
        print(f" • {acc:<12} | {b['name']:<24} | 曲目: {bcount:<5} | 占用: {gb:6.3f} GB / 9.50 GB ({pct:5.1f}%) | {status_flag}")

    print("\n" + "=" * 80)
    print("🎤 重点排查歌手专辑点亮进展")
    print("=" * 80)
    artists = ['齐秦', '高胜美', '黄品源', '万芳', '罗大佑', '费玉清', '林宥嘉', '黄小琥', '庾澄庆', '苏慧伦']
    for art in artists:
        cur.execute("""
            SELECT COUNT(s.id),
                   SUM(CASE WHEN s.file_path IS NOT NULL AND s.file_path != '' THEN 1 ELSE 0 END),
                   COUNT(DISTINCT s.album_id)
            FROM songs s
            JOIN artists ar ON s.artist_id = ar.id
            WHERE ar.name = ?
        """, (art,))
        tot, lit, albs = cur.fetchone()
        pct = (lit / tot * 100) if tot > 0 else 0
        status_sym = "🟢 100% 全满贯" if lit == tot else f"🟡 待补齐 {tot - lit} 首"
        print(f" • {art:<6} | 专辑: {albs:2d} 张 | 曲目: {lit:3d}/{tot:3d} ({pct:5.1f}%) | {status_sym}")

    conn.close()

if __name__ == "__main__":
    check()
