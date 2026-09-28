#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

content_to_append = """

---

## 31. 历史专辑骨架重构与曲目正本清源 SOP (Album Skeleton Restructuring & Tracklist Realignment) (2026-09-28)

- **业务背景与问题形态**：
  在动力火车全量 10 张大碟深度治理中，发现部分早期抓取的专辑骨架存在严重偏差：
  1. **严重缺漏与粗暴拼盘**：《都是因为爱》（2021原创新专，官方11首）在库中仅有8首，且混入陈淑桦原唱《滚滚红尘》及非专辑曲目；《结伴》（2024最新大碟，官方10首）在库中仅有8首，且混入郑中基《我这个你不爱的人》以及重复的《背叛情歌》、《当》；
  2. **民间盲猜曲名引发错乱**：《明天的明天的明天》（1998经典，官方12首）因原建库者误填曲名，将《刺猬》错写为《爱情电影》（误采熊天平并被说唱吴子健污染），将《我知道你要的是什么》错写为《你是我的眼》（误采萧煌奇），将《让我哭》错写为《别让我流泪》（误采张宇），且缺失第12首《翅膀之歌》。
- **标准化重构与治理流程**：
  1. **实体盘面官方核准**：立足第一性原理，以台湾唱片公司（上华/华研）官方实体黑胶/CD Tracklist 及维基百科官方专辑词条为唯一真理源，建立包含 Track 序号、官方标准中文曲名的精确映射列表。
  2. **主键无损复用与原子更正 (Preserve Existing Primary Keys)**：
     - 调用 `POST /api/admin/songs/batch-update` 批量将现有记录的 `title` 和 `track_index` 矫正为官方标准，保留主键 ID，不破坏用户历史收藏或统计；
     - 严禁盲目执行暴力重置（delete-all），杜绝主键空洞或外键断链。
  3. **缺失音轨幂等补齐 (Idempotent Track Insertion)**：
     - 对比预期官方曲目数，若有缺失，调用 `POST /api/admin/songs/batch-insert` 批量追加插入缺失音轨，并回取分配的自增 `song_ids` 纳入后续处理流。
  4. **全链路采录、压制与点亮**：
     - 采用预先探针验证的官方 YouTube Topic / Official 音源，结合标准响度压制（-14 LUFS, 160k CBR）与正版 LRC 清洗；
     - 写入活跃桶 `account_11`，并调用 `POST /api/admin/songs/batch-light` 完成 D1 原子切链。

---

## 32. 第三方高保真歌词通道防爬与上下文感知校验规约 (Robust Lyric Channel & Context-Aware Auditing) (2026-09-28)

- **故障现象与技术根因**：
  1. **歌词接口 502 Bad Gateway**：在批量拉取酷狗歌词时，旧版 `krcs.kugou.com` 或未带标准请求头的 HTTP 请求会间歇性被 WAF 拦截或抛出 502/反爬验证；
  2. **敏感词过滤误判翻唱曲目**：动力火车翻唱萧煌奇经典名作《你是我的眼》（收录于《继续转动》），歌词元数据含 `[00:02.81]词：萧煌奇`，盲目的李鬼敏感词匹配会将原唱词曲作者信息误判为李鬼。
- **治理与工程标准**：
  1. **双阶请求头伪装与移动端 CDN 结合**：
     - 搜索阶段：优先采用高可用移动端搜索端点 `http://mobilecdn.kugou.com/api/v3/search/song`，并匹配原唱艺人筛选 Hash；
     - 下载阶段：调用 `http://lyrics.kugou.com/search` 与 `http://lyrics.kugou.com/download` 时，必须强制携带完整的桌面 User-Agent 与 Referer 请求头，确保 100% 稳定返回 HTTP 200；
  2. **歌词李鬼审查上下文感知 (Context-Aware Auditing)**：
     - 审查李鬼歌词时，必须将“词曲作者署名”（如“词：萧煌奇”）与“正文演唱者”（如“小安迪说唱”、“幼稚园杀手”）区分开；若演唱者标头为目标艺人（动力火车），且正文内容与原曲一致，允许合法词曲作者署名存在。
"""

targets = [
    "MoodyMusic-Server/docs/KNOWLEDGE_BASE.md",
    os.path.expanduser("~/.gemini/config/knowledge_base.md")
]

for t in targets:
    if os.path.exists(t):
        with open(t, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # 截断到 30 条之前（如果之前有被损坏的 31）
        cut_idx = len(lines)
        for i, l in enumerate(lines):
            if "## 31." in l:
                cut_idx = i - 1
                break
        valid_lines = lines[:cut_idx]
        with open(t, "w", encoding="utf-8") as f:
            f.write("".join(valid_lines).strip() + content_to_append + "\n")
        print(f"Updated {t}")
