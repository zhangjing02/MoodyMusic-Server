import json, requests

PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}

with open("reports/SUPERSTARS_LYRICS_REMEDIATION_LOG.json") as f:
    log = json.load(f)

success_uploads = log["success_uploads"]
print(f"待同步 D1 歌词总数: {len(success_uploads)} 首")

D1_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"
batch_size = 50
total_updated = 0

for i in range(0, len(success_uploads), batch_size):
    chunk = success_uploads[i:i+batch_size]
    updates = []
    for s in chunk:
        sid = s["id"]
        fp = s.get("path") or ""
        lp = s["lrc_path"]
        if sid and fp:
            updates.append({
                "id": int(sid),
                "file_path": fp,
                "lrc_path": lp
            })
            
    if not updates:
        continue
        
    r = requests.post(D1_URL, json={"updates": updates}, headers={"Content-Type": "application/json"}, timeout=20)
    print(f"Batch [{i//batch_size + 1}]: HTTP {r.status_code} | {r.text[:120]}")
    if r.status_code == 200:
        total_updated += len(updates)

print(f"\n🎉 D1 批量原子更新完成！共计成功同步: {total_updated}/{len(success_uploads)} 首")
