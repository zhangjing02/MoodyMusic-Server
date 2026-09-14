import { Hono } from 'hono'
import type { Bindings } from './types'
import { fail, serverError } from './error'

type AppType = { Bindings: Bindings; Variables: { user: any; token: string } }

/**
 * 版本检查结果数据契约
 */
export interface AppVersionData {
  has_update: boolean
  is_force_update: boolean        // 强制更新标识（客户端低于最低支持版本时触发）
  is_ignored_allowed: boolean     // 非强制更新标识（是否允许用户选择“稍后提醒”或“忽略此版本”）
  is_silent_update: boolean      // 是否支持在 WiFi 下静默预下载
  
  // 版本号信息
  version_code: number           // 服务器最新构建号 (int)
  version_name: string           // 服务器最新版本名 (如 "1.0.1")
  min_version_code: number       // 最低受支持版本号
  min_version_name: string       // 最低受支持版本名
  
  // 软件包与下载
  download_url: string           // 安装包下载直链 (蒲公英签名直链或 CDN)
  download_url_mirror?: string   // 备用分发页面地址 (蒲公英应用页面)
  package_size: number           // 安装包字节数 (Bytes)
  package_size_str: string       // 人类可读包体积 (如 "22.6 MB")
  package_md5?: string           // 安装包校验 Hash
  
  // 文案与日志
  title: string                  // 升级弹窗标题
  release_notes: string          // 更新日志说明
  publish_time: string           // 发布时间 (ISO 8601)
}

/**
 * 客户端请求元数据（从 Header 与 Query 中采集）
 */
export interface ClientDeviceContext {
  platform: 'android' | 'ios' | 'web' | string
  versionCode: number
  versionName: string
  packageName: string
  channel: string
  deviceBrand: string
  deviceModel: string
  osVersion: string
  sdkInt: number
  deviceArch: string
  deviceId: string
  locale: string
  networkType: string
}

/**
 * 从请求中提取客户端与设备详细信息
 */
function extractClientContext(c: any): ClientDeviceContext {
  const req = c.req
  
  // 优先从 Header 提取（由 Retrofit 统一拦截器上报）
  const platformHeader = req.header('x-app-platform') || req.header('x-client-type') || req.query('platform') || 'android'
  const versionCodeHeader = parseInt(req.header('x-app-version-code') || req.query('version_code') || '1', 10)
  const versionNameHeader = req.header('x-app-version-name') || req.header('x-app-version') || req.query('version_name') || '1.0.0'
  const packageNameHeader = req.header('x-app-package-name') || req.query('package_name') || 'com.example.moodymusicforandroid'
  const channelHeader = req.header('x-app-channel') || req.query('channel') || 'official'
  const brandHeader = req.header('x-device-brand') || req.query('brand') || 'Unknown'
  const modelHeader = req.header('x-device-model') || req.query('model') || 'Unknown'
  const osVersionHeader = req.header('x-device-os-version') || req.query('os_version') || ''
  const sdkIntHeader = parseInt(req.header('x-device-sdk-int') || req.query('sdk_int') || '0', 10)
  const archHeader = req.header('x-device-arch') || req.query('arch') || 'arm64-v8a'
  const deviceIdHeader = req.header('x-device-id') || req.query('device_id') || ''
  const localeHeader = req.header('x-app-locale') || req.header('accept-language') || 'zh-CN'
  const networkHeader = req.header('x-network-type') || 'WIFI'

  return {
    platform: platformHeader.toLowerCase(),
    versionCode: isNaN(versionCodeHeader) ? 1 : versionCodeHeader,
    versionName: versionNameHeader,
    packageName: packageNameHeader,
    channel: channelHeader,
    deviceBrand: brandHeader,
    deviceModel: modelHeader,
    osVersion: osVersionHeader,
    sdkInt: isNaN(sdkIntHeader) ? 0 : sdkIntHeader,
    deviceArch: archHeader,
    deviceId: deviceIdHeader,
    locale: localeHeader,
    networkType: networkHeader
  }
}

