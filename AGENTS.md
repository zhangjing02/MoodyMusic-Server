# AGENTS.md

本文件为 Codex (Codex.ai/code) 提供项目指导，包含架构说明、开发流程和关键实现细节。

---

## 📋 项目概述

**MOODY 音乐库 V2** 是一个现代化的音乐存储与流媒体系统，采用**纯 Worker 架构**：

- **边缘计算**：Cloudflare Worker (TypeScript/Hono) - 所有 API 和数据存储
- **边缘计算**：Cloudflare Worker (TypeScript/Hono) - 所有 API 和数据存储
- **前端界面**：极简播放器 + 管理后台（纯静态 HTML/CSS/JS），托管于 Vercel
- **存储系统**：Cloudflare R2（对象存储，八桶集群 80GB）+ D1 数据库
- **部署方式**：Vercel (Git 联动自动秒级上线) + Cloudflare Worker (wrangler deploy)

### 技术栈
- **边缘计算**：Cloudflare Workers + Hono + D1 数据库
- **存储**：Cloudflare R2（八桶物理隔离集群，兼容 S3 API）
- **前端**：纯静态 HTML/CSS/JavaScript（无框架，托管于 Vercel）
- **部署**：Vercel 自动化部署

---

## 🌐 生产环境配置

### 域名和端点
```
前端播放器：https://moody-music-archiv-vercel.vercel.app/
管理后台：  https://moody-music-archiv-vercel.vercel.app/admin/
Worker API： https://m-api.changgepd.ccwu.cc
```

### ⚠️ 重要架构理解（纯 Worker + Vercel 极速架构）

**为什么采用纯 Worker + Vercel 架构？**
- Cloudflare Worker 与 R2 同地域，上传与解析速度极快
- Worker 直接绑定 D1 和 R2，无需复杂服务器维护
- 全球 CDN 加速，边缘计算低延迟
- 前端代码推送到 GitHub `MoodyMusic-Web` 后，Vercel 自动秒级构建生效，零运维压力

**数据流向**：
```
用户请求 → Vercel 前端 (播放器 / CMS 后台)
           ↓ HTTPS
    Cloudflare Worker (m-api.changgepd.ccwu.cc + D1 数据库)
           ↓
    Cloudflare R2 (八桶对象存储)
```

---

## 🔧 开发命令

### Cloudflare Worker（核心 API）

```bash
cd cloudflare-worker

# 安装依赖
npm install

# 本地开发
npx wrangler dev

# 部署到 Cloudflare
npx wrangler deploy

# 类型检查
npx tsc --noEmit
```

**Wrangler 配置**：
- `wrangler.toml` 定义了 D1 数据库绑定（`moody-d1-test`）
- R2 bucket 绑定（`moody-music-asset`）
- 部署前确保已登录：`npx wrangler login`

### 前端（本地调试）

```bash
cd frontend

# 前端为纯静态 HTML/CSS/JS，无需构建
# 直接用浏览器打开即可

# 或使用简易 HTTP 服务器
python -m http.server 8000
# 然后访问 http://localhost:8000
```

### Docker（生产部署）

```bash
# 构建镜像
docker build -t moodymusic:latest .

# 运行容器（测试）
docker run -p 80:80 moodymusic:latest
```

**Docker 构建**：
- 基于 `nginx:alpine` 镜像
- 只包含前端静态文件（~20MB）
- 自动配置 Nginx 和 Worker 代理

---

## 🏗️ 核心架构

### 纯 Worker 架构

```
┌─────────────────────────────────────┐
│   用户（浏览器）                    │
└──────────────┬──────────────────────┘
               │
               ↓
┌──────────────────────────────────────┐
│  Docker 容器（Nginx + 前端静态文件）  │
│  - 端口 80                           │
│  - 只托管 HTML/CSS/JS                │
│  - 代理 API 请求到 Worker            │
└──────────────┬───────────────────────┘
               │
               ↓
┌──────────────────────────────────────┐
│  Cloudflare Worker（边缘计算）       │
│  - Hono 框架                         │
│  - D1 数据库                         │
│  - R2 存储绑定                       │
└──────────────┬───────────────────────┘
               │
               ↓
┌──────────────────────────────────────┐
│  Cloudflare R2（对象存储）           │
│  - 音乐文件（.mp3）                  │
│  - 专辑封面                          │
│  - 歌词文件（.lrc）                  │
└──────────────────────────────────────┘
```

