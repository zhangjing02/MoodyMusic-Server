import json, requests, time

with open("reports/SUPERSTARS_LYRICS_REMEDIATION_LOG.json") as f:
    log = json.load(f)

success_uploads = log["success_uploads"]
print(f"全量待同步歌词: {len(success_uploads)} 首")

D1_URL = "https://m-api.changgepd.ccwu.cc/api/admin/songs/batch-light"

success_count = 0
failed_list = []

# 采用逐首更新，遇到成功的快速累加，遇到失败的捕获异常
print(">>> 开始稳健逐首同步 D1 数据库...")
for i, s in enumerate(success_uploads):
    sid = s.get("id")
    fp = s.get("path")
    lp = s.get("lrc_path")
    if not sid or not fp:
        continue
        
    payload = {"updates": [{
        "id": int(sid),
        "file_path": fp,
        "lrc_path": lp
    }]}
    
    try:
        r = requests.post(D1_URL, json=payload, timeout=6)
        if r.status_code == 200:
            success_count += 1
            if success_count % 30 == 0:
                print(f"  ⚡ 已同步 {success_count}/{len(success_uploads)} 首...")
        else:
            failed_list.append((s, r.status_code, r.text[:80]))
            print(f"  ⚠️ ID {sid} 《{s.get('title')}》失败: HTTP {r.status_code}")
    except Exception as e:
        failed_list.append((s, 0, str(e)))

print("\n" + "="*50)
print(f"D1 歌词同步完成！")
print(f"成功: {success_count}/{len(success_uploads)} 首 (成功率 {success_count/len(success_uploads)*100:.1f}%)")
print(f"失败/异常跳过: {len(failed_list)} 首")
print("="*50)

with open("reports/D1_LYRICS_SYNC_RESULT.json", "w", encoding="utf-8") as f:
    json.dump({
        "success_count": success_count,
        "failed_count": len(failed_list),
        "failed_list": failed_list
    }, f, ensure_ascii=False, indent=2)