/**
 * 语义化版本名称比对算法 (Semantic Versioning Comparison)
 * 
 * 核心规则：
 * 1. 忽略 Build 数字，仅根据版本名称（Version Name，如 "1.0.1" vs "1.0.0"）进行多段比对
 * 2. 自动剔除 'v'/'V' 前缀及空白
 * 3. 逐段对比：纯数字段按数值大小自然数比对（例如 10 > 2，避免字典序错误）
 * 4. 缺省段处理：例如 "1.0" 与 "1.0.1"，后者有非零数字，后者更大
 * 
 * 返回值：
 *   > 0 : v1 > v2 (v1 较大)
 *   < 0 : v1 < v2 (v1 较小)
 *   = 0 : v1 == v2 (两版本等价)
 */
export function compareVersionNames(v1: string, v2: string): number {
  if (!v1 && !v2) return 0
  if (!v1) return -1
  if (!v2) return 1

  const clean = (s: string) => s.trim().replace(/^[vV]/, '')
  const s1 = clean(v1)
  const s2 = clean(v2)

  if (s1 === s2) return 0

  const parts1 = s1.split(/[.\-_+]/).filter(p => p.length > 0)
  const parts2 = s2.split(/[.\-_+]/).filter(p => p.length > 0)

  const maxLen = Math.max(parts1.length, parts2.length)
  for (let i = 0; i < maxLen; i++) {
    const p1 = parts1[i]
    const p2 = parts2[i]

    if (p1 === undefined) {
      const n2 = parseInt(p2, 10)
      return !isNaN(n2) && n2 > 0 ? -1 : 0
    }
    if (p2 === undefined) {
      const n1 = parseInt(p1, 10)
      return !isNaN(n1) && n1 > 0 ? 1 : 0
    }

    const num1 = parseInt(p1, 10)
    const num2 = parseInt(p2, 10)
    const isNum1 = !isNaN(num1) && String(num1) === p1
    const isNum2 = !isNaN(num2) && String(num2) === p2

    if (isNum1 && isNum2) {
      if (num1 !== num2) {
        return num1 > num2 ? 1 : -1
      }
    } else {
      const cmp = p1.localeCompare(p2, undefined, { numeric: true, sensitivity: 'base' })
      if (cmp !== 0) return cmp > 0 ? 1 : -1
    }
  }

  return 0
}

/**
 * 蒲公英 API 内存缓存（TTL: 3分钟）
 * 避免用户频繁打开 App 消耗蒲公英每日接口调用配额
 */
interface PgyerCacheEntry {
  timestamp: number
  data: any
}

let pgyerCache: PgyerCacheEntry | null = null
const PGYER_CACHE_TTL_MS = 3 * 60 * 1000 // 3 分钟

/**
 * 请求蒲公英 API 获取最新版本元数据
 */
async function fetchLatestFromPgyer(apiKey: string, appKey: string): Promise<any | null> {
  const now = Date.now()
  if (pgyerCache && (now - pgyerCache.timestamp < PGYER_CACHE_TTL_MS)) {
    return pgyerCache.data
  }

  try {
    const formData = new URLSearchParams()
    formData.append('_api_key', apiKey)
    formData.append('appKey', appKey)

    const response = await fetch('https://www.pgyer.com/apiv2/app/check', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: formData.toString()
    })

    if (!response.ok) {
      console.error(`[Pgyer] HTTP error: ${response.status} ${response.statusText}`)
      return pgyerCache ? pgyerCache.data : null
    }

    const json = await response.json() as any
    if (json.code === 0 && json.data) {
      pgyerCache = {
        timestamp: now,
        data: json.data
      }
      return json.data
    } else {
      console.warn(`[Pgyer] API warning: code=${json.code}, message=${json.message}`)
      return pgyerCache ? pgyerCache.data : null
    }
  } catch (error) {
    console.error('[Pgyer] Fetch exception:', error)
    return pgyerCache ? pgyerCache.data : null
  }
}

/**
 * 注册 App 版本与更新相关路由
 */
