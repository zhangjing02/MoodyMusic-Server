# 🤝 2026-09-19 MOODY 音频治理与两地协同交接文档（致公司电脑 AI）

> **交接对象**：公司电脑 Claude / Antigravity AI Agent  
> **编写时间**：2026-09-19 20:20 (夜间协同交接)  
> **交接级别**：P0 核心架构级协同保障  

---

## 一、故障背景：今天白天在公司下载的歌曲在 App 端为何无法播放？

### 1. 现象与体检
用户晚上在手机端（Android App）试听白天公司电脑下载点亮的新歌手（**零点乐队、迪克牛仔、萧煌奇、郑智化** 等）时，发现**每一首歌曲都处于“一直在加载中、转圈卡死、无法播放”的状态**。

### 2. 根因确诊（100% 查明）
- **物理文件安全**：所有音频与歌词物理对象已经 100% 成功上传到 Cloudflare R2（零点乐队、迪克牛仔、郑智化在第 7 桶，萧煌奇在第 8 桶），文件完整、大小正常，**绝非文件丢失**。
- **致命路径 bug**：公司端的采录脚本（`five_artists_orchestrator.py` 等）在调用 `/api/admin/songs/batch-light` 向 Cloudflare D1 写入数据时，填入的是**相对路径**（例如 `"file_path": "music/零点乐队/别误会/s_28720.mp3"`）。
- **客户端解析逻辑死锁**：
  1. Android App 的 `PlayerViewModel.kt` 判断 `path` 不是以 `http` 开头，便自动拼接为 Worker 网关：`https://m-api.changgepd.ccwu.cc/storage/music/...`；
  2. Cloudflare Worker 的 `/storage/*` 代理**仅挂载了第 1 存储桶（moody-music-asset，55GB 只读）**，根本没有挂载第 7 桶与第 8 桶，导致直接返回 **HTTP 404 Not Found**；
  3. 客户端触发内置容灾降级（`MusicPlayerService.kt`），将请求替换为第 2 存储桶（`pub-9ea7ff16...`），再次返回 **404 Not Found**；
  4. ExoPlayer 连续收到 404 后陷入无限缓冲等待队列，导致用户界面**转圈卡死**。

---

## 二、家里电脑 AI 今晚已完成的工作（请勿重复执行或改坏）

1. **已修复全库 1,299 首真实音频的绝对 CDN 直链**：
   - 编写并执行了 `backend/scripts/fix_company_and_unlight_ghosts.py`；
   - 将包括 **零点乐队 (65首)、迪克牛仔 (72首)、郑智化 (87首)、萧煌奇 (151首)、尚雯婕 (141首)、窦唯 (108首)、苏慧伦 (106首)、王心凌 (99首)、庾澄庆 (95首)、曾轶可 (82首)、古巨基 (76首)、动力火车 (57首)、张靓颖 (44首)、张雨生 (43首)、飞儿乐团 (37首)、那英 (36首)** 在内的共计 16 位歌手、**1,299 首曲目全部修复为完整的绝对直链**！
   - 手机端 App 重新进入后已**秒级起播，LRC 歌词同步展示**。

2. **已将全库 1,626 首历史占位假点亮全量置灰留白**：
   - 彻底排查出早期历史批次中周杰伦、陈奕迅、林俊杰、梁静茹、五月天、孙燕姿、Beyond 等 22 位歌手的 1,626 首“库里填了相对路径、但 R2 无任何物理文件”的幽灵曲目；
   - 已全量调用 `/api/admin/songs/batch-unlight` 置灰（`file_path = NULL`），消除了 404 隐患。

3. **已达成 100% 全大碟录音室大满贯歌手名单**：
   - 🟢 **齐秦 (Chyi Chin)**：25 张大碟，269 / 269 首 100% 全满贯；
   - 🟢 **高胜美 (Sammi Kao)**：16 张大碟，205 / 205 首 100% 全满贯；
   - 🟢 **黄品源 (Huang Pinyuan)**：21 张大碟，234 / 234 首 100% 全满贯；
   - 🟢 **万芳 (Wan Fang)**：18 张大碟，191 / 191 首 100% 全满贯；
   - 🟢 **罗大佑 (Luo Dayou)**：22 张大碟，294 / 294 首 100% 全满贯；
   - 🟢 **费玉清 (Fei Yu-ching)**：38 张大碟，495 / 495 首 100% 全满贯；
   - 🟢 **林宥嘉 (Yoga Lin)**：10 张大碟，136 / 136 首 100% 全满贯；
   - 🟢 **黄小琥 (Tiger Huang)**：21 张大碟，221 / 221 首 100% 全满贯。

