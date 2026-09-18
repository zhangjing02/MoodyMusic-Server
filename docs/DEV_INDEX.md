# MOODY Music Archiv V2 - Dev Index

> Auto-generated: 2026-04-15 (Asia/Shanghai)
> Goal: 开发命令与工作流 quick reference

## 1. 工作目录

- Repo root: `D:\PersonalProject\Music-Archiv-V2`
- Worker: `D:\PersonalProject\Music-Archiv-V2\cloudflare-worker`
- Frontend: `D:\PersonalProject\Music-Archiv-V2\frontend`

## 2. Worker 开发

```powershell
cd D:\PersonalProject\Music-Archiv-V2\cloudflare-worker
npm install
npx wrangler dev
```

Type check：

```powershell
cd D:\PersonalProject\Music-Archiv-V2\cloudflare-worker
npx tsc --noEmit
```

Deploy Worker：

```powershell
cd D:\PersonalProject\Music-Archiv-V2\cloudflare-worker
npx wrangler deploy
```

## 3. D1 Migration 命令

```powershell
cd D:\PersonalProject\Music-Archiv-V2\cloudflare-worker
npx wrangler d1 execute moody-d1-test --remote --file=migrations/001_create_user_profiles.sql
npx wrangler d1 execute moody-d1-test --remote --file=migrations/002_create_roster_system.sql
```

## 4. Frontend 本地调试

静态 Frontend 无需 build：

```powershell
cd D:\PersonalProject\Music-Archiv-V2\frontend
python -m http.server 8000
```

Open:

- Player: `http://localhost:8000`
- Admin: `http://localhost:8000/admin/`

## 5. Docker Build 与 Run

Build image：

```powershell
cd D:\PersonalProject\Music-Archiv-V2
docker build -t moodymusic:latest .
```

Run container（Dockerfile 暴露 8080/8082）：

```powershell
docker run -p 8080:8080 -p 8082:8082 moodymusic:latest
```

## 6. Production Endpoint

- Player: `https://moody-music-archiv-vercel.vercel.app/`
- Admin: `https://moody-music-archiv-vercel.vercel.app/admin/`
- Worker API: `https://m-api.changgepd.ccwu.cc`

## 7. Health Check

```powershell
curl -I https://moody-music-archiv-vercel.vercel.app/
curl -I https://moody-music-archiv-vercel.vercel.app/admin/
curl https://m-api.changgepd.ccwu.cc/api/admin/stats
```

## 8. Deployment Runbook（当前流程）

1. **Web 前端与 CMS 管理后台**：
   - 代码同步推送至 GitHub `zhangjing02/MoodyMusic-Web` 仓库 `main` 分支。
   - Vercel 自动触发秒级流水线，免除一切容器与 Docker 依赖。
2. **Worker 业务中台**：
   - 进入 `cloudflare-worker/` 运行 `npx wrangler deploy`。

## 9. 常见故障排查快捷项

Frontend 未更新：

- 强制刷新浏览器缓存 (`Ctrl+F5` 或 `Ctrl+Shift+R`)
- 检查 GitHub `MoodyMusic-Web` 仓库最后 commit 状态
- 访问 Vercel 控制台查看最新 Deployment 详情

API 请求失败：

- Test worker health endpoint (`https://m-api.changgepd.ccwu.cc/api/admin/stats`)
- Redeploy Worker with `npx wrangler deploy`
- Verify `wrangler.toml` bindings (`DB`, `BUCKET`, Supabase vars)

## 10. 常用索引/扫描命令

列出主要文档：

```powershell
cd D:\PersonalProject\Music-Archiv-V2
Get-ChildItem docs -File
```

列出核心源码文件：

```powershell
Get-ChildItem cloudflare-worker/src -File
Get-ChildItem frontend/admin -File
Get-ChildItem frontend/src/js -File
```

扫描 Route 定义：

```powershell
Select-String -Path cloudflare-worker/src/index.ts -Pattern "app\.(get|post|put|delete)\("
Select-String -Path cloudflare-worker/src/auth.ts -Pattern "app\.(get|post|put|delete)\("
Select-String -Path cloudflare-worker/src/upload.ts -Pattern "(app|uploadApp)\.(get|post|put|delete)\("
```
