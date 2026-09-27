import requests, sys
sys.stdout.reconfigure(encoding='utf-8')

song_ids = [
    (150992, "其实你不懂我的心"), (150994, "让生命等候"), (150996, "明天你是否依然爱我"),
    (150999, "飞雪"), (151002, "别离歌"), (151005, "忘不了"),
    (151007, "干燥花"), (151009, "永远不要说放弃"), (151011, "看不清的未来"),
    (151014, "爱,让世界更美"), (151017, "扑克先生"), (151021, "灯")
]

for nid, title in song_ids:
    r = requests.get(f"https://music.163.com/api/song/lyric?os=pc&id={nid}&lv=-1&kv=-1&tv=-1", headers={'User-Agent': 'Mozilla/5.0'}).json()
    lrc = r.get('lrc', {}).get('lyric', '').strip()
    has_sync = "[00:" in lrc
    print(f"[{nid}] 《{title}》: {len(lrc)} chars | has sync: {has_sync}")
