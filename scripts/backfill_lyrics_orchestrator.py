#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY - 全盘已点亮歌曲缺失/异常歌词地毯式补齐流水线
(Comprehensive Lyrics Backfill Orchestrator to Bucket 09 & D1)

功能：
1. 读取待补齐清单 (data/songs_needing_backfill.json)，支持断点续传
2. 多源精准检索：
   - 酷狗移动端高精度歌词接口 (Kugou API)
   - 网易云音乐原生检索与歌词接口 (NetEase API)
   - syncedlyrics 多候选回退
3. 工业级繁简转换 (OpenCC t2s/s2t) + 智能歌名清洗 (移除括号、序号、版本后缀)
4. 标准动态歌词时间轴强校验 ([mm:ss.xx]，过滤纯音乐占位)
5. 上传至全新 Bucket 09 (lyrics/{Artist}/{Album}/s_{id}.lrc)
6. 批量调用 Worker /api/admin/songs/batch-light 秒级点亮 D1
7. 实时持久化进度 checkpoint (data/lyrics_backfill_progress.json)
"""

import os
import sys
import re
import time
import json
import base64
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import boto3
from botocore.config import Config
import opencc

# 基础路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
BACKFILL_INPUT_PATH = os.path.join(BASE_DIR, "data", "songs_needing_backfill.json")
PROGRESS_PATH = os.path.join(BASE_DIR, "data", "lyrics_backfill_progress.json")
SUMMARY_REPORT_PATH = os.path.join(BASE_DIR, "reports", "lyrics_backfill_summary.json")

API_BATCH_LIGHT_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

# 繁简转换引擎
t2s = opencc.OpenCC('t2s')
s2t = opencc.OpenCC('s2t')

# 线程锁
progress_lock = threading.Lock()
db_write_lock = threading.Lock()

# ----------------- R2 客户端初始化 -----------------
def get_r2_b9_client():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    b_info = cfg["buckets"]["account_09"]
    s3 = boto3.client(
        service_name="s3",
        endpoint_url=b_info["endpoint_url"],
        aws_access_key_id=b_info["access_key_id"],
        aws_secret_access_key=b_info["secret_access_key"],
        region_name="auto",
        config=Config(
            s3={"addressing_style": "path"},
            max_pool_connections=50
        )
    )
    return s3, b_info["name"], b_info["public_url"].rstrip('/')

# ----------------- 网络 Session -----------------
def create_session(pool_size=30):
    s = requests.Session()
    retries = Retry(total=2, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retries)
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    return s

thread_local = threading.local()

def get_thread_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = create_session(10)
    return thread_local.session

# ----------------- 歌名与字符清洗 -----------------
def clean_song_title(title: str) -> list:
    candidates = [title]
    t1 = re.sub(r'\(.*?\)|（.*?）|\[.*?\]|【.*?】|《.*?》', '', title).strip()
    if t1 and t1 not in candidates:
        candidates.append(t1)
    t2 = re.sub(r'^\d+[\s\.\-_]+', '', title).strip()
    if t2 and t2 not in candidates:
        candidates.append(t2)
    t3 = re.sub(r'^\d+[\s\.\-_]+', '', t1).strip()
    if t3 and t3 not in candidates:
        candidates.append(t3)
    return candidates

def safe_path_segment(name: str) -> str:
    """清理路径中的非法字符或多余斜杠，避免形成意外的深层 S3 虚拟目录"""
    if not name:
        return "Unknown"
    return re.sub(r'[\/\\:*?"<>|]', '_', name).strip()

def is_valid_lrc(text: str) -> bool:
    if not text or len(text) < 40:
        return False
    timestamps = re.findall(r'\[\d{2}:\d{2}\.\d{2,3}\]', text)
    if len(timestamps) < 3:
        return False
    # 纯音乐过滤
    if '纯音乐，无歌词' in text or '没有填词的纯音乐' in text:
        return False
    return True

# ----------------- 多源抓取引擎 -----------------
def fetch_kugou_lrc(artist: str, title: str, session: requests.Session) -> tuple:
    clean_titles = clean_song_title(title)
    for ct in clean_titles:
        for t_ver in set([ct, t2s.convert(ct), s2t.convert(ct)]):
            q = f"{artist} {t_ver}".strip()
            try:
                url = f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={urllib.parse.quote(q)}&page=1&pagesize=4"
                resp = session.get(url, timeout=4)
                if resp.status_code != 200:
                    continue
                items = resp.json().get('data', {}).get('info', [])
                for item in items:
                    cand_name = item.get('songname', '')
                    cand_singer = item.get('singername', '')
                    duration = item.get('duration', 0)
                    hash_val = item.get('hash', '')
                    if not hash_val:
                        continue
                    
                    lrc_search_url = f"http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword={urllib.parse.quote(cand_name)}&duration={duration}&hash={hash_val}"
                    lrc_resp = session.get(lrc_search_url, timeout=4)
                    if lrc_resp.status_code != 200:
                        continue
                    candidates = lrc_resp.json().get('candidates', [])
                    if candidates:
                        c0 = candidates[0]
                        dl_url = f"http://krcs.kugou.com/download?ver=1&client=mobi&id={c0['id']}&accesskey={c0['accesskey']}&fmt=lrc&charset=utf8"
                        dl_resp = session.get(dl_url, timeout=4)
                        if dl_resp.status_code == 200:
                            b64 = dl_resp.json().get('content', '')
                            if b64:
                                decoded = base64.b64decode(b64).decode('utf-8', errors='ignore')
                                if is_valid_lrc(decoded):
                                    return decoded, "Kugou"
            except Exception:
                pass
    return None, None

def fetch_netease_lrc(artist: str, title: str, session: requests.Session) -> tuple:
    clean_titles = clean_song_title(title)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://music.163.com/'
    }
    for ct in clean_titles:
        for t_ver in set([ct, t2s.convert(ct), s2t.convert(ct)]):
            q = f"{artist} {t_ver}".strip()
            try:
                search_url = f"http://music.163.com/api/search/get/web?s={urllib.parse.quote(q)}&type=1&offset=0&limit=4"
                resp = session.get(search_url, headers=headers, timeout=4)
                if resp.status_code != 200:
                    continue
                songs = resp.json().get('result', {}).get('songs', [])
                for s in songs:
                    sid = s['id']
                    lrc_url = f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1"
                    lrc_resp = session.get(lrc_url, headers=headers, timeout=4)
                    if lrc_resp.status_code == 200:
                        lrc_text = lrc_resp.json().get('lrc', {}).get('lyric', '')
                        if is_valid_lrc(lrc_text):
                            return lrc_text, "NetEase"
            except Exception:
                pass
    return None, None

def fetch_syncedlyrics_fallback(artist: str, title: str) -> tuple:
    try:
        import syncedlyrics
        clean_titles = clean_song_title(title)
        for ct in clean_titles:
            q = f"{artist} {t2s.convert(ct)}"
            lrc = syncedlyrics.search(q, providers=['NetEase', 'Lrclib'])
            if is_valid_lrc(lrc):
                return lrc, "SyncedLyrics"
    except Exception:
        pass
    return None, None

def fetch_lyrics_multi_source(artist: str, title: str, session: requests.Session) -> tuple:
    # 策略 1: 酷狗音乐 (中文曲库覆盖率最高)
    lrc, src = fetch_kugou_lrc(artist, title, session)
    if lrc:
        return lrc, src
    
    # 策略 2: 网易云音乐原生 API
    lrc, src = fetch_netease_lrc(artist, title, session)
    if lrc:
        return lrc, src

    # 策略 3: SyncedLyrics (包含 Lrclib 国际源)
    lrc, src = fetch_syncedlyrics_fallback(artist, title)
    if lrc:
        return lrc, src

    return None, None

# ----------------- 批量点亮 D1 -----------------
def batch_light_d1(updates_batch: list) -> int:
    if not updates_batch:
        return 0
    payload = {"updates": updates_batch}
    try:
        r = requests.post(API_BATCH_LIGHT_URL, json=payload, timeout=25)
        if r.status_code == 200:
            return len(updates_batch)
        else:
            print(f"⚠️ [D1 点亮返回错误] HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        print(f"❌ [D1 点亮网络异常] {e}")
    return 0

# ----------------- 主流程 -----------------
def run_orchestrator(max_workers=12, limit=None):
    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "reports"), exist_ok=True)

    print("=" * 80)
    print("🚀 MOODY - 全盘 15,090 首歌词地毯式全网检索与 Bucket 09 点亮流水线启动")
    print(f"📂 待补齐数据源: {BACKFILL_INPUT_PATH}")
    print("=" * 80)

    if not os.path.exists(BACKFILL_INPUT_PATH):
        print(f"❌ 待补齐清单不存在: {BACKFILL_INPUT_PATH}")
        sys.exit(1)

    with open(BACKFILL_INPUT_PATH, 'r', encoding='utf-8') as f:
        all_backfill_items = json.load(f)

    if limit and limit > 0:
        all_backfill_items = all_backfill_items[:limit]

    total_tasks = len(all_backfill_items)
    print(f"📋 本次计划补齐歌曲总数: {total_tasks} 首")

    # 读取进度缓存
    progress_data = {}
    if os.path.exists(PROGRESS_PATH):
        try:
            with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
            print(f"🔄 检测到断点续传文件: 已记录 {len(progress_data.get('completed_ids', []))} 首")
        except Exception:
            progress_data = {"completed_ids": [], "success_items": [], "failed_items": []}
    else:
        progress_data = {"completed_ids": [], "success_items": [], "failed_items": []}

    completed_ids = set(progress_data.get("completed_ids", []))
    pending_items = [it for it in all_backfill_items if it["id"] not in completed_ids]

    print(f"⚡ 待实际处理差额: {len(pending_items)} 首 (已跳过已处理 {len(completed_ids)} 首)")
    print(f"⚙️ 运行并发度: {max_workers} 线程")
    print("=" * 80)

    if not pending_items:
        print("🎉 所有待补齐歌曲均已处理完毕！")
        return

    s3_client, b9_name, b9_public_url = get_r2_b9_client()
    print(f"☁️ R2 目标存储桶: {b9_name} ({b9_public_url})")

    pending_d1_updates = []
    success_count = len(progress_data.get("success_items", []))
    failed_count = len(progress_data.get("failed_items", []))

    t_start = time.time()
    processed_in_this_run = 0

    def process_single_song(item):
        sid = item["id"]
        artist = item.get("artist_name") or "Unknown"
        album = item.get("album_title") or "Unknown"
        title = item["song_title"]
        file_path = item["file_path"]

        session = get_thread_session()
        lrc_text, source = fetch_lyrics_multi_source(artist, title, session)

        if not lrc_text:
            return {
                "id": sid,
                "status": "NOT_FOUND",
                "artist": artist,
                "title": title
            }

        # 构造 Bucket 09 S3 Key
        safe_art = safe_path_segment(artist)
        safe_alb = safe_path_segment(album)
        s3_key = f"lyrics/{safe_art}/{safe_alb}/s_{sid}.lrc"
        cdn_lrc_url = f"{b9_public_url}/{s3_key}"

        # 上传至 S3 Bucket 09
        try:
            s3_client.put_object(
                Bucket=b9_name,
                Key=s3_key,
                Body=lrc_text.encode('utf-8'),
                ContentType="text/plain; charset=utf-8"
            )
            return {
                "id": sid,
                "status": "UPLOADED",
                "file_path": file_path,
                "lrc_path": cdn_lrc_url,
                "s3_key": s3_key,
                "artist": artist,
                "album": album,
                "title": title,
                "source": source,
                "bytes": len(lrc_text)
            }
        except Exception as e:
            return {
                "id": sid,
                "status": "S3_ERROR",
                "error": str(e),
                "artist": artist,
                "title": title
            }

    # 执行线程池
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_single_song, it): it for it in pending_items}

        for future in as_completed(futures):
            res = future.result()
            sid = res["id"]
            processed_in_this_run += 1
            completed_ids.add(sid)

            if res["status"] == "UPLOADED":
                success_count += 1
                progress_data.setdefault("success_items", []).append({
                    "id": sid,
                    "artist": res["artist"],
                    "title": res["title"],
                    "lrc_path": res["lrc_path"],
                    "source": res["source"]
                })
                pending_d1_updates.append({
                    "id": sid,
                    "file_path": res["file_path"],
                    "lrc_path": res["lrc_path"]
                })
                print(f"[{processed_in_this_run}/{len(pending_items)}] ✅ 抓取并上传成功 ({res['source']}): {res['artist']} - 《{res['title']}》 ({res['bytes']}B)")
            else:
                failed_count += 1
                progress_data.setdefault("failed_items", []).append({
                    "id": sid,
                    "artist": res["artist"],
                    "title": res["title"],
                    "reason": res.get("status")
                })
                print(f"[{processed_in_this_run}/{len(pending_items)}] ⚠️ 未匹配到有效歌词: {res['artist']} - 《{res['title']}》")

            # 每攒满 50 首执行一次 D1 批量点亮
            if len(pending_d1_updates) >= 50:
                with db_write_lock:
                    chunk = pending_d1_updates[:]
                    pending_d1_updates.clear()
                lit_cnt = batch_light_d1(chunk)
                print(f"   ✨ [D1 批量点亮] 成功点亮 {lit_cnt} 首歌曲！")

            # 每 25 首保存一次 checkpoint
            if processed_in_this_run % 25 == 0:
                with progress_lock:
                    progress_data["completed_ids"] = list(completed_ids)
                    with open(PROGRESS_PATH, 'w', encoding='utf-8') as pf:
                        json.dump(progress_data, pf, ensure_ascii=False)

    # 处理剩余不足 50 首的批次
    if pending_d1_updates:
        lit_cnt = batch_light_d1(pending_d1_updates)
        print(f"   ✨ [D1 最终批次点亮] 成功点亮 {lit_cnt} 首歌曲！")
        pending_d1_updates.clear()

    # 最终保存 checkpoint
    progress_data["completed_ids"] = list(completed_ids)
    with open(PROGRESS_PATH, 'w', encoding='utf-8') as pf:
        json.dump(progress_data, pf, ensure_ascii=False)

    elapsed = time.time() - t_start
    print("=" * 80)
    print(f"🏁 补齐执行收官！本次处理: {processed_in_this_run} 首，耗时: {elapsed:.1f} 秒")
    print(f"📊 累计总结果: 成功补全并点亮: {len(progress_data['success_items'])} 首 | 未匹配: {len(progress_data['failed_items'])} 首")
    print("=" * 80)

if __name__ == "__main__":
    workers = 12
    if len(sys.argv) > 1:
        try:
            workers = int(sys.argv[1])
        except ValueError:
            pass
    run_orchestrator(max_workers=workers)