---

## 三、公司电脑 AI 明天接手需要立即执行的修改（核心动作）

### 1. 立即修改公司端 6 个 Orchestrator 采录脚本的写入格式
请立即打开公司端以下脚本：
- `backend/scripts/five_artists_orchestrator.py` (Line 342)
- `backend/scripts/second_wave_orchestrator.py` (Line 259)
- `backend/scripts/priority_gap_orchestrator.py` (Line 354)
- `backend/scripts/fix_2_leoku_songs.py` (Line 89)
- `backend/scripts/fix_chang_yu_sheng.py` (Line 109)
- `backend/scripts/reharvest_v3_hardcoded.py` (Line 160)

**❌ 原错误写法**：
```python
return {
    "status": "SUCCESS",
    "id": song_id,
    "file_path": r2_audio_key,           # 错误！写入了相对路径 music/...
    "lrc_path": r2_lrc_key if has_lrc else None, # 错误！写入了相对路径 lyrics/...
    "bucket": target_bucket_id
}
```

**✅ 必须替换为标准绝对直链写法**：
```python
cdn_domain = target_bucket_cfg.get("public_domain", "").rstrip('/')
abs_audio_url = f"{cdn_domain}/{r2_audio_key}"
abs_lrc_url = f"{cdn_domain}/{r2_lrc_key}" if (has_lrc and r2_lrc_key) else None

return {
    "status": "SUCCESS",
    "id": song_id,
    "file_path": abs_audio_url,  # 确保是 https://pub-xxxx.r2.dev/music/...
    "lrc_path": abs_lrc_url,    # 确保是 https://pub-xxxx.r2.dev/lyrics/... (或 None)
    "bucket": target_bucket_id
}
```

### 2. 补救公司电脑昨晚后台可能新增的相对路径
如果你（公司 AI）昨晚在公司电脑后台继续运行了下载，并且又有新歌曲被写入了相对路径，**请直接运行**：
```powershell
python backend/scripts/fix_company_and_unlight_ghosts.py
```
该脚本会自动对齐全部 16 位歌手在 07/08 桶中的物理位置，一键秒级补齐 CDN 域名。

---

## 四、两地协作分工与存储桶安全隔离（9.50 GB 铁律）

用户明确指示了今晚与明天的存储分工策略，防止两台电脑并发写入导致存储桶被撑爆：

1. **家里电脑采录范围与写入桶**：
   - 家里电脑今晚起已**强制切换主力写入桶为第 8 存储桶 (`moody-music-asset-08`)**；
   - 家里电脑今晚负责推进此前被置灰的重点歌手（陈奕迅、周杰伦、五月天、林俊杰等）以及庾澄庆、苏慧伦未补全的差额；
   - 所有产物完全写入 Bucket 08，**绝不触碰第 7 桶**。

2. **公司电脑采录范围与写入桶**：
   - 第 7 存储桶 (`moody-music-asset-07`) 当前占用 **7.11 GB / 9.50 GB，安全余量约 2.39 GB（可容纳 ~480 首）**；
   - **该余量专门留给公司电脑使用**；
   - 若公司电脑在下载过程中发现第 7 桶达到 **9.30 GB 警戒线**，请自动切换到第 8 桶 (`moody-music-asset-08`)。

3. **存储桶公网直链速查表**：
   - **Bucket 07**：`https://pub-a0a90fda9b0d45d59a52685eb2ee93d6.r2.dev`
   - **Bucket 08**：`https://pub-dd32e05660c74c3dba04d231391eb82b.r2.dev`

请公司电脑 AI 按照上述规范平稳接续，共同保障 MOODY 音乐档案库的 100% 高质量交付！
