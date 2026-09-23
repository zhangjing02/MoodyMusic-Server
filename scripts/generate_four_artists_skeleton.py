# -*- coding: utf-8 -*-
"""
generate_four_artists_skeleton.py
精准抓取 4 位华语传奇歌手（刘若英、小虎队、谭维维、林志炫）
共计 45 张核心录音室大碟及全部完整曲目，并标注【大热专辑】标签。
"""
import requests
import json
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com/'
}

# 权威精选的 45 张大碟配置映射（按专辑ID精确匹配曲目）
ARTISTS_CONFIG = [
    {
        "name": "刘若英",
        "artist_id_163": 8326,
        "avatar_url": "http://p2.music.126.net/lkPWuNPoa9ood4pJiXURxA==/109951167974416547.jpg",
        "albums": [
            {"id": 25444, "title": "少女小渔刘若英的美丽与哀愁", "year": "1995", "is_hot": False},
            {"id": 25442, "title": "雨季", "year": "1995", "is_hot": False},
            {"id": 25439, "title": "到处乱走", "year": "1996", "is_hot": False},
            {"id": 25438, "title": "很爱很爱你", "year": "1998", "is_hot": True},
            {"id": 25437, "title": "我等你", "year": "2000", "is_hot": True},
            {"id": 25436, "title": "年华", "year": "2001", "is_hot": True},
            {"id": 25430, "title": "收获 新歌+精选", "year": "2001", "is_hot": True},
            {"id": 25427, "title": "Love and the City", "year": "2002", "is_hot": True},
            {"id": 25414, "title": "我的失败与伟大", "year": "2003", "is_hot": False},
            {"id": 25408, "title": "听说？", "year": "2004", "is_hot": False},
            {"id": 25403, "title": "一整夜", "year": "2005", "is_hot": False},
            {"id": 25399, "title": "我很好", "year": "2008", "is_hot": False},
            {"id": 25389, "title": "在一起", "year": "2010", "is_hot": True},
            {"id": 2423021, "title": "亲爱的路人", "year": "2013", "is_hot": False},
            {"id": 125146619, "title": "各自安好", "year": "2021", "is_hot": True}
        ]
    },
    {
        "name": "小虎队",
        "artist_id_163": 13286,
        "avatar_url": "http://p1.music.126.net/voZEMSHx4W23weBI_fu4cA==/109951170501514593.jpg",
        "albums": [
            {"id": 38439, "title": "新年快乐", "year": "1989", "is_hot": True},
            {"id": 38438, "title": "逍遥游", "year": "1989", "is_hot": True},
            {"id": 38436, "title": "男孩不哭", "year": "1989", "is_hot": False},
            {"id": 81982285, "title": "红蜻蜓", "year": "1990", "is_hot": True},
            {"id": 38431, "title": "星星的约会", "year": "1990", "is_hot": True},
            {"id": 38429, "title": "爱", "year": "1991", "is_hot": True},
            {"id": 38426, "title": "再见", "year": "1991", "is_hot": True},
            {"id": 38419, "title": "星光依旧灿烂", "year": "1993", "is_hot": True},
            {"id": 38415, "title": "快乐的感觉永远一样", "year": "1994", "is_hot": False},
            {"id": 38411, "title": "庸人自扰", "year": "1995", "is_hot": False}
        ]
    },
    {
        "name": "谭维维",
        "artist_id_163": 9489,
        "avatar_url": "http://p2.music.126.net/CfxqOLswiU8APLIxo0pCPw==/109951165761619079.jpg",
        "albums": [
            {"id": 29202, "title": "高原之心", "year": "2005", "is_hot": False},
            {"id": 29199, "title": "耳界", "year": "2007", "is_hot": True},
            {"id": 29196, "title": "传说", "year": "2009", "is_hot": False},
            {"id": 29193, "title": "谭某某", "year": "2010", "is_hot": True},
            {"id": 29183, "title": "3", "year": "2011", "is_hot": False},
            {"id": 2685007, "title": "乌龟的阿基里斯", "year": "2013", "is_hot": False},
            {"id": 99378512, "title": "3811", "year": "2020", "is_hot": True},
            {"id": 96678260, "title": "姐放3811", "year": "2020", "is_hot": False}
        ]
    },
    {
        "name": "林志炫",
        "artist_id_163": 3692,
        "avatar_url": "http://p1.music.126.net/V0TLPlWSkpFuZPsbDBJv1w==/109951173481193938.jpg",
        "albums": [
            {"id": 10922, "title": "一个人的样子", "year": "1995", "is_hot": False},
            {"id": 10917, "title": "追寻伦敦星空下", "year": "1996", "is_hot": False},
            {"id": 10911, "title": "散了吧", "year": "1997", "is_hot": True},
            {"id": 10907, "title": "蒙娜丽莎的眼泪", "year": "1998", "is_hot": True},
            {"id": 10895, "title": "单身情歌 超炫精选", "year": "1999", "is_hot": True},
            {"id": 10889, "title": "擦声而过", "year": "2001", "is_hot": True},
            {"id": 10885, "title": "时间的味道", "year": "2002", "is_hot": False},
            {"id": 10881, "title": "至情志炫", "year": "2004", "is_hot": True},
            {"id": 10879, "title": "熟情歌", "year": "2005", "is_hot": False},
            {"id": 10876, "title": "原声之旅", "year": "2005", "is_hot": False},
            {"id": 10871, "title": "擦声而过 2", "year": "2008", "is_hot": True},
            {"id": 97409474, "title": "ONEtake 2.0", "year": "2020", "is_hot": False}
        ]
    }
]

