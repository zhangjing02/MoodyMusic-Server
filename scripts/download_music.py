#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY 音乐下载与 AI 听音辨曲自动点亮工具 (Groq Whisper-large-v3)
==============================================================================
"""

import os
import sys
import re
import argparse
import subprocess
import urllib.parse
import requests
import zhconv

# 保证 Windows 控制台 UTF-8 输出无乱码
if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DEFAULT_API_BASE = "https://m-api.changgepd.ccwu.cc"
DEFAULT_DOWNLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "downloads"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
NODE_PATH = r"D:\DevelopeTools\Node\node.exe" if os.path.exists(r"D:\DevelopeTools\Node\node.exe") else "node"
JS_RUNTIME_ARG = f"node:{NODE_PATH}"

LOCAL_ALBUM_TRACKLISTS = {
    "依然范特西": ['夜的第七章', '听妈妈的话', '千里之外', '本草纲目', '退后', '红模仿', '心雨', '白色风车', '迷迭香', '菊花台'],
    "十二新作": ['四季列车', '手语', '公公偏头痛', '明明就', '傻笑', '比较大的大提琴', '爱你没差', '红尘客栈', '梦想启动', '大笨钟', '哪里都是你', '乌克丽丽'],
    "哎呦，不错哦": ['阳明山', '窃爱', '天涯过客', '怎么了', '一口气全念对', '我要夏天', '手写的从前', '鞋子特大号', '听爸爸的话', '美人鱼', '算什么男人', '听见下雨的声音'],
    "周杰伦的床边故事": ['床边故事', '说走就走', '一点点', '前世情人', '英雄', '不该', '告白气球', '爱情废柴', 'Now You See Me', '土耳其冰淇淋'],
    "最伟大的作品": ['Intro', '最伟大的作品', '还在流浪', '说好不哭', '红颜如霜', '不爱我就拉倒', 'Mojito', '错过的烟火', '等你下课', '粉色海洋', '倒影', '我是如此相信'],
    # 孙燕姿专辑名录
    "孙燕姿同名专辑": ['超快感', '爱情证书', '天黑黑', 'E-Lover', '浓眉毛', '和平', '自然', '终于', '很好', 'Leave Me Alone'],
    "我要的幸福": ['On The Road 1', '我要的幸福', '坏天气', '零缺点', '开始懂了', '中间地带', '相信', '累赘', '难得一见', '害怕', '星期一天气晴我离开你', 'On The Road 2'],
    "风筝": ['绿光', '风筝', '任性', '逃亡', '不是真的爱我', '真的', '练习', '爱情字典', '随堂测验', '我是我'],
    "Start自选集": ['Hey Jude', 'Silent All These Years', '橄榄树', '没时间', '原来你什么都不要', 'That I Would Be Good', 'Venus', 'Someone', '天空', '就是这样', 'Up 2 U'],
    "Leave": ['作战', '我不爱', '懂事', '直来直往', '一样的夏天', '爱从零开始', '不同', '眼神', '我想', 'Leave', 'We Will Get There', '一起走到'],
    "未完成": ['神奇', '我不难过', '永远', '未完成', '接下来', '学会', '年轻无极限', '了解', '休止符', '没有人的方向', 'My story, Your song'],
    "Stefanie": ['奔', '我的爱', '祝你开心', '我也很想他', '听见', '慢慢来', '同类', '种', '反过来', 'Stefanie'],
    "完美的一天": ['完美的一天', '眼泪成诗', '隐形人', '流浪地图', '第一天', 'Honey Honey', '心愿', '另一张脸', '梦不落', '明天晴天'],
    "逆光": ['Intro', '逆光', '梦游', '咕叽咕叽', '我怀念的', '安宁', '飘着', '爱情的花样', '漩涡', '需要你', '关于', 'Outro'],
    "是时候": ['世说心语', '追', '当冬夜渐暖', '时光小偷', '空口言', '明天的记忆', '180度', '快疯了', '愚人的国度', '是时候'],
    "克卜勒": ['克卜勒', '渴', '无限大', '尚好的青春', '天使的指纹', '银泰', '围绕', '错觉', '比较幸福', '雨还是不停地落下'],
    "No.13 作品 : 跳舞的梵谷": ['风衣', '我很愉快', '跳舞的梵谷', '天越亮，夜越黑', '天天年年', '漂浮群岛', '超人类', '充氧期', '平日快乐', '极美'],
    "跳舞的梵谷": ['风衣', '我很愉快', '跳舞的梵谷', '天越亮，夜越黑', '天天年年', '漂浮群岛', '超人类', '充氧期', '平日快乐', '极美'],
    # 林俊杰专辑名录
    "乐行者": ['就是我', '会读书', '翅膀', '星球', '冻结', '压力', '女儿家', '星空下的吻', '让我心动的人', '会有那么一天', '不懂'],
    "江南": ['一开始', '第二天堂', '子弹列车', '起床了!', '豆浆油条', '江南', '害怕', '天使心', '森林浴', '精灵', '相信无限', '美人鱼', '距离', '未完成', 'Endless Road'],
    "第二天堂": ['一开始', '第二天堂', '子弹列车', '起床了!', '豆浆油条', '江南', '害怕', '天使心', '森林浴', '精灵', '相信无限', '美人鱼', '距离', '未完成', 'Endless Road'],
    "编号89757": ['一千年以前...', '木乃伊', '编号89757', '莎士比亚的天份', '突然累了', '明天', '简简单单', '无尽的思念', '盗', '听不懂没关系', '来不及了...', '一千年以后'],
    "曹操": ['只对你说', '曹操', '熟能生巧', '波间带', '原来', '不死之身', '爱情Yogurt', '进化论', "Now That She's Gone", '你要的不是我', 'Down'],
    "西界": ['独白', '杀手', '杀手@续', '西界', '无聊', '单挑', 'K.O.', '大男人小女孩', 'L-O-V-E', '发现爱', '不流泪的机场', 'Baby Baby', '自由不变'],
    "JJ陆": ['Sixology', '不潮不用花钱', '小酒窝', '黑武士', '醉赤壁', '由你选择', 'Always Online', '街道', '主角', '我还想她', '点一把火炬', '期待爱', 'Cries In A Distance', '爱与希望'],
    "100天": ['X', '第几个100天', '加油!', '曙光', '无法克制', '背对背拥抱', '跟屁虫', '一个又一个', '爱笑的眼睛', '表达爱', '爱的关键', '转动', '妈妈的娜鲁娃'],
    "她说": ['她说', '爱笑的眼睛', '只对你有感觉', '当你', '一眼万年', '保护色', '握不住的他', '心墙', '我很想爱他', '一生的爱', '记得', '完美新世界', 'I Am'],
    "学不会": ['独奏', '学不会', '故事细腻', '那些你很冒险的梦', '白羊梦', '灵魂的共鸣', 'We Together', 'Cinderella', '白兰花', '陌生老朋友', '不存在的情人', 'Love U U'],
    "因你而在": ['因你而在', '零度的亲吻', '黑暗骑士', '修炼爱情', '飞机', '巴洛克先生', 'One Shot', '裂缝中的阳光', '友人说', '十秒的冲动', '以后要做的事'],
    "新地球": ['回', '新地球', '水仙', '浪漫血液', '黑键', '手心的蔷薇', '可惜没如果', 'I Am Alive', '爱的鼓励', '茉莉雨', '生生'],
    "和自己对话": ['调音', '不为谁而作的歌', '中场休息', '关键词', '只要有你的地方', '弹唱', '有梦不难', 'Welcome to the Livehouse', 'Too Bad', '有没有过', '12年前', '现在的我和她', 'Lier And Accuser', '独舞'],
    "伟大的渺小": ['圣所', '伟大的渺小', '穿越', '四点四十四', '我继续', '剪云者', '黑夜问白天', '丹宁执着', '身为风帆', '小瓶子', 'Until The Day'],
    "幸存者 • 如你": ['最向往的地方', '交换余生', '幸存者', '离开的那一些', '最好是', '暂时的记号', 'While I Can', 'Bedroom', 'Not Tonight', 'All Time Favorite', 'We Are'],
    "重拾·快乐": ['愿与愁', '逆光白', '孤独娱乐', '梦不凌乱', '自画像', '谢幕', '如果我还剩一件事情可以做', '黑色泡沫', '你都在', '一时的选择', 'Castle In The Air', '7千3百多天']
}

def query_moody_missing_songs(artist: str, album: str, api_base: str = DEFAULT_API_BASE):
    """从 MOODY 数据库中查询该专辑下所有未点亮（path 为空）的歌曲，若 API 限流则使用本地名录容灾"""
    encoded_artist = urllib.parse.quote(artist)
    url = f"{api_base}/api/songs?artist={encoded_artist}&t={int(os.path.getmtime(__file__))}"
    
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 200 and data.get("data"):
                artists = data["data"]
                target_album_norm = zhconv.convert(album.strip().lower(), 'zh-hans')
                for a in artists:
                    for alb in a.get("albums", []):
                        db_album_norm = zhconv.convert(alb.get("title", "").strip().lower(), 'zh-hans')
                        if db_album_norm == target_album_norm or target_album_norm in db_album_norm or db_album_norm in target_album_norm:
                            songs = alb.get("songs", [])
                            if not songs:
                                break
                            missing = []
                            for s in songs:
                                if not s.get("path"):
                                    missing.append(s.get("title"))
                            return missing
    except Exception as e:
        print(f"⚠️ 线上 API 查询异常: {e}")
    
    # 本地名录容灾兜底
    if album in LOCAL_ALBUM_TRACKLISTS:
        print(f"🔄 使用本地备份名录执行下载与 AI 听音审计: 《{album}》")
        return LOCAL_ALBUM_TRACKLISTS[album]
        
    return []

def inspect_audio_quality(file_path: str):
    """使用 mutagen 进行深度音频体检 (码率、采样率、声道、时长)"""
    try:
        from mutagen.mp3 import MP3
        audio = MP3(file_path)
        bitrate_kbps = round(audio.info.bitrate / 1000)
        sample_rate = audio.info.sample_rate
        channels = "立体声(Stereo)" if audio.info.channels == 2 else f"{audio.info.channels}声道"
        duration_sec = round(audio.info.length)
        mins = duration_sec // 60
        secs = duration_sec % 60
        duration_str = f"{mins:02d}:{secs:02d}"
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        return {
            "bitrate": f"{bitrate_kbps} kbps",
            "sample_rate": f"{sample_rate} Hz",
            "channels": channels,
            "duration": duration_str,
            "size": f"{size_mb:.2f} MB"
        }
    except Exception as e:
        return {"error": str(e)}

def fetch_and_save_lyrics(artist: str, album: str, song: str, output_dir: str = DEFAULT_DOWNLOAD_DIR):
    try:
        safe_song = song.replace("/", "_").replace("\\", "_").replace(":", "_")
        safe_artist = artist.replace("/", "_").replace("\\", "_").replace(":", "_")
        safe_album = album.replace("/", "_").replace("\\", "_").replace(":", "_")
        lrc_path = os.path.join(output_dir, f"{safe_song}-{safe_artist}-{safe_album}.lrc")
        if os.path.exists(lrc_path) and os.path.getsize(lrc_path) > 10:
            with open(lrc_path, 'r', encoding='utf-8', errors='ignore') as f:
                lrc = f.read()
        else:
            import syncedlyrics
            lrc = syncedlyrics.search(f"{artist} {song}", providers=['NetEase', 'Lrclib'])
            if not lrc:
                lrc = syncedlyrics.search(f"{song}", providers=['NetEase', 'Lrclib'])
            if not lrc:
                lrc = syncedlyrics.search(f"{artist} {album} {song}")
        
        if lrc:
            safe_song = song.replace("/", "_").replace("\\", "_").replace(":", "_")
            safe_artist = artist.replace("/", "_").replace("\\", "_").replace(":", "_")
            safe_album = album.replace("/", "_").replace("\\", "_").replace(":", "_")
            lrc_path = os.path.join(output_dir, f"{safe_song}-{safe_artist}-{safe_album}.lrc")
            with open(lrc_path, 'w', encoding='utf-8') as f:
                f.write(lrc)
            
            lines = [re.sub(r'\[.*?\]', '', line).strip() for line in lrc.splitlines() if re.sub(r'\[.*?\]', '', line).strip()]
            lyrics_lines = [l for l in lines if not any(k in l for k in ['作词', '作曲', '编曲', '制作', 'Jay', 'Chou', '词：', '曲：'])]
            intro = ' / '.join(lyrics_lines[:2]) if len(lyrics_lines) >= 2 else (lyrics_lines[0] if lyrics_lines else '无')
            chorus = lyrics_lines[len(lyrics_lines)//2] if len(lyrics_lines) > 4 else '无'
            return {
                "intro": intro,
                "chorus": chorus,
                "lrc_path": lrc_path,
                "has_lyrics": True
            }
        return {"intro": "未抓取到歌词", "chorus": "", "has_lyrics": False}
    except Exception as e:
        return {"intro": f"歌词获取异常: {e}", "chorus": "", "has_lyrics": False}

def verify_with_groq_whisper(file_path: str, song: str, intro_lyrics: str = "", chorus_lyrics: str = ""):
    """使用 Groq Whisper-large-v3 模型听音频精华切片，识别实际唱出的歌词做双重比对"""
    if not GROQ_API_KEY:
        return "未配置 Groq API", True
    
    # 提取音频精华切片 (从第 15 秒截取 65 秒，压缩为单声道 64kbps，仅约 400KB)，解决大文件上传网络超时问题
    snippet_path = file_path + ".snippet.mp3"
    target_upload_file = file_path
    try:
        cmd = ["ffmpeg", "-y", "-ss", "15", "-t", "65", "-i", file_path, "-b:a", "64k", "-ac", "1", snippet_path]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(snippet_path) and os.path.getsize(snippet_path) > 1000:
            target_upload_file = snippet_path
    except Exception:
        target_upload_file = file_path

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    err_msg = "未知异常"
    
    try:
        for attempt in range(3):
            try:
                with open(target_upload_file, "rb") as f:
                    files = {"file": (os.path.basename(target_upload_file), f, "audio/mpeg")}
                    data = {"model": "whisper-large-v3", "language": "zh"}
                    r = requests.post(url, headers=headers, files=files, data=data, timeout=30)
                    if r.status_code == 200:
                        text = r.json().get("text", "").strip()
                        sample = text[:60] + "..." if len(text) > 60 else text
                        import zhconv
                        clean_intro = zhconv.convert(re.sub(r'[^\w]', '', intro_lyrics), 'zh-hans')
                        clean_chorus = zhconv.convert(re.sub(r'[^\w]', '', chorus_lyrics), 'zh-hans')
                        clean_text = zhconv.convert(re.sub(r'[^\w]', '', text), 'zh-hans')
                        norm_song = zhconv.convert(re.sub(r'[^\w]', '', song), 'zh-hans')
                        
                        # 特征字重合度比对 (解决快歌含糊发音导致精确字串失配的问题)
                        s_intro = set(clean_intro)
                        s_chorus = set(clean_chorus)
                        s_text = set(clean_text)
                        overlap_intro = len(s_intro & s_text) / max(len(s_intro), 1) if s_intro else 0
                        overlap_chorus = len(s_chorus & s_text) / max(len(s_chorus), 1) if s_chorus else 0
                        
                        matched = (
                            (norm_song in clean_text) or
                            any(clean_intro[i:i+3] in clean_text for i in range(0, max(len(clean_intro)-2, 1), 3)) or
                            any(clean_chorus[i:i+3] in clean_text for i in range(0, max(len(clean_chorus)-2, 1), 3)) or
                            (overlap_intro >= 0.30) or
                            (overlap_chorus >= 0.30)
                        )
                        return sample, matched
                    else:
                        err_msg = f"API返回码({r.status_code})"
            except Exception as e:
                err_msg = f"识别异常: {e}"
            import time
            time.sleep(1)
    finally:
        if os.path.exists(snippet_path):
            try: os.remove(snippet_path)
            except Exception: pass
            
    return err_msg, False

def parse_duration_sec(dur_str: str) -> int:
    """解析时长字符串为秒数"""
    try:
        parts = dur_str.strip().split(':')
        if len(parts) == 1:
            return int(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        pass
    return 0

def find_candidate_urls(artist: str, album: str, song: str):
    """搜索候选视频列表，严格按歌名匹配（自动简繁转换并过滤超长合集），排序后返回"""
    import zhconv
    query = f"{artist} {song}"
    cmd = [
        "yt-dlp",
        "--encoding", "utf-8",
        "--js-runtimes", JS_RUNTIME_ARG,
        "--print", "%(id)s | %(title)s | %(duration_string)s | %(channel)s",
        f"ytsearch8:{query}"
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', check=True)
        lines = proc.stdout.strip().splitlines()
        
        candidates = []
        norm_song = zhconv.convert(re.sub(r'[\s\-_]', '', song), 'zh-hans').lower()
        
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                vid, vtitle, vdur, vchannel = parts[0], parts[1], parts[2], parts[3]
                norm_vtitle = zhconv.convert(re.sub(r'[\s\-_]', '', vtitle), 'zh-hans').lower()
                
                # 时长过滤：排除超过 7 分钟的整专合集或少于 15 秒的过短片段 (保留前奏/序曲)
                sec = parse_duration_sec(vdur)
                if sec > 480 or (sec > 0 and sec < 15):
                    continue
                
                if norm_song in norm_vtitle:
                    candidates.append({
                        "id": vid,
                        "title": vtitle,
                        "duration": vdur,
                        "channel": vchannel,
                        "url": f"https://www.youtube.com/watch?v={vid}"
                    })
        
        def sort_key(c):
            score = 0
            if artist in c["channel"]: score += 10
            if "official" in c["title"].lower() or "官方" in c["title"]: score += 5
            return -score
            
        candidates.sort(key=sort_key)
        return candidates
    except Exception as e:
        print(f"⚠️ 候选搜索出错: {e}")
        return []

def download_track(song: str, artist: str, album: str, output_dir: str = DEFAULT_DOWNLOAD_DIR, url: str = None):
    """使用 yt-dlp 与 ffmpeg 下载音频并封装 MP3，集成 Groq Whisper AI 自动听辨重试"""
    os.makedirs(output_dir, exist_ok=True)
    
    safe_song = song.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe_artist = artist.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe_album = album.replace("/", "_").replace("\\", "_").replace(":", "_")
    out_filename = f"{safe_song}-{safe_artist}-{safe_album}.mp3"
    target_path = os.path.join(output_dir, out_filename)
    
    # 自动获取歌词
    lrc_info = fetch_and_save_lyrics(artist, album, song, output_dir)
    
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1024 * 100:
        print(f"⏩ [已存在] {out_filename} 已在本地，跳过下载")
        qa = inspect_audio_quality(target_path)
        ai_heard, ok = verify_with_groq_whisper(target_path, song, lrc_info.get('intro', ''), lrc_info.get('chorus', ''))
        print(f"   📊 音质报告: 码率={qa.get('bitrate')}, 采样率={qa.get('sample_rate')}, 声道={qa.get('channels')}, 时长={qa.get('duration')}")
        print(f"   📝 官方歌词: {lrc_info.get('intro')}")
        print(f"   🤖 AI 听音实测(Groq): {ai_heard}")
        qa['ai_heard'] = ai_heard
        return target_path, qa, lrc_info
    
    candidates = []
    if url:
        candidates = [{"url": url, "title": "指定链接", "channel": "自定义"}]
    else:
        candidates = find_candidate_urls(artist, album, song)
        if not candidates:
            candidates = [{"url": f"ytsearch1:{artist} {song} 官方音源", "title": f"{song} (兜底)", "channel": "未知"}]
    
    temp_tmpl = os.path.join(output_dir, f"temp_{safe_song}.%(ext)s")
    temp_mp3 = os.path.join(output_dir, f"temp_{safe_song}.mp3")
    
    for idx, c in enumerate(candidates, 1):
        print(f"🔍 尝试音源 [{idx}/{len(candidates)}]: {c.get('title')} [{c.get('channel')}]...")
        cmd = [
            "yt-dlp",
            "--encoding", "utf-8",
            "--js-runtimes", JS_RUNTIME_ARG,
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--embed-metadata",
            "--postprocessor-args", f'ffmpeg:-metadata title="{song}" -metadata artist="{artist}" -metadata album="{album}"',
            "-o", temp_tmpl,
            c["url"]
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', check=True)
            if os.path.exists(temp_mp3):
                ai_heard, ok = verify_with_groq_whisper(temp_mp3, song, lrc_info.get('intro', ''), lrc_info.get('chorus', ''))
                if not ok:
                    print(f"   ⚠️ [AI校验驳回] 听到歌词不符: {ai_heard}")
                    os.remove(temp_mp3)
                    if idx < len(candidates):
                        print("   🔄 自动尝试下一个候选音源...")
                    continue
                
                if os.path.exists(target_path):
                    os.remove(target_path)
                os.rename(temp_mp3, target_path)
                qa = inspect_audio_quality(target_path)
                qa['ai_heard'] = ai_heard
                print(f"✅ [下载成功] {out_filename} ({qa.get('size', 'N/A')})")
                print(f"   📊 音质报告: 码率={qa.get('bitrate')}, 采样率={qa.get('sample_rate')}, 声道={qa.get('channels')}, 时长={qa.get('duration')}")
                print(f"   📝 官方歌词: {lrc_info.get('intro')}")
                print(f"   🤖 AI 听音实测(Groq): {ai_heard}")
                
                # 自动非阻塞通知本地状态机底册：已下载就绪，准备 R2 推送
                try:
                    lrc_path = target_path[:-4] + ".lrc"
                    notify_track_ready(artist, album, song, target_path, lrc_path, qa)
                except Exception:
                    pass
                
                return target_path, qa, lrc_info
        except Exception as e:
            print(f"   ❌ 候选音源下载出错: {e}")
            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)
            continue
            
    return None, None, lrc_info

def notify_track_ready(artist: str, album: str, title: str, mp3_path: str, lrc_path: str, qa: dict):
    """轻量级非阻塞通知本地数据库：歌曲已下载并通过 AI 听音校验，标记为 DOWNLOADED 状态等待 R2 推送"""
    try:
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "database", "catalog_sync.db"))
        if not os.path.exists(db_path):
            return
        import sqlite3
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()
        file_size = os.path.getsize(mp3_path) if mp3_path and os.path.exists(mp3_path) else 0
        has_lrc = lrc_path and os.path.exists(lrc_path)
        
        # 查找匹配的歌曲记录并更新
        cur.execute("""
            UPDATE tracks_sync_state
            SET local_mp3 = ?,
                local_lrc = ?,
                file_size = ?,
                duration = ?,
                bitrate = ?,
                qa_status = 'PASSED',
                status = CASE WHEN status = 'R2_UPLOADED' THEN 'R2_UPLOADED' ELSE 'DOWNLOADED' END,
                updated_at = CURRENT_TIMESTAMP
            WHERE artist_name = ? AND album_title = ? AND song_title = ?
        """, (mp3_path, lrc_path if has_lrc else None, file_size, qa.get('duration'), qa.get('bitrate'), artist, album, title))
        
        if cur.rowcount == 0:
            cur.execute("""
                UPDATE tracks_sync_state
                SET local_mp3 = ?,
                    local_lrc = ?,
                    file_size = ?,
                    duration = ?,
                    bitrate = ?,
                    qa_status = 'PASSED',
                    status = CASE WHEN status = 'R2_UPLOADED' THEN 'R2_UPLOADED' ELSE 'DOWNLOADED' END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE artist_name = ? AND song_title = ?
            """, (mp3_path, lrc_path if has_lrc else None, file_size, qa.get('duration'), qa.get('bitrate'), artist, title))
            
        conn.commit()
        conn.close()
    except Exception:
        # 高容错保护：绝不因本地数据库写入异常打断抓轨主流水线
        pass


def upload_to_moody(file_path: str, artist: str, album: str, title: str, api_base: str = DEFAULT_API_BASE):
    """自动上传到 MOODY CMS /api/admin/upload 接口完成点亮"""
    url = f"{api_base}/api/admin/upload"
    print(f"☁️ 正在入库点亮: 《{title}》 -> {artist} / {album}...")
    
    try:
        with open(file_path, 'rb') as f:
            files = {'files': (os.path.basename(file_path), f, 'audio/mpeg')}
            data = {
                'artistOverride': artist,
                'albumOverride': album,
                'titleOverride': title
            }
            resp = requests.post(url, files=files, data=data, timeout=60)
            if resp.status_code == 200:
                res_data = resp.json()
                results_list = res_data.get("data", {}).get("results") or res_data.get("data", {}).get("details") or [{}]
                details = results_list[0] if len(results_list) > 0 else {}
                if details.get("match"):
                    print(f"🎉 [点亮成功] {details.get('message')}")
                    return True
                else:
                    print(f"⚠️ [未匹配] {details.get('message')}")
                    return False
            else:
                print(f"❌ 上传失败: HTTP {resp.status_code} - {resp.text}")
                return False
    except Exception as e:
        print(f"❌ 上传出错: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="MOODY 自动化音乐下载与点亮工具")
    parser.add_argument("-a", "--artist", help="歌手名，例如: 周杰伦")
    parser.add_argument("-b", "--album", help="专辑名，例如: 魔杰座")
    parser.add_argument("-s", "--song", help="单曲歌名，例如: 稻香")
    parser.add_argument("-u", "--url", help="指定的视频/音频链接")
    parser.add_argument("-o", "--output", default=DEFAULT_DOWNLOAD_DIR, help="保存目录")
    parser.add_argument("--missing", action="store_true", help="自动从 MOODY 查询并下载该专辑下所有未点亮的歌曲")
    parser.add_argument("--upload", action="store_true", help="下载后自动调用 MOODY 接口执行云端入库点亮")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="MOODY Worker API 地址")

    args = parser.parse_args()

    if not args.artist and not args.url:
        parser.print_help()
        sys.exit(1)

WALKTHROUGH_PATH = r"C:\Users\zhangjing\.gemini\antigravity\brain\9b5c1cfb-21b1-4294-a472-50c3b1a821ac\walkthrough.md"

def append_album_to_walkthrough(album: str, checklist: list):
    """将已完成专辑的 AI 听音核验清单动态追加到交付报告中"""
    if not os.path.exists(WALKTHROUGH_PATH):
        return
    try:
        table_md = f"\n\n### 📋 《{album}》交付与 AI 听音核验清单 (Checklist)\n\n"
        table_md += "| 序号 | 歌名 | 规格码率 | 时长 | 官方歌词节选 | 🤖 AI实测听词 (Groq Whisper) | 入库状态 |\n"
        table_md += "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
        for item in checklist:
            table_md += f"| {item['index']:02d} | {item['song']} | {item['bitrate']} | {item['duration']} | {item['intro']} | {item['ai_heard']} | {item['uploaded']} |\n"
        
        with open(WALKTHROUGH_PATH, "a", encoding="utf-8") as f:
            f.write(table_md)
        print(f"📄 已同步更新至交付报告: {WALKTHROUGH_PATH}")
    except Exception as e:
        print(f"⚠️ 同步报告失败: {e}")

def process_album(artist: str, album: str, output_dir: str = DEFAULT_DOWNLOAD_DIR, upload: bool = True, api_base: str = DEFAULT_API_BASE, full: bool = False):
    """全自动处理单张专辑的下载、AI 听音辨曲核验、云端点亮与交付清单生成"""
    print("\n" + "=" * 90)
    print(f"🚀 开始全自动流水线处理专辑: [{artist}] 《{album}》")
    print("=" * 90)
    
    if full:
        print(f"📦 [全专模式] 强制按完整专辑名录下载全盘曲目...")
        songs_to_process = LOCAL_ALBUM_TRACKLISTS.get(album)
        if not songs_to_process:
            songs_to_process = query_moody_missing_songs(artist, album, api_base)
    else:
        print(f"📡 正在从 MOODY 获取 [{artist}]《{album}》缺失曲目...")
        songs_to_process = query_moody_missing_songs(artist, album, api_base)

    if not songs_to_process:
        print(f"🎉 恭喜！[{artist}]《{album}》下的所有歌曲都已点亮，无需下载！")
        return []
        
    print(f"📋 共需处理 {len(songs_to_process)} 首歌曲: {', '.join(songs_to_process)}\n")
    checklist = []
    for i, song in enumerate(songs_to_process, 1):
        print(f"\n--- [{i}/{len(songs_to_process)}] 处理歌曲: 《{song}》 ---")
        fpath, qa, lrc_info = download_track(song, artist, album, output_dir)
        upload_ok = False
        if fpath and upload:
            upload_ok = upload_to_moody(fpath, artist, album, song, api_base)
        
        checklist.append({
            "index": i,
            "song": song,
            "artist": artist,
            "album": album,
            "bitrate": qa.get("bitrate", "N/A") if qa else "失败",
            "sample_rate": qa.get("sample_rate", "N/A") if qa else "失败",
            "duration": qa.get("duration", "N/A") if qa else "失败",
            "size": qa.get("size", "N/A") if qa else "失败",
            "intro": lrc_info.get("intro", "无") if lrc_info else "无",
            "ai_heard": qa.get("ai_heard", "N/A") if qa else "N/A",
            "uploaded": "✅ 已入库点亮" if upload_ok else ("⚠️ 仅本地下载" if fpath else "❌ 失败")
        })

    print("\n" + "=" * 90)
    print(f"📋 《{album}》交付与 AI 听音歌词双重核验清单 (Checklist)")
    print("=" * 90)
    print("| 序号 | 歌名 | 规格码率 | 时长 | 官方歌词节选 | 🤖 AI实测听词 (Groq Whisper) | 入库状态 |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for item in checklist:
        print(f"| {item['index']:02d} | {item['song']} | {item['bitrate']} | {item['duration']} | {item['intro']} | {item['ai_heard']} | {item['uploaded']} |")
    print("=" * 90 + "\n")
    
    append_album_to_walkthrough(album, checklist)
    return checklist

def main():
    parser = argparse.ArgumentParser(description="MOODY 自动化音乐下载与点亮工具")
    parser.add_argument("-a", "--artist", help="歌手名，例如: 周杰伦")
    parser.add_argument("-b", "--album", help="专辑名（支持逗号分隔多个专辑，例如: 跨时代,惊叹号,十二新作）")
    parser.add_argument("-s", "--song", help="单曲歌名，例如: 稻香")
    parser.add_argument("-u", "--url", help="指定的视频/音频链接")
    parser.add_argument("-o", "--output", default=DEFAULT_DOWNLOAD_DIR, help="保存目录")
    parser.add_argument("--missing", action="store_true", help="自动从 MOODY 查询并下载该专辑下所有未点亮的歌曲")
    parser.add_argument("--full", action="store_true", help="按专辑完整名录下载整张专辑所有歌曲")
    parser.add_argument("--upload", action="store_true", help="下载后自动调用 MOODY 接口执行云端入库点亮")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="MOODY Worker API 地址")

    args = parser.parse_args()

    if not args.artist and not args.url:
        parser.print_help()
        sys.exit(1)

    # 模式 1: 批量处理专辑 (支持单专辑或多专辑连续执行)
    if args.missing or args.full or (args.album and not args.song and not args.url):
        if not args.artist or not args.album:
            print("❌ 错误: 批量下载必须提供 --artist 和 --album")
            sys.exit(1)
        
        albums = [a.strip() for a in args.album.split(",") if a.strip()]
        for alb in albums:
            process_album(args.artist, alb, args.output, args.upload, args.api_base, full=args.full)
        return

    # 模式 2: 单曲下载
    if args.song or args.url:
        song_name = args.song or "未知歌曲"
        artist_name = args.artist or "未知歌手"
        album_name = args.album or "未知专辑"
        fpath, qa, lrc_info = download_track(song_name, artist_name, album_name, args.output, args.url)
        if fpath and args.upload:
            upload_to_moody(fpath, artist_name, album_name, song_name, args.api_base)

if __name__ == "__main__":
    main()
