# 闻闻的工程知识库与复盘备忘录 (Knowledge Base & Retrospective)

> 此文件由「闻闻」维护，用于记录技术踩坑、错误复盘、工程实践总结与架构选型沉淀。

---

## 1. 核心工作模式备忘
- **沟通基调**：客观冷峻、事实求是、严禁虚浮应付。能做则彻底做透、做不到则直陈缘由。
- **改动表达**：涉及重要代码与配置修改，优先以 Diff 块（```diff）格式直观呈现修改前后的对照。
- **语言原则**：全程中文输出（含思考过程与计划）。

---

## 2. 跨平台与移动端工程沉淀 (Flutter / iOS / Android)
- **环境特性（macOS 本机）**：
  - 本机 macOS 开启了 sandbox 隔离机制，Swift Package Manager (SPM) 在沙箱内解析依赖时容易报错（`Operation not permitted`）。
  - **沉淀应对方案**：针对 iOS 依赖管理，强制回退使用 CocoaPods（`pubspec.yaml` 中配置 `enable-swift-package-manager: false`）。
- **代码生成冲突**：
  - Freezed / Riverpod Generator 在增量编译报错或生成失效时，首选 `dart run build_runner build --delete-conflicting-outputs`，切忌手动改动 `*.g.dart` 或 `*.freezed.dart`。
- **Android 12+ 启动图适配**：
  - Android 12 系统启动图标强制裁切为圆形，宽版 logo 会畸变。必须通过 `tool/gen_android12_splash.py` 生成方形母版后通过 `flutter_native_splash:create` 部署。

---

## 3. 错误复盘与教训日志 (Error Post-Mortem Log)
| 日期 | 问题表现 | 根本原因 (First Principles) | 改进措施与规避方案 |
| :--- | :--- | :--- | :--- |
| 2026-09-16 | 沙箱内读取外部目录报 `Operation not permitted` | 默认沙箱权限仅隔离在 workspace 目录内 | 对需要操作全局配置 `~/.gemini/config/` 或外部项目目录的操作，需显式请求并利用系统授权机制执行，避免无意义重试。 |
| 2026-09-18 | GitHub Push 被 GH013 Secret Scanning 拦截拒绝 | 配置文件（如 `wrangler.toml`）中包含真实 Resend API Token | 源码仓库只保留占位符或环境变量，敏感凭证统一通过 wrangler secret 或 CI/CD 环境变量注入，严禁提交到 git 历史。 |
| 2026-09-18 | Gradle 构建与依赖拉取阻塞挂起或报代理端口连接失败 | 项目级 `gradle.properties` 硬编码了局域网代理 `127.0.0.1:10090` | 严禁在项目级 `gradle.properties` 提交硬编码代理，个人开发代理必须配置在用户级 `~/.gradle/gradle.properties` 中。 |
| 2026-09-19 | yt-dlp 采录报假失败 (yt-dlp failed) | YouTube 对纯音频流开启 SABR 实验回退选择 360p mp4 封装。脚本仅检测 m4a/webm 等音频扩展名，缺失 mp4/mkv，导致实物下载完成却被判定失败。 | 音源探测扩展名列表必须涵盖 `mp4, m4a, webm, opus, mp3, ogg, mkv`。检查实物文件是否存在与体积达标（>50KB）。 |
| 2026-09-19 | yt-dlp 带 `--max-downloads 1` 导致脚本崩溃 | yt-dlp 达到 `--max-downloads` 限额时会主动以 exit code 101 退出，若在 `subprocess.run` 中设置 `check=True` 会抛异常阻断。 | 禁用 `check=True`，改用实物文件探测和体积验证作为下载成功的真实判定依据。 |

---

## 4. 云存储与多桶集群工程沉淀 (Cloudflare R2 Cluster)
- **双同构前端同步约束**：
  - `MoodyMusic-Web`（纯静态前端工程）与 `MoodyMusic-Server/frontend`（服务端内置前端）保持同构。涉及 CMS 管理后台的 DOM 结构、仪表盘 JS、`r2_stats.json` 状态变动时，必须严格保持两端双向同步，避免服务部署与静态托管产生视图脱节。
- **多桶扩展与安全阀门**：
  - 存储桶集群扩容时，后端监控核算脚本（`check_r2_storage.py`）的主桶过滤条件必须动态排除新桶 public domain 与 name，否则新桶数据会被误算入 Bucket 01。
  - 本地无数据库时，必须提供既有快照 fallback 容灾逻辑，保证在本地纯开发模式下监控面板依然能够毫秒级渲染。
  - 凭证与物理安全：敏感桶凭证保存在被 `.gitignore` 保护的 `r2_config.json` 中，未受限且标记为 `standby` 的新桶 `allow_writes` 保持 true，待前序桶满额后可平滑作为主力写入桶。

---

## 5. 多媒体采录、母带压制与听音大模型质检工程沉淀 (Audio & AI-STT Quality Assurance)
- **Whisper 音乐伴奏前奏的自回归幻觉陷阱 (Repetition Loops)**：
  - **故障表现**：在对纯伴奏或前奏长达 10~25 秒的歌曲进行听音审计时，Groq Whisper (Large v3) 频繁在转写开头输出“作词 李宗盛 作曲 李宗盛 优优独播剧场 字幕志愿者...”，容易被误判为“音频开头被拼接盗版语音水印”而引发误切。
  - **第一性原理剖析**：中文流行音乐训练语料中大量片头 LRC 带有固定的制作人与电视台片头元数据。当音频仅有旋律乐器（吉他/合成器/钢琴）而没有人声时，自回归 Decoder 在低信噪比下退化，触发高频序列生成幻觉。
  - **最佳实践与质检规范**：
    1. 听音质检时切片起始点（`-ss`）必须结合 LRC 歌词中人声唱响的时间戳，避开纯乐器前奏（推荐从人声进入后 10 秒开始取样 30 秒）。
    2. 绝不可单凭转写中出现“作词/作曲 李宗盛”等字眼直接裁切前奏。如怀疑有真正语音水印，必须针对 0~3 秒单独做高频能量/静音检测或人工复核。
- **音源抓取与反爬规避**：
  - YouTube 抓取需配置 `--proxy http://127.0.0.1:7890 --extractor-args "youtube:player_client=android,web" --js-runtimes node:...` 规避 poToken / 403 阻断。
  - B站官方专辑分 P 视频是华语老歌（如王菲、周杰伦早期录音室母带）高质量音频抓取的高效替代来源。
