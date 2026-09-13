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
  version_name: string           // 服务器最新版本名 (如 "1.1.0")
  min_version_code: number       // 最低受支持版本（低于此版本强制更新）
  min_version_name: string       // 最低受支持版本名
  
  // 软件包与下载
  download_url: string           // 安装包下载直链 (Cloudflare R2 / Worker Storage)
  download_url_mirror?: string   // 备用镜像地址（防止国内部分网络 DNS 阻断）
  package_size: number           // 安装包字节数 (Bytes)
  package_size_str: string       // 人类可读包体积 (如 "21.4 MB")
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
  
  // 1. 优先从 Header 提取（标准拦截器上报）
  const platformHeader = req.header('x-app-platform') || req.header('x-client-type') || req.query('platform') || 'android'
  const versionCodeHeader = parseInt(req.header('x-app-version-code') || req.query('version_code') || '1', 10)
  const versionNameHeader = req.header('x-app-version-name') || req.header('x-app-version') || req.query('version_name') || '1.0'
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
 * 注册 App 版本与更新相关路由
 */
export function registerAppVersionRoutes(app: Hono<AppType>) {
  
  // ==========================================
  // GET & POST /api/app/version/check (检查版本更新)
  // ==========================================
  const handleVersionCheck = async (c: any) => {
    try {
      const client = extractClientContext(c)
      const baseUrl = new URL(c.req.url).origin

      console.log(`[VersionCheck] Platform: ${client.platform}, ClientCode: ${client.versionCode}, Brand: ${client.deviceBrand} (${client.deviceModel}), Arch: ${client.deviceArch}`)

      // 最新发布的版本配置（支持未来接入 D1 app_settings 动态调控）
      const LATEST_VERSION_CODE = 2
      const LATEST_VERSION_NAME = "1.1.0"
      const MIN_SUPPORTED_VERSION_CODE = 1 // 低于此版本执行强制更新
      const MIN_SUPPORTED_VERSION_NAME = "1.0.0"

      // 瘦身后实测包体积：22,473,035 字节 (21.43 MB)
      const PACKAGE_SIZE_BYTES = 22473035
      const PACKAGE_SIZE_STR = "21.4 MB"
      const DOWNLOAD_PATH = "/storage/releases/MoodyMusic-v1.1.0.apk"
      const FULL_DOWNLOAD_URL = `${baseUrl}${DOWNLOAD_PATH}`
      const MIRROR_DOWNLOAD_URL = "https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/releases/MoodyMusic-v1.1.0.apk"

      // 判定逻辑
      const hasUpdate = client.versionCode < LATEST_VERSION_CODE
      // 强制更新：客户端构建号低于最低要求
      const isForceUpdate = hasUpdate && (client.versionCode < MIN_SUPPORTED_VERSION_CODE)
      // 非强制更新：允许用户暂不更新、忽略此版本
      const isIgnoredAllowed = !isForceUpdate

      const updateData: AppVersionData = {
        has_update: hasUpdate,
        is_force_update: isForceUpdate,
        is_ignored_allowed: isIgnoredAllowed,
        is_silent_update: false,
        version_code: LATEST_VERSION_CODE,
        version_name: LATEST_VERSION_NAME,
        min_version_code: MIN_SUPPORTED_VERSION_CODE,
        min_version_name: MIN_SUPPORTED_VERSION_NAME,
        download_url: FULL_DOWNLOAD_URL,
        download_url_mirror: MIRROR_DOWNLOAD_URL,
        package_size: PACKAGE_SIZE_BYTES,
        package_size_str: PACKAGE_SIZE_STR,
        package_md5: "b4c2089f3b1406859e35da17aef92c4b",
        title: hasUpdate ? (isForceUpdate ? "核心版本升级提醒" : "发现新版本 v1.1.0") : "当前已是最新版本",
        release_notes: [
          "1. 【极速瘦身】删除冗余字库包，安装包体积从 53.2 MB 骤降至 21.4 MB（缩小 60%）！",
          "2. 【抽屉重构】优化侧滑抽屉布局，移除字体及主题切换，视觉纯粹统一",
          "3. 【在线更新】新增在线版本检测与 APK 一键下载更新安装体系",
          "4. 【存储管理】新增本地图片与音乐缓存一键清理功能",
          "5. 【体验提升】优化启动字体异步预加载与后台播放稳定性"
        ].join("\n"),
        publish_time: "2026-09-12T01:30:00Z"
      }

      return c.json({
        code: 200,
        message: "success",
        data: updateData
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
