import requests

def search_song(name):
    url = "https://music.163.com/api/search/get/web"
    params = {'s': f"童安格 {name}", 'type': 1, 'limit': 3}
    r = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}).json()
    songs = r.get('result', {}).get('songs', [])
    if songs:
        s = songs[0]
        al = s.get('album', {})
        print(f"{name:12s} -> SongID: {s['id']:<10} | Album: {al.get('name')} (AlbumID: {al.get('id')}) | Dur: {s.get('duration', 0)//1000}s")
        return s['id']
    else:
        print(f"{name:12s} -> Not Found")
        return None

if __name__ == '__main__':
    print("=== 《梦开始的地方》 (1989) 歌曲检索 ===")
    tracks_meng = [
        "梦开始的地方", "耶利亚女郎", "借我一点爱", "今天的我", 
        "跨过彩虹", "汇流", "诀别", "我曾经爱过", "根本都没做", "努力"
    ]
    for t in tracks_meng:
        search_song(t)

    print("\n=== 《花瓣雨》 (1990) 歌曲检索 ===")
    tracks_hua = [
        "花瓣雨", "你我的爱只能擦肩而过", "晚归的丈夫", "那一段日子", 
        "把根留住", "尘埃", "爱情终究是一场难圆的梦", "无所谓的歌", 
        "香水城", "爱的主题曲", "跨越彩虹"
    ]
    for t in tracks_hua:
        search_song(t)

    print("\n=== 《一世情缘》 (1991) 歌曲检索 ===")
    tracks_yi = [
        "一世情缘", "留声机恋曲", "回首的梦", "永远为了你", 
        "痴心", "游戏与诺言", "伤感列车", "夜色", "梦已遥远", "扑火的飞蛾"
    ]
    for t in tracks_yi:
        search_song(t)