### 目录结构

```
Music-Archiv-V2/
├── cloudflare-worker/          # 核心业务逻辑
│   ├── src/
│   │   ├── index.ts           # Worker 主文件
│   │   └── upload.ts          # 上传处理逻辑
│   └── wrangler.toml          # Cloudflare 配置
├── frontend/                   # 前端静态文件
│   ├── admin/                 # 管理后台
│   │   ├── index.html
│   │   ├── admin.js
│   │   ├── admin.css
│   │   └── album-manager.js   # 专辑管理功能
│   └── src/                   # 播放器
├── docs/                      # 文档
│   ├── API.md                 # API 文档
│   └── archive/               # 旧文档归档
├── Dockerfile                 # Docker 构建文件
└── README.md                  # 项目说明
```

---

## 🔌 核心 API 接口

### 公共 API（Worker）

```
GET /api/skeleton              # 艺人列表
GET /api/songs                 # 完整歌曲数据
GET /api/search?q={query}      # 全局搜索
GET /api/welcome-images        # 背景图片
```

### 管理 API（Worker）

```
GET  /api/admin/stats                      # 系统统计
GET  /api/admin/albums/search?keyword=xx   # 搜索专辑
GET  /api/admin/albums/detail?album_id=xx  # 专辑详情
POST /api/admin/songs/batch-update          # 批量更新歌曲
POST /api/admin/songs/delete-all            # 清空专辑歌曲
POST /api/admin/songs/batch-insert          # 批量插入歌曲
POST /api/admin/songs/cleanup-no-path       # 清理无路径歌曲
POST /api/admin/albums/delete               # 删除专辑
POST /api/admin/cleanup-duplicates          # 清理重复专辑
POST /api/admin/upload                      # 批量上传
```

**完整 API 文档**：查看 `docs/API.md`

### API 响应规范（必须遵守）

新增或修改接口时必须保持响应结构稳定，方便 Android App 和前端统一处理：

**成功响应**：
```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

- 新接口的业务数据必须放在 `data` 中。
- 兼容旧接口时，可以同时保留顶层业务字段，例如 `claim_token` 与 `data.claim_token` 同时返回，避免 Android `BaseResponse<T>.data` 解析为空。
- 不要只把业务字段放在顶层，尤其是认证、注册、登录、刷新 Token 等 App 强依赖接口。
- 认领注册接口的 `email` 是可选项；不要要求用户注册时输入邮箱。Supabase Auth 使用后端生成的纯 ASCII 内部邮箱，用户真实邮箱只在后续绑定邮箱流程中写入。

**错误响应**：
```json
{
  "code": 1304,
  "error_key": "CLAIM_SECURITY_ANSWER_MISMATCH",
  "message": "第 2 道问题答案不正确",
  "details": {
    "question_index": 2
  }
}
```

- HTTP 状态码只表达协议层分类，JSON `code` 表达具体业务原因。
- `code` 必须全局唯一，不允许不同错误复用同一个业务码。
- App 端应优先按 `code` 或 `error_key` 分支，不要把所有业务失败都压成 `401`。
- Worker 侧应优先使用 `cloudflare-worker/src/error.ts` 中的 `fail()`、`serverError()` 和错误码字典，不要手写散落的 `{ code: 400 }` / `{ code: 401 }`。

---

## 💾 数据库架构

### Cloudflare D1（生产环境）

**核心表结构**：
```sql
-- 艺人表
artists (id, name, region, bio, photo_url)

-- 专辑表
albums (id, title, release_date, genre, cover_url, artist_id)

-- 歌曲表
songs (id, title, duration, file_path, lrc_path, album_id, storage_id, track_index)

