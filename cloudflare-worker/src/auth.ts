import { Hono, Context } from 'hono'
import { createClient } from '@supabase/supabase-js'
import { SignJWT, jwtVerify, createRemoteJWKSet } from 'jose'
import type { Bindings } from './types'
import { fail, serverError } from './error'


type Variables = {
  user: any
  token: string
}

type AppType = { Bindings: Bindings; Variables: Variables }

const JWT_SECRET_DEFAULT = 'moody-music-songbook-secret-key-2026-auth'

function getJwtSecret(env: Bindings): Uint8Array {
  return new TextEncoder().encode(env.JWT_SECRET || JWT_SECRET_DEFAULT)
}

async function signUserToken(user: { id: number; supabase_uid?: string; email?: string; role?: string }, env: Bindings): Promise<string> {
  return await new SignJWT({
    sub: user.supabase_uid || String(user.id),
    user_id: user.id,
    email: user.email || '',
    role: user.role || 'user'
  })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('30d')
    .sign(getJwtSecret(env))
}

// ==========================================
// Supabase Helpers (Legacy fallback)
// ==========================================

function getSupabase(env: Bindings) {
  return createClient(env.SUPABASE_URL || 'https://placeholder.supabase.co', env.SUPABASE_ANON_KEY || 'anon')
}

function getSupabaseAdmin(env: Bindings) {
  return createClient(env.SUPABASE_URL || 'https://placeholder.supabase.co', env.SUPABASE_SERVICE_KEY || 'service')
}

function getJWKS(env: Bindings) {
  return createRemoteJWKSet(new URL(`${env.SUPABASE_URL || 'https://placeholder.supabase.co'}/auth/v1/.well-known/jwks.json`))
}

// ==========================================
// Kick-out Push Helper
// ==========================================

/**
 * 向旧设备的 JPush RegistrationId 发送互踢透传消息。
 * @param env Cloudflare Worker Bindings
 * @param oldJPushRegId 旧设备的极光推送 RegistrationId
 * @param ctx executionCtx（用于 waitUntil）
 */