- **母带标准化压制与点亮闭环**：
  - 规范命令：`ffmpeg -y -i raw.mp3 -vn -af loudnorm=I=-14:TP=-1.0:LRA=11 -c:a libmp3lame -b:a 160k -ar 44100 -write_xing 1 -metadata ... target.mp3`。
  - 存储溢出分流：老桶容量超限（>9.5GB）时严格禁止写入，平滑溢出写入新桶（`account_07`），通过 `POST /api/admin/songs/batch-light` 提交 D1 实现全平台无感点亮。
- **骨架元数据与正式发行译名差异处理 (Tracklist Mapping)**：
  - 早期建库抓轨时，部分曲目使用了 Demo 暂定名或纯英文直译（如毛不易《失落成群》骨架登记为《荒原》(Forsaken Dreams)、周华健《情蒸發》登记为 `Vaporized Love`、任贤齐《爱过才心痛》登记为 `Love Won't Hurt Until Loved`）。
  - 在全自动化补齐采录时，必须比对官方发行标准曲目表或英文副标题，建立两端精确映射字典，杜绝因歌名不符导致的漏采或错采。
- **早期曲库爬虫幽灵曲目与混入音轨治理 (Phantom Tracks & Cross-Artist Contamination)**：
  - **故障表现**：个别早期由爬虫抓取的曲目骨架中混入了网络文学台词（如 S.H.E《青春株式會社》中的“他是心理醫生嗎”）或邻近热门音轨（如杜德伟《重愛輕友》、动力火车《給你幸福》），导致自动化采录匹配到错误歌曲或无法搜寻。
  - **治理方法**：
    1. 交叉比对台湾官方实体唱片发行 Tracklist（如 Apple Music、KKBOX）定位真实缺失曲目（如《Belief》、《給我多一點》、《記得要忘記》）。
    2. 使用 Cloudflare Worker 后台路由 `POST /api/admin/ops/songs/batch-update`，批量对曲名进行热更正，无需破坏既有歌曲 ID 关联。
    3. 重新采录正确音源并通过 `POST /api/admin/songs/batch-light` 覆盖音频与 LRC 歌词，彻底消除错配。


---

## 30. 曲库自动化采录“同名李鬼污染”与“古早占位骨架偏差”正本清源规约 (2026-09-28)

- **业务背景与故障表现**：
  在动力火车专辑歌曲体检中，用户听音发现大量歌曲非动力火车原唱，甚至曲目本身货不对板：
  1. **说唱同名与网络翻唱李鬼**：《我爱过你》错配为说唱歌手连麻Swimming；《看透》错配为法老/Lil Jet；《爱情电影》错配为吴子健REmi；《不只是》错配为小安迪；《再见我的爱人》错配为赵辰龙(Dragon X)；
  2. **万能群星/神曲词曲串歌**：《不甘心不放手》、《可不可能》错套王力宏/陶喆群星抗击SARS《手牵手》；《不要怪我》、《Sorry Sunday》、《Com'on Baby》、《Bye Bye Subway》大面积错套《第一滴泪》或《当》；
  3. **早期爬虫幽灵曲目与专辑骨架错乱**：《背叛情歌》第2首曲名错为《不要怪 me》；《都是因为爱》被混入陈淑桦《滚滚红尘》等8首拼盘错歌；《结伴》混入郑中基《我这个你不爱的人》及重复的《背叛情歌》。