def fetch_album_details(artist_name, album_id, album_title):
    pic_url = None
    song_titles = []
    
    # 1. 尝试 163 v1 接口
    try:
        url_v1 = f"http://music.163.com/api/v1/album/{album_id}"
        resp = requests.get(url_v1, headers=headers, timeout=10).json()
        alb = resp.get('album', {})
        pic_url = alb.get('picUrl')
        songs_raw = resp.get('songs', []) or alb.get('songs', [])
        for s in songs_raw:
            st = s.get('name', '').strip()
            if st and st not in song_titles:
                song_titles.append(st)
    except Exception as e:
        pass

    # 2. 若 163 歌曲为空，使用 QQ 音乐精准解析
    if not song_titles:
        try:
            q = f"{artist_name} {album_title}"
            qq_search_url = f"https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w={requests.utils.quote(q)}&format=json&t=8"
            rq = requests.get(qq_search_url, timeout=10).json()
            albs = rq.get('data', {}).get('album', {}).get('list', [])
            matched_mid = None
            for a in albs:
                a_name = a.get('albumName', '').strip()
                s_name = a.get('singerName', '').strip()
                if (album_title.lower() in a_name.lower() or a_name.lower() in album_title.lower()) and (artist_name in s_name):
                    matched_mid = a.get('albumMID')
                    if not pic_url:
                        pic_url = a.get('albumPic')
                    break
            if not matched_mid and albs:
                matched_mid = albs[0].get('albumMID')
                if not pic_url:
                    pic_url = albs[0].get('albumPic')

            if matched_mid:
                qq_detail = f"https://c.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg?albummid={matched_mid}&format=json"
                rd = requests.get(qq_detail, timeout=10).json()
                for s in rd.get('data', {}).get('list', []):
                    st = s.get('songname', '').strip()
                    if st and st not in song_titles:
                        song_titles.append(st)
        except Exception as e:
            pass

    return pic_url, song_titles

def main():
    print("=" * 80)
    print("🚀 启动 4 位传奇歌手全量核心专辑及曲目详情抓取")
    print("=" * 80)

    result_data = []
    total_albums = 0
    total_songs = 0
    total_hot_albums = 0

    for artist_cfg in ARTISTS_CONFIG:
        art_name = artist_cfg["name"]
        print(f"\n🎤 正在提取艺人: {art_name}...")
        artist_obj = {
            "artist_name": art_name,
            "avatar_url": artist_cfg["avatar_url"],
            "albums": []
        }

        for alb_cfg in artist_cfg["albums"]:
            alb_id = alb_cfg["id"]
            title = alb_cfg["title"]
            year = alb_cfg["year"]
            is_hot = alb_cfg["is_hot"]
            if is_hot:
                total_hot_albums += 1

            print(f"   💿 抓取专辑: 《{title}》 ({year}年) [{'🔥大热' if is_hot else '常规'}]...", end="", flush=True)
            pic_url, songs = fetch_album_details(art_name, alb_id, title)
            print(f" 获得封面与 {len(songs)} 首曲目 ✅")

            total_albums += 1
            total_songs += len(songs)

            artist_obj["albums"].append({
                "title": title,
                "year": year,
                "cover_url": pic_url,
                "is_hot": is_hot,
                "genre": "大热流行" if is_hot else "华语流行",
                "songs": songs
            })
            time.sleep(0.3)

        result_data.append(artist_obj)

    out_file = r"e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts\configs\four_new_artists_skeleton.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("🎉 抓取并构建完成！")
    print(f"📦 导出文件: {out_file}")
    print(f"✨ 艺人总数: {len(result_data)} 位")
    print(f"✨ 专辑总数: {total_albums} 张 (其中 🔥大热专辑: {total_hot_albums} 张)")
    print(f"✨ 曲目总数: {total_songs} 首")
    print("=" * 80)

if __name__ == '__main__':
    main()
