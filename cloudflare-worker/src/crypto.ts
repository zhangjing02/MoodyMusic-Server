import { Hono, Context } from 'hono'
import type { Bindings } from './types'
import { compareVersionNames } from './app_version'
import { fail, serverError } from './error'

export const DEFAULT_RSA_PUBLIC_KEY = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAo+PGbCPY6AkZmGp0qn3I
5H52lgi9pIscVRsqtu/SukEpSM7OatPiPCBVg/Zk86+6PpgSNR8rmeWUaP6jDCRP
37S1hWcuD52TSpfVCyqgJ0E897aObaVSBjJAS2jJnrClwk4rJ7xzVgKhOwo6h4Lb
25GJcJ8ZnpiESBf8EXaZskuBuiFGQ1GDwXHipdlh8bkdpxKOv99KY89eS2vc+OqQ
LwHYliAz6fYSgtl4hb5+nIsQuxTrPtqjp97dF1XIXnltY3YkCf4LybuAn7NFfU99
X8Px27lCepYwJJ8/WRVZw/LRkV5gU4AYGAYwhvrGvrMn0PSqJN5/24WTlNTyXqNI
MQIDAQAB
-----END PUBLIC KEY-----`

export const DEFAULT_RSA_PRIVATE_KEY = `-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCj48ZsI9joCRmY
anSqfcjkfnaWCL2kixxVGyq279K6QSlIzs5q0+I8IFWD9mTzr7o+mBI1HyuZ5ZRo
/qMMJE/ftLWFZy4PnZNKl9ULKqAnQTz3to5tpVIGMkBLaMmesKXCTisnvHNWAqE7
CjqHgtvbkYlwnxmemIRIF/wRdpmyS4G6IUZDUYPBceKl2WHxuR2nEo6/30pjz15L
a9z46pAvAdiWIDPp9hKC2XiFvn6cixC7FOs+2qOn3t0XVcheeW1jdiQJ/gvJu4Cf
s0V9T31fw/HbuUJ6ljAknz9ZFVnD8tGRXmBTgBgYBjCG+sa+syfQ9Kok3n/bhZOU
1PJeo0gxAgMBAAECggEAFIVavQOoDzXEfK8nuIlTdDjZhGPHyyiX/ZgPOyTAUA4E
q1cpxXqOY1TxIDrj3RdtzJSiAwDKJtT2RkdMByMs1Sf9apzGybHDVZ25UVKfBwtG
JQY4w0XmBVyZbFfMlxArUS8UfD8+edCOe6QGPB2Ihe+tM+rX/GHAfn5yU4V0LTzP
uANUjKrt3uAqIkc34yIhoaOBAzqGpyDib4EwJTXi8AJ1k0ajRC2usoVkN4KxHQrv
Zpz96k1YFWww5+96ypMbMTOFZJt3ahKpHeGMCkB47uqRsVpQ+fU0PW/K6NoLRGRb
FqjQVpILJyb9Rb9zRODMuCKEsYe0f1DX/Gf5fHbB+QKBgQDZlFZJ8JXOcOS0pDqf
JloOOJatxNDpG9y8kFi+VaWjxKT4ok2xprsP9WagRRAl8dZXiFzE8ZBno+gOyarf
+mnpNBRiGnaZEVYiGWSeJgUx0y8d8koeJmFSzH+IOa7l51mgXq5Mo4MwBVS7XuLD
kcP8BomyVd19UN61mlubQakwRwKBgQDA1GYz6m2DOAegXAxhgx6FjKWZhHX06h9h
pAA5tD0+lz4QwJc33UAJWNkll6EJf3dAix5VXliymfL9WBNE6yU8jENqdMZHDy7M
4bFcyYQ4ubUQ71x53JfAf54tBqmlg2M89Wupo09mMfKlPSkDmh7aJqi2K1VtY70p
z0yLkoS3xwKBgBoeN1l62tDENoAEstDF7suEOXo0hQtmf9HW1gBLEa4d/dumyALK
S+w3fhFBGRYk+KDbSp+Ni9MVFtcnmC54xdvrl4LLQG9RaHCBcdWWJMt9WUuT+Rez
bb1dtPVqTzdj1RtuIigq/KV4DlrLohbt2YPYWREiQ4s2ePV9yP9TG3cjAoGAUPUb
z7IdtljAwu/CdvIwz0skf5agW2osMLdFLPTiPbQL58aj9l1atFHsIR9PCgjNDXkb
DCZnQNznqrveozHCWXBeIYTTdiQGtxgOefFVJOe7AFguUC9wOu6Zfzfr48SM1pwH
Tpp1DGfuArfxz0RWrapLbOg2no2gbrxM29BxDiMCgYBhS+xyFKR6kkqtIhkcL3MN
JJ+6jAZcpECrwsw6LTgJQeaiK6tk5ggRuTa0G9+oqrJZsmPslMHlDkvLzZSwXCre
QhmSq6NWssthAEWtIeFaGwbcLL/ggIxZ5xQ73RXqVqoDN7TGix5ukXtxPyTY/Mf0
+7GkMUyA0HzEu5tyoI/fuw==
-----END PRIVATE KEY-----`

export const DEFAULT_STREAM_SIGN_SECRET = 'moody-music-stream-protection-secret-key-2026'

// 辅助：从 PEM 转换为 ArrayBuffer 二进制
function pemToArrayBuffer(pem: string): ArrayBuffer {
  const b64 = pem
    .replace(/-----BEGIN [A-Z ]+-----/, '')
    .replace(/-----END [A-Z ]+-----/, '')
    .replace(/[\r\n\s]/g, '')
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes.buffer
}

// 辅助：ArrayBuffer 转 Base64
export function bufferToBase64(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

// 辅助：Base64 转 Uint8Array
export function base64ToUint8Array(base64: string): Uint8Array {
  const binary = atob(base64.trim())
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

// 缓存已导入的 RSA 私钥对象，避免每次请求重复解析
let cachedPrivateKey: CryptoKey | null = null
let cachedPrivateKeyPem: string = ''

export async function getRsaPrivateKey(env: Bindings): Promise<CryptoKey> {
  const pem = env.RSA_PRIVATE_KEY || DEFAULT_RSA_PRIVATE_KEY
  if (cachedPrivateKey && cachedPrivateKeyPem === pem) {
    return cachedPrivateKey
  }
  const keyBuffer = pemToArrayBuffer(pem)
  cachedPrivateKey = await crypto.subtle.importKey(
    'pkcs8',
    keyBuffer,
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['decrypt']
  )
  cachedPrivateKeyPem = pem
  return cachedPrivateKey
}

// 解密客户端上报的 RSA-OAEP 加密后的 AES-256 密钥
export async function decryptRsaKey(encryptedKeyBase64: string, env: Bindings): Promise<CryptoKey> {
  const privateKey = await getRsaPrivateKey(env)
  const encryptedBytes = base64ToUint8Array(encryptedKeyBase64)
  const decryptedRawKey = await crypto.subtle.decrypt(
    { name: 'RSA-OAEP' },
    privateKey,
    encryptedBytes
  )
  // 将解出的 32 字节密钥导入为 AES-GCM CryptoKey
  return await crypto.subtle.importKey(
    'raw',
    decryptedRawKey,
    { name: 'AES-GCM' },
    false,
    ['encrypt', 'decrypt']
  )
}

// AES-256-GCM 解密请求负载
export async function decryptPayload(
  encryptedBase64: string,
  ivBase64: string,
  aesKey: CryptoKey
): Promise<string> {
  const ciphertext = base64ToUint8Array(encryptedBase64)
  const iv = base64ToUint8Array(ivBase64)
  const decryptedBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    aesKey,
    ciphertext
  )
  return new TextDecoder().decode(decryptedBuffer)
}

// AES-256-GCM 加密响应负载
export async function encryptPayload(
  plaintext: string,
  aesKey: CryptoKey
): Promise<{ payload: string; iv: string }> {
  // 生成随机 12 字节 IV
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const data = new TextEncoder().encode(plaintext)
  const encryptedBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    aesKey,
    data
  )
  return {
    payload: bufferToBase64(encryptedBuffer),
    iv: bufferToBase64(iv)
  }
}

// ========================================================
// 音频流短效 HMAC-SHA256 签名与鉴权
// ========================================================

async function getHmacKey(secret: string): Promise<CryptoKey> {
  return await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify']
  )
}

function toHex(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  return Array.from(bytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
}

/**
 * 为目标音频 URL 签发短效播放流地址
 * @param targetUrl 真实公网或 R2 存储 URL
 * @param baseUrl 当前 Worker 基础域名 (如 https://m-api.changgepd.ccwu.cc)
 * @param secret 签名私钥
 * @param ttlSeconds 有效期（秒），默认 15 分钟
 */
export async function generateSignedStreamUrl(
  targetUrl: string,
  baseUrl: string,
  secret: string,
  ttlSeconds: number = 14400 // 默认 4 小时 (长效保证整张专辑预加载与循环播放体验)
): Promise<string> {
  if (!targetUrl) return ''
  const exp = Math.floor(Date.now() / 1000) + ttlSeconds
  // 对目标 URL 进行安全 Base64 编码 (使用 URL Safe Base64)
  const targetEncoded = btoa(encodeURIComponent(targetUrl))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')

  const message = `${targetEncoded}:${exp}`
  const hmacKey = await getHmacKey(secret)
  const sigBuffer = await crypto.subtle.sign(
    'HMAC',
    hmacKey,
    new TextEncoder().encode(message)
  )
  const sig = toHex(sigBuffer)

  // 拼接短效流式代理 URL (/api/media/stream)
  const cleanBase = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl
  return `${cleanBase}/api/media/stream?target=${targetEncoded}&exp=${exp}&sig=${sig}`
}

/**
 * 校验流式音频签名的合法性与有效期
 */
export async function verifyStreamSignature(
  targetEncoded: string,
  exp: number,
  sig: string,
  secret: string
): Promise<{ valid: boolean; rawUrl?: string; error?: string }> {
  const now = Math.floor(Date.now() / 1000)
  if (now > exp) {
    return { valid: false, error: 'STREAM_EXPIRED' }
  }

  const message = `${targetEncoded}:${exp}`
  const hmacKey = await getHmacKey(secret)
  const expectedSigBuffer = await crypto.subtle.sign(
    'HMAC',
    hmacKey,
    new TextEncoder().encode(message)
  )
  const expectedSig = toHex(expectedSigBuffer)

  if (expectedSig.toLowerCase() !== sig.toLowerCase()) {
    return { valid: false, error: 'SIGNATURE_MISMATCH' }
  }

  try {
    // 还原 URL
    let b64 = targetEncoded.replace(/-/g, '+').replace(/_/g, '/')
    while (b64.length % 4 !== 0) b64 += '='
    const rawUrl = decodeURIComponent(atob(b64))
    return { valid: true, rawUrl }
  } catch {
    return { valid: false, error: 'INVALID_TARGET' }
  }
}

/**
 * 判定客户端是否支持/要求加密通信
 * 满足以下任一条件时自动激活密文通道：
 * 1. 显式上报了 x-encrypted-key
 * 2. Android 客户端版本 >= 1.0.15 或 versionCode >= 15
 * 3. 显式携带了 x-client-crypto: true
 */
export function isCryptoClient(c: Context<any>): boolean {
  if (c.req.header('x-encrypted-key')) return true
  if (c.req.header('x-client-crypto') === 'true') return true

  const clientType = (c.req.header('x-app-platform') || c.req.header('x-client-type') || '').toLowerCase()
  const versionName = c.req.header('x-app-version-name') || c.req.header('x-app-version') || ''
  const versionCode = parseInt(c.req.header('x-app-version-code') || '0', 10)

  if (clientType === 'android') {
    if (versionCode >= 15 || (versionName && compareVersionNames(versionName, '1.0.15') >= 0)) {
      return true
    }
  }

  return false
}

/**
 * 递归遍历响应体，将所有暴露的 R2 音频直链（http... 或 /storage/...）转换为带短效 HMAC 签名的流式播放地址
 */
export async function transformResourceUrlsToSignedStreams(
  data: any,
  baseUrl: string,
  secret: string
): Promise<any> {
  if (!data || typeof data !== 'object') return data

  if (Array.isArray(data)) {
    for (let i = 0; i < data.length; i++) {
      data[i] = await transformResourceUrlsToSignedStreams(data[i], baseUrl, secret)
    }
    return data
  }

  for (const key of Object.keys(data)) {
    const val = data[key]
    if (typeof val === 'string' && val.length > 0) {
      // 匹配音频路径（mp3, m4a, flac, wav 或包含 /music/ 的资源路径）
      const isAudioKey = (key === 'path' || key === 'file_path' || key === 'filePath' || key === 'audioUrl')
      const isAudioUrl = val.includes('.mp3') || val.includes('.m4a') || val.includes('.flac') || val.includes('/music/')
      
      if (
        (isAudioKey || isAudioUrl) &&
        (val.startsWith('http://') || val.startsWith('https://') || val.startsWith('/storage/')) &&
        !val.includes('/api/media/stream?')
      ) {
        data[key] = await generateSignedStreamUrl(val, baseUrl, secret)
      }
    } else if (val && typeof val === 'object') {
      data[key] = await transformResourceUrlsToSignedStreams(val, baseUrl, secret)
    }
  }
  return data
}

/**
 * 全局 API 报文信封加解密与音频直链脱敏中间件
 */
export const cryptoMiddleware = async (c: Context<{ Bindings: Bindings; Variables: any }>, next: any) => {
  const path = c.req.path

  // 公钥获取端点、音频中转端点以及 OPTIONS 预检请求不走加解密逻辑
  if (path === '/api/crypto/public-key' || path.startsWith('/api/media/stream') || c.req.method === 'OPTIONS') {
    return await next()
  }

  const encryptedKeyHeader = c.req.header('x-encrypted-key')

  // 1. 全局统一强制要求握手信封秘钥（不依赖版本号或特定客户端，统一加解密）
  if (!encryptedKeyHeader) {
    return c.json({
      code: 400,
      message: 'Enveloped encryption required. Missing x-encrypted-key header.'
    }, 400)
  }

  // 2. 解密 RSA-OAEP 封装的 AES-256 Key
  let aesKey: CryptoKey
  try {
    aesKey = await decryptRsaKey(encryptedKeyHeader, c.env)
    c.set('aesKey', aesKey)
    c.set('isCryptoClient', true)
  } catch (err: any) {
    console.error('[CryptoMiddleware] RSA decrypt aes key failed:', err.message)
    return c.json({ code: 400, message: 'Invalid encrypted key handshake' }, 400)
  }

  // 3. 处理请求体解密（POST / PUT / PATCH）
  const contentType = c.req.header('content-type') || ''
  if (contentType.includes('application/json') && (c.req.method === 'POST' || c.req.method === 'PUT' || c.req.method === 'PATCH')) {
    try {
      const rawBodyText = await c.req.text()
      if (rawBodyText && rawBodyText.trim().length > 0) {
        const bodyJson = JSON.parse(rawBodyText)
        if (bodyJson && bodyJson.payload) {
          const iv = c.req.header('x-encrypted-iv') || bodyJson.iv
          if (!iv) {
            return c.json({ code: 400, message: 'Missing encrypted IV in header or payload' }, 400)
          }
          const decryptedJsonStr = await decryptPayload(bodyJson.payload, iv, aesKey)
          const decryptedObj = JSON.parse(decryptedJsonStr)
          
          // 覆盖 c.req.json 方法
          c.req.json = async () => decryptedObj
          ;(c.req as any)._decryptedJson = decryptedObj
        }
      }
    } catch (err: any) {
      console.error('[CryptoMiddleware] Decrypt request body failed:', err.message)
      return c.json({ code: 400, message: 'Failed to decrypt request body' }, 400)
    }
  }

  // 4. 执行下游业务路由
  await next()

  // 5. 处理响应阶段：全局强制加密回传
  if (c.res) {
    try {
      const resContentType = c.res.headers.get('content-type') || ''
      if (resContentType.includes('application/json')) {
        const originalJson = await c.res.json()
        const baseUrl = new URL(c.req.url).origin
        const secret = c.env.STREAM_SIGN_SECRET || DEFAULT_STREAM_SIGN_SECRET

        // 对响应数据中的所有音视频直链进行动态短效 HMAC 签名保护
        const maskedData = await transformResourceUrlsToSignedStreams(originalJson, baseUrl, secret)

        // 加密响应 JSON 字符串
        const jsonStr = JSON.stringify(maskedData)
        const encrypted = await encryptPayload(jsonStr, aesKey)

        // 构造加密回传响应
        c.res = c.json({
          code: 200,
          encrypted: true,
          iv: encrypted.iv,
          payload: encrypted.payload
        })
        c.res.headers.set('X-Crypto-Response', 'AES-256-GCM')
      }
    } catch (err: any) {
      console.error('[CryptoMiddleware] Response encryption error:', err.message)
    }
  }
}

// ========================================================
// 路由与流式转发处理
// ========================================================

export function registerCryptoRoutes(app: Hono<{ Bindings: Bindings; Variables: any }>) {
  
  // 1. 公钥获取端点（App 与 Web 启动时拉取并缓存在本地）
  app.get('/api/crypto/public-key', (c) => {
    const pubKey = c.env.RSA_PUBLIC_KEY || DEFAULT_RSA_PUBLIC_KEY
    return c.json({
      code: 200,
      message: 'success',
      data: {
        public_key: pubKey,
        algorithm: 'RSA-OAEP-SHA256',
        target_version: 'v1.0.15',
        min_crypto_version_code: 15
      }
    })
  })

  // 2. 音频防盗链流式中转代理（支持 HTTP Range 206 毫秒级拖动快进）
  app.get('/api/media/stream', async (c) => {
    const target = c.req.query('target')
    const expStr = c.req.query('exp')
    const sig = c.req.query('sig')

    if (!target || !expStr || !sig) {
      return c.text('Forbidden: Missing signature parameters', 403)
    }

    const exp = parseInt(expStr, 10)
    if (isNaN(exp)) {
      return c.text('Forbidden: Invalid expiration', 403)
    }

    const secret = c.env.STREAM_SIGN_SECRET || DEFAULT_STREAM_SIGN_SECRET
    const verification = await verifyStreamSignature(target, exp, sig, secret)

    if (!verification.valid || !verification.rawUrl) {
      console.warn(`[StreamSecurity] Blocked unauthorized stream access: reason=${verification.error}`)
      return c.text(`Forbidden: ${verification.error || 'Access Denied'}`, 403)
    }

    const rawUrl = verification.rawUrl

    // 检查防盗链与来源合法性（双白名单机制：Web 端必须带合法 Referer，App 端必须带 App 特征）
    const referer = c.req.header('referer') || ''
    const userAgent = (c.req.header('user-agent') || '').toLowerCase()
    const platform = (c.req.header('x-app-platform') || '').toLowerCase()
    const isAndroidApp = platform === 'android' || userAgent.includes('moodymusic-android') || userAgent.includes('exoplayer')

    let isAllowedOrigin = false
    if (referer) {
      try {
        const refUrl = new URL(referer)
        const host = refUrl.hostname
        // 允许自己站点的域名和本地开发测试
        isAllowedOrigin = host.endsWith('ccwu.cc') ||
                          host.endsWith('workers.dev') ||
                          host.endsWith('netlify.app') ||
                          host.includes('localhost') ||
                          host.includes('127.0.0.1') ||
                          host.includes('pgyer.com')
      } catch {
        isAllowedOrigin = false
      }
    }

    // 必须满足：合法 Web 来源 或 合法 Android App 客户端
    if (!isAllowedOrigin && !isAndroidApp) {
      console.warn(`[StreamSecurity] Blocked unauthorized media access: referer="${referer}", ua="${userAgent}"`)
      return c.text('Forbidden: Unauthorized player origin or missing referer', 403)
    }
    // 转发请求头（特别是 Range 标头，保障 ExoPlayer 毫秒级 Seek 快进能力）
    const rangeHeader = c.req.header('range')
    const upstreamHeaders = new Headers()
    if (rangeHeader) {
      upstreamHeaders.set('Range', rangeHeader)
    }
    upstreamHeaders.set('User-Agent', 'MoodyMusic-EdgeStream/2.0')

    try {
      let safeUrl = rawUrl
      // 处理可能的相对路径
      if (safeUrl.startsWith('/')) {
        const baseUrl = new URL(c.req.url).origin
        safeUrl = `${baseUrl}${safeUrl}`
      }
      // 防御双重 URL 编码：先 decodeURI 还原，再 safe encodeURI，坚决避免 % 变为 %25 导致 R2 报 404
      try {
        safeUrl = encodeURI(decodeURI(safeUrl))
      } catch {
        // 若含有特殊畸形编码则维持 safeUrl 原状
      }

      const upstreamRes = await fetch(safeUrl, {
        method: 'GET',
        headers: upstreamHeaders
      })

      // 组装回传标头
      const responseHeaders = new Headers()
      const forwardHeaderList = [
        'content-type',
        'content-length',
        'content-range',
        'accept-ranges',
        'etag',
        'last-modified'
      ]

      for (const h of forwardHeaderList) {
        const val = upstreamRes.headers.get(h)
        if (val) responseHeaders.set(h, val)
      }

      // 永远声明支持 Range 请求
      responseHeaders.set('Accept-Ranges', 'bytes')
      // 短效边缘缓存（根据剩余有效期设置，最长 600 秒）
      responseHeaders.set('Cache-Control', 'public, max-age=600')

      return new Response(upstreamRes.body, {
        status: upstreamRes.status,
        headers: responseHeaders
      })
    } catch (err: any) {
      console.error('[StreamProxy] Fetch upstream error:', err.message)
      return c.text('Failed to fetch audio stream', 502)
    }
  })
}

// ========================================================
// 方案一/三：Web 专属字段轻量对称加解密 (流密码 + 随机盐)
// ========================================================

export const MOODY_WEB_FIELD_KEY = 'MoodyMusic-WebGuard-Secret-2026!'

/**
 * 轻量对称流密码加密（针对 Web 端专属字段如 song.path 混淆）
 * 每次生成 8 字节随机盐，保证同一 URL 每次加密输出的密文均完全不同
 */
export function encryptWebField(plainText: string, keyStr: string = MOODY_WEB_FIELD_KEY): string {
  if (!plainText) return plainText
  const salt = new Uint8Array(8)
  crypto.getRandomValues(salt)
  
  // KSA
  const keyBytes = new TextEncoder().encode(keyStr)
  const comb = new Uint8Array(keyBytes.length + salt.length)
  comb.set(keyBytes, 0)
  comb.set(salt, keyBytes.length)

  const s = new Uint8Array(256)
  for (let i = 0; i < 256; i++) s[i] = i
  let j = 0
  for (let i = 0; i < 256; i++) {
    j = (j + s[i] + comb[i % comb.length]) & 0xff
    const tmp = s[i]
    s[i] = s[j]
    s[j] = tmp
  }

  // Drop 512
  let si = 0, sj = 0
  for (let d = 0; d < 512; d++) {
    si = (si + 1) & 0xff
    sj = (sj + s[si]) & 0xff
    const tmp = s[si]
    s[si] = s[sj]
    s[sj] = tmp
  }

  const plainBytes = new TextEncoder().encode(plainText)
  const cipher = new Uint8Array(plainBytes.length)
  for (let k = 0; k < plainBytes.length; k++) {
    si = (si + 1) & 0xff
    sj = (sj + s[si]) & 0xff
    const tmp = s[si]
    s[si] = s[sj]
    s[sj] = tmp
    cipher[k] = plainBytes[k] ^ s[(s[si] + s[sj]) & 0xff]
  }

  let saltHex = ''
  for (let i = 0; i < salt.length; i++) {
    saltHex += salt[i].toString(16).padStart(2, '0')
  }
  let cipherHex = ''
  for (let i = 0; i < cipher.length; i++) {
    cipherHex += cipher[i].toString(16).padStart(2, '0')
  }

  return `moody://enc_v1:${saltHex}${cipherHex}`
}