async function sendKickOutPush(
  env: Bindings,
  oldJPushRegId: string,
  ctx?: ExecutionContext,
  targetDeviceId?: string
): Promise<void> {
  if (!env.JPUSH_APP_KEY || !env.JPUSH_MASTER_SECRET || !oldJPushRegId) {
    console.warn('[JPush] sendKickOutPush skipped: missing credentials or oldJPushRegId', { oldJPushRegId })
    return
  }
  const payload = {
    platform: 'android',
    audience: { registration_id: [oldJPushRegId] },
    message: {
      msg_content: '您的账号已在另一台设备登录，当前设备已下线。',
      extras: {
        action: 'KICK_OUT',
        reason: 'new_login',
        kick_timestamp: Date.now(),
        target_device_id: targetDeviceId || ''
      }
    }
  }
  try {
    const res = await fetch('https://api.jpush.cn/v3/push', {
      method: 'POST',
      headers: {
        'Authorization': `Basic ${btoa(`${env.JPUSH_APP_KEY}:${env.JPUSH_MASTER_SECRET}`)}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    const resText = await res.text()
    console.log(`[JPush] kickout push sent to ${oldJPushRegId}, status: ${res.status}, response: ${resText}`)
  } catch (err) {
    console.error('[JPush] kickout push exception:', err)
  }
}

// ==========================================
// Auth Middleware
// ==========================================

export const authMiddleware = async (c: Context<AppType>, next: any) => {
  const authHeader = c.req.header('Authorization')
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return fail(c, 'UNAUTHENTICATED')
  }

  const token = authHeader.slice(7)
  try {
    // [D1 Quota Fix] DDL 已从中间件移除 - schema 迁移应通过 wrangler d1 migrations apply 执行

    let payload: any = null
    try {
      // 优先尝试原生 HS256 JWT 解密
      const verified = await jwtVerify(token, getJwtSecret(c.env))
      payload = verified.payload
    } catch {
      // 若原生验证失败且配置了 Supabase，回退尝试 Supabase JWKS 验证
      if (c.env.SUPABASE_URL && !c.env.SUPABASE_URL.includes('tvrnftaciirswmvpsngp')) {
        try {
          const JWKS = getJWKS(c.env)
          const verified = await jwtVerify(token, JWKS)
          payload = verified.payload
        } catch {
          // ignore fallback error
        }
      }
    }

    if (!payload) {
      return fail(c, 'TOKEN_INVALID')
    }

    const supabaseUid = payload.sub
    const userId = payload.user_id

    let profile: any = null
    if (userId) {
      profile = await c.env.DB.prepare(
        'SELECT id, supabase_uid, username, nickname, bio, email, level, role, avatar_url, play_mode, created_at, updated_at, last_android_device_id, last_android_session_at, jpush_registration_id FROM user_profiles WHERE id = ?'
      ).bind(userId).first() as any
    }
    if (!profile && supabaseUid) {
      profile = await c.env.DB.prepare(
        'SELECT id, supabase_uid, username, nickname, bio, email, level, role, avatar_url, play_mode, created_at, updated_at, last_android_device_id, last_android_session_at, jpush_registration_id FROM user_profiles WHERE supabase_uid = ?'
      ).bind(supabaseUid).first() as any
    }

    if (!profile) {
      return fail(c, 'TOKEN_INVALID', { message: '用户不存在' })
    }

    // [单点登录 Token 黑名单检测]
    // 比较 JWT 的 iat（签发时间）与数据库中 last_android_session_at（最新一次登录时间）。
    // 如果数据库中有更新的登录记录，则当前 token 已失效（旧设备 token 被踢下线）。
    const clientType = c.req.header('X-Client-Type') || ''

    if (clientType === 'android') {
      const iat = payload.iat as number | undefined // JWT issued-at (seconds)
      const lastSessionAt = profile.last_android_session_at
        ? new Date(profile.last_android_session_at).getTime() / 1000
        : 0

      // 允许 2 秒时钟漂移容差
      if (lastSessionAt > (iat || 0) + 2) {
        return fail(c, 'TOKEN_EXPIRED_OR_INVALID', {
          message: '您的账号已在其他设备登录，当前会话已失效，请重新登录',
          error_key: 'SESSION_KICKED_OUT'
        } as any)
      }
    }

    c.set('user', profile)
    c.set('token', token)
    await next()
  } catch (err: any) {
    console.error('JWT verify error:', err.message)
    return fail(c, 'TOKEN_EXPIRED_OR_INVALID')
  }
}

// ==========================================
// Require Admin Middleware (admin + master)
// ==========================================

export const requireAdmin = async (c: Context<AppType>, next: any) => {
  const user = c.get('user')
  if (!user || !isGlobalAdminRole(user.role)) {
    return fail(c, 'ADMIN_FORBIDDEN')
  }
  await next()
}

// Require master only
export const requireMaster = async (c: Context<AppType>, next: any) => {
  const user = c.get('user')
  if (!user || !isDevelopMasterRole(user.role)) {
    return fail(c, 'MASTER_FORBIDDEN')
  }
  await next()
}

function parsePageNumber(raw: string | undefined, fallback: number, min: number, max: number): number {
  if (!raw) return fallback
  const value = parseInt(raw, 10)
  if (Number.isNaN(value)) return fallback
  return Math.min(max, Math.max(min, value))
}

function parseBooleanFlag(raw: unknown, fallback = false): boolean {
  if (raw === undefined || raw === null) return fallback
  if (typeof raw === 'boolean') return raw
  if (typeof raw === 'number') return raw !== 0
  if (typeof raw === 'string') {
    const normalized = raw.trim().toLowerCase()
    if (normalized === 'true' || normalized === '1' || normalized === 'yes' || normalized === 'y') return true
    if (normalized === 'false' || normalized === '0' || normalized === 'no' || normalized === 'n') return false
  }
  return fallback
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

function buildSqlInPlaceholders(length: number): string {
  return Array.from({ length }, () => '?').join(', ')
}

function isDevelopMasterRole(role?: string | null): boolean {
  return role === 'develop_master'
}

function isGlobalAdminRole(role?: string | null): boolean {
  return role === 'admin' || isDevelopMasterRole(role)
}

async function ensureDevelopMasterAccess(c: Context<AppType>) {
  const user = c.get('user') as any
  if (!user || !isDevelopMasterRole(user.role)) {
    return fail(c, 'MASTER_FORBIDDEN', { message: '需要 develop-master 权限' })
  }
  return null
}


let _userProfileSessionColumnsEnsured = false
async function ensureUserProfileSessionColumns(db: D1Database) {
  if (_userProfileSessionColumnsEnsured) return
  _userProfileSessionColumnsEnsured = true
  try {
    await db.prepare('ALTER TABLE user_profiles ADD COLUMN last_android_device_id TEXT').run()
  } catch (error: any) {
    const message = String(error?.message || '')
    if (!message.toLowerCase().includes('duplicate column name')) {
      throw error
    }
  }

  try {
    await db.prepare('ALTER TABLE user_profiles ADD COLUMN last_android_session_at DATETIME').run()
  } catch (error: any) {
    const message = String(error?.message || '')
    if (!message.toLowerCase().includes('duplicate column name')) {
      throw error
    }
  }

  try {
    await db.prepare('ALTER TABLE user_profiles ADD COLUMN jpush_registration_id TEXT').run()
  } catch (error: any) {
    const message = String(error?.message || '')
    if (!message.toLowerCase().includes('duplicate column name')) {
      throw error
    }
  }
}

let _modernAuthAndLibrarySchemaEnsured = false
async function ensureModernAuthAndLibrarySchema(db: D1Database) {
  if (_modernAuthAndLibrarySchemaEnsured) return

  await db.prepare(`
    CREATE TABLE IF NOT EXISTS user_profiles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      supabase_uid TEXT UNIQUE,
      username TEXT UNIQUE NOT NULL,
      email TEXT,
      nickname TEXT DEFAULT '',
      bio TEXT DEFAULT '在音信里听风的声音',
      password_hash TEXT DEFAULT '',
      level INTEGER DEFAULT 1,
      role TEXT DEFAULT 'user',
      avatar_url TEXT,
      play_mode TEXT DEFAULT 'SEQUENTIAL',
      last_android_device_id TEXT,
      last_android_session_at DATETIME,
      jpush_registration_id TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `).run()

  const columnsToAdd = [
    'ALTER TABLE user_profiles ADD COLUMN nickname TEXT DEFAULT ""',
    'ALTER TABLE user_profiles ADD COLUMN bio TEXT DEFAULT "在音信里听风的声音"',
    'ALTER TABLE user_profiles ADD COLUMN password_hash TEXT DEFAULT ""',
    'ALTER TABLE user_profiles ADD COLUMN play_mode TEXT DEFAULT "SEQUENTIAL"',
    'ALTER TABLE user_profiles ADD COLUMN updated_at DATETIME',
    'ALTER TABLE user_profiles ADD COLUMN last_android_device_id TEXT',
    'ALTER TABLE user_profiles ADD COLUMN last_android_session_at DATETIME',
    'ALTER TABLE user_profiles ADD COLUMN jpush_registration_id TEXT',
  ]

  for (const sql of columnsToAdd) {
    try {
      await db.prepare(sql).run()
    } catch (error: any) {
      const message = String(error?.message || '')
      if (!message.toLowerCase().includes('duplicate column name')) {
        // ignore if already added
      }
    }
  }

  await db.prepare(`
    CREATE TABLE IF NOT EXISTS email_verification_codes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL,
      code TEXT NOT NULL,
      type TEXT NOT NULL DEFAULT 'login',
      expires_at INTEGER NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      used_at DATETIME
    )
  `).run()


  await db.prepare(`
    CREATE INDEX IF NOT EXISTS idx_email_verification_codes_lookup 
    ON email_verification_codes (email, code, used_at)
  `).run()

  await db.prepare(`
    CREATE TABLE IF NOT EXISTS user_favorite_songs (
      user_id INTEGER NOT NULL,
      song_id INTEGER NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, song_id),
      FOREIGN KEY(user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
    )
  `).run()

  await db.prepare(`
    CREATE TABLE IF NOT EXISTS albums (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      cover TEXT DEFAULT '',
      artist_id TEXT DEFAULT ''
    )
  `).run()

  await db.prepare(`
    CREATE TABLE IF NOT EXISTS artists (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      avatar TEXT DEFAULT ''
    )
  `).run()

  await db.prepare(`
    CREATE TABLE IF NOT EXISTS user_favorite_albums (
      user_id INTEGER NOT NULL,
      album_id TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, album_id),
      FOREIGN KEY(user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
    )
  `).run()

  await db.prepare(`
    CREATE TABLE IF NOT EXISTS user_followed_artists (
      user_id INTEGER NOT NULL,
      artist_id TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, artist_id),
      FOREIGN KEY(user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
    )
  `).run()

  await db.prepare(`
    CREATE TABLE IF NOT EXISTS user_play_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      song_id INTEGER NOT NULL,
      played_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
    )
  `).run()

  _modernAuthAndLibrarySchemaEnsured = true
}

// ==========================================
// Auth Routes
// ==========================================

export function registerAuthRoutes(app: Hono<AppType>) {

  // ========================================
  // 0.1 POST /api/auth/send-code — 发送邮箱验证码 (OTP)
  // ========================================
  app.post('/api/auth/send-code', async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const { email, type = 'login' } = await c.req.json() as {
        email?: string
        type?: 'login' | 'reset_password'
      }

      if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
        return fail(c, 'EMAIL_INVALID', { message: '请输入有效的邮箱地址' })
      }

      const cleanEmail = email.trim().toLowerCase()

      // 频率限制：检查最近 60 秒内是否已经向该邮箱发送过同类型验证码
      const recent = await c.env.DB.prepare(
        `SELECT id FROM email_verification_codes 
         WHERE email = ? AND type = ? AND created_at > datetime('now', '-60 seconds')
         ORDER BY id DESC LIMIT 1`
      ).bind(cleanEmail, type).first()

      if (recent) {
        return fail(c, 'RATE_LIMITED', { message: '验证码发送太频繁，请稍后再试' })
      }

      // 生成 6 位随机验证码
      const code = Math.floor(100000 + Math.random() * 900000).toString()
      const expiresAt = Date.now() + 10 * 60 * 1000 // 10分钟有效

      // 写入 D1
      await c.env.DB.prepare(
        `INSERT INTO email_verification_codes (email, code, type, expires_at)
         VALUES (?, ?, ?, ?)`
      ).bind(cleanEmail, code, type, expiresAt).run()

      // 尝试通过 Resend 发送真实邮件 (如果配置了 RESEND_API_KEY)
      if (!c.env.RESEND_API_KEY || c.env.RESEND_API_KEY === 'your_resend_api_key_here') {
        return fail(c, 'SEND_CODE_FAILED', { message: '邮件服务未配置，请联系管理员' })
      }

      let emailSent = false
      try {
          const res = await fetch('https://api.resend.com/emails', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${c.env.RESEND_API_KEY}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              from: c.env.RESEND_FROM || 'Moody Music <onboarding@resend.dev>',
              to: [cleanEmail],
              subject: type === 'reset_password' ? '【Moody Music】重置密码验证码' : '【Moody Music】登录注册验证码',
              html: `
                <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; background: #0c0d12; color: #f2ede4; border-radius: 12px; border: 1px solid rgba(255,255,255,0.08);">
                  <div style="font-size: 11px; letter-spacing: 2px; text-transform: uppercase; color: #d4af37; font-weight: bold; margin-bottom: 16px;">THE MODERN SONGBOOK</div>
                  <h2 style="font-size: 22px; font-weight: 300; margin: 0 0 16px 0; color: #ffffff;">您的验证码</h2>
                  <p style="font-size: 14px; line-height: 1.6; color: #a0a0a8; margin-bottom: 24px;">您正在通过邮箱 ${cleanEmail} ${type === 'reset_password' ? '重置密码' : '登录或注册'} Moody 音乐空间。请使用以下 6 位验证码完成验证：</p>
                  <div style="background: rgba(212, 175, 55, 0.1); border: 1px solid rgba(212, 175, 55, 0.3); border-radius: 8px; padding: 18px 24px; text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #d4af37; font-family: monospace; margin-bottom: 24px;">
                    ${code}
                  </div>
                  <p style="font-size: 12px; color: #666670; line-height: 1.5; margin: 0;">验证码有效期为 10 分钟。如果这不是您的操作，请忽略此邮件。</p>
                </div>
              `
            })
          })
          if (res.ok) {
            emailSent = true
          } else {
            console.error('Resend email failed:', await res.text())
          }
        } catch (mailErr: any) {
          console.error('Mail sending exception:', mailErr)
        }

      if (!emailSent) {
        return fail(c, 'SEND_CODE_FAILED')
      }

      console.log(`[AUTH-OTP] Email: ${cleanEmail}, Type: ${type}, Code: ${code}, EmailSent: ${emailSent}`)

      const responseData = {
        email: cleanEmail,
      }

      return c.json({
        code: 200,
        message: '验证码已发送至您的邮箱，请注意查收',
        ...responseData,
        data: responseData,
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 0.2 POST /api/auth/verify-code — 验证码极速登录 / 自动注册
  // ========================================
  app.post('/api/auth/verify-code', async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      await ensureUserProfileSessionColumns(c.env.DB)

      const { email, code, password_hash, nickname } = await c.req.json() as {
        email?: string
        code?: string
        password_hash?: string
        nickname?: string
      }

      if (!email || !code) {
        return fail(c, 'MISSING_PARAMETER', {
          message: '邮箱和验证码不能为空',
          details: { required: ['email', 'code'] }
        })
      }

      const cleanEmail = email.trim().toLowerCase()
      const cleanCode = code.trim()
      const now = Date.now()

      // 验证码匹配与有效性检查
      const otpRecord = await c.env.DB.prepare(
        `SELECT id, code, expires_at FROM email_verification_codes
         WHERE email = ? AND code = ? AND (type = 'login' OR type = 'any' OR type = 'register') AND used_at IS NULL
         ORDER BY id DESC LIMIT 1`
      ).bind(cleanEmail, cleanCode).first<{ id: number; code: string; expires_at: number }>()

      if (!otpRecord) {
        return fail(c, 'VERIFY_CODE_FAILED', {
          message: '验证码不正确或已被使用'
        })
      }

      if (now > otpRecord.expires_at) {
        return fail(c, 'VERIFY_CODE_FAILED', {
          message: '验证码已过期，请重新获取'
        })
      }

      // 标记验证码已使用
      await c.env.DB.prepare(
        `UPDATE email_verification_codes SET used_at = CURRENT_TIMESTAMP WHERE id = ?`
      ).bind(otpRecord.id).run()

      // 查找或创建用户 Profile
      let profile = await c.env.DB.prepare(
        'SELECT id, supabase_uid, username, nickname, bio, email, password_hash, level, role, avatar_url, play_mode, created_at, updated_at, last_android_device_id, last_android_session_at, jpush_registration_id FROM user_profiles WHERE email = ?'
      ).bind(cleanEmail).first() as any

      if (!profile) {
        const prefix = cleanEmail.split('@')[0].replace(/[^a-zA-Z0-9_\u4e00-\u9fa5]/g, '_') || 'user'
        const customNickname = (nickname && nickname.trim()) ? nickname.trim() : prefix
        const randomSuffix = Math.floor(1000 + Math.random() * 9000)
        let username = `${prefix}_${randomSuffix}`

        let checkUser = await c.env.DB.prepare('SELECT id FROM user_profiles WHERE username = ?').bind(username).first()
        while (checkUser) {
          username = `${prefix}_${Math.floor(10000 + Math.random() * 90000)}`
          checkUser = await c.env.DB.prepare('SELECT id FROM user_profiles WHERE username = ?').bind(username).first()
        }

        const syntheticUid = `moody_u_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

        await c.env.DB.prepare(
          `INSERT INTO user_profiles (supabase_uid, username, nickname, email, bio, level, role, password_hash, play_mode)
           VALUES (?, ?, ?, ?, '在音信里听风的声音', 1, 'user', ?, 'SEQUENTIAL')`
        ).bind(syntheticUid, username, customNickname, cleanEmail, password_hash || '').run()

        profile = await c.env.DB.prepare(
          'SELECT id, supabase_uid, username, nickname, bio, email, password_hash, level, role, avatar_url, play_mode, created_at, updated_at, last_android_device_id, last_android_session_at, jpush_registration_id FROM user_profiles WHERE email = ?'
        ).bind(cleanEmail).first() as any
      } else if (password_hash) {
        // 如果传入了新密码哈希，同步更新
        await c.env.DB.prepare(
          'UPDATE user_profiles SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        ).bind(password_hash, profile.id).run()
        profile.password_hash = password_hash
      }

      // 生成原生 JWT 访问令牌
      const accessToken = await signUserToken(profile, c.env)
      const refreshToken = `ref_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`

      // ── 单点登录互踢逻辑 ──
      // 1. 读取当前请求的 JPush RegistrationId（由客户端在 Header 中上报）
      // 2. 如果数据库存有旧 RegistrationId 且与当前不同，向旧设备推 KICK_OUT
      // 3. 更新 DB：新的 RegistrationId + last_android_session_at（供 token 黑名单检测）
      const clientType = c.req.header('X-Client-Type') || ''
      const deviceId = c.req.header('X-Device-Id') || ''
      const newJPushRegId = c.req.header('X-JPush-Registration-Id') || ''

      if (clientType === 'android') {
        const oldJPushRegId = profile.jpush_registration_id || ''

        // 互踢保护原则：
        // 1. 只有当旧设备极光 ID 存在且与当前新设备不同（oldJPushRegId !== newJPushRegId）时，才能向旧设备推 KICK_OUT！
        // 2. 严禁向正在登录的新设备推互踢（即使本地 UUID 重置，只要 RegistrationId 相同绝不推自己）
        const isDeviceChanged = (newJPushRegId && oldJPushRegId && oldJPushRegId !== newJPushRegId) ||
          (!newJPushRegId && oldJPushRegId && deviceId && profile.last_android_device_id && profile.last_android_device_id !== deviceId)

        if (isDeviceChanged && oldJPushRegId && oldJPushRegId !== newJPushRegId) {
          await sendKickOutPush(c.env, oldJPushRegId, c.executionCtx, profile.last_android_device_id)
        }

        const finalJPushId = newJPushRegId || profile.jpush_registration_id || null

        await c.env.DB.prepare(
          'UPDATE user_profiles SET last_android_device_id = ?, last_android_session_at = CURRENT_TIMESTAMP, jpush_registration_id = ? WHERE id = ?'
        ).bind(deviceId || profile.last_android_device_id || null, finalJPushId, profile.id).run()
      }

      const { password_hash: _, ...safeProfile } = profile
      const responseData = {
        user: { ...safeProfile, has_password: Boolean(profile.password_hash) },
        token: accessToken,
        refresh_token: refreshToken,
      }

      return c.json({
        code: 200,
        message: '登录成功',
        ...responseData,
        data: responseData,
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 0.22 GET /api/auth/check-username — 用户名查重
  // ========================================
  app.get('/api/auth/check-username', async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const rawUsername = c.req.query('username') || ''
      const username = rawUsername.normalize('NFKC').trim()

      if (!username) {
        return c.json({ code: 400, message: '用户名不能为空', data: { available: false, message: '用户名不能为空' } })
      }
      if (username.length < 2 || username.length > 20 || !/^[\u4e00-\u9fa5a-zA-Z0-9_\-]+$/.test(username)) {
        return c.json({ code: 200, data: { available: false, message: '用户名长度需在 2-20 位，仅支持中英文字符、数字及下划线' } })
      }

      const existing = await c.env.DB.prepare(
        'SELECT id FROM user_profiles WHERE username = ? COLLATE NOCASE'
      ).bind(username).first()

      if (existing) {
        return c.json({ code: 200, data: { available: false, message: '该用户名已被占用' } })
      }

      return c.json({ code: 200, data: { available: true, message: '该用户名可以使用' } })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 0.24 POST /api/auth/internal-purge-account — 内部账号清理 (安全验证密钥删除，支持重置注册测试)
  // ========================================
  app.post('/api/auth/internal-purge-account', async (c) => {
    try {
      const secret = c.req.header('X-Admin-Secret')
      if (!secret || secret !== c.env.JWT_SECRET) {
        return fail(c, 'FORBIDDEN', { message: '无权操作' })
      }

      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const { email, username } = await c.req.json().catch(() => ({})) as { email?: string; username?: string }
      const cleanEmail = email?.trim().toLowerCase() || ''
      const cleanUsername = username?.trim() || ''

      if (!cleanEmail && !cleanUsername) {
        return fail(c, 'MISSING_PARAMETER', { message: '请提供 email 或 username' })
      }

      let profile: any = null
      if (cleanEmail) {
        profile = await c.env.DB.prepare(
          'SELECT id, username, email FROM user_profiles WHERE email = ?'
        ).bind(cleanEmail).first()
      }
      if (!profile && cleanUsername) {
        profile = await c.env.DB.prepare(
          'SELECT id, username, email FROM user_profiles WHERE username = ? COLLATE NOCASE'
        ).bind(cleanUsername).first()
      }

      let deletedUser: any = null
      if (profile) {
        const userId = profile.id
        deletedUser = profile
        await c.env.DB.prepare('DELETE FROM user_settings WHERE user_id = ?').bind(userId).run()
        await c.env.DB.prepare('DELETE FROM user_favorite_songs WHERE user_id = ?').bind(userId).run()
        await c.env.DB.prepare('DELETE FROM user_favorite_albums WHERE user_id = ?').bind(userId).run()
        await c.env.DB.prepare('DELETE FROM user_followed_artists WHERE user_id = ?').bind(userId).run()
        await c.env.DB.prepare('DELETE FROM user_play_history WHERE user_id = ?').bind(userId).run()
        await c.env.DB.prepare('DELETE FROM user_profiles WHERE id = ?').bind(userId).run()
      }

      if (cleanEmail) {
        await c.env.DB.prepare('DELETE FROM email_verification_codes WHERE email = ?').bind(cleanEmail).run()
      }

      return c.json({
        code: 200,
        message: deletedUser ? `账号【${deletedUser.email || deletedUser.username}】及关联记录已完全清除` : '未找到匹配的用户账号，已清除可能存在的验证码缓存',
        deleted_user: deletedUser,
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 0.25 POST /api/auth/register-with-code — 验证码注册并设置密码
  // ========================================
  app.post('/api/auth/register-with-code', async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      await ensureUserProfileSessionColumns(c.env.DB)

      const { email, code, password_hash, username: rawUsername, nickname } = await c.req.json() as {
        email?: string
        code?: string
        password_hash?: string
        username?: string
        nickname?: string
      }

      if (!email || !code || !password_hash) {
        return fail(c, 'MISSING_PARAMETER', {
          message: '邮箱、验证码和密码不能为空',
          details: { required: ['email', 'code', 'password_hash'] }
        })
      }

      if (password_hash.length !== 64) {
        return fail(c, 'PASSWORD_HASH_INVALID', { message: '密码哈希格式无效' })
      }

      const cleanEmail = email.trim().toLowerCase()
      const cleanCode = code.trim()
      const now = Date.now()

      // 1. 检查邮箱是否已注册且已有密码
      const existing = await c.env.DB.prepare(
        'SELECT id, password_hash, username FROM user_profiles WHERE email = ?'
      ).bind(cleanEmail).first<{ id: number; password_hash?: string; username: string }>()

      if (existing && existing.password_hash) {
        return fail(c, 'EMAIL_ALREADY_REGISTERED', {
          message: '该邮箱已注册，请直接使用密码登录或找回密码'
        })
      }

      // 2. 处理用户名与查重
      let targetUsername = ''
      const userSupplied = Boolean(rawUsername && rawUsername.trim())

      if (userSupplied) {
        targetUsername = rawUsername!.normalize('NFKC').trim()
        if (targetUsername.length < 2 || targetUsername.length > 20 || !/^[\u4e00-\u9fa5a-zA-Z0-9_\-]+$/.test(targetUsername)) {
          return fail(c, 'INVALID_USERNAME', {
            message: '用户名需在 2-20 位字符，支持中文汉字、英文字母、数字与下划线'
          })
        }

        // 严格查重 (忽略大小写且比对 UTF-8)
        const dupCheck = await c.env.DB.prepare(
          'SELECT id FROM user_profiles WHERE username = ? COLLATE NOCASE'
        ).bind(targetUsername).first()

        if (dupCheck && (!existing || dupCheck.id !== existing.id)) {
          return fail(c, 'USERNAME_ALREADY_EXISTS', {
            message: '该用户名已被占用，请换一个用户名'
          })
        }
      } else {
        // 用户未填用户名：自动提取邮箱 @ 之前的前缀作为默认候选用户名
        const rawPrefix = cleanEmail.split('@')[0].normalize('NFKC').trim()
        let candidate = rawPrefix.replace(/[^a-zA-Z0-9_\u4e00-\u9fa5\-]/g, '_')
        if (candidate.length < 2) candidate = `${candidate}_user`
        if (candidate.length > 20) candidate = candidate.slice(0, 20)
        targetUsername = candidate

        // 检查默认用户名是否重名
        const dupCheck = await c.env.DB.prepare(
          'SELECT id FROM user_profiles WHERE username = ? COLLATE NOCASE'
        ).bind(targetUsername).first()

        if (dupCheck && (!existing || dupCheck.id !== existing.id)) {
          return fail(c, 'DEFAULT_USERNAME_TAKEN', {
            message: `默认用户名【${targetUsername}】已被占用，请在上方手动输入专属用户名`
          })
        }
      }

      // 3. 验证码匹配与有效性检查
      const otpRecord = await c.env.DB.prepare(
        `SELECT id, code, expires_at FROM email_verification_codes
         WHERE email = ? AND code = ? AND (type = 'login' OR type = 'any' OR type = 'register') AND used_at IS NULL
         ORDER BY id DESC LIMIT 1`
      ).bind(cleanEmail, cleanCode).first<{ id: number; code: string; expires_at: number }>()

      if (!otpRecord) {
        return fail(c, 'VERIFY_CODE_FAILED', {
          message: '验证码不正确或已被使用'
        })
      }

      if (now > otpRecord.expires_at) {
        return fail(c, 'VERIFY_CODE_FAILED', {
          message: '验证码已过期，请重新获取'
        })
      }

      // 4. 标记验证码已使用
      await c.env.DB.prepare(
        `UPDATE email_verification_codes SET used_at = CURRENT_TIMESTAMP WHERE id = ?`
      ).bind(otpRecord.id).run()

      let profile: any

      if (existing) {
        // 老账号补齐密码及更新用户名/昵称
        const customNickname = (nickname && nickname.trim()) ? nickname.trim() : (targetUsername || existing.username)
        await c.env.DB.prepare(
          'UPDATE user_profiles SET password_hash = ?, username = ?, nickname = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        ).bind(password_hash, targetUsername || existing.username, customNickname, existing.id).run()

        profile = await c.env.DB.prepare(
          'SELECT id, supabase_uid, username, nickname, bio, email, password_hash, level, role, avatar_url, play_mode, created_at, updated_at, last_android_device_id, last_android_session_at, jpush_registration_id FROM user_profiles WHERE id = ?'
        ).bind(existing.id).first()
      } else {
        const customNickname = (nickname && nickname.trim()) ? nickname.trim() : targetUsername
        const syntheticUid = `moody_u_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

        await c.env.DB.prepare(
          `INSERT INTO user_profiles (supabase_uid, username, nickname, email, bio, level, role, password_hash, play_mode)
           VALUES (?, ?, ?, ?, '在音信里听风的声音', 1, 'user', ?, 'SEQUENTIAL')`
        ).bind(syntheticUid, targetUsername, customNickname, cleanEmail, password_hash).run()

        profile = await c.env.DB.prepare(
          'SELECT id, supabase_uid, username, nickname, bio, email, password_hash, level, role, avatar_url, play_mode, created_at, updated_at, last_android_device_id, last_android_session_at, jpush_registration_id FROM user_profiles WHERE email = ?'
        ).bind(cleanEmail).first()
      }

      // 生成原生 JWT 访问令牌
      const accessToken = await signUserToken(profile, c.env)
      const refreshToken = `ref_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`

      // ── 单点登录互踢逻辑 ──
      const clientType = c.req.header('X-Client-Type') || ''
      const deviceId = c.req.header('X-Device-Id') || ''
      const newJPushRegId = c.req.header('X-JPush-Registration-Id') || ''

      if (clientType === 'android') {
        const oldJPushRegId = profile.jpush_registration_id || ''

        const isDeviceChanged = (newJPushRegId && oldJPushRegId && oldJPushRegId !== newJPushRegId) ||
          (!newJPushRegId && oldJPushRegId && deviceId && profile.last_android_device_id && profile.last_android_device_id !== deviceId)

        if (isDeviceChanged && oldJPushRegId && oldJPushRegId !== newJPushRegId) {
          await sendKickOutPush(c.env, oldJPushRegId, c.executionCtx, profile.last_android_device_id)
        }

        const finalJPushId = newJPushRegId || profile.jpush_registration_id || null

        await c.env.DB.prepare(
          'UPDATE user_profiles SET last_android_device_id = ?, last_android_session_at = CURRENT_TIMESTAMP, jpush_registration_id = ? WHERE id = ?'
        ).bind(deviceId || profile.last_android_device_id || null, finalJPushId, profile.id).run()
      }

      const { password_hash: _, ...safeProfile } = profile
      const responseData = {
        user: { ...safeProfile, has_password: true },
        token: accessToken,
        refresh_token: refreshToken,
      }

      return c.json({
        code: 200,
        message: '注册成功并已登录',
        ...responseData,
        data: responseData,
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 0.3 POST /api/auth/login-with-password — 用户名/邮箱 + 密码登录
  // ========================================
  app.post('/api/auth/login-with-password', async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      await ensureUserProfileSessionColumns(c.env.DB)

      const { account, email, username, password_hash } = await c.req.json() as {
        account?: string
        email?: string
        username?: string
        password_hash?: string
      }

      const rawAccount = (account || email || username || '').trim()

      if (!rawAccount || !password_hash) {
        return fail(c, 'MISSING_PARAMETER', {
          message: '账号和密码不能为空',
          details: { required: ['account', 'password_hash'] },
        })
      }

      let profile: any = null

      // 若包含 @ 符号，优先按邮箱查
      if (rawAccount.includes('@')) {
        const cleanEmail = rawAccount.toLowerCase()
        profile = await c.env.DB.prepare(
          'SELECT id, supabase_uid, username, nickname, bio, email, password_hash, level, role, avatar_url, play_mode, created_at, updated_at, last_android_device_id, last_android_session_at, jpush_registration_id FROM user_profiles WHERE email = ?'
        ).bind(cleanEmail).first()
      }

      // 若未查到或不含 @ 符号，按用户名（支持中文及大小写忽略）查
      if (!profile) {
        const cleanUsername = rawAccount.normalize('NFKC').trim()
        profile = await c.env.DB.prepare(
          'SELECT id, supabase_uid, username, nickname, bio, email, password_hash, level, role, avatar_url, play_mode, created_at, updated_at, last_android_device_id, last_android_session_at, jpush_registration_id FROM user_profiles WHERE username = ? COLLATE NOCASE'
        ).bind(cleanUsername).first()
      }

      if (!profile) {
        return fail(c, 'LOGIN_FAILED', { message: '该账号尚未注册，请检查输入或先进行注册' })
      }

      if (!profile.password_hash) {
        return fail(c, 'LOGIN_FAILED', { message: '该账号尚未设置密码，请使用验证码免密登录' })
      }

      if (profile.password_hash !== password_hash) {
        return fail(c, 'LOGIN_FAILED', { message: '账号或密码错误' })
      }

      const accessToken = await signUserToken(profile, c.env)
      const refreshToken = `ref_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`

      // ── 单点登录互踢逻辑 ──
      const clientType = c.req.header('X-Client-Type') || ''
      const deviceId = c.req.header('X-Device-Id') || ''
      const newJPushRegId = c.req.header('X-JPush-Registration-Id') || ''

      if (clientType === 'android') {
        const oldJPushRegId = profile.jpush_registration_id || ''

        const isDeviceChanged = (newJPushRegId && oldJPushRegId && oldJPushRegId !== newJPushRegId) ||
          (!newJPushRegId && oldJPushRegId && deviceId && profile.last_android_device_id && profile.last_android_device_id !== deviceId)

        if (isDeviceChanged && oldJPushRegId && oldJPushRegId !== newJPushRegId) {
          await sendKickOutPush(c.env, oldJPushRegId, c.executionCtx, profile.last_android_device_id)
        }

        const finalJPushId = newJPushRegId || profile.jpush_registration_id || null

        // 更新 DB：last_android_session_at 使旧 token 失效，jpush_registration_id 供下次互踢使用
        await c.env.DB.prepare(
          'UPDATE user_profiles SET last_android_device_id = ?, last_android_session_at = CURRENT_TIMESTAMP, jpush_registration_id = ? WHERE id = ?'
        ).bind(deviceId || profile.last_android_device_id || null, finalJPushId, profile.id).run()
      }

      const { password_hash: _, ...safeProfile } = profile
      const responseData = {
        user: safeProfile,
        token: accessToken,
        refresh_token: refreshToken,
      }

      return c.json({
        code: 200,
        message: '登录成功',
        ...responseData,
        data: responseData,
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 0.4 POST /api/auth/reset-password — 邮箱验证码重置密码
  // ========================================
  app.post('/api/auth/reset-password', async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)

      const { email, code, new_password_hash } = await c.req.json() as {
        email?: string
        code?: string
        new_password_hash?: string
      }

      if (!email || !code || !new_password_hash) {
        return fail(c, 'MISSING_PARAMETER', {
          message: '缺少必要参数',
          details: { required: ['email', 'code', 'new_password_hash'] }
        })
      }

      if (new_password_hash.length !== 64) {
        return fail(c, 'PASSWORD_HASH_INVALID')
      }

      const cleanEmail = email.trim().toLowerCase()
      const cleanCode = code.trim()
      const now = Date.now()

      const otpRecord = await c.env.DB.prepare(
        `SELECT id, code, expires_at FROM email_verification_codes
         WHERE email = ? AND code = ? AND (type = 'reset_password' OR type = 'any' OR type = 'login') AND used_at IS NULL
         ORDER BY id DESC LIMIT 1`
      ).bind(cleanEmail, cleanCode).first<{ id: number; code: string; expires_at: number }>()

      if (!otpRecord) {
        return fail(c, 'VERIFY_CODE_FAILED', { message: '验证码不正确或已被使用' })
      }

      if (now > otpRecord.expires_at) {
        return fail(c, 'VERIFY_CODE_FAILED', { message: '验证码已过期，请重新获取' })
      }

      await c.env.DB.prepare(
        `UPDATE email_verification_codes SET used_at = CURRENT_TIMESTAMP WHERE id = ?`
      ).bind(otpRecord.id).run()

      let profile = await c.env.DB.prepare(
        'SELECT id FROM user_profiles WHERE email = ?'
      ).bind(cleanEmail).first()

      if (!profile) {
        return fail(c, 'USER_NOT_FOUND', { message: '未找到该邮箱关联的用户' })
      }

      await c.env.DB.prepare(
        'UPDATE user_profiles SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?'
      ).bind(new_password_hash, cleanEmail).run()

      return c.json({
        code: 200,
        message: '密码重置成功，请使用新密码登录'
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 5. POST /api/user/refresh — 刷新 Token
  // ========================================
  app.post('/api/user/refresh', async (c) => {
    try {
      const { refresh_token } = await c.req.json() as { refresh_token?: string }

      if (!refresh_token) {
        return fail(c, 'MISSING_PARAMETER', {
          message: '缺少 refresh_token',
          details: { required: ['refresh_token'] },
        })
      }

      const supabase = getSupabase(c.env)
      const { data, error } = await supabase.auth.refreshSession({ refresh_token })

      if (error) {
        return fail(c, 'REFRESH_TOKEN_INVALID')
      }

      const responseData = {
        token: data.session?.access_token,
        refresh_token: data.session?.refresh_token,
      }

      return c.json({
        code: 200,
        message: '刷新成功',
        ...responseData,
        data: responseData,
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 6. GET /api/user/me — 当前用户信息（需 auth）
  // ========================================
  app.get('/api/user/me', authMiddleware, async (c) => {
    const user = c.get('user') as any
    return c.json({
      code: 200,
      message: 'success',
      user,
    })
  })

  // ========================================
  // 7.0 GET /api/user/profile — 获取当前用户完整资料及统计（需 auth）
  // ========================================
  app.get('/api/user/profile', authMiddleware, async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const user = c.get('user') as any

      const favSongs = await c.env.DB.prepare(
        'SELECT COUNT(*) as count FROM user_favorite_songs WHERE user_id = ?'
      ).bind(user.id).first<{ count: number }>()

      const favAlbums = await c.env.DB.prepare(
        'SELECT COUNT(*) as count FROM user_favorite_albums WHERE user_id = ?'
      ).bind(user.id).first<{ count: number }>()

      const followedArtists = await c.env.DB.prepare(
        'SELECT COUNT(*) as count FROM user_followed_artists WHERE user_id = ?'
      ).bind(user.id).first<{ count: number }>()

      const profileData = {
        ...user,
        favorite_songs_count: favSongs?.count || 0,
        favorite_albums_count: favAlbums?.count || 0,
        followed_artists_count: followedArtists?.count || 0,
      }

      return c.json({
        code: 200,
        message: 'success',
        user: profileData,
        data: profileData,
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // POST /api/auth/update-jpush-id — 更新极光推送 RegistrationId（需 auth）
  // 客户端在 App 启动、极光重新注册后主动调用，确保服务端存有最新推送目标 ID。
  // ========================================
  app.post('/api/auth/update-jpush-id', authMiddleware, async (c) => {
    try {
      await ensureUserProfileSessionColumns(c.env.DB)
      const user = c.get('user') as any
      const body = await c.req.json() as { jpush_registration_id?: string }
      const newRegId = (body.jpush_registration_id || '').trim()

      if (!newRegId) {
        return fail(c, 'MISSING_PARAMETER', { message: '缺少 jpush_registration_id' })
      }

      await c.env.DB.prepare(
        'UPDATE user_profiles SET jpush_registration_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
      ).bind(newRegId, user.id).run()

      return c.json({ code: 200, message: '更新成功', data: null })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // ========================================
  // 7.1 PUT /api/user/profile — 更新资料与偏好（需 auth）
  // ========================================
  app.put('/api/user/profile', authMiddleware, async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const user = c.get('user') as any
      const body = await c.req.json()
      const allowedFields = ['avatar_url', 'nickname', 'bio', 'play_mode']

      const updates = Object.keys(body)
        .filter(k => allowedFields.includes(k))
        .map(k => `${k} = ?`)
      const params = Object.keys(body)
        .filter(k => allowedFields.includes(k))
        .map(k => body[k])

      if (updates.length === 0) {
        return fail(c, 'NO_VALID_FIELDS', { message: '无有效更新字段（用户名与邮箱不可更改）' })
      }

      updates.push('updated_at = CURRENT_TIMESTAMP')
      params.push(user.id)
      await c.env.DB.prepare(
        `UPDATE user_profiles SET ${updates.join(', ')} WHERE id = ?`
      ).bind(...params).run()

      const profile = await c.env.DB.prepare(
        'SELECT id, supabase_uid, username, nickname, email, bio, level, role, avatar_url, play_mode, created_at, updated_at FROM user_profiles WHERE id = ?'
      ).bind(user.id).first()

      return c.json({ code: 200, message: '更新成功', user: profile, data: profile })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 7.2 GET /api/user/library — 音信页面用户收藏与关注数据（需 auth）
  // ========================================
  app.get('/api/user/library', authMiddleware, async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const user = c.get('user') as any

      const { results: favoriteAlbums } = await c.env.DB.prepare(
        `SELECT ufa.album_id, ufa.created_at, 
                COALESCE(a.title, ufa.album_id) as title, 
                COALESCE(a.cover_url, '') as cover, 
                COALESCE(CAST(a.artist_id AS TEXT), '') as artist_id
         FROM user_favorite_albums ufa
         LEFT JOIN albums a ON CAST(a.id AS TEXT) = REPLACE(REPLACE(CAST(ufa.album_id AS TEXT), 'db_', ''), 'album_', '')
         WHERE ufa.user_id = ?
         ORDER BY ufa.created_at DESC`
      ).bind(user.id).all() as { results: any[] }

      const { results: followedArtists } = await c.env.DB.prepare(
        `SELECT ufa.artist_id, ufa.created_at, 
                COALESCE(ar.name, ufa.artist_id) as name, 
                COALESCE(ar.photo_url, '') as avatar
         FROM user_followed_artists ufa
         LEFT JOIN artists ar ON CAST(ar.id AS TEXT) = REPLACE(REPLACE(CAST(ufa.artist_id AS TEXT), 'db_', ''), 'artist_', '')
         WHERE ufa.user_id = ?
         ORDER BY ufa.created_at DESC`
      ).bind(user.id).all() as { results: any[] }

      const { results: favoriteSongs } = await c.env.DB.prepare(
        `SELECT song_id, created_at
         FROM user_favorite_songs
         WHERE user_id = ?
         ORDER BY created_at DESC`
      ).bind(user.id).all() as { results: any[] }

      const libraryData = {
        favorite_albums: favoriteAlbums || [],
        followed_artists: followedArtists || [],
        favorite_songs: favoriteSongs || [],
        favorite_song_ids: (favoriteSongs || []).map(s => Number(s.song_id)),
        favorite_songs_count: favoriteSongs?.length || 0,
        favorite_albums_count: favoriteAlbums?.length || 0,
        followed_artists_count: followedArtists?.length || 0,
      }

      return c.json({
        code: 200,
        message: 'success',
        data: libraryData,
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 7.3 POST /api/user/library/favorite-album — 收藏/取消收藏专辑（需 auth）
  // ========================================
  app.post('/api/user/library/favorite-album', authMiddleware, async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const user = c.get('user') as any
      const { album_id } = await c.req.json() as { album_id?: string }

      if (!album_id) {
        return fail(c, 'MISSING_PARAMETER', { details: { required: ['album_id'] } })
      }

      const existing = await c.env.DB.prepare(
        'SELECT album_id FROM user_favorite_albums WHERE user_id = ? AND album_id = ?'
      ).bind(user.id, album_id).first()

      let isFavorited = false
      if (existing) {
        await c.env.DB.prepare(
          'DELETE FROM user_favorite_albums WHERE user_id = ? AND album_id = ?'
        ).bind(user.id, album_id).run()
        isFavorited = false
      } else {
        await c.env.DB.prepare(
          'INSERT INTO user_favorite_albums (user_id, album_id) VALUES (?, ?)'
        ).bind(user.id, album_id).run()
        isFavorited = true
      }

      return c.json({
        code: 200,
        message: isFavorited ? '已加入收藏' : '已取消收藏',
        data: { album_id, is_favorited: isFavorited }
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 7.4 POST /api/user/library/follow-artist — 关注/取消关注歌手（需 auth）
  // ========================================
  app.post('/api/user/library/follow-artist', authMiddleware, async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const user = c.get('user') as any
      const { artist_id } = await c.req.json() as { artist_id?: string }

      if (!artist_id) {
        return fail(c, 'MISSING_PARAMETER', { details: { required: ['artist_id'] } })
      }

      const existing = await c.env.DB.prepare(
        'SELECT artist_id FROM user_followed_artists WHERE user_id = ? AND artist_id = ?'
      ).bind(user.id, artist_id).first()

      let isFollowed = false
      if (existing) {
        await c.env.DB.prepare(
          'DELETE FROM user_followed_artists WHERE user_id = ? AND artist_id = ?'
        ).bind(user.id, artist_id).run()
        isFollowed = false
      } else {
        await c.env.DB.prepare(
          'INSERT INTO user_followed_artists (user_id, artist_id) VALUES (?, ?)'
        ).bind(user.id, artist_id).run()
        isFollowed = true
      }

      return c.json({
        code: 200,
        message: isFollowed ? '已关注' : '已取消关注',
        data: { artist_id, is_followed: isFollowed }
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 7.5 POST /api/user/library/favorite-song — 收藏/取消收藏歌曲（需 auth）
  // ========================================
  const handleToggleFavoriteSong = async (c: any) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const user = c.get('user') as any
      const body = await c.req.json() as { song_id?: number | string, songId?: number | string }
      const rawSongId = body.song_id ?? body.songId

      if (rawSongId === undefined || rawSongId === null) {
        return fail(c, 'MISSING_PARAMETER', { details: { required: ['song_id'] } })
      }

      const songId = Number(rawSongId)
      if (isNaN(songId)) {
        return fail(c, 'INVALID_PARAMETER', { details: { message: 'song_id 必须为有效数字' } })
      }

      const existing = await c.env.DB.prepare(
        'SELECT song_id FROM user_favorite_songs WHERE user_id = ? AND song_id = ?'
      ).bind(user.id, songId).first()

      let isFavorited = false
      if (existing) {
        await c.env.DB.prepare(
          'DELETE FROM user_favorite_songs WHERE user_id = ? AND song_id = ?'
        ).bind(user.id, songId).run()
        isFavorited = false
      } else {
        await c.env.DB.prepare(
          'INSERT INTO user_favorite_songs (user_id, song_id) VALUES (?, ?)'
        ).bind(user.id, songId).run()
        isFavorited = true
      }

      return c.json({
        code: 200,
        message: isFavorited ? '已加入收藏' : '已取消收藏',
        data: { song_id: songId, is_favorited: isFavorited, isFavorite: isFavorited }
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  }

  app.post('/api/user/library/favorite-song', authMiddleware, handleToggleFavoriteSong)
  app.post('/api/user/favorites/toggle', authMiddleware, handleToggleFavoriteSong)

  // ========================================
  // 7.6 POST /api/user/library/batch-remove — 批量取消收藏/关注（需 auth）
  // ========================================
  app.post('/api/user/library/batch-remove', authMiddleware, async (c) => {
    try {
      await ensureModernAuthAndLibrarySchema(c.env.DB)
      const user = c.get('user') as any
      const { type, ids } = await c.req.json() as { type?: string; ids?: any[] }

      if (!type || !Array.isArray(ids) || ids.length === 0) {
        return fail(c, 'MISSING_PARAMETER', { details: { required: ['type', 'ids'] } })
      }

      let removedCount = 0

      if (type === 'songs') {
        const numericIds = ids.map(id => Number(id)).filter(id => !isNaN(id))
        if (numericIds.length > 0) {
          const placeholders = numericIds.map(() => '?').join(',')
          const res = await c.env.DB.prepare(
            `DELETE FROM user_favorite_songs WHERE user_id = ? AND song_id IN (${placeholders})`
          ).bind(user.id, ...numericIds).run()
          removedCount = res.meta?.changes || numericIds.length
        }
      } else if (type === 'albums') {
        const stringIds = ids.map(id => String(id)).filter(id => id.trim().length > 0)
        if (stringIds.length > 0) {
          const placeholders = stringIds.map(() => '?').join(',')
          const res = await c.env.DB.prepare(
            `DELETE FROM user_favorite_albums WHERE user_id = ? AND album_id IN (${placeholders})`
          ).bind(user.id, ...stringIds).run()
          removedCount = res.meta?.changes || stringIds.length
        }
      } else if (type === 'artists') {
        const stringIds = ids.map(id => String(id)).filter(id => id.trim().length > 0)
        if (stringIds.length > 0) {
          const placeholders = stringIds.map(() => '?').join(',')
          const res = await c.env.DB.prepare(
            `DELETE FROM user_followed_artists WHERE user_id = ? AND artist_id IN (${placeholders})`
          ).bind(user.id, ...stringIds).run()
          removedCount = res.meta?.changes || stringIds.length
        }
      } else {
        return fail(c, 'INVALID_PARAMETER', { details: { message: 'type 必须是 songs, albums 或 artists' } })
      }

      return c.json({
        code: 200,
        message: '批量删除成功',
        data: {
          type,
          removed_count: removedCount
        }
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 8. POST /api/user/bind-email — 绑定邮箱（需 auth）
  // ========================================
  app.post('/api/user/bind-email', authMiddleware, async (c) => {
    try {
      const user = c.get('user') as any
      const { email } = await c.req.json() as { email?: string }

      if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        return fail(c, 'EMAIL_INVALID')
      }

      // 更新 D1 user_profiles
      await c.env.DB.prepare(
        'UPDATE user_profiles SET email = ? WHERE id = ?'
      ).bind(email, user.id).run()

      return c.json({ code: 200, message: '邮箱绑定成功' })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // ========================================
  // 12. GET /api/user/settings — 获取用户设置
  // ========================================
  app.get('/api/user/settings', authMiddleware, async (c) => {
    try {
      const user = c.get('user') as any

      let settings = await c.env.DB.prepare(
        'SELECT last_volume, theme_mode, auto_play FROM user_settings WHERE user_id = ?'
      ).bind(user.id).first()

      if (!settings) {
        await c.env.DB.prepare(
          'INSERT INTO user_settings (user_id, last_volume, theme_mode, auto_play) VALUES (?, 0.5, ?, 1)'
        ).bind(user.id, 'dark').run()

        settings = { last_volume: 0.5, theme_mode: 'dark', auto_play: 1 }
      }

      return c.json({ code: 200, message: 'success', ...settings })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ========================================
  // 13. PUT /api/user/settings — 更新设置
  // ========================================
  app.put('/api/user/settings', authMiddleware, async (c) => {
    try {
      const user = c.get('user') as any
      const body = await c.req.json()
      const allowedFields = ['last_volume', 'theme_mode', 'auto_play']

      const updates = Object.keys(body)
        .filter(k => allowedFields.includes(k))
        .map(k => `${k} = ?`)
      const params = Object.keys(body)
        .filter(k => allowedFields.includes(k))
        .map(k => body[k])

      if (updates.length === 0) {
        return fail(c, 'NO_VALID_FIELDS', { message: 'No valid fields' })
      }

      const existing = await c.env.DB.prepare(
        'SELECT user_id FROM user_settings WHERE user_id = ?'
      ).bind(user.id).first()

      if (!existing) {
        await c.env.DB.prepare(
          'INSERT INTO user_settings (user_id, last_volume, theme_mode, auto_play) VALUES (?, ?, ?, ?)'
        ).bind(user.id, body.last_volume ?? 0.5, body.theme_mode ?? 'dark', body.auto_play ?? 1).run()
      } else {
        params.push(user.id)
        await c.env.DB.prepare(
          `UPDATE user_settings SET ${updates.join(', ')} WHERE user_id = ?`
        ).bind(...params).run()
      }

      return c.json({ code: 200, message: '设置已更新' })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // ============================================================
  // === 管理员接口 (需要 admin 或 master 权限) ==================
  // ============================================================

  // 21. GET /api/admin/dashboard - overview for management console
  app.get('/api/admin/dashboard', authMiddleware, requireAdmin, async (c) => {
    try {
      const usersResult = await c.env.DB.prepare(
        `SELECT 
           COUNT(*) AS total_users,
           SUM(CASE WHEN role = 'master' THEN 1 ELSE 0 END) AS master_users,
           SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) AS admin_users,
           SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) AS normal_users
         FROM user_profiles`
      ).first() as any

      return c.json({
        code: 200,
        stats: {
          users: usersResult,
          roster: { total_roster: 0, claimed_roster: 0, unclaimed_roster: 0 },
          active_tokens: 0,
        },
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // 22. GET /api/admin/users - list all user profiles with optional keyword filtering
  app.get('/api/admin/users', authMiddleware, requireAdmin, async (c) => {
    try {
      const keyword = (c.req.query('keyword') || '').trim()
      const role = (c.req.query('role') || '').trim()
      const limit = parsePageNumber(c.req.query('limit'), 100, 1, 500)
      const offset = parsePageNumber(c.req.query('offset'), 0, 0, 50000)

      if (role && !['user', 'admin', 'master', 'develop_master'].includes(role)) {
        return fail(c, 'ROLE_INVALID', {
          message: 'role 只能是 user / admin / master / develop_master',
          details: { field: 'role' },
        })
      }

      const whereParts: string[] = []
      const whereParams: Array<string | number> = []

      if (role) {
        whereParts.push('p.role = ?')
        whereParams.push(role)
      }

      if (keyword) {
        const like = `%${keyword}%`
        whereParts.push(
          "(p.username LIKE ? OR IFNULL(p.email, '') LIKE ? OR IFNULL(p.nickname, '') LIKE ?)"
        )
        whereParams.push(like, like, like)
      }

      const whereSql = whereParts.length > 0 ? `WHERE ${whereParts.join(' AND ')}` : ''

      const countResult = await c.env.DB.prepare(
        `SELECT COUNT(*) AS total
         FROM user_profiles p
         ${whereSql}`
      ).bind(...whereParams).first<{ total: number }>()

      const { results } = await c.env.DB.prepare(
        `SELECT 
           p.id,
           p.supabase_uid,
           p.username,
           p.email,
           p.level,
           p.role,
           p.avatar_url,
           p.created_at,
           p.last_android_device_id,
           p.last_android_session_at
         FROM user_profiles p
         ${whereSql}
         ORDER BY p.created_at DESC, p.id DESC
         LIMIT ? OFFSET ?`
      ).bind(...whereParams, limit, offset).all() as { results: any[] }

      return c.json({
        code: 200,
        message: 'success',
        users: results || [],
        pagination: {
          total: countResult?.total || 0,
          limit,
          offset,
        },
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // 23. PUT /api/admin/users/:id - update user profile fields
  app.put('/api/admin/users/:id', authMiddleware, requireMaster, async (c) => {
    try {
      const requester = c.get('user') as any
      const userId = parseInt(c.req.param('id') || '', 10)
      if (Number.isNaN(userId) || userId <= 0) {
        return fail(c, 'INVALID_PARAMETER', {
          message: '用户 ID 不合法',
          details: { field: 'id' },
        })
      }

      const body = await c.req.json() as {
        username?: string
        email?: string | null
        level?: number
        avatar_url?: string | null
        role?: string
      }

      const target = await c.env.DB.prepare(
        'SELECT id, role FROM user_profiles WHERE id = ?'
      ).bind(userId).first<{ id: number; role: string }>()

      if (!target) {
        return fail(c, 'USER_NOT_FOUND')
      }

      if (requester.id === target.id && body.role && body.role !== target.role) {
        return fail(c, 'INVALID_FIELD', {
          message: '不能通过该接口修改自己的角色',
          details: { field: 'role' },
        })
      }

      const updates: string[] = []
      const params: Array<string | number | null> = []

      if (body.username !== undefined) {
        const username = body.username.trim()
        if (!username) {
          return fail(c, 'INVALID_FIELD', {
            message: 'username 不能为空',
            details: { field: 'username' },
          })
        }
        updates.push('username = ?')
        params.push(username)
      }

      if (body.email !== undefined) {
        const email = body.email === null || body.email === '' ? null : String(body.email).trim()
        if (email && !isValidEmail(email)) {
          return fail(c, 'EMAIL_INVALID')
        }
        updates.push('email = ?')
        params.push(email)
      }

      if (body.level !== undefined) {
        if (!Number.isInteger(body.level) || body.level < 1 || body.level > 100) {
          return fail(c, 'INVALID_FIELD', {
            message: 'level 必须是 1-100 的整数',
            details: { field: 'level' },
          })
        }
        updates.push('level = ?')
        params.push(body.level)
      }

      if (body.avatar_url !== undefined) {
        const avatarUrl = body.avatar_url === null || body.avatar_url === '' ? null : String(body.avatar_url).trim()
        updates.push('avatar_url = ?')
        params.push(avatarUrl)
      }

      if (body.role !== undefined) {
        if (!isDevelopMasterRole(requester.role)) {
          return fail(c, 'MASTER_FORBIDDEN')
        }

        if (!['user', 'admin', 'master', 'develop_master'].includes(body.role)) {
          return fail(c, 'ROLE_INVALID', {
            message: 'role 只能是 user / admin / master / develop_master',
            details: { field: 'role' },
          })
        }

        updates.push('role = ?')
        params.push(body.role)
      }

      if (updates.length === 0) {
        return fail(c, 'NO_VALID_FIELDS', {
          message: '没有需要更新的字段',
        })
      }

      params.push(userId)
      await c.env.DB.prepare(
        `UPDATE user_profiles SET ${updates.join(', ')} WHERE id = ?`
      ).bind(...params).run()

      const updated = await c.env.DB.prepare(
        `SELECT
           p.id, p.supabase_uid, p.username, p.email, p.level, p.role, p.avatar_url, p.created_at,
           p.last_android_device_id, p.last_android_session_at
         FROM user_profiles p
         WHERE p.id = ?`
      ).bind(userId).first() as any

      if (!updated) {
        return fail(c, 'USER_NOT_FOUND')
      }

      return c.json({
        code: 200,
        message: '用户资料已更新',
        user: {
          id: updated.id,
          supabase_uid: updated.supabase_uid,
          username: updated.username,
          email: updated.email,
          level: updated.level,
          role: updated.role,
          avatar_url: updated.avatar_url,
          created_at: updated.created_at,
          last_android_device_id: updated.last_android_device_id,
          last_android_session_at: updated.last_android_session_at,
        },
      })
    } catch (error: any) {
      if (String(error?.message || '').includes('UNIQUE')) {
        return fail(c, 'INVALID_FIELD', {
          message: 'username 已存在',
          details: { field: 'username' },
        })
      }
      return serverError(c, error)
    }
  })

  // 24. DELETE /api/admin/users/:id - remove user profile
  app.delete('/api/admin/users/:id', authMiddleware, requireMaster, async (c) => {
    try {
      const requester = c.get('user') as any
      const userId = parseInt(c.req.param('id') || '', 10)
      if (Number.isNaN(userId) || userId <= 0) {
        return fail(c, 'INVALID_PARAMETER', {
          message: '用户 ID 不合法',
        })
      }

      const body = await c.req.json().catch(() => ({})) as {
        delete_supabase_auth?: boolean
      }

      const deleteSupabaseAuth = parseBooleanFlag(body.delete_supabase_auth, true)

      const profile = await c.env.DB.prepare(
        'SELECT id, supabase_uid, username, role FROM user_profiles WHERE id = ?'
      ).bind(userId).first() as any

      if (!profile) {
        return fail(c, 'USER_NOT_FOUND')
      }

      if (requester.id === profile.id) {
        return fail(c, 'INVALID_FIELD', {
          message: '不能删除当前登录管理员自己',
        })
      }

      if (deleteSupabaseAuth && profile.supabase_uid) {
        const supabaseAdmin = getSupabaseAdmin(c.env)
        await supabaseAdmin.auth.admin.deleteUser(profile.supabase_uid)
      }

      await c.env.DB.prepare('DELETE FROM user_settings WHERE user_id = ?').bind(userId).run()
      await c.env.DB.prepare('DELETE FROM user_profiles WHERE id = ?').bind(userId).run()

      return c.json({
        code: 200,
        message: '用户已删除',
        deleted: {
          user_id: userId,
          username: profile.username,
        },
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

}


