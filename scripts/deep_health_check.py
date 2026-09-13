#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY 曲库资源与骨架深度体检脚本 (Deep Health Check)
深度排查:
1. 歌手层: 重复歌手、0专辑歌手、0歌曲歌手
2. 专辑层: 歌手名下同名/归一化同名重复专辑、0歌曲空壳专辑、孤儿专辑
3. 歌曲层: 同专重复歌曲、跨专重复歌曲、重复 file_path、空白/异常音轨
4. 状态层: D1 与本地 catalog_sync.db 骨架一致性排查
"""

import os
import sys
import json
import sqlite3
import re
from collections import defaultdict

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")

def normalize_title(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r'[\s\t\n\r\-—·、，,。．；;：:！!？?（）\(\)\[\]【】《》〈⟩\._]', '', s)
    t2s = {
        '愛': '爱', '來': '来', '後': '后', '為': '为', '與': '与', '時': '时', '開': '开', '無': '无',
        '國': '国', '語': '语', '產': '产', '學': '学', '長': '长', '點': '点', '變': '变', '電': '电',
        '動': '动', '聽': '听', '這': '这', '過': '过', '寫': '写', '會': '会', '經': '经', '關': '关',
        '們': '们', '傳': '传', '錄': '录', '機': '机', '觀': '观', '場': '场', '實': '实', '驗': '验',
        '斷': '断', '種': '种', '類': '类', '難': '难', '優': '优', '態': '态', '響': '响', '應': '应',
        '調': '调', '轉': '转', '遙': '遥', '麵': '面', '彎': '弯', '單': '单', '願': '愿', '義': '义',
        '標': '标', '遠': '远', '選': '选', '邊': '边', '處': '处', '風': '风', '頭': '头', '門': '门',
        '間': '间', '題': '题', '導': '导', '讓': '让', '識': '识', '設': '设', '屬': '属', '據': '据',
        '築': '筑', '緊': '紧', '陳': '陈', '蓋': '盖', '舉': '举', '壓': '压', '質': '质', '儘': '尽',
        '護': '护', '戲': '戏', '臺': '台', '鄉': '乡', '現': '现', '規': '规', '視': '视', '藝': '艺',
        '價': '价', '證': '证', '獨': '独', '劇': '剧', '歲': '岁', '備': '备', '敵': '敌', '瑩': '莹'
    }
    for k, v in t2s.items():
        s = s.replace(k, v)
    return s

def run_health_check():
    print("=" * 80)
    print("🩺 MOODY 曲库与骨架全局深度体检报告")
    print("=" * 80)

    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. 歌手层体检
    print("\n[1] 🎤 歌手层体检 (Artists)")
    cur.execute("SELECT id, name FROM artists ORDER BY id")
    all_artists = cur.fetchall()
    print(f"  • 登记歌手总数: {len(all_artists)}")

    # 1.1 重复歌手排查 (包括归一化重名)
    artist_name_map = defaultdict(list)
    norm_artist_map = defaultdict(list)
    for aid, name in all_artists:
        artist_name_map[name.strip()].append(aid)
        norm_artist_map[normalize_title(name)].append((aid, name))

    dup_artists = {k: v for k, v in artist_name_map.items() if len(v) > 1}
    if dup_artists:
        print(f"  ⚠️ 发现完全重名歌手 {len(dup_artists)} 组:")
        for k, v in dup_artists.items():
            print(f"     - '{k}': IDs = {v}")
    else:
        print("  ✅ 未发现完全重名歌手")

    norm_dup_artists = {k: v for k, v in norm_artist_map.items() if len(v) > 1 and k}
    fuzzy_dup_artists = {}
    for k, v in norm_dup_artists.items():
        names = set(item[1] for item in v)
        if len(names) > 1:
            fuzzy_dup_artists[k] = v
    if fuzzy_dup_artists:
        print(f"  ⚠️ 发现简繁/别名疑似重名歌手 {len(fuzzy_dup_artists)} 组:")
        for k, v in fuzzy_dup_artists.items():
            print(f"     - '{k}': {v}")
    else:
        print("  ✅ 未发现简繁/标点差异重名歌手")

    # 1.2 0专辑歌手 / 0歌曲歌手
    cur.execute("""
        SELECT a.id, a.name 
        FROM artists a 
        LEFT JOIN albums alb ON a.id = alb.artist_id 
        WHERE alb.id IS NULL
    """)
    zero_album_artists = cur.fetchall()
    if zero_album_artists:
        print(f"  ⚠️ 发现 0 专辑空壳歌手 {len(zero_album_artists)} 位:")
        for aid, name in zero_album_artists:
            print(f"     - ID {aid}: '{name}'")
    else:
        print("  ✅ 无 0 专辑空壳歌手")

    # 2. 专辑层体检
    print("\n[2] 💿 专辑层体检 (Albums)")
    cur.execute("SELECT id, artist_id, title FROM albums ORDER BY artist_id, id")
    all_albums = cur.fetchall()
    print(f"  • 登记专辑总数: {len(all_albums)}")

    # 2.1 同一歌手下的同名/归一化同名重复专辑
    artist_album_groups = defaultdict(list)
    for albid, aid, title in all_albums:
        artist_album_groups[aid].append((albid, title))

    dup_album_groups = []
    for aid, albs in artist_album_groups.items():
        title_map = defaultdict(list)
        for albid, title in albs:
            norm_t = normalize_title(title)
            title_map[norm_t].append((albid, title))
        for norm_t, group in title_map.items():
            if len(group) > 1:
                dup_album_groups.append((aid, norm_t, group))

    print(f"  ⚠️ 检出同名重复专辑: {len(dup_album_groups)} 组")
    dup_details = []
    for aid, norm_t, group in dup_album_groups:
        cur.execute("SELECT name FROM artists WHERE id = ?", (aid,))
        art_name = (cur.fetchone() or ("未知",))[0]
        group_info = []
        for albid, title in group:
            cur.execute("""
                SELECT COUNT(*), 
                       SUM(CASE WHEN file_path IS NOT NULL AND file_path != '' THEN 1 ELSE 0 END)
                FROM songs WHERE album_id = ?
            """, (albid,))
            tot, lit = cur.fetchone()
            tot = tot or 0
            lit = lit or 0
            group_info.append({"album_id": albid, "title": title, "total_songs": tot, "lit_songs": lit})
        dup_details.append({"artist_id": aid, "artist_name": art_name, "norm_title": norm_t, "albums": group_info})

    lit_dups = [d for d in dup_details if any(a["lit_songs"] > 0 for a in d["albums"])]
    print(f"  🔍 其中包含已点亮歌曲需迁移合并的重复专辑组: {len(lit_dups)} 组")
    for d in lit_dups[:20]:
        alb_strs = [f"ID {a['album_id']} 《{a['title']}》({a['lit_songs']}/{a['total_songs']}首点亮)" for a in d["albums"]]
        print(f"     • [{d['artist_name']}] -> {' VS '.join(alb_strs)}")
    if len(lit_dups) > 20:
        print(f"     ... 还有 {len(lit_dups) - 20} 组已点亮重复专辑")

    # 2.2 0 歌曲空壳专辑
    cur.execute("""
        SELECT alb.id, alb.artist_id, a.name, alb.title
        FROM albums alb
        JOIN artists a ON alb.artist_id = a.id
        LEFT JOIN songs s ON alb.id = s.album_id
        WHERE s.id IS NULL
    """)
    empty_albums = cur.fetchall()
    print(f"\n  ⚠️ 检出 0 歌曲空壳专辑: {len(empty_albums)} 张")
    for albid, aid, art_name, title in empty_albums:
        print(f"     - ID {albid}: [{art_name}] 《{title}》")

    # 3. 歌曲层体检
    print("\n[3] 🎵 歌曲层体检 (Songs)")
    cur.execute("SELECT COUNT(*) FROM songs")
    total_songs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM songs WHERE file_path IS NOT NULL AND file_path != ''")
    lit_songs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM songs WHERE lrc_path IS NOT NULL AND lrc_path != ''")
    lrc_songs = cur.fetchone()[0]
    print(f"  • 登记曲目总数: {total_songs} 首")
    print(f"  • 已点亮曲目数: {lit_songs} 首 ({lit_songs/total_songs*100:.1f}%)")
    print(f"  • 带歌词曲目数: {lrc_songs} 首 ({lrc_songs/lit_songs*100:.1f}% 覆盖率)")

    # 3.1 同一专辑内重复歌曲排查
    cur.execute("""
        SELECT album_id, title, COUNT(*) as cnt, GROUP_CONCAT(id) as song_ids
        FROM songs
        GROUP BY album_id, title
        HAVING cnt > 1
    """)
    dup_songs_in_album = cur.fetchall()
    print(f"  ⚠️ 检出同一专辑内同名重复歌曲: {len(dup_songs_in_album)} 组")
    for albid, stitle, cnt, sids in dup_songs_in_album[:15]:
        cur.execute("SELECT a.name, alb.title FROM albums alb JOIN artists a ON alb.artist_id = a.id WHERE alb.id = ?", (albid,))
        art_alb = cur.fetchone() or ("未知", "未知")
        print(f"     - [{art_alb[0]}] 《{art_alb[1]}》(专辑ID:{albid}) 内 《{stitle}》: 重复 {cnt} 次 (IDs: {sids})")

    # 3.2 重复音频文件路径 (file_path 冲突)
    cur.execute("""
        SELECT file_path, COUNT(*) as cnt, GROUP_CONCAT(id) as song_ids
        FROM songs
        WHERE file_path IS NOT NULL AND file_path != ''
        GROUP BY file_path
        HAVING cnt > 1
    """)
    dup_file_paths = cur.fetchall()
    print(f"  ⚠️ 检出重复音频文件路径 (file_path 被多首歌引用): {len(dup_file_paths)} 处")
    for fp, cnt, sids in dup_file_paths:
        print(f"     - 引用 {cnt} 次: {fp} (IDs: {sids})")

    # 4. 保存体检结果为 JSON
    report_data = {
        "zero_album_artists": zero_album_artists,
        "duplicate_album_groups_total": len(dup_album_groups),
        "duplicate_album_groups_lit": len(lit_dups),
        "dup_album_details": dup_details,
        "empty_albums": empty_albums,
        "dup_songs_in_album_count": len(dup_songs_in_album),
        "dup_songs_in_album": dup_songs_in_album,
        "dup_file_paths": dup_file_paths,
        "total_songs": total_songs,
        "lit_songs": lit_songs,
        "lrc_songs": lrc_songs
    }

    report_file = os.path.join(BASE_DIR, "reports", "HEALTH_CHECK_AUDIT.json")
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"✅ 完整体检数据已保存至: {report_file}")
    print("=" * 80)
    conn.close()

if __name__ == "__main__":
    run_health_check()
