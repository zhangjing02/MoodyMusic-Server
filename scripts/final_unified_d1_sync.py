import json, requests

with open("reports/SUPERSTARS_AUDIO_REMEDIATION_LOG.json") as f:
    audio_log = json.load(f)
with open("reports/SUPERSTARS_LYRICS_REMEDIATION_LOG.json") as f:
    lyric_log = json.load(f)

# 构建 id -> lrc_path 映射
id_to_lrc = {}
for l in lyric_log["success_uploads"]:
    id_to_lrc[int(l["id"])] = l["lrc_path"]

# 构建 id -> audio_path 映射
id_to_audio = {}
for a in audio_log["success_items"]:
    id_to_audio[int(a["id"])] = a["path"]

print(f"有效修复母带音轨: {len(id_to_audio)} 条")
print(f"有效修复正版歌词: {len(id_to_lrc)} 条")

# 联合所有涉及的 ID
all_ids = set(id_to_audio.keys()).union(set(id_to_lrc.keys()))
print(f"联合治理唯一曲目 ID: {len(all_ids)} 首")

# 查生产 API 获取当前的完整 path/lrc_path 兜底
artists = ["周杰伦", "孙燕姿", "陈奕迅", "林俊杰", "张学友"]
current_db_map = {}
for art in artists:
    r = requests.get(f"https://m-api.changgepd.ccwu.cc/api/songs?artist={art}", timeout=10)
    for alb in r.json().get("data", [])[0].get("albums", []):
        for s in alb.get("songs", []):
            m = __import__("re").search(r"s_(\d+)\.(mp3|lrc|flac)", (s.get("path") or "") + (s.get("lrc_path") or ""))
            if m:
                sid = int(m.group(1))
                current_db_map[sid] = {"path": s.get("path"), "lrc_path": s.get("lrc_path")}

D1_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
success_count = 0
for sid in all_ids:
    cur = current_db_map.get(sid, {})
    final_audio = id_to_audio.get(sid) or cur.get("path")
    final_lrc = id_to_lrc.get(sid) or cur.get("lrc_path")
    
    if not final_audio:
        continue
        
    payload = {"updates": [{
        "id": sid,
        "file_path": final_audio,
        "lrc_path": final_lrc
    }]}
    try:
        r = requests.post(D1_URL, json=payload, timeout=5)
        if r.status_code == 200:
            success_count += 1
    except:
        pass

print(f"\n🎉 终极联合同步完成！成功同步点亮: {success_count}/{len(all_ids)} 首！")

