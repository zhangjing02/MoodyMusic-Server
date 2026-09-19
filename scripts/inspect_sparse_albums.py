# -*- coding: utf-8 -*-
import sys
import os
import sqlite3

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
DB_PATH = os.path.join(WORKSPACE, 'backend', 'database', 'catalog_sync.db')

def inspect():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("=" * 85)
    print("🎸【齐秦 (Chyi Chin) 全专深度体检 (基于 tracks_sync_state)】")
    print("=" * 85)

    cur.execute("""
        SELECT album_title, COUNT(*) as tot,
               SUM(CASE WHEN status = 'D1_LIT' THEN 1 ELSE 0 END) as lit
        FROM tracks_sync_state
        WHERE artist_name LIKE '%齐秦%'
        GROUP BY album_title
        ORDER BY album_title
    """)
    qiqin_albums = cur.fetchall()
    tot_songs = sum(r[1] for r in qiqin_albums)
    tot_lit = sum(r[2] for r in qiqin_albums)
    print(f"齐秦收录专辑数: {len(qiqin_albums)} 张 | 总曲目数: {tot_songs} 首 | 已点亮: {tot_lit} 首 | 缺失: {tot_songs - tot_lit} 首")
    print("-" * 85)
    print(f"{'点亮状态':<14} | {'已点亮/总数':<12} | {'点亮比例':<8} | {'专辑名称'}")
    print("-" * 85)
    
    for atitle, tot, lit in qiqin_albums:
        pct = (lit / tot * 100) if tot else 0
        flag = "🔴 严重稀疏" if (0 < lit < tot and pct < 60) else ("🟡 大部点亮" if (0 < lit < tot) else ("⚪ 完全空白" if lit == 0 else "🟢 100%满贯"))
        print(f"{flag:<14} | {lit:>2}/{tot:<2} 首      | {pct:>5.1f}%  | 《{atitle}》")

    print("\n📦【齐秦现有已点亮音轨存储桶分布】:")
    cur.execute("""
        SELECT r2_mp3_key
        FROM tracks_sync_state
        WHERE artist_name LIKE '%齐秦%' AND status = 'D1_LIT'
    """)
    paths = [r[0] for r in cur.fetchall() if r[0]]
    buckets = {}
    for p in paths:
        b = "未知"
        if "pub-9ea7ff16135d47238c0229f1aa54ecc4" in p: b = "Bucket 02 (moody-music-asset-02)"
        elif "pub-383b876c0bb840f6b852946604275232" in p: b = "Bucket 03 (moody-music-asset-03)"
        elif "pub-3507a1a1bc4b4ac3a3340833031078c2" in p: b = "Bucket 04 (moody-music-asset-04)"
        elif "pub-e7d069eb11954440aeb32012e8e3c670" in p: b = "Bucket 05 (moody-music-asset-05)"
        elif "pub-46ab5c0015d84be1b748cffecd23fdbb" in p: b = "Bucket 06 (moody-music-asset-06)"
        elif "r2.changgepd.ccwu.cc" in p or "asset/" in p: b = "Bucket 01 (moody-music-asset)"
        buckets[b] = buckets.get(b, 0) + 1
    for b, cnt in buckets.items():
        print(f"  • {b}: {cnt} 首")

    print("\n" + "=" * 85)
    print("🔍【全库知名歌手稀疏专辑大普查】(点亮 1~5 首，且缺失 ≥ 5 首)")
    print("=" * 85)
    cur.execute("""
        SELECT artist_name, album_title, COUNT(*) as tot,
               SUM(CASE WHEN status = 'D1_LIT' THEN 1 ELSE 0 END) as lit
        FROM tracks_sync_state
        GROUP BY artist_name, album_title
        HAVING lit > 0 AND (tot - lit) >= 5 AND (CAST(lit AS FLOAT) / tot) <= 0.6
        ORDER BY artist_name
    """)
    sparse = cur.fetchall()
    artists = {}
    for art, alb, tot, lit in sparse:
        if art not in artists: artists[art] = []
        artists[art].append((alb, tot, lit, tot - lit))

    sorted_arts = sorted(artists.items(), key=lambda x: sum(i[3] for i in x[1]), reverse=True)
    print(f"{'歌手':<14} | {'稀疏专数':<8} | {'缺失歌曲总数':<12} | {'典型稀疏专辑与比例'}")
    print("-" * 85)
    for art, albs in sorted_arts[:25]:
        missing = sum(i[3] for i in albs)
        samples = ', '.join([f'《{i[0]}》({i[2]}/{i[1]})' for i in albs[:3]])
        print(f"{art:<14} | {len(albs):<8} | 缺 {missing:<10} 首 | {samples}")

    conn.close()

if __name__ == '__main__':
    inspect()
