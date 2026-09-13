#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - D1 云端生产数据库 100% 真实状态体检脚本
直接从 https://m-api.changgepd.ccwu.cc/api/songs 与 /api/skeleton 提取生产全量数据进行体检：
1. 生产环境中实际展示给用户的歌手、专辑、歌曲
2. 重复专辑（同一歌手下多个同名专辑）
3. 0歌曲空专辑
4. 同专辑内重复歌曲
5. 点亮歌曲与歌词覆盖率
6. 重复音轨路径
"""

import sys
import json
import requests
import re
from collections import defaultdict

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

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

def run_d1_audit():
    print("=" * 80)
    print("🌐 开始拉取 Cloudflare D1 生产环境真实全量数据...")
    resp = requests.get('https://m-api.changgepd.ccwu.cc/api/songs', timeout=30)
    if resp.status_code != 200:
        print(f"❌ 拉取失败: {resp.status_code}")
        return
    
    data = resp.json().get('data', [])
    print(f"✅ 拉取成功! 共有 {len(data)} 位歌手数据")
    print("=" * 80)

    total_artists = len(data)
    total_albums = 0
    total_songs = 0
    lit_songs = 0
    lrc_songs = 0

    zero_album_artists = []
    empty_albums = []
    dup_albums_per_artist = []
    dup_songs_in_album = []
    file_path_counts = defaultdict(list)

    for art in data:
        art_id = art.get('id')
        art_name = art.get('name')
        albums = art.get('albums', [])
        total_albums += len(albums)

        if not albums:
            zero_album_artists.append((art_id, art_name))
            continue

        # 检查同一歌手下的重复专辑
        alb_norm_map = defaultdict(list)
        for alb in albums:
            alb_title = alb.get('title', '')
            songs = alb.get('songs', [])
            total_songs += len(songs)

            lit_in_alb = 0
            song_titles_in_alb = defaultdict(list)
            for s in songs:
                s_title = s.get('title', '')
                fp = s.get('path')
                lp = s.get('lrc_path')
                if fp:
                    lit_songs += 1
                    lit_in_alb += 1
                    file_path_counts[fp].append(f"[{art_name}]《{alb_title}》-《{s_title}》")
                if lp:
                    lrc_songs += 1
                song_titles_in_alb[normalize_title(s_title)].append(s_title)

            # 检查专辑内重复歌曲
            for norm_st, st_list in song_titles_in_alb.items():
                if len(st_list) > 1:
                    dup_songs_in_album.append({
                        "artist": art_name,
                        "album": alb_title,
                        "norm_title": norm_st,
                        "count": len(st_list),
                        "titles": st_list
                    })

            if len(songs) == 0:
                empty_albums.append({
                    "artist": art_name,
                    "album": alb_title,
                    "year": alb.get('year')
                })

            alb_norm_map[normalize_title(alb_title)].append({
                "title": alb_title,
                "year": alb.get('year'),
                "total_songs": len(songs),
                "lit_songs": lit_in_alb
            })

        for norm_at, alb_list in alb_norm_map.items():
            if len(alb_list) > 1:
                dup_albums_per_artist.append({
                    "artist": art_name,
                    "artist_id": art_id,
                    "norm_title": norm_at,
                    "albums": alb_list
                })

    print(f"\n📊 【Cloudflare D1 生产总体指标】:")
    print(f"  • 歌手总数: {total_artists}")
    print(f"  • 专辑总数: {total_albums}")
    print(f"  • 歌曲总数: {total_songs}")
    print(f"  • 已点亮歌曲: {lit_songs} ({lit_songs/total_songs*100:.1f}%)")
    print(f"  • 歌词覆盖: {lrc_songs} ({lrc_songs/lit_songs*100:.1f}% 覆盖率)")

    print(f"\n⚠️ 【1. 空壳歌手 (0 专辑)】: {len(zero_album_artists)} 位")
    for a in zero_album_artists:
        print(f"   - {a[0]}: {a[1]}")

    print(f"\n⚠️ 【2. 0 歌曲空专辑】: {len(empty_albums)} 张")
    for a in empty_albums:
        print(f"   - [{a['artist']}] 《{a['album']}》 ({a['year']})")

    print(f"\n⚠️ 【3. 生产端同名重复专辑 (同一歌手名下)】: {len(dup_albums_per_artist)} 组")
    for d in dup_albums_per_artist:
        alb_desc = " VS ".join([f"《{a['title']}》({a['lit_songs']}/{a['total_songs']}首点亮, {a['year']})" for a in d['albums']])
        print(f"   • [{d['artist']}] -> {alb_desc}")

    print(f"\n⚠️ 【4. 专辑内同名重复歌曲】: {len(dup_songs_in_album)} 组")
    for s in dup_songs_in_album[:10]:
        print(f"   - [{s['artist']}] 《{s['album']}》 内 《{s['norm_title']}》 重复 {s['count']} 次")
    if len(dup_songs_in_album) > 10:
        print(f"   ... 还有 {len(dup_songs_in_album) - 10} 组")

    dup_fps = {k: v for k, v in file_path_counts.items() if len(v) > 1}
    print(f"\n⚠️ 【5. 重复音频文件路径 (多首不同歌曲指向同一 URL)】: {len(dup_fps)} 处")
    for fp, refs in dup_fps.items():
        print(f"   - {fp} 被引用 {len(refs)} 次: {refs}")

    import os
    os.makedirs('backend/reports', exist_ok=True)
    with open('backend/reports/D1_LIVE_AUDIT.json', 'w', encoding='utf-8') as f:
        json.dump({
            "total_artists": total_artists,
            "total_albums": total_albums,
            "total_songs": total_songs,
            "lit_songs": lit_songs,
            "lrc_songs": lrc_songs,
            "zero_album_artists": zero_album_artists,
            "empty_albums": empty_albums,
            "dup_albums_per_artist": dup_albums_per_artist,
            "dup_songs_in_album": dup_songs_in_album,
            "dup_fps": dup_fps
        }, f, ensure_ascii=False, indent=2)
    print("\n✅ 真实审计报告已保存至 reports/D1_LIVE_AUDIT.json")

if __name__ == "__main__":
    run_d1_audit()