export function registerAppVersionRoutes(app: Hono<AppType>) {
  
  // ==========================================
  // GET & POST /api/app/version/check (检查版本更新)
  // ==========================================
  const handleVersionCheck = async (c: any) => {
    try {
      const client = extractClientContext(c)
      const pgyerApiKey = c.env?.PGYER_API_KEY || "48ceaf75791c09d36fdb364b8f1fd314"
      const pgyerAppKey = c.env?.PGYER_APP_KEY || "e127ba6898e9d160519e7fb0b0dc3bde"

      console.log(`[VersionCheck] Client VersionName: "${client.versionName}", ClientCode: ${client.versionCode}, Brand: ${client.deviceBrand}`)

      // 1. 从蒲公英拉取最新的应用信息
      const pgyerData = await fetchLatestFromPgyer(pgyerApiKey, pgyerAppKey)

      // 如果蒲公英数据获取成功
      if (pgyerData) {
        const latestVersionName = pgyerData.buildVersion || "1.0.0"
        const latestBuildVersion = parseInt(pgyerData.buildBuildVersion || "1", 10)
        const packageSizeBytes = parseInt(pgyerData.buildFileSize || "0", 10)
        const packageSizeStr = packageSizeBytes > 0
          ? `${(packageSizeBytes / (1024 * 1024)).toFixed(1)} MB`
          : "22.6 MB"
        
        const downloadUrl = pgyerData.downloadURL || ""
        const mirrorUrl = pgyerData.buildShortcutUrl || pgyerData.appURl || "https://www.pgyer.com/yinxin-android"
        const releaseNotes = pgyerData.buildUpdateDescription?.trim() 
          ? pgyerData.buildUpdateDescription 
          : (pgyerData.buildDescription?.trim() || "发现新版本，优化系统体验与性能。")

        // 2. 核心比对逻辑：使用版本名称（Version Name）严格比对，忽略 Build 编号
        // 只有蒲公英上的版本名称严格大于客户端版本名称时，才判定为有新版本
        const comparison = compareVersionNames(latestVersionName, client.versionName)
        const hasUpdate = comparison > 0

        // 强制更新策略（若蒲公英标记 needForceUpdate 为 true，或客户端版本极低）
        const isForceUpdate = hasUpdate && Boolean(pgyerData.needForceUpdate)
        const isIgnoredAllowed = !isForceUpdate

        const updateData: AppVersionData = {
          has_update: hasUpdate,
          is_force_update: isForceUpdate,
          is_ignored_allowed: isIgnoredAllowed,
          is_silent_update: false,
          version_code: isNaN(latestBuildVersion) ? 1 : latestBuildVersion,
          version_name: latestVersionName,
          min_version_code: 1,
          min_version_name: "1.0.0",
          download_url: downloadUrl,
          download_url_mirror: mirrorUrl,
          package_size: packageSizeBytes,
          package_size_str: packageSizeStr,
          package_md5: pgyerData.buildFileKey,
          title: hasUpdate ? (isForceUpdate ? "核心版本升级提醒" : `发现新版本 v${latestVersionName}`) : "当前已是最新版本",
          release_notes: releaseNotes,
          publish_time: pgyerData.buildCreated || new Date().toISOString()
        }

        return c.json({
          code: 200,
          message: "success",
          data: updateData
        })
      }

      // 兜底回退：若蒲公英完全不可达，提供安全默认应答，避免客户端报错
      const fallbackData: AppVersionData = {
        has_update: false,
        is_force_update: false,
        is_ignored_allowed: true,
        is_silent_update: false,
        version_code: client.versionCode,
        version_name: client.versionName,
        min_version_code: 1,
        min_version_name: "1.0.0",
        download_url: "",
        download_url_mirror: "https://www.pgyer.com/yinxin-android",
        package_size: 0,
        package_size_str: "0.0 MB",
        title: "当前已是最新版本",
        release_notes: "当前已是最新稳定版本",
        publish_time: new Date().toISOString()
      }

      return c.json({
        code: 200,
        message: "success",
        data: fallbackData
      })
    } catch (error: any) {
      console.error('[VersionCheck] Error:', error)
      return serverError(c, error)
    }
  }

  app.get('/api/app/version/check', handleVersionCheck)
  app.post('/api/app/version/check', handleVersionCheck)
  app.get('/api/app/version/latest', handleVersionCheck)
}
