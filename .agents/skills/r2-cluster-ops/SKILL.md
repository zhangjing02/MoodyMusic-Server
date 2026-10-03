---
name: r2-cluster-ops
description: >-
  Cloudflare R2 九桶集群运维与容量安全 Skill。
  当用户提出「检查存储桶用量」、「R2容量」、「跨桶平移」、「排雷」、「扩容存储桶」、「检查曲库容量」、「九桶状态」等诉求时触发。
  负责执行容量监控核算（check_r2_storage.py）、9.50GB 熔断安全防护、Zero-Loss 工业级跨桶平移 SOP 以及 D1 动态广播与原子切链。
---

# Cloudflare R2 多桶集群运维与安全平移 Skill

本 Skill 规范了音信（MoodyMusic）云存储多桶集群（Buckets 01~N）的容量监控、防爆熔断、Zero-Loss 平移排雷与 D1 原子切链的标准作业程序（SOP）。
*新桶入网接入请参阅专属自动化 Skill：[`r2-bucket-onboarding`](../r2-bucket-onboarding/SKILL.md)*。

---

## 一、核心红线与物理铁律 (First Principles)

1. **商业十进制计费标准**：
   - 严格按 Cloudflare 官方计费标准计量：`1 GB = 1,000,000,000 字节`（非 1024 进制）。
   - 每桶安全红线：**9.50 GB 强制熔断封箱（CRITICAL_THRESHOLD_PERCENT = 95.0%）**，死守 10.00 GB 免费额度底线，严禁任何可能产生超额账单的写入。
2. **绝对 CDN 直链铁律**：
   - 写入 D1 `songs` 表的 `file_path` 与 `lrc_path` **必须始终为完整的绝对 CDN 直链**（格式形如 `https://pub-xxxx.r2.dev/music/...`）。
   - **绝对严禁写入相对路径**（如 `music/...`），否则将触发客户端 Android ExoPlayer 404 死锁与无限缓冲假死。
3. **D1 广播行数保护**：
   - 管理后台与大盘状态统一通过 Worker `GET/POST /api/admin/r2/stats` 存取 D1 `app_settings` 单行广播，严格保障读写消耗为 1 行，**严禁全表扫描**。

---

## 二、常用诊断与运维流程

### 1. 实时容量核查与大盘同步
当需要检查集群用量或更新前端展示数据时执行：
```powershell
python backend/scripts/check_r2_storage.py
```
- 该脚本会并发统计各桶物理对象与字节数，打印商业计费容量矩阵；
- 自动将最新指标持久化至 D1 `app_settings`，实现 Web 管理后台秒级刷新；
- 自动备份生成 `r2_stats.json` 快照作为三级容灾兜底。

### 2. Zero-Loss 工业级跨桶平移 SOP (防爆排雷)
当某桶逼近 9.50 GB 警戒线，需要将指定歌手（500MB~1.5GB）平移至余量桶（如 Bucket 09）时，**必须严格按 6 步流水线执行，严禁手工跳步或直接删源文件**：

* **Step 1: 前置双向拓扑审计**
  - 扫描源桶物理对象（`.mp3` 与 `.lrc`）；
  - 查询 D1 数据库提取待迁移曲目的自增主键 ID 列表与原始路径。
* **Step 2: 并发流式安全传输**
  - 通过 S3 API / Worker 原生代理直连流式拷贝对象至目标桶，并严格保持正确的 Content-Type（`audio/mpeg` / `text/plain`）。
* **Step 3: S3 HEAD 字节强核验 (零容错)**
  - 对目标桶对象逐一执行 `head_object` 校验，`ContentLength` 必须 1:1 完全吻合。
  - **若有任何 1 个文件大小不符或传输失败，立即终止切链与删除！**
* **Step 4: D1 数据库原子切链**
  - 调用 `POST /api/admin/songs/batch-light`（提交 `updates` 列表），基于主键秒级将 `file_path` 和 `lrc_path` 更新为目标桶的绝对 CDN 直链。
* **Step 5: 生产 CDN 连通性抽验**
  - 对迁移歌手的随机与经典曲目发起 HTTP HEAD 测试，确保全部返回 HTTP 200 且字节长度完全一致。
* **Step 6: 安全释放源桶空间与大盘刷新**
  - 验证全部通过后，调用 S3 `delete_objects` 释放源桶对应的源文件；
  - 再次执行 `python backend/scripts/check_r2_storage.py` 刷新九桶水位并广播至 D1。

---

## 三、脚本参考与维护工具库

- **集群核算与大盘监控**：`backend/scripts/check_r2_storage.py`
- **跨桶平移专用脚本模板**：
  - `backend/scripts/migrate_bucket01_to_09.py`
  - `backend/scripts/migrate_bucket07_to_09.py`
  - `backend/scripts/finish_migrate_01_to_09.py`
- **直链补齐与幽灵曲目清理**：`backend/scripts/fix_company_and_unlight_ghosts.py`
