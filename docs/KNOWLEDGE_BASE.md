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
