# MOODY 音乐库 API 文档 (v15.1)

本文档描述了 MOODY 系统的所有对外接口，基于 **Cloudflare Worker + D1 + R2** 纯边缘计算架构。

**基础 URL**: `https://m-api.changgepd.top`

> 班级认领系统接口分组文档（客户端 API / 管理后台 API）请优先查看：
> `docs/CLASSROOM_API.md`

> 旧域名 `https://moody-worker.changgepd.workers.dev` 仍可使用，但推荐使用自定义域名。

---

## 📋 目录

1. [统一响应与错误码](#统一响应与错误码)
2. [用户认证系统](#用户认证系统) 🔐 **座位认领/登录**
3. [系统状态与统计](#系统状态与统计)
4. [数据查询接口](#数据查询接口)
5. [存储服务](#存储服务)
6. [专辑管理](#专辑管理)
7. [歌曲管理](#歌曲管理)
8. [运营友好接口](#运营友好接口) ⭐ **推荐使用**
9. [数据治理](#数据治理)
10. [调试工具](#调试工具)

---

## 统一响应与错误码

### 成功响应

成功时统一返回。新接口必须把业务对象放入 `data`，并且为了兼容旧 Android/前端，也可以在顶层保留同名字段：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

例如认领校验成功会同时返回顶层 `claim_token` 和 `data.claim_token`。App 如果使用 `BaseResponse<T>`，应读取 `data`；旧客户端如果直接读取顶层字段，也能继续工作。只要 `code = 200` 即表示本次业务处理成功。

### 错误响应

错误时统一返回：

```json
{
  "code": 1304,
  "error_key": "CLAIM_SECURITY_ANSWER_MISMATCH",
  "message": "第 2 道问题答案不正确",
  "details": {
    "question_index": 2,
    "question_id": 2
  }
}
```

App 端判断错误时优先使用 `code` 或 `error_key`，不要只依赖 HTTP 状态码。HTTP 状态码只表示协议层分类，JSON `code` 表示具体业务原因。

### HTTP 状态码使用原则

| HTTP | 使用场景 |
|------|----------|
| 400 | 请求缺少参数、请求体格式错误、参数格式不合法 |
| 401 | 未登录、Token 无效/过期、登录凭证错误 |
| 403 | 已登录但权限不足，或账号未满足操作条件 |
| 404 | 指定资源不存在 |
| 409 | 当前资源状态冲突，例如已认领、重复创建 |
| 410 | 临时凭证或验证码已过期 |
| 422 | 请求格式正确，但业务校验不通过，例如安全题答案错误 |
| 500 | 服务端配置、数据库、外部服务异常 |

### 业务错误码总表

错误码按模块分段，**同一个 code 只表达一种错误语义**。

| code | error_key | HTTP | 说明 | App 建议 |
|------|-----------|------|------|----------|
| 1001 | INVALID_REQUEST_BODY | 400 | 请求体不是合法 JSON 或无法解析 | 提示刷新/重试，检查客户端请求体 |
| 1002 | MISSING_PARAMETER | 400 | 缺少必要参数 | 根据 `details.required` 高亮缺失字段 |
| 1003 | INVALID_PARAMETER | 400 | 参数格式错误 | 提示用户检查输入 |
| 1004 | INVALID_FIELD | 400 | 字段值不合法 | 提示用户修正该字段 |
| 1005 | NO_VALID_FIELDS | 400 | 没有可更新的有效字段 | 不提交空更新 |
| 1101 | UNAUTHENTICATED | 401 | 未携带 Bearer Token | 跳转登录 |
| 1102 | TOKEN_INVALID | 401 | Token 格式或签名无效 | 清除本地 token 后重新登录 |
| 1103 | TOKEN_EXPIRED_OR_INVALID | 401 | Token 过期或验证失败 | 尝试 refresh，失败则重新登录 |
| 1104 | ADMIN_FORBIDDEN | 403 | 需要 admin 或 master 权限 | 隐藏管理员入口或提示无权限 |
| 1105 | MASTER_FORBIDDEN | 403 | 需要 master 权限 | 隐藏最高权限操作 |
| 1201 | LOGIN_FAILED | 401 | 用户名或密码错误 | 提示重新输入 |
| 1202 | REFRESH_TOKEN_INVALID | 401 | refresh_token 无效或过期 | 重新登录 |
| 1203 | USER_NOT_FOUND | 404 | 用户资料不存在 | 提示联系管理员 |
| 1204 | EMAIL_INVALID | 400 | 邮箱格式不正确 | 高亮邮箱输入框 |
| 1205 | RESET_EMAIL_NOT_BOUND | 403 | 账号未绑定邮箱，不能自助找回 | 引导联系班长/管理员 |
| 1206 | RESET_REQUEST_NOT_FOUND | 401 | 未找到有效重置请求 | 重新申请验证码 |
| 1207 | RESET_CODE_EXPIRED | 410 | 验证码已过期 | 重新申请验证码 |
| 1208 | RESET_CODE_MISMATCH | 422 | 验证码不正确 | 提示重新输入验证码 |
| 1209 | PASSWORD_HASH_INVALID | 400 | 密码哈希不是 64 位 SHA-256 hex | 检查 App 本地哈希逻辑 |
| 1210 | PASSWORD_UPDATE_FAILED | 500 | 密码更新失败 | 稍后重试或联系管理员 |
| 1211 | SESSION_CREATE_FAILED | 500 | 登录成功但会话信息缺失 | 稍后重试 |
| 1301 | CLAIM_ROSTER_NOT_FOUND | 404 | 名录/座位不存在 | 刷新座位表 |
| 1302 | CLAIM_ROSTER_ALREADY_CLAIMED | 409 | 该同学/座位已被认领 | 置灰该座位，提示联系班长 |
| 1303 | CLAIM_SECURITY_CONFIG_INVALID | 500 | 安全问题配置不完整 | 提示联系管理员 |
| 1304 | CLAIM_SECURITY_ANSWER_MISMATCH | 422 | 安全题答案错误 | 使用 `details.question_index` 标出第几题 |
| 1305 | CLAIM_TOKEN_INVALID | 401 | claim_token 无效 | 回到安全题校验步骤 |
| 1306 | CLAIM_TOKEN_USED | 409 | claim_token 已被使用 | 重新走认领流程 |
| 1307 | CLAIM_TOKEN_EXPIRED | 410 | claim_token 已过期 | 重新校验安全题 |
| 1308 | CLAIM_FINALIZE_FAILED | 500 | 完成认领注册失败 | 稍后重试或联系管理员 |
| 1309 | ROSTER_NOT_CLAIMED | 409 | 名录尚未被认领 | 禁用重置操作 |
| 1310 | ROSTER_ALREADY_EXISTS | 409 | 名录已存在 | 检查姓名/年份/座位号 |
| 1311 | ROSTER_NOT_FOUND_OR_UNCLAIMED | 404 | 名录不存在或未认领 | 刷新后台名录 |
| 1401 | ROLE_INVALID | 400 | role 只能是 `user/admin/master` | 修正角色参数 |
| 1402 | QUESTION_ANSWERS_INVALID | 400 | 安全问题答案数组不是 3 项 | 修正后台表单 |
| 1501 | STORAGE_OBJECT_KEY_MISSING | 400 | 存储对象 key 缺失 | 检查资源路径 |
| 1502 | STORAGE_OBJECT_NOT_FOUND | 404 | R2 对象不存在 | 使用默认图或提示资源缺失 |
| 1601 | QUERY_MISSING | 400 | 查询参数缺失 | 检查搜索或筛选参数 |
| 1602 | ARTIST_NOT_FOUND | 404 | 艺人不存在 | 提示无匹配艺人 |
| 1603 | ALBUM_NOT_FOUND | 404 | 专辑不存在 | 提示无匹配专辑 |
| 1604 | SONG_NOT_FOUND | 404 | 歌曲不存在 | 提示无匹配歌曲 |
| 1701 | UPLOAD_NO_FILES | 400 | 未检测到上传文件 | 提示选择文件 |
| 1702 | UPLOAD_EMPTY_FILES | 400 | 上传文件为空 | 提示重新选择文件 |
| 1703 | UPLOAD_FAILED | 500 | 上传失败 | 稍后重试 |
| 9000 | INTERNAL_ERROR | 500 | 未归类服务端异常 | 稍后重试或上报日志 |

> 兼容说明：Worker 会把旧接口中历史遗留的 `{ "code": 400 }`、`{ "error": "..." }` 形式自动规范化为上面的错误结构。

### 各接口可能错误码速查

| 接口 | 可能错误码 |
|------|------------|
| `GET /api/roster` | `9000` |
| `POST /api/user/claim/verify` | `1002`, `1301`, `1302`, `1303`, `1304`, `9000` |
| `POST /api/user/claim/finalize` | `1002`, `1209`, `1301`, `1302`, `1305`, `1306`, `1307`, `1308`, `9000` |
| `POST /api/user/login` | `1002`, `1201`, `1211`, `9000` |
| `POST /api/user/refresh` | `1002`, `1202`, `9000` |
| `GET /api/user/me` | `1101`, `1102`, `1103` |
| `PUT /api/user/profile` | `1101`, `1102`, `1103`, `1005`, `9000` |
| `POST /api/user/bind-email` | `1101`, `1102`, `1103`, `1204`, `9000` |
| `POST /api/user/reset/request` | `1002`, `1203`, `1205`, `9000` |
| `POST /api/user/reset/confirm` | `1002`, `1203`, `1206`, `1207`, `1208`, `1209`, `1210`, `9000` |
| `POST /api/user/reset/set-new` | `1101`, `1102`, `1103`, `1209`, `1210`, `9000` |
| `GET /api/user/settings` | `1101`, `1102`, `1103`, `9000` |
| `PUT /api/user/settings` | `1101`, `1102`, `1103`, `1005`, `9000` |
| `GET /storage/*` | `1501`, `1502` |
| `GET /api/welcome-images` | `9000` |
| `GET /api/skeleton` | `9000` |
| `GET /api/songs` | `9000` |
| `GET /api/search` | `1601`, `9000` |
| `GET /api/admin/stats` | `9000` |
| `POST /api/admin/upload` | `1701`, `1702`, `1703` |
| `GET /api/admin/upload/status` | `9000` |
| `GET /api/admin/roster` | `1101`, `1102`, `1103`, `1104`, `9000` |
| `POST /api/admin/roster/add` | `1101`, `1102`, `1103`, `1104`, `1002`, `1310`, `9000` |
| `POST /api/admin/roster/reset` | `1101`, `1102`, `1103`, `1104`, `1002`, `1301`, `1309`, `9000` |
| `POST /api/admin/roster/unclaim` | `1101`, `1102`, `1103`, `1105`, `1002`, `1311`, `9000` |
| `PUT /api/admin/user/role` | `1101`, `1102`, `1103`, `1105`, `1002`, `1203`, `1401`, `9000` |
| `PUT /api/admin/questions` | `1101`, `1102`, `1103`, `1105`, `1402`, `9000` |
| `GET /api/admin/albums/search` | `1002`, `9000` |
| `GET /api/admin/albums/detail` | `1002`, `1603`, `9000` |
| `PATCH /api/admin/albums/:id` | `1005`, `9000` |
| `POST /api/admin/albums/delete` | `1002`, `1603`, `9000` |
| `POST /api/admin/albums/merge` | `1002`, `9000` |
| `POST /api/admin/albums/cleanup-duplicates` | `1002`, `1603`, `9000` |
| `POST /api/admin/cleanup-duplicates` | `9000` |
| `POST /api/admin/fix-paths` | `9000` |
| `POST /api/admin/songs/batch-update` | `1002`, `1005`, `9000` |
| `POST /api/admin/songs/batch-insert` | `1002`, `1603`, `9000` |
| `POST /api/admin/songs/delete-all` | `1002`, `9000` |
| `POST /api/admin/songs/cleanup-no-path` | `1002`, `9000` |
| `GET /api/admin/songs/debug` | `1002`, `1604`, `9000` |
| `POST /api/admin/songs/move` | `1002`, `9000` |
| `POST /api/admin/songs/create-full` | `1002`, `9000` |
| `POST /api/admin/songs/test-update` | `1002`, `1005`, `1604`, `9000` |
| `POST /api/admin/ops/songs/batch-update` | `1002`, `1602`, `1603`, `9000` |
| `POST /api/admin/ops/songs/batch-insert` | `1002`, `9000` |
| `POST /api/admin/ops/albums/rename` | `1002`, `1602`, `1603`, `9000` |
| `POST /api/admin/ops/albums/merge` | `1002`, `1004`, `1602`, `1603`, `9000` |
| `POST /api/admin/ops/albums/delete` | `1002`, `1602`, `1603`, `9000` |
| `POST /api/admin/ops/artists/rename` | `1002`, `1602`, `9000` |
| `GET /api/debug/*` | `1002`, `9000` |

---

## 关于认证

> **音乐浏览接口均可匿名访问**，无需登录即可搜索歌曲、播放音乐。用户系统用于解锁个人功能：
> - ❤️ 个人收藏 / 播放历史同步
> - ⚙️ 个人设置（音量、主题）云端保存

**注册方式**：本系统采用「**白名单座位认领**」，无开放注册，仅限名录内成员。

> 需要认证的接口均标注 🔒，调用时需在 Header 中携带：`Authorization: Bearer <token>`

---

## 用户认证系统

> 基于 **Supabase Auth + JWT** 的用户认证系统，采用「白名单座位认领」模式。

### 认证架构

```
移动端/前端 → Worker (验证 JWT) → Supabase Auth (签发 JWT)
                               → D1 (名录、用户资料、设置)
```

**Token 说明**：
- 认领/登录成功后返回 `token`（access_token，约1小时有效）和 `refresh_token`
- 🔒 接口需在 Header 中携带：`Authorization: Bearer <token>`
- Token 过期后用 `refresh_token` 刷新，无需重新登录

### ⚠️ 密码哈希规范（重要）

所有密码相关接口均**不接受明文密码**，客户端必须先哈希再上传：

```
原始密码 → trim() → SHA-256 → 小写 hex 字符串（64位）→ 上传
```

**Android（Kotlin）示例**：
```kotlin
import java.security.MessageDigest
fun hashPassword(raw: String): String {
    val digest = MessageDigest.getInstance("SHA-256")
    val bytes = digest.digest(raw.trim().toByteArray(Charsets.UTF_8))
    return bytes.joinToString("") { "%02x".format(it) }
}
```

---

### 🗒️ 获取座位表（注册第一步）

获取全班名单及当前认领状态，以及三道安全问题文本。公开接口，无需登录。

**接口**: `GET /api/roster`

**请求示例**:
```bash
curl "https://m-api.changgepd.top/api/roster"
```

**返回示例**:
```json
{
  "code": 200,
  "roster": [
    {
      "id": 1,
      "real_name": "张伟",
      "year_code": "2006",
      "seat_code": "0301",
      "is_claimed": 0,
      "status": "normal"
    },
    {
      "id": 2,
      "real_name": "王芳",
      "year_code": "2006",
      "seat_code": "0302",
      "is_claimed": 1,
      "status": "normal"
    }
  ],
  "security_questions": [
    { "id": 1, "question": "我们的班主任叫什么名字？" },
    { "id": 2, "question": "我们的数学老师叫什么名字？" },
    { "id": 3, "question": "我们的班级在几楼？" }
  ]
}
```

**字段说明**:
| 字段 | 说明 |
|------|------|
| `is_claimed` | `0` = 可认领；`1` = 已被他人认领（置灰） |
| `status` | `normal` = 正常；`reset_pending` = 管理员已重置，等待设置新密码 |

---

### 🔐 校验安全问题（注册第二步）

**接口**: `POST /api/user/claim/verify`

**请求体**:
```json
{
  "roster_id": 1,
  "answers": ["班主任名字", "数学老师名字", "楼层"]
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| roster_id | number | 是 | 从座位表中选择自己的 ID |
| answers | string[] | 是 | 三道安全题的答案，顺序与 `security_questions` 一致；按明文提交 |

> 校验采用**宽容匹配**：会处理大小写、空格、常见后缀（如“老师”），以及楼层等价表达（`3层/3楼/三层/三楼/第3层`）。

**请求示例**:
```bash
curl -X POST "https://m-api.changgepd.top/api/user/claim/verify" \
  -H "Content-Type: application/json" \
  -d '{"roster_id": 1, "answers": ["张明亮老师", "王燕老师", "三楼"]}'
```

**返回示例（成功）**:
```json
{
  "code": 200,
  "message": "验证通过，请在10分钟内完成注册",
  "claim_token": "a1b2c3d4e5f6...",
  "roster": {
    "id": 1,
    "real_name": "张伟",
    "year_code": "2006",
    "seat_code": "0301"
  },
  "data": {
    "claim_token": "a1b2c3d4e5f6...",
    "roster": {
      "id": 1,
      "real_name": "张伟",
      "year_code": "2006",
      "seat_code": "0301"
    }
  }
}
```

> `claim_token` 有效期 **10 分钟**，仅能使用一次。

**错误响应**:
| HTTP 状态码 | code | error_key | 说明 |
|------------|------|-----------|------|
| 400 | 1002 | MISSING_PARAMETER | 参数缺失或 answers 数量不为 3 |
| 404 | 1301 | CLAIM_ROSTER_NOT_FOUND | roster_id 不存在 |
| 409 | 1302 | CLAIM_ROSTER_ALREADY_CLAIMED | 该同学已被他人认领 |
| 422 | 1304 | CLAIM_SECURITY_ANSWER_MISMATCH | 第 N 道问题答案错误，`details.question_index` 表示第几题 |
| 500 | 1303 | CLAIM_SECURITY_CONFIG_INVALID | 安全问题配置错误 |

**答案错误示例**:
```json
{
  "code": 1304,
  "error_key": "CLAIM_SECURITY_ANSWER_MISMATCH",
  "message": "第 2 道问题答案不正确",
  "details": {
    "question_index": 2,
    "question_id": 2
  }
}
```

---

### ✅ 完成认领注册（注册第三步）

**接口**: `POST /api/user/claim/finalize`

**请求体**:
```json
{
  "claim_token": "a1b2c3d4e5f6...",
  "password_hash": "e3b0c44298fc1c149afbf4c8996fb924...",
  "email": "zhangwei@example.com"
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| claim_token | string | 是 | 第二步返回的临时令牌 |
| password_hash | string | 是 | SHA-256(原始密码)，64 位小写 hex |
| email | string | 否 | 可选绑定邮箱；注册时可以不填，后续在账户设置中再绑定 |

> 邮箱不是注册必填项。后端会使用纯 ASCII 的内部 Auth 邮箱创建 Supabase 账号，用户真实邮箱仅用于后续找回密码；不填写时 `user.email` 为 `null`。

**请求示例**:
```bash
curl -X POST "https://m-api.changgepd.top/api/user/claim/finalize" \
  -H "Content-Type: application/json" \
  -d '{"claim_token": "a1b2...", "password_hash": "e3b0c4..."}'
```

**返回示例（成功）**:
```json
{
  "code": 200,
  "message": "认领成功！欢迎 张伟",
  "user": {
    "id": 1,
    "username": "2006.0301张伟",
    "email": null,
    "level": 1,
    "role": "user",
    "avatar_url": null,
    "created_at": "2026-04-13T06:00:00.000Z"
  },
  "token": "eyJhbGci...",
  "refresh_token": "v1.Xk9p...",
  "data": {
    "user": {
      "id": 1,
      "username": "2006.0301张伟",
      "email": null,
      "level": 1,
      "role": "user",
      "avatar_url": null,
      "created_at": "2026-04-13T06:00:00.000Z"
    },
    "token": "eyJhbGci...",
    "refresh_token": "v1.Xk9p..."
  }
}
```

> 注册即登录，直接存储 `token` 和 `refresh_token` 进入主界面。用户名由系统自动生成，格式为 `{年份}.{座位}{姓名}`。

**错误响应**:
| HTTP 状态码 | code | error_key | 说明 |
|------------|------|-----------|------|
| 400 | 1002 | MISSING_PARAMETER | 缺少 claim_token 或 password_hash |
| 400 | 1209 | PASSWORD_HASH_INVALID | password_hash 不是 64 位 SHA-256 hex |
| 401 | 1305 | CLAIM_TOKEN_INVALID | claim_token 无效 |
| 404 | 1301 | CLAIM_ROSTER_NOT_FOUND | 名录不存在 |
| 409 | 1302 | CLAIM_ROSTER_ALREADY_CLAIMED | 该名录已被他人认领 |
| 409 | 1306 | CLAIM_TOKEN_USED | claim_token 已被使用 |
| 410 | 1307 | CLAIM_TOKEN_EXPIRED | claim_token 已过期 |
| 500 | 1308 | CLAIM_FINALIZE_FAILED | 注册/认领写入失败 |

---

### 🔑 用户登录

**接口**: `POST /api/user/login`

**请求体**:
```json
{
  "username": "2006.0301张伟",
  "password_hash": "e3b0c44298fc..."
}
```

**请求示例**:
```bash
curl -X POST "https://m-api.changgepd.top/api/user/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "2006.0301张伟", "password_hash": "e3b0c4..."}'
```

**返回示例（成功）**:
```json
{
  "code": 200,
  "message": "登录成功",
  "user": {
    "id": 1,
    "username": "2006.0301张伟",
    "level": 1,
    "role": "user",
    "avatar_url": null
  },
  "token": "eyJhbGci...",
  "refresh_token": "v1.Xk9p...",
  "reset_pending": false
}
```

> ⚠️ **`reset_pending: true` 时**：须强制跳转「设置新密码」页，调用 [管理员重置后设置新密码](#-管理员重置后设置新密码-🔒)，完成前不得进入主界面。

**错误响应**:
| HTTP 状态码 | code | error_key | 说明 |
|------------|------|-----------|------|
| 400 | 1002 | MISSING_PARAMETER | 缺少 username 或 password_hash |
| 401 | 1201 | LOGIN_FAILED | 用户名或密码错误 |
| 500 | 1211 | SESSION_CREATE_FAILED | 登录成功但未拿到会话信息 |

---

### 🔄 刷新 Token

**接口**: `POST /api/user/refresh`

**请求体**:
```json
{
  "refresh_token": "v1.MrH4..."
}
```

**请求示例**:
```bash
curl -X POST "https://m-api.changgepd.top/api/user/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "v1.MrH4..."}'
```

**返回示例**:
```json
{
  "code": 200,
  "message": "刷新成功",
  "token": "eyJhbGci...",
  "refresh_token": "v1.Xk9p..."
}
```

**错误响应**:
| HTTP 状态码 | code | error_key | 说明 |
|------------|------|-----------|------|
| 400 | 1002 | MISSING_PARAMETER | 缺少 refresh_token |
| 401 | 1202 | REFRESH_TOKEN_INVALID | refresh_token 无效或已过期 |

---

### 👤 获取当前用户信息 🔒

**接口**: `GET /api/user/me`

**请求示例**:
```bash
curl "https://m-api.changgepd.top/api/user/me" \
  -H "Authorization: Bearer eyJhbGci..."
```

**返回示例**:
```json
{
  "code": 200,
  "user": {
    "id": 1,
    "username": "2006.0301张伟",
    "level": 1,
    "role": "user",
    "avatar_url": null,
    "created_at": "2026-04-13T06:00:00.000Z"
  },
  "roster": {
    "id": 1,
    "real_name": "张伟",
    "seat_code": "0301",
    "status": "normal"
  }
}
```

**错误响应**:
| HTTP 状态码 | code | error_key | 说明 |
|------------|------|-----------|------|
| 401 | 1101 | UNAUTHENTICATED | 未携带 Bearer Token |
| 401 | 1102 | TOKEN_INVALID | Token 格式或签名无效 |
| 401 | 1103 | TOKEN_EXPIRED_OR_INVALID | Token 已过期或验证失败 |

---

### ✏️ 更新用户头像 🔒

用户名由系统生成，不可修改；仅支持更新头像。

**接口**: `PUT /api/user/profile`

**请求体**:
```json
{
  "avatar_url": "https://cdn.example.com/avatar/abc.jpg"
}
```

**请求示例**:
```bash
curl -X PUT "https://m-api.changgepd.top/api/user/profile" \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"avatar_url": "https://cdn.example.com/avatar/abc.jpg"}'
```

**返回示例**:
```json
{
  "code": 200,
  "message": "更新成功",
  "user": { "id": 1, "username": "2006.0301张伟", "avatar_url": "https://cdn.example.com/avatar/abc.jpg" }
}
```

---

### 📧 绑定邮箱 🔒

注册时跳过邮箱的用户可在账户设置页补绑，用于支持邮件找回密码。

**接口**: `POST /api/user/bind-email`

**请求体**:
```json
{
  "email": "user@example.com"
}
```

**请求示例**:
```bash
curl -X POST "https://m-api.changgepd.top/api/user/bind-email" \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

**返回示例**:
```json
{
  "code": 200,
  "message": "邮箱绑定成功"
}
```

---

### 📬 申请密码重置邮件

忘记密码时，向绑定邮箱发送验证码。

**接口**: `POST /api/user/reset/request`

**请求体**:
```json
{
  "username": "2006.0301张伟"
}
```

**请求示例**:
```bash
curl -X POST "https://m-api.changgepd.top/api/user/reset/request" \
  -H "Content-Type: application/json" \
  -d '{"username": "2006.0301张伟"}'
```

**返回示例**:
```json
{
  "code": 200,
  "message": "验证码已发送至 zh***@example.com，15分钟内有效"
}
```

**错误响应**:
| HTTP 状态码 | code | error_key | 说明 |
|------------|------|-----------|------|
| 400 | 1002 | MISSING_PARAMETER | 缺少 username |
| 403 | 1205 | RESET_EMAIL_NOT_BOUND | 未绑定邮箱，提示联系班长重置 |
| 404 | 1203 | USER_NOT_FOUND | 用户不存在 |

---

### 🔑 验证码确认重置密码

**接口**: `POST /api/user/reset/confirm`

**请求体**:
```json
{
  "username": "2006.0301张伟",
  "code": "123456",
  "new_password_hash": "e3b0c44298fc..."
}
```

**请求示例**:
```bash
curl -X POST "https://m-api.changgepd.top/api/user/reset/confirm" \
  -H "Content-Type: application/json" \
  -d '{"username": "2006.0301张伟", "code": "123456", "new_password_hash": "e3b0c4..."}'
```

**返回示例**:
```json
{
  "code": 200,
  "message": "密码重置成功，请使用新密码登录"
}
```

---

### 🔐 管理员重置后设置新密码 🔒

适用于登录时收到 `reset_pending: true` 的情况，必须强制完成此步骤才可进入主界面。

**接口**: `POST /api/user/reset/set-new`

**请求体**:
```json
{
  "new_password_hash": "e3b0c44298fc..."
}
```

**请求示例**:
```bash
curl -X POST "https://m-api.changgepd.top/api/user/reset/set-new" \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"new_password_hash": "e3b0c4..."}'
```

**返回示例**:
```json
{
  "code": 200,
  "message": "新密码设置成功"
}
```

---

### ⚙️ 获取用户设置 🔒

**接口**: `GET /api/user/settings`

**请求示例**:
```bash
curl "https://m-api.changgepd.top/api/user/settings" \
  -H "Authorization: Bearer eyJhbGci..."
```

**返回示例**:
```json
{
  "code": 200,
  "last_volume": 0.7,
  "theme_mode": "dark",
  "auto_play": 1
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| last_volume | number | 音量，0.0 ~ 1.0 |
| theme_mode | string | `"dark"` \| `"light"` |
| auto_play | number | `1` = 开启，`0` = 关闭 |

---

### ⚙️ 更新用户设置 🔒

**接口**: `PUT /api/user/settings`

**请求体（字段均可选）**:
```json
{
  "last_volume": 0.8,
  "theme_mode": "light",
  "auto_play": 0
}
```

**请求示例**:
```bash
curl -X PUT "https://m-api.changgepd.top/api/user/settings" \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"last_volume": 0.8, "theme_mode": "dark"}'
```

**返回示例**:
```json
{
  "code": 200,
  "message": "设置已更新"
}
```

---

### 👥 管理员接口

> 以下接口需要 `admin` 或 `master` 权限的 Token。

**权限等级**:
| role | 获取方式 | 额外能力 |
|------|---------|--------|
| `user` | 完成认领后自动授予 | — |
| `admin` | master 授权 | 查看名录、新增条目、重置密码标记 |
| `master` | 系统内置 | + 撤销认领、修改权限、更新安全题答案 |

#### 查看全部名录 🔒（admin）

**接口**: `GET /api/admin/roster`

返回所有名录信息和认领状态。

---

#### 新增名录条目 🔒（admin）

**接口**: `POST /api/admin/roster/add`

**请求体**:
```json
{
  "real_name": "补录同学",
  "year_code": "2006",
  "seat_code": "0341"
}
```

---

#### 重置某人密码 🔒（admin）

执行后，该用户下次登录时 `reset_pending: true`，客户端须强制引导设置新密码。

**接口**: `POST /api/admin/roster/reset`

**请求体**:
```json
{ "roster_id": 1 }
```

---

#### 完全撤销认领 🔒（master）

仅断开名录与账户关联，不删除 Supabase 账户，座位重新开放认领。

**接口**: `POST /api/admin/roster/unclaim`

**请求体**:
```json
{ "roster_id": 1 }
```

---

#### 修改用户权限 🔒（master）

**接口**: `PUT /api/admin/user/role`

**请求体**:
```json
{
  "username": "2006.0302王芳",
  "role": "admin"
}
```

---

#### 更新安全问题答案 🔒（master）

> 默认已内置一组可用答案；如需调整可调用此接口覆盖。答案按明文保存，便于维护。

**接口**: `PUT /api/admin/questions`

**请求体**:
```json
{
  "answers": ["班主任真实姓名", "数学老师真实姓名", "楼层"]
}
```

**请求示例**:
```bash
curl -X PUT "https://m-api.changgepd.top/api/admin/questions" \
  -H "Authorization: Bearer <master_token>" \
  -H "Content-Type: application/json" \
  -d '{"answers": ["李明", "王平", "3"]}'
```

**返回示例**:
```json
{
  "code": 200,
  "message": "安全问题答案已更新"
}
```

---

## 系统状态与统计

### 🔵 系统探活

检查 Worker 服务是否正常运行。

**接口**: `GET /`

**请求示例**:
```bash
curl https://m-api.changgepd.top/
```

**返回示例**:
```
MOODY API Edge Worker is running!
```

---

### 📊 系统统计

获取数据库中艺人、专辑、歌曲的总数。

**接口**: `GET /api/admin/stats`

**请求示例**:
```bash
curl https://m-api.changgepd.top/api/admin/stats
```

**返回示例**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "artists": 120,
    "albums": 1562,
    "tracks": 27661
  }
}
```

---

## 数据查询接口

### 🎵 艺人骨架列表

获取艺人列表，包含专辑数量统计。用于首屏极速加载。

**接口**: `GET /api/skeleton`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| group | string | 否 | 按首字母筛选（如 "A", "Z"） |

**请求示例**:
```bash
# 获取所有艺人
curl https://m-api.changgepd.top/api/skeleton

# 按首字母筛选
curl https://m-api.changgepd.top/api/skeleton?group=Z
```

**返回示例**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "artists": [
      {
        "id": "db_1",
        "name": "周杰伦",
        "group": "Z",
        "category": "华语",
        "avatar": "https://m-api.changgepd.top/storage/avatars/zhoujielun.jpg",
        "albumCount": 14
      }
    ]
  }
}
```

---

### 🎶 完整歌曲数据

获取完整的艺人 -> 专辑 -> 歌曲嵌套结构，包含文件路径。

**接口**: `GET /api/songs`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| artistId | string | 否 | 艺人 ID（精确匹配，如 `db_123`） |
| artist | string | 否 | 歌手名（模糊匹配） |
| album | string | 否 | 专辑名（模糊匹配，支持繁简体） |

**请求示例**:
```bash
# 获取所有数据
curl https://m-api.changgepd.top/api/songs

# 按艺人筛选
curl https://m-api.changgepd.top/api/songs?artist=周杰伦

# 按专辑筛选
curl https://m-api.changgepd.top/api/songs?album=Jay
```

**返回示例**:
```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": "db_1",
      "name": "周杰伦",
      "category": "华语",
      "avatar": "/storage/avatars/zhoujielun.jpg",
      "group": "Z",
      "albums": [
        {
          "title": "Jay",
          "year": "2000",
          "cover": "/storage/covers/c_1.jpg",
          "songs": [
            {
              "title": "可爱女人",
              "path": "music/周杰伦/Jay/s_10001.mp3",
              "lrc_path": "music/周杰伦/Jay/s_10001.lrc",
              "TrackIndex": 1
            }
          ]
        }
      ]
    }
  ]
}
```

---

### 🔍 全局模糊搜索

跨维度搜索歌手、专辑、歌曲名。

**接口**: `GET /api/search`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| q | string | 是 | 搜索关键词 |

**请求示例**:
```bash
curl "https://m-api.changgepd.top/api/search?q=晴天"
```

**返回示例**:
```json
{
  "code": 200,
  "message": "找到 15 条相关结果",
  "data": {
    "artists": [],
    "albums": [
      {
        "id": 8,
        "title": "七里香",
        "ArtistID": 1,
        "CoverURL": "/storage/covers/c_8.jpg"
      }
    ],
    "songs": [
      {
        "id": 10025,
        "title": "晴天",
        "ArtistID": 1,
        "Album_ID": 8,
        "FilePath": "music/周杰伦/七里香/s_10025.mp3"
      }
    ]
  }
}
```

---

### 🖼️ 欢迎页背景图

获取欢迎页随机背景图片列表。

**接口**: `GET /api/welcome-images`

**请求示例**:
```bash
curl https://m-api.changgepd.top/api/welcome-images
```

**返回示例**:
```json
{
  "code": 200,
  "message": "success",
  "data": [
    "cover1.jpg",
    "cover2.png",
    "cover3.webp"
  ]
}
```

---

## 存储服务

### 📦 R2 对象存储代理

直接访问 R2 存储的对象（音乐文件、封面、歌词等）。

**接口**: `GET /storage/{path}`

**说明**:
- 自动 CDN 缓存（30天）
- 支持所有媒体类型
- 路径示例：
  - `/storage/music/周杰伦/Jay/song.mp3`
  - `/storage/covers/c_1.jpg`
  - `/storage/lyrics/song.lrc`

**请求示例**:
```bash
# 获取音乐文件
curl https://m-api.changgepd.top/storage/music/周杰伦/Jay/s_10001.mp3

# 获取专辑封面
curl https://m-api.changgepd.top/storage/covers/c_1.jpg -o cover.jpg
```

---

## 专辑管理

### 🔍 搜索专辑

根据关键词或艺人 ID 搜索专辑。

**接口**: `GET /api/admin/albums/search`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| keyword | string | 否* | 搜索关键词（专辑名，支持模糊搜索） |
| artist_id | number | 否* | 艺人 ID（精确匹配） |
| limit | number | 否 | 返回数量限制，默认 20 |

*至少提供 `keyword` 或 `artist_id` 中的一个

**请求示例**:
```bash
curl "https://m-api.changgepd.top/api/admin/albums/search?keyword=smile&limit=20"
```

**返回示例**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "count": 2,
    "albums": [
      {
        "id": 1562,
        "title": "Smile",
        "artist_id": 109,
        "artist_name": "张学友",
        "release_date": "1985",
        "cover_url": "https://m-api.changgepd.top/storage/covers/c_1562.jpg",
        "song_count": 11
      }
    ]
  }
}
```

---

### 📀 获取专辑详情

获取专辑的完整信息，包括艺人信息和歌曲列表。

**接口**: `GET /api/admin/albums/detail`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| album_id | number | 是 | 专辑 ID |

**请求示例**:
```bash
curl "https://m-api.changgepd.top/api/admin/albums/detail?album_id=1562"
```

---

### ✏️ 更新专辑信息

更新专辑的标题、发布日期、封面或艺人。

**接口**: `PATCH /api/admin/albums/:id`

**请求体**:
```json
{
  "title": "Smile (Remastered)",
  "release_date": "1985-10"
}
```

**请求示例**:
```bash
curl -X PATCH "https://m-api.changgepd.top/api/admin/albums/1562" \
  -H "Content-Type: application/json" \
  -d '{"title": "Smile (Remastered)", "release_date": "1985-10"}'
```

---

### 🗑️ 删除专辑

删除专辑及其所有歌曲。

**接口**: `POST /api/admin/albums/delete`

**请求体**:
```json
{
  "album_id": 1562
}
```

---

### 🔀 合并专辑

将一个专辑的所有歌曲合并到另一个专辑，然后删除源专辑。

**接口**: `POST /api/admin/albums/merge`

**请求体**:
```json
{
  "sourceId": 100,
  "targetId": 101
}
```

---

## 歌曲管理

### ✏️ 批量更新歌曲

批量更新歌曲的标题、TrackIndex 等信息。

**接口**: `POST /api/admin/songs/batch-update`

**请求体**:
```json
{
  "updates": [
    {"id": 27661, "title": "轻抚你的脸", "track_index": 1},
    {"id": 27657, "title": "爱的卡帮", "track_index": 2}
  ]
}
```

---

### 🧹 清空专辑下所有歌曲

删除指定专辑下的所有歌曲（保留专辑本身）。

**接口**: `POST /api/admin/songs/delete-all`

**请求体**:
```json
{
  "album_id": 1562
}
```

---

### ➕ 批量插入歌曲

批量插入新歌曲到指定专辑。

**接口**: `POST /api/admin/songs/batch-insert`

**请求体**:
```json
{
  "album_id": 1562,
  "songs": [
    {"title": "新歌曲", "file_path": "music/张学友/Smile/new_song.mp3", "track_index": 12}
  ]
}
```

---

### 🔄 移动歌曲到专辑

将指定歌曲移动到另一个专辑。

**接口**: `POST /api/admin/songs/move`

**请求体**:
```json
{
  "targetAlbumId": 100,
  "songIds": [101, 102, 103]
}
```

或使用 ID 范围：
```json
{
  "targetAlbumId": 100,
  "songIdRange": [101, 200]
}
```

---

### 📝 创建完整元数据

创建完整的艺人、专辑、歌曲元数据。用于后台上传后同步数据到 D1。

**接口**: `POST /api/admin/songs/create-full`

**请求体**:
```json
{
  "songs": [
    {
      "title": "可爱女人",
      "artist_name": "周杰伦",
      "album_title": "Jay",
      "file_path": "music/周杰伦/Jay/s_10001.mp3",
      "track_index": 1
    }
  ]
}
```

---

### 🔍 调试歌曲信息

查询指定 ID 的歌曲详细信息。

**接口**: `GET /api/admin/songs/debug?id={id}`

---

### 📤 文件上传（智能匹配）

上传音频文件并自动匹配到数据库中的歌曲记录。

**接口**: `POST /api/admin/upload`

**请求体** (multipart/form-data):
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| files | File[] | 是 | 音频文件（支持多个） |
| artistOverride | string | 否 | 歌手名称覆盖 |
| albumOverride | string | 否 | 专辑名称覆盖 |
| titleOverride | string | 否 | 歌曲标题覆盖 |

---

## 运营友好接口

> ⭐ **推荐使用**：这些接口专为运营人员设计，使用**名称**而非 ID，操作简单直观，无需了解数据库结构。

所有运营接口都支持 **dry_run（预览模式）**，可以在不实际修改数据的情况下预览操作结果。

---

### 🎵 批量更新歌曲（按名称）

通过歌手名、专辑名来批量更新歌曲标题和曲目序号。

**接口**: `POST /api/admin/ops/songs/batch-update`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| artist_name | string | 是 | 歌手名称（支持模糊匹配） |
| album_title | string | 是 | 专辑名称（支持模糊匹配） |
| updates | array | 是 | 更新列表 |
| dry_run | boolean | 否 | 预览模式（不实际修改），默认 false |

**请求示例**:
```bash
curl -X POST "https://m-api.changgepd.top/api/admin/ops/songs/batch-update" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "artist_name": "张学友",
    "album_title": "Smile",
    "dry_run": true,
    "updates": [
      {"old_title": "轻抚你的脸", "new_title": "轻抚你的脸", "track_index": 1}
    ]
  }'
```

---

### 💿 重命名专辑

**接口**: `POST /api/admin/ops/albums/rename`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| artist_name | string | 是 | 歌手名称 |
| old_title | string | 是 | 专辑旧标题 |
| new_title | string | 是 | 专辑新标题 |
| dry_run | boolean | 否 | 预览模式 |

---

### 🎤 重命名艺人

**接口**: `POST /api/admin/ops/artists/rename`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| old_name | string | 是 | 艺人旧名称 |
| new_name | string | 是 | 艺人新名称 |
| dry_run | boolean | 否 | 预览模式 |

---

### 🔀 合并专辑（按名称）

**接口**: `POST /api/admin/ops/albums/merge`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| artist_name | string | 是 | 歌手名称 |
| source_album_title | string | 是 | 源专辑标题（将被删除） |
| target_album_title | string | 是 | 目标专辑标题（保留） |
| dry_run | boolean | 否 | 预览模式 |

---

### 🗑️ 删除专辑（按名称）

**接口**: `POST /api/admin/ops/albums/delete`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| artist_name | string | 是 | 歌手名称 |
| album_title | string | 是 | 专辑标题 |
| dry_run | boolean | 否 | 预览模式 |

---

### ➕ 批量插入歌曲（按名称）

**接口**: `POST /api/admin/ops/songs/batch-insert`

**参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| artist_name | string | 是 | 歌手名称（不存在会自动创建） |
| album_title | string | 是 | 专辑名称（不存在会自动创建） |
| songs | array | 是 | 歌曲列表 |
| dry_run | boolean | 否 | 预览模式 |

---

### 🌟 运营接口 vs 技术接口对比

| 功能 | 运营接口 ⭐ | 技术接口 |
|------|------------|----------|
| 更新歌曲 | `POST /api/admin/ops/songs/batch-update` | `POST /api/admin/songs/batch-update` |
| 重命名专辑 | `POST /api/admin/ops/albums/rename` | `PATCH /api/admin/albums/:id` |
| 合并专辑 | `POST /api/admin/ops/albums/merge` | `POST /api/admin/albums/merge` |
| 删除专辑 | `POST /api/admin/ops/albums/delete` | `POST /api/admin/albums/delete` |
| 参数方式 | 使用**名称** | 使用 **ID** |
| 预览模式 | ✅ 支持 (`dry_run`) | ❌ 不支持 |
| 模糊匹配 | ✅ 支持 | ❌ 不支持 |

---

## 数据治理

### 🧹 清理无路径歌曲

删除指定专辑下没有 `file_path` 的歌曲记录。

**接口**: `POST /api/admin/songs/cleanup-no-path`

---

### 🧹 清理重复专辑

自动识别并删除重复的专辑占位符。

**接口**: `POST /api/admin/cleanup-duplicates`

---

### 🔧 修复路径前缀

为所有缺少 `music/` 前缀的歌曲路径添加前缀。

**接口**: `POST /api/admin/fix-paths`

---

## 调试工具

### 📊 R2 存储列表

列出 R2 存储桶中的所有 MP3 文件。

**接口**: `GET /api/debug/r2`

---

### 🔍 完整审计报告

对比 D1 数据库和 R2 存储，生成数据一致性报告。

**接口**: `GET /api/debug/audit`

---

### 🔌 Supabase 连通性测试

测试 Worker 到 Supabase 服务的连通性。

**接口**: `GET /api/debug/supabase-test`

---

## 用户系统 Postman 测试指南

### 注册（认领）流程测试

**1. 获取座位表**:
```
GET https://m-api.changgepd.top/api/roster
```
> 记下目标同学的 `id`（`is_claimed` 为 0），以及三道安全题。

**2. 校验安全问题**:
```
POST https://m-api.changgepd.top/api/user/claim/verify
Content-Type: application/json

Body (raw JSON):
{
  "roster_id": 1,
  "answers": ["张明亮老师", "王燕老师", "三楼"]
}
```
> 返回 `claim_token`，10 分钟内有效。

**3. 完成注册**:
```
POST https://m-api.changgepd.top/api/user/claim/finalize
Content-Type: application/json

Body (raw JSON):
{
  "claim_token": "<上一步返回的token>",
  "password_hash": "<SHA-256(密码)的hex>",
  "email": "me@example.com"
}
```
> 返回 `token` 和 `refresh_token`，直接存储后进入主界面。

### 登录流程测试

**4. 登录**:
```
POST https://m-api.changgepd.top/api/user/login
Content-Type: application/json

Body (raw JSON):
{
  "username": "2006.0301张伟",
  "password_hash": "<SHA-256(密码)的hex>"
}
```
> 检查 `reset_pending` 字段，若为 `true` 需强制调用 `/api/user/reset/set-new`。

**5. 获取用户信息**:
```
GET https://m-api.changgepd.top/api/user/me
Authorization: Bearer <token>
```

**6. 获取 / 更新用户设置**:
```
GET  https://m-api.changgepd.top/api/user/settings
PUT  https://m-api.changgepd.top/api/user/settings
Authorization: Bearer <token>
Content-Type: application/json

Body (PUT):
{
  "last_volume": 0.8,
  "theme_mode": "dark"
}
```

---

## ⚠️ 注意事项

1. **删除操作不可恢复**: 删除专辑或歌曲前请确认，操作无法撤销
2. **编码问题**: 批量更新中文标题时，确保请求头包含 `charset=utf-8`
3. **ID 的重要性**: 技术接口操作依赖 ID，请确保使用正确的 `album_id` 和 `song_id`
4. **R2 路径**: 所有文件路径必须以 `music/` 开头（相对 R2 根目录）
5. **运营接口推荐**: 日常运营操作优先使用 `ops` 系列接口，更安全、更直观

---

## 🔗 相关链接

- **Worker API**: `https://m-api.changgepd.ccwu.cc`
- **管理后台**: `https://moody-music-archiv-vercel.vercel.app/admin/`
- **前端播放器**: `https://moody-music-archiv-vercel.vercel.app/`

---

**最后更新**: 2026-04-13
**维护者**: zhangjing02
**版本**: v15.0 (纯 Worker 架构 + 白名单座位认领系统)