- **第一性原理与根因剖析 (Root Causes)**：
  1. **自动化采录仅以“曲名”搜索引发的盲目命中**：许多流行金曲与网络说唱、主播同名，搜索引擎优先返回新潮或无版权限制的同名翻唱，未将 `演唱者必须包含动力火车且属于录音室版本` 作为硬性过滤前置断言；
  2. **第三方平台搜索联想溢出**：搜索某些歌曲时，网易云/酷狗因版权限制无原版，返回由动力火车客串的群星合辑（如《手牵手》），脚本提取了第一条，造成整张专辑多首曲目词曲全部变成《手牵手》；
  3. **建库抓轨源混乱**：早期爬虫抓取了民间自制歌单或 Demo 占位曲目，未与唱片公司官方（华研国际 / 上华唱片）实体发行 Tracklist 进行交叉校验。
- **最佳实践与治理 SOP (Remediation & Best Practices)**：
  1. **官方标准发行档案锚定 (Official Tracklist Grounding)**：
     - 在采录前，必须优先核实唱片公司（华研国际官网 / 维基百科官方唱片词条 / 官方黑胶实体盘面）的精确曲序与曲名；
     - 发现曲名偏差立即调用 `POST /api/admin/songs/batch-update` 热更正（如《不要怪 me》 -> 《不要怪我》）。
  2. **官方录音室音源（YouTube Topic / 华研官方频道）优先采集**：
     - 优先提取 YouTube 生成的官方录音室音源（`动力火车 - Topic` 纯录音室母带），杜绝 MV 剧情对话杂音或现场版瑕疵；
     - yt-dlp 必须携带 `--extractor-args "youtube:player_client=ios,web,mweb"` 彻底杜绝 HTTP 403 阻断；
     - 必须以实物文件大小（>50KB）与多扩展名探测判断下载成功。
  3. **声学标准化母带压制与 LRC 精密清洗**：
     - 统一压制参数：`loudnorm=I=-14:TP=-1.0:LRA=11 -c:a libmp3lame -b:a 160k -ar 44100`；
     - 歌词必须进行 `[id:`, `[qq:`, `[hash:` 等私有标签与 BOM 清洗，并校验歌词正文文本与歌手名吻合，杜绝广告与说唱李鬼；
  4. **分布式 R2 多桶集群规范与 D1 原子切链**：
     - 遵循 `cloudflare-r2-cluster-ops` 规约，音频与歌词写入当前唯一的活跃写入桶（`account_11`）；
     - 批量调用 `POST /api/admin/songs/batch-light` 完成 D1 原子切链，并逐一发起 HTTP HEAD 校验返回 HTTP 200 闭环交付。

---

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

---

## 33. Groq Whisper 多 Token 轮换与 429 动态故障转移规约 (Groq Token Pool & 429 Rate-Limit Failover) (2026-09-28)

- **业务背景与单点瓶颈**：
  在音频采录与入库核验中，Groq Whisper (`whisper-large-v3`) 是保障音质与内容真伪的核心声学质检门禁。然而 Groq 免费层具备严格的限频机制（单 Token 20 RPM / 2000 RPD / 25,000 TPM）。在执行批量多专辑连续重采或多并发核验时，单一 Token 极易触发 `HTTP 429 Too Many Requests (Rate limit reached)`，导致全流程阻塞挂起或引发假阳性报错中断。
- **长效架构与调度标准**：
  1. **凭证隔离与多端中心化沉淀 (Multi-Tier Credential Safety)**：
     - 严禁在脚本或代码中硬编码任何 Token；
     - 物理凭据统一沉淀于 `MoodyMusic-Server/groq_config.json`，且受 `.gitignore` 保护绝不入版本库；
     - 云端在 Notion 知识主页「MOODY 音乐档案项目 (Cloudflare Worker + R2)」持久化维护 3 个及以上绑定账号的 API Keys 清单与验证状态。
  2. **线程安全多 Token 轮询调度器 (Round-Robin with Lock)**：
     - 封装核心模块 `groq_manager.py`，设计 `GroqTokenPool`；
     - 使用 `threading.Lock()` 保障多线程并发请求时的原子轮转获取，消除多任务撞车；
     - 保证请求平均分摊至所有健康 Token，有效将系统并发与日调用配额提升 3 倍。
  3. **429 智能熔断与无感故障转移 (Failover & Cooldown Pipeline)**：
     - 捕获 HTTP 429 状态码时，立即将触发限流的 Token 标记为熔断冷却（默认 60 秒冷却期）；
     - 核心调用函数 `verify_audio_with_groq` 自动透明无缝切换到下一健康 Token 重新发起请求，流水线零感知、零阻塞；
     - 仅当所有 Token 均处于冷却期时才抛出等待异常，彻底消除偶发抖动。
  4. **声学切片轻量化与高保真繁简比对**：
     - 强制将上传音频切片压制为 64kbps 单声道轻量 MP3（~400KB），极大节省带宽与 TPM 消耗；
     - 采用 `zhconv` 简体归一化与字符集重合度模糊匹配，稳健兼容港台原版繁体与方言发音差异。

