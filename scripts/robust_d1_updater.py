import json, requests, time

with open("reports/SUPERSTARS_LYRICS_REMEDIATION_LOG.json") as f:
    log = json.load(f)

success_uploads = log["success_uploads"]
print(f"全量待同步: {len(success_uploads)} 首")

# 已经同步了前 150 首，从 150 开始处理
remaining = success_uploads[150:]
print(f"剩余待同步: {len(remaining)} 首")

D1_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

success_count = 0
failed_items = []

# 按 10 首一组
batch_size = 10
for i in range(0, len(remaining), batch_size):
    chunk = remaining[i:i+batch_size]
    updates = []
    for s in chunk:
        sid = s.get("id")
        fp = s.get("path")
        lp = s.get("lrc_path")
        if sid and fp:
            updates.append({
                "id": int(sid),
                "file_path": fp,
                "lrc_path": lp
            })
            
    if not updates:
        continue
        
    try:
        r = requests.post(D1_URL, json={"updates": updates}, timeout=15)
        if r.status_code == 200:
            success_count += len(updates)
            print(f"  ⚡ [{i+len(updates)}/{len(remaining)}] 批次同步成功 ({len(updates)} 首)")
        else:
            # 逐首细查
            print(f"  ⚠️ 批次失败，切入单首逐条重试...")
            for u in updates:
                try:
                    r_single = requests.post(D1_URL, json={"updates": [u]}, timeout=8)
                    if r_single.status_code == 200:
                        success_count += 1
                    else:
                        failed_items.append((u, r_single.status_code, r_single.text[:100]))
                        print(f"    ❌ 单首失败: ID {u['id']} -> {r_single.text[:100]}")
                except Exception as e:
                    failed_items.append((u, 0, str(e)))
    except Exception as e:
        print(f"  ⚠️ 网络异常: {e}")

print(f"\n🎉 剩余同步完成！成功: {success_count} 首 | 失败: {len(failed_items)} 首")