-- 用户相关
users, playlists, playlist_songs
```

**重要字段说明**：
- `file_path`：相对路径，带 `music/` 前缀（如 `music/李宗盛/不舍/s_10025.mp3`）
- `storage_id`：存储标识（primary）
- `track_index`：歌曲在专辑中的排序
- **UTF-8 编码严格强制**：所有文本字段使用 UTF-8

---

## 🚀 部署流程

### 前端与 CMS 管理后台（Vercel 自动化）
1. 代码提交至独立 GitHub 仓库 **`MoodyMusic-Web`** 的 `main` 分支。
2. Vercel 自动触发秒级 CI/CD 构建并全球即刻上线：
   - 线上主站：https://moody-music-archiv-vercel.vercel.app/
   - 管理后台：https://moody-music-archiv-vercel.vercel.app/admin/

### 后端 Worker API（Cloudflare）
1. 进入 `cloudflare-worker/` 目录。
2. 执行部署：
   ```bash
   npx wrangler deploy
   ```
3. 生产域名：`https://m-api.changgepd.ccwu.cc`

### 健康检查
```bash
# 检查前端管理后台
curl -I https://moody-music-archiv-vercel.vercel.app/admin/

# 检查 Worker API
curl https://m-api.changgepd.ccwu.cc/api/admin/stats
```

---

## 📝 常见开发任务

### 添加新音乐

使用管理后台：
1. 访问 https://moody-music-archiv-vercel.vercel.app/admin/
2. 点击"☁️ 超级上传"
3. 拖拽音乐文件到上传区域
4. 点击"🚀 执行入库"

### 批量更新歌曲信息

使用管理后台的专辑管理功能：
1. 点击"💿 专辑管理"
2. 搜索专辑
3. 点击"批量编辑歌曲"
4. 在文本框中编辑歌曲信息
5. 点击"保存更改"

或通过 API：
```python
import requests, json

API_BASE = "https://m-api.changgepd.ccwu.cc"
updates = [
    {"id": 10025, "title": "新的歌曲名", "track_index": 1}
]

response = requests.post(
    f"{API_BASE}/api/admin/songs/batch-update",
    data=json.dumps({"updates": updates}, ensure_ascii=False).encode('utf-8'),
    headers={"Content-Type": "application/json; charset=utf-8"}
)
```

---

## 🔧 故障排查

### 前端页面没有更新

1. **硬刷新浏览器**：`Ctrl + Shift + R` 或 `Ctrl + F5`（Windows）/ `Cmd + Shift + R`（Mac）
2. **检查 GitHub 与 Vercel 状态**：
   - 检查 `MoodyMusic-Web` 仓库的最后提交是否成功
   - 访问 Vercel Dashboard 查看最新一次 Deployment 状态

### API 请求失败

1. **检查 Worker 状态**：访问 https://m-api.changgepd.ccwu.cc/api/admin/stats
2. **重新部署 Worker**：
   ```bash
   cd cloudflare-worker
   npx wrangler deploy
   ```

---

## 📚 相关文档

- `README.md` - 中文项目概述
- `docs/API.md` - 完整 API 文档
- `docs/archive/` - 历史文档归档

---

## 🎯 快速参考

### 域名速查
```
生产前端：https://moody-music-archiv-vercel.vercel.app/
生产管理：https://moody-music-archiv-vercel.vercel.app/admin/
Worker API：https://m-api.changgepd.ccwu.cc
```

### 常用 API
```bash
# 获取艺人列表
curl https://m-api.changgepd.ccwu.cc/api/skeleton

# 获取完整数据
curl https://m-api.changgepd.ccwu.cc/api/songs

# 系统统计
curl https://m-api.changgepd.ccwu.cc/api/admin/stats
```

---

## 💡 最佳实践

1. **Worker 优先**：所有业务逻辑在 Cloudflare Worker 中实现
2. **UTF-8 优先**：所有文本数据使用 UTF-8 编码
3. **批量操作**：使用 Worker 的 batch API 提高性能
4. **测试先行**：先在测试环境验证，再应用到生产环境
5. **Vercel 自动化**：前端与 CMS 提交即部署，免去容器运维烦恼

---

**最后更新**：2026-09-18
**维护者**：zhangjing02
**版本**：v14.0 (纯 Worker + Vercel 架构)

---

## 🔍 进一步阅读

### 项目演进历史
- `docs/archive/云端上传架构设计方案.md` - Worker 架构设计决策
- `docs/archive/上传失败问题修复报告.md` - 上传问题排查
- `docs/archive/李宗盛专辑修复总结.md` - 数据修复案例
