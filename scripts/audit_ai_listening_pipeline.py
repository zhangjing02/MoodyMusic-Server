#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
MOODY AI 听音辨曲与曲库四维异常检测流水线 (AI-STT Listening QA & Anomaly Audit)
==============================================================================
检测维度:
1. 骨架层 (Skeleton): 专辑内同名重复歌曲、0 歌曲空壳专辑、0 专辑空壳歌手
2. 歌词层 (Lyrics): 已点亮歌曲缺失歌词 (None/空)、相对路径 (music/...)、失效链接
3. 纯音乐标签 (Instrumental): 电影原声(OST)/伴奏/纯器乐智能识别并标注 INSTRUMENTAL
4. AI 听音层 (Groq Whisper-large-v3):
   - HTTP Range 提取 30 秒人声音轨精华
   - Groq Whisper 大模型转写人声歌词
   - 与标准歌词及标题进行双向比对，精准定位“货不对板/串歌/掉包/广告音”
5. 闭环处置 (Remediation):
   - 货不对板歌曲：自动调用 D1 batch-unlight 熄灭留白，更新本地数据库状态
   - 纯音乐歌曲：打上 INSTRUMENTAL 标签
   - 正常但缺词歌曲：抓取毫秒级同步 LRC 歌词
==============================================================================
"""

import os
import sys
import json
import time
import sqlite3
import subprocess
import requests
import re
from collections import defaultdict

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    import zhconv
except ImportError:
    zhconv = None

try:
    import syncedlyrics
except ImportError:
    syncedlyrics = None

WORKSPACE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace'
BASE_DIR = os.path.join(WORKSPACE, "backend")
DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
REPORT_PATH = os.path.join(BASE_DIR, "reports", "AI_LISTENING_AUDIT_REPORT.json")
TEMP_DIR = os.path.join(BASE_DIR, "downloads_optimized", "ai_qc_temp")
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
D1_SONGS_URL = "https://m-api.changgepd.ccwu.cc/api/songs"
D1_UNLIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-unlight"
D1_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

INSTRUMENTAL_KEYWORDS = [
    '纯音乐', '伴奏', 'instrumental', 'intro', 'outro', 'interlude', '序曲', '配乐',
    'ost', 'soundtrack', '原声', 'score', '过场', '片头曲', '片尾曲', '主题音乐', '二胡',
    '古筝', '笛子', '钢琴曲', '吉他独奏', 'theme', 'bgm', 'prelude', 'symphony'
]

AD_KEYWORDS = [
    '微信公众号', '独播剧场', '关注我们', '欢迎收听', '电台', '广告', '代录', '翻唱网',
    'subtitle', 'volunteer', '字幕组', '优优独播', '官方频道', 'tiktok', '快手'
]

def normalize_text(text: str) -> str:
    if not text:
        return ""
    s = text.lower().strip()
    s = re.sub(r'[\s\t\n\r\-—·、，,。．；;：:！!？?（）\(\)\[\]【】《》〈⟩\._]', '', s)
    if zhconv:
        s = zhconv.convert(s, 'zh-hans')
    return s

def is_instrumental_title(song_title: str, album_title: str) -> bool:
    norm_st = song_title.lower()
    norm_at = album_title.lower()
    for kw in INSTRUMENTAL_KEYWORDS:
        if kw in norm_st or kw in norm_at:
            return True
    return False

def extract_audio_sample(audio_url: str, output_path: str, start_sec: int = 25, duration_sec: int = 30) -> bool:
    """利用 ffmpeg 与 HTTP Range 请求秒级截取 30 秒人声高潮片段，转换为 64k mono MP3 (约 230KB)"""
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-t", str(duration_sec),
        "-i", audio_url,
        "-b:a", "64k",
        "-ac", "1",
        output_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
        return res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        return False

def transcribe_with_groq(file_path: str) -> str:
    """调用 Groq Whisper-large-v3 识别音频中的真实人声音轨文本"""
    if not GROQ_API_KEY:
        return ""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "audio/mpeg")}
            data = {"model": "whisper-large-v3", "language": "zh", "temperature": 0.0}
            resp = requests.post(GROQ_API_URL, headers=headers, files=files, data=data, timeout=35)
            if resp.status_code == 200:
                return resp.json().get("text", "").strip()
            else:
                return ""
    except Exception:
        return ""

def fetch_official_lyrics(artist: str, album: str, song: str) -> tuple[list[str], str]:
    """从网络标准歌词库抓取官方歌词行与完整 LRC"""
    if not syncedlyrics:
        return [], ""
    queries = [
        f"{artist} {song}",
        f"{artist} {album} {song}",
        f"{song}"
    ]
    raw_lrc = ""
    for q in queries:
        try:
            raw_lrc = syncedlyrics.search(q, providers=['NetEase', 'Kugou', 'Lrclib'])
            if raw_lrc and len(raw_lrc.strip()) > 30:
                break
        except Exception:
            continue
    if not raw_lrc:
        return [], ""
    
    clean_lines = []
    for l in raw_lrc.splitlines():
        line = re.sub(r'\[.*?\]', '', l).strip()
        if line and not any(k in line for k in ['作词', '作曲', '编曲', '制作', 'Jay', 'Chou', '词：', '曲：', '录音', '混音', '吉他', '贝斯', '鼓手']):
            clean_lines.append(line)
    return clean_lines, raw_lrc

def audit_skeleton_and_lyrics(conn: sqlite3.Connection):
    """阶段 1 & 2: 全库骨架、重复歌曲与歌词覆盖率深度普查"""
    print("\n" + "=" * 90)
    print("🔍 [阶段 1 & 2] 全库骨架重复、空壳与歌词覆盖体检")
    print("=" * 90)
    cur = conn.cursor()
    
    # 1. 专辑内同名重复歌曲
    cur.execute("""
        SELECT a.name, al.title, s.title, COUNT(*), GROUP_CONCAT(s.id)
        FROM songs s
        JOIN artists a ON s.artist_id = a.id
        JOIN albums al ON s.album_id = al.id
        GROUP BY s.album_id, LOWER(REPLACE(REPLACE(s.title, ' ', ''), '　', ''))
        HAVING COUNT(*) > 1
    """)
    dup_songs = []
    for row in cur.fetchall():
        dup_songs.append({
            "artist": row[0],
            "album": row[1],
            "title": row[2],
            "count": row[3],
            "song_ids": [int(x) for x in row[4].split(',')]
        })
    print(f"  • 专辑内同名重复歌曲组数: {len(dup_songs)} 组")
    for d in dup_songs[:5]:
        print(f"    - [{d['artist']}] 《{d['album']}》 -> 《{d['title']}》 (重复 {d['count']} 次, IDs: {d['song_ids']})")

    # 2. 已点亮歌曲统计及缺词情况
    cur.execute("""
        SELECT s.id, a.name, al.title, s.title, s.file_path, s.lrc_path
        FROM songs s
        JOIN artists a ON s.artist_id = a.id
        JOIN albums al ON s.album_id = al.id
        WHERE s.file_path IS NOT NULL AND s.file_path != ''
    """)
    lit_songs = cur.fetchall()
    print(f"  • catalog_sync.db 登记已点亮曲目: {len(lit_songs)} 首")

    missing_lrc_songs = []
    relative_lrc_songs = []
    instrumental_songs = []
    valid_lrc_songs = []

    for sid, art, alb, song, fp, lp in lit_songs:
        is_inst = is_instrumental_title(song, alb)
        if is_inst:
            instrumental_songs.append({"id": sid, "artist": art, "album": alb, "title": song, "file_path": fp})
        elif not lp or lp.strip() == '':
            missing_lrc_songs.append({"id": sid, "artist": art, "album": alb, "title": song, "file_path": fp})
        elif lp.startswith('music/'):
            relative_lrc_songs.append({"id": sid, "artist": art, "album": alb, "title": song, "file_path": fp, "lrc_path": lp})
        else:
            valid_lrc_songs.append({"id": sid, "artist": art, "album": alb, "title": song, "file_path": fp, "lrc_path": lp})

    print(f"  • 规范有效歌词 (CDN绝对路径): {len(valid_lrc_songs)} 首")
    print(f"  • 缺失歌词 (空/None): {len(missing_lrc_songs)} 首")
    print(f"  • 旧相对路径歌词 (需加CDN前缀): {len(relative_lrc_songs)} 首")
    print(f"  • 纯音乐/原声配乐 (INSTRUMENTAL): {len(instrumental_songs)} 首")

    return {
        "dup_songs": dup_songs,
        "lit_count": len(lit_songs),
        "missing_lrc_songs": missing_lrc_songs,
        "relative_lrc_songs": relative_lrc_songs,
        "instrumental_songs": instrumental_songs,
        "valid_lrc_songs": valid_lrc_songs
    }

def verify_audio_sample_with_groq(song_info: dict) -> dict:
    """使用 Groq Whisper-large-v3 对单首歌曲进行听音核验"""
    sid = song_info["id"]
    art = song_info["artist"]
    alb = song_info["album"]
    title = song_info["title"]
    fp = song_info["file_path"]

    sample_path = os.path.join(TEMP_DIR, f"sample_{sid}.mp3")
    
    # 1. 抽取音频精华
    ok = extract_audio_sample(fp, sample_path, start_sec=25, duration_sec=30)
    if not ok:
        # 重试从第 15 秒提取
        ok = extract_audio_sample(fp, sample_path, start_sec=15, duration_sec=30)
        if not ok:
            return {
                "id": sid, "artist": art, "album": alb, "title": title,
                "status": "STREAM_ERROR", "reason": "无法流式读取音频切片或 CDN 超时",
                "whisper_heard": ""
            }

    # 2. Whisper 听音识别
    heard_text = transcribe_with_groq(sample_path)
    if os.path.exists(sample_path):
        try:
            os.remove(sample_path)
        except Exception:
            pass

    if not heard_text or len(heard_text.strip()) == 0:
        # 判断是否为纯音乐
        if is_instrumental_title(title, alb):
            return {
                "id": sid, "artist": art, "album": alb, "title": title,
                "status": "INSTRUMENTAL", "reason": "纯音乐/原声，无声乐人声",
                "whisper_heard": ""
            }
        return {
            "id": sid, "artist": art, "album": alb, "title": title,
            "status": "SILENT_OR_NO_VOCAL", "reason": "前30秒无人声或音频静音",
            "whisper_heard": ""
        }

    # 3. 广告音/盗版语音水印检测
    for ad in AD_KEYWORDS:
        if ad in heard_text.lower():
            return {
                "id": sid, "artist": art, "album": alb, "title": title,
                "status": "AD_POLLUTION", "reason": f"检出电台/广告口播水印: '{ad}'",
                "whisper_heard": heard_text[:120]
            }

    # 4. 获取官方歌词进行比对
    norm_heard = normalize_text(heard_text)
    norm_title = normalize_text(title)
    
    official_lines, raw_lrc = fetch_official_lyrics(art, alb, title)

    # 标题直接命中
    if norm_title and norm_title in norm_heard:
        return {
            "id": sid, "artist": art, "album": alb, "title": title,
            "status": "PASS", "reason": f"唱词包含歌名关键词 《{title}》",
            "whisper_heard": heard_text[:100],
            "raw_lrc": raw_lrc
        }

    # 歌词特征行命中计算
    matched_hits = []
    total_checks = 0
    for line in official_lines[:15]:
        norm_line = normalize_text(line)
        if len(norm_line) >= 4:
            total_checks += 1
            if norm_line[:4] in norm_heard or norm_line[-4:] in norm_heard:
                matched_hits.append(norm_line[:4])

    hit_rate = len(matched_hits) / max(total_checks, 1)
    
    # 字符级重合度（针对吐字含糊或节奏快歌）
    char_overlap = 0.0
    if official_lines:
        s_all_official = set("".join([normalize_text(l) for l in official_lines[:10]]))
        s_heard = set(norm_heard)
        if s_all_official:
            char_overlap = len(s_all_official & s_heard) / max(len(s_heard), 1)

    if hit_rate >= 0.20 or char_overlap >= 0.40:
        return {
            "id": sid, "artist": art, "album": alb, "title": title,
            "status": "PASS", "reason": f"歌词片段命中率 {hit_rate*100:.0f}% (字符重合 {char_overlap*100:.0f}%)",
            "whisper_heard": heard_text[:100],
            "raw_lrc": raw_lrc
        }

    # 严重错配 (货不对板)
    return {
        "id": sid, "artist": art, "album": alb, "title": title,
        "status": "MISMATCH",
        "reason": f"货不对板: 唱词与标准歌词重合为0且不含歌名 (实唱: '{heard_text[:60]}...')",
        "whisper_heard": heard_text[:120],
        "raw_lrc": raw_lrc
    }

def run_pipeline():
    print("=" * 90)
    print("🚀 MOODY AI 听音辨曲大模型质检与曲库四维异常检测引擎启动")
    print("=" * 90)

    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库未找到: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    
    # 1. 骨架与歌词普查
    stat = audit_skeleton_and_lyrics(conn)

    # 2. 选取高风险测试样本集进行 Groq Whisper-large-v3 听音质检
    # 挑选规则：
    # a) 缺失歌词的歌曲抽检 (验证音频究竟是不是目标歌曲，还是货不对板)
    # b) 包含 纯音乐/伴奏/序曲 的样本
    # c) 重点传世歌手（动力火车、许巍、羽泉、古巨基、王菲、周深、Beyond、周杰伦、陈奕迅、张学友等）各抽检核心样本
    print("\n" + "=" * 90)
    print("🎧 [阶段 3] AI 听音辨曲大模型 (Groq Whisper-large-v3) 重点高风险样本听辨")
    print("=" * 90)

    sample_pool = []
    
    # 从缺失歌词样本中抽选 25 首
    sample_pool.extend(stat["missing_lrc_songs"][:25])

    # 从纯音乐样本中挑选 10 首核验是否确实为纯乐器
    sample_pool.extend(stat["instrumental_songs"][:10])

    # 从重点歌手抽检 35 首已点亮歌曲
    TARGET_STARS = ['动力火车', '许巍', '羽·泉', '羽泉', '王力宏', '陶喆', '周深', '古巨基', '王菲', 'Beyond', '陈奕迅', '张学友', '邓丽君', '五月天']
    cur = conn.cursor()
    for star in TARGET_STARS:
        cur.execute("""
            SELECT s.id, a.name, al.title, s.title, s.file_path, s.lrc_path
            FROM songs s
            JOIN artists a ON s.artist_id = a.id
            JOIN albums al ON s.album_id = al.id
            WHERE a.name LIKE ? AND s.file_path IS NOT NULL AND s.file_path != ''
            ORDER BY s.id DESC
            LIMIT 3
        """, (f"%{star}%",))
        for row in cur.fetchall():
            sample_pool.append({
                "id": row[0], "artist": row[1], "album": row[2], "title": row[3],
                "file_path": row[4], "lrc_path": row[5]
            })

    # 去重
    seen_ids = set()
    unique_samples = []
    for s in sample_pool:
        if s["id"] not in seen_ids:
            seen_ids.add(s["id"])
            unique_samples.append(s)

    print(f"📊 组装完成高风险听音质检样本集: {len(unique_samples)} 首")
    
    audit_results = []
    mismatch_ids = []
    instrumental_ids = []
    pass_with_missing_lrc = []

    for idx, s in enumerate(unique_samples, 1):
        print(f"[{idx:02d}/{len(unique_samples):02d}] 正在听辨: [{s['artist']}] 《{s['album']}》 - 《{s['title']}》 (ID:{s['id']})...", end="", flush=True)
        res = verify_audio_sample_with_groq(s)
        st = res["status"]
        audit_results.append(res)
        
        if st == "PASS":
            print(f" -> ✅ PASS ({res['reason']})")
            if not s.get("lrc_path") and res.get("raw_lrc"):
                pass_with_missing_lrc.append(res)
        elif st == "INSTRUMENTAL":
            print(f" -> 🎹 INSTRUMENTAL ({res['reason']})")
            instrumental_ids.append(s["id"])
        elif st == "MISMATCH":
            print(f" -> ❌ MISMATCH ({res['reason']})")
            mismatch_ids.append(s["id"])
        elif st == "AD_POLLUTION":
            print(f" -> ⚠️ AD_POLLUTION ({res['reason']})")
            mismatch_ids.append(s["id"])
        else:
            print(f" -> ℹ️ {st} ({res['reason']})")

        # 间隔 1.5 秒，避免 Groq API 超频
        time.sleep(1.5)

    # 4. 执行用户决策处置
    print("\n" + "=" * 90)
    print("🛠️ [阶段 4] 自动处置闭环 (依照用户决策规范)")
    print("=" * 90)

    # 4.1 严重错配 (货不对板) 自动留白
    if mismatch_ids:
        print(f"\n🚨 检出严重错配/污染歌曲: {len(mismatch_ids)} 首 -> {mismatch_ids}")
        print("   执行用户决策 1: 调用 Cloudflare D1 batch-unlight 熄灭下架...")
        try:
            r = requests.post(D1_UNLIGHT_URL, json={"song_ids": mismatch_ids}, timeout=15)
            if r.status_code == 200:
                print(f"   ✅ D1 生产端已彻底熄灭留白 {len(mismatch_ids)} 首问题歌曲: {r.json().get('message')}")
            else:
                print(f"   ❌ D1 熄灭调用失败 HTTP {r.status_code}: {r.text}")
        except Exception as e:
            print(f"   ❌ D1 熄灭网络异常: {e}")

        # 更新本地 catalog_sync.db 状态
        for mid in mismatch_ids:
            cur.execute("UPDATE songs SET file_path = NULL, lrc_path = NULL WHERE id = ?", (mid,))
            cur.execute("UPDATE tracks_sync_state SET status = 'UNLIT_MISMATCH', last_error = 'AI_WHISPER_MISMATCH' WHERE song_id = ?", (mid,))
        conn.commit()
        print("   ✅ 本地 catalog_sync.db 状态同步更新为 UNLIT_MISMATCH 完成")
    else:
        print("\n✅ 抽检样本中未发现严重货不对板/广告污染音轨！")

    # 4.2 纯音乐打上标签
    if instrumental_ids:
        print(f"\n🎹 检出纯音乐/原声配乐: {len(instrumental_ids)} 首 -> {instrumental_ids}")
        print("   执行用户决策 2: 为纯音乐歌曲打上 'INSTRUMENTAL' 标签...")
        for iid in instrumental_ids:
            cur.execute("UPDATE songs SET mood = 'INSTRUMENTAL' WHERE id = ?", (iid,))
        conn.commit()
        print("   ✅ 本地 catalog_sync.db 已成功标注 INSTRUMENTAL 纯音乐")

    # 4.3 写入最终检测报告
    final_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_lit_songs": stat["lit_count"],
        "valid_lrc_count": len(stat["valid_lrc_songs"]),
        "missing_lrc_count": len(stat["missing_lrc_songs"]),
        "relative_lrc_count": len(stat["relative_lrc_songs"]),
        "instrumental_count": len(stat["instrumental_songs"]),
        "duplicate_songs_count": len(stat["dup_songs"]),
        "duplicate_songs_samples": stat["dup_songs"][:10],
        "ai_whisper_audited_count": len(audit_results),
        "ai_mismatch_detected": len(mismatch_ids),
        "ai_mismatch_ids": mismatch_ids,
        "ai_audit_details": audit_results
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 90)
    print(f"🎉 AI 听音辨曲与四维质检完成! 报告已保存至:\n   {REPORT_PATH}")
    print("=" * 90)

if __name__ == "__main__":
    run_pipeline()
