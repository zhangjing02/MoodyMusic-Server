# MOODY 内部开发知识库 (AI 持久化规则)

## 🏗️ 基础设施核心快照 (Infrastructure Snapshot)

### 1. 运行环境 (Runtime)
- **Web 前端 & CMS 后台**: Vercel (`https://moody-music-archiv-vercel.vercel.app/` 与 `/admin/`)
- **API 中台**: Cloudflare Workers (`https://m-api.changgepd.ccwu.cc`)
- **源码仓库**: GitHub (`zhangjing02/MoodyMusic-Web` 与 `zhangjing02/MoodyMusic-Server`)

### 2. 存储与数据库 (Storage & DB)
- **R2 八桶集群**: `moody-music-asset` (01 ~ 08) 80GB 独立隔离池
- **D1 数据库**: 核心元数据（歌曲、专辑、名册）
- **Supabase**: 身份验证与社交评论

### 3. 网络与域名 (Networking)
- **生产 API**: `https://m-api.changgepd.ccwu.cc`
- **资产直链**: `https://r2.changgepd.ccwu.cc` 等多桶 CDN
- **Web 端点**: `https://moody-music-archiv-vercel.vercel.app`

---

## 🎲 自动化与代码 (Automation & Assets)
- **GitHub Server**: `https://github.com/zhangjing02/MoodyMusic-Server`
- **GitHub Web**: `https://github.com/zhangjing02/MoodyMusic-Web` (联动 Vercel)
- **Hugging Face**: `hf_iox...` (用于备份同步)

---

## 🎯 核心原则 (Core Principles)

### 1. 三击不中对齐原则 (Three-Strike Baseline Alignment)
**定义**：连续 3 次尝试失败且未锁定本质原因时，必须立即停止“盲试”，向用户发起“物理配置对齐请求”（核实截图/Token）。

### 2. 配置即资产原则 (Config-as-an-Asset)
**定义**：任何环境变更（如 Vercel 域名变更、Token 重写）必须第一时间同步至项目配置中心。

---
*注：⚠️ 故障排查红线规则已根据用户要求移至文档最下方。*