/**
 * 轻量对称流密码解密
 */
export function decryptWebField(cipherStr: string, keyStr: string = MOODY_WEB_FIELD_KEY): string {
  if (!cipherStr || !cipherStr.startsWith('moody://enc_v1:')) return cipherStr
  const hex = cipherStr.slice('moody://enc_v1:'.length)
  if (hex.length < 16) return cipherStr
  const saltHex = hex.slice(0, 16)
  const bodyHex = hex.slice(16)
  
  const salt = new Uint8Array(8)
  for (let i = 0; i < 8; i++) {
    salt[i] = parseInt(saltHex.substr(i * 2, 2), 16)
  }

  const bodyLen = bodyHex.length / 2
  const body = new Uint8Array(bodyLen)
  for (let i = 0; i < bodyLen; i++) {
    body[i] = parseInt(bodyHex.substr(i * 2, 2), 16)
  }

  // KSA
  const keyBytes = new TextEncoder().encode(keyStr)
  const comb = new Uint8Array(keyBytes.length + salt.length)
  comb.set(keyBytes, 0)
  comb.set(salt, keyBytes.length)

  const s = new Uint8Array(256)
  for (let i = 0; i < 256; i++) s[i] = i
  let j = 0
  for (let i = 0; i < 256; i++) {
    j = (j + s[i] + comb[i % comb.length]) & 0xff
    const tmp = s[i]
    s[i] = s[j]
    s[j] = tmp
  }

  // Drop 512
  let si = 0, sj = 0
  for (let d = 0; d < 512; d++) {
    si = (si + 1) & 0xff
    sj = (sj + s[si]) & 0xff
    const tmp = s[si]
    s[si] = s[sj]
    s[sj] = tmp
  }

  const plain = new Uint8Array(bodyLen)
  for (let k = 0; k < bodyLen; k++) {
    si = (si + 1) & 0xff
    sj = (sj + s[si]) & 0xff
    const tmp = s[si]
    s[si] = s[sj]
    s[sj] = tmp
    plain[k] = body[k] ^ s[(s[si] + s[sj]) & 0xff]
  }

  return new TextDecoder().decode(plain)
}

