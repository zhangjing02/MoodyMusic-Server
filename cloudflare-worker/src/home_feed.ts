import { Hono } from 'hono'
import type {
  Bindings,
  HomeFeedData,
  HomeBlock,
  SaveHomeFeedRequest
} from './types'
import { fail, serverError } from './error'

type AppType = { Bindings: Bindings; Variables: { user: any; token: string } }

/**
 * 内置高质量默认首页切片流（确保在 D1/R2 未配置或初次启动时，任何情况下请求都不为空）
 */
export const DEFAULT_HOME_FEED: HomeFeedData = {
  version: '2.0.0',
  updatedAt: '2026-09-13T01:50:00.000Z',
  items: [
    {
      id: 'block_top_recommend_banner',
      type: 'top_recommend_banner',
      sortOrder: 1,
      visible: true,
      data: {
        id: 'snow_cafe_theme',
        title: '《雪天咖啡館的閱讀鋼琴》',
        subtitle: '窗邊熱咖啡、一本書，慢慢過今天',
        badge: 'TOP 推荐',
        coverUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/home/snow_cafe_static.jpg',
        audioUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/music/theme/snow_cafe_piano.mp3',
        artistName: '放鬆鋼琴 · 慢時光',
        actionType: 'theme',
        actionTarget: 'snow_cafe_theme'
      }
    },
    {
      id: 'block_today_recommend_scroll',
      type: 'today_recommend_scroll',
      sortOrder: 2,
      visible: true,
      data: {
        title: '今日推荐',
        subtitle: "TODAY'S VINYL SELECTION",
        items: [
          {
            id: 'bach_cello_theme',
            title: '巴赫大提琴作品集',
            artist: 'Lu Dimon & Mu Dimon',
            year: '1720 / 2026',
            subtitle: '让巴赫的大提琴安抚浮躁的心',
            coverUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/albums/bach_cello_cover.jpg',
            audioUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/music/theme/bach_cello_collection.mp3',
            isTheme: true,
            themeId: 'bach_cello_theme'
          },
          {
            id: 'jonathan_lee_theme',
            title: '理性與感性',
            artist: '李宗盛',
            year: '2007',
            subtitle: '30首歲月金曲 · 寫盡人世間的悲歡離合',
            coverUrl: 'https://m-api.changgepd.ccwu.cc/storage/covers/albums/album_jonathan_lee.jpg',
            audioUrl: 'https://m-api.changgepd.ccwu.cc/storage/music/theme/jonathan_lee_30.m4a',
            isTheme: true,
            themeId: 'jonathan_lee_theme'
          },
          {
            id: 'lofi_chill_theme',
            title: '忘記時間的旋律',
            artist: 'Lova Radio',
            year: '2026',
            subtitle: 'Lo-fi Chill 溫柔旋律陪你慢慢回血',
            coverUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/albums/lofi_chill_cover.jpg',
            audioUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/music/theme/lofi_chill.mp3',
            isTheme: true,
            themeId: 'lofi_chill_theme'
          },
          {
            id: 'pop_piano_theme',
            title: '華語經典鋼琴曲',
            artist: 'Love Piano',
            year: '2026',
            subtitle: '流行情歌鋼琴改編，只想靜靜聽音樂',
            coverUrl: 'https://m-api.changgepd.ccwu.cc/storage/covers/albums/pop_piano_cover.jpg',
            audioUrl: 'https://m-api.changgepd.ccwu.cc/storage/music/theme/pop_piano.mp3',
            isTheme: true,
            themeId: 'pop_piano_theme'
          }
        ]
      }
    },
    {
      id: 'block_deep_dive_feature',
      type: 'deep_dive_feature',
      sortOrder: 3,
      visible: true,
      data: {
        id: 'butterfly_lovers_deep_dive',
        title: '《梁祝》小提琴协奏曲：东方交响的化蝶史诗',
        tag: '深度名作解析 · DEEP DIVE',
        summary: '以西方交响之弓，引越剧缠绵之韵。何占豪与陈钢笔下的东方绝唱，在草桥结拜、长亭惜别、抗婚哭灵与双双化蝶中，成就半个世纪的传世经典。',
        coverUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/hero/butterfly_lovers_hero_clean.jpg',
        audioUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/music/theme/butterfly_lovers_concerto.mp3',
        articleId: 'butterfly_lovers_deep_dive',
        albumId: 'butterfly_lovers_album',
        albumTitle: '《梁祝》小提琴协奏曲',
        primaryActionText: '阅读深度专题',
        secondaryActionText: '聆听全曲'
      }
    },
    {
      id: 'block_variety_show_grid',
      type: 'variety_show_grid',
      sortOrder: 4,
      visible: true,
      data: {
        title: '音乐综艺精选',
        subtitle: 'POPULAR MUSIC VARIETY',
        items: [
          {
            id: 'variety_voice_of_china',
            title: '中国好声音',
            subtitle: '导师盲选 · 为梦想转身',
            coverUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/variety/voice_of_china.jpg',
            actionType: 'playlist',
            actionTarget: 'voice_of_china'
          },
          {
            id: 'variety_i_am_singer',
            title: '我是歌手',
            subtitle: '殿堂唱将 · 极致交响Live',
            coverUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/variety/i_am_singer.jpg',
            actionType: 'playlist',
            actionTarget: 'i_am_singer'
          },
          {
            id: 'variety_masked_singer',
            title: '蒙面唱将猜猜猜',
            subtitle: '面具之下 · 纯粹原声共鸣',
            coverUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/variety/masked_singer.jpg',
            actionType: 'playlist',
            actionTarget: 'masked_singer'
          },
          {
            id: 'variety_big_band',
            title: '乐队的夏天',
            subtitle: '燥热现场 · 独立原创摇滚',
            coverUrl: 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/variety/big_band.jpg',
            actionType: 'playlist',
            actionTarget: 'big_band'
          }
        ]
      }
    }
  ]
}

/**
 * 资源 URL 归一化函数
 */
function normalizeResourceUrl(path: string | null | undefined, baseUrl: string, type: 'avatar' | 'cover' | 'mp3' | 'lrc'): string {
  if (!path) {
    if (type === 'avatar') return '/src/assets/images/avatars/default.png'
    if (type === 'cover') return '/src/assets/images/vinyl_default.png'
    return ''
  }

  if (path.startsWith('http://') || path.startsWith('https://')) return path
  if (path.startsWith('/src/')) return path

  let finalPath = path
  if (!path.startsWith('/storage/')) {
    finalPath = `/storage/${path.startsWith('/') ? path.slice(1) : path}`
  }

  return baseUrl + finalPath
}

/**
 * 归一化首页切片流中的所有资源链接为完整可用 URL
 */
export function normalizeHomeFeedUrls(feedData: HomeFeedData, baseUrl: string): HomeFeedData {
  const normalizedItems = (feedData.items || []).map((rawBlock) => {
    const block = { ...rawBlock } as HomeBlock

    switch (block.type) {
      case 'top_recommend_banner':
        if (block.data) {
          if (block.data.coverUrl) block.data.coverUrl = normalizeResourceUrl(block.data.coverUrl, baseUrl, 'cover')
          if (block.data.audioUrl) block.data.audioUrl = normalizeResourceUrl(block.data.audioUrl, baseUrl, 'mp3')
        }
        break

      case 'today_recommend_scroll':
        if (block.data && Array.isArray(block.data.items)) {
          block.data.items = block.data.items.map((item: any) => ({
            ...item,
            coverUrl: normalizeResourceUrl(item.coverUrl, baseUrl, 'cover'),
            audioUrl: item.audioUrl ? normalizeResourceUrl(item.audioUrl, baseUrl, 'mp3') : undefined
          }))
        }
        break

      case 'deep_dive_feature':
        if (block.data) {
          if (block.data.coverUrl) block.data.coverUrl = normalizeResourceUrl(block.data.coverUrl, baseUrl, 'cover')
          if (block.data.audioUrl) block.data.audioUrl = normalizeResourceUrl(block.data.audioUrl, baseUrl, 'mp3')
        }
        break

      case 'variety_show_grid':
        if (block.data && Array.isArray(block.data.items)) {
          block.data.items = block.data.items.map((item: any) => ({
            ...item,
            coverUrl: normalizeResourceUrl(item.coverUrl, baseUrl, 'cover')
          }))
        }
        break

      case 'hero_banner':
        if (Array.isArray(block.items)) {
          block.items = block.items.map((item) => ({
            ...item,
            coverUrl: normalizeResourceUrl(item.coverUrl, baseUrl, 'cover')
          }))
        }
        break

      case 'artist_grid':
        if (Array.isArray(block.items)) {
          block.items = block.items.map((item) => ({
            ...item,
            avatarUrl: normalizeResourceUrl(item.avatarUrl, baseUrl, 'avatar')
          }))
        }
        break

      case 'essay_card':
        if (block.coverUrl) {
          block.coverUrl = normalizeResourceUrl(block.coverUrl, baseUrl, 'cover')
        }
        break

      case 'track_list':
        if (Array.isArray(block.items)) {
          block.items = block.items.map((item) => ({
            ...item,
            coverUrl: normalizeResourceUrl(item.coverUrl, baseUrl, 'cover'),
            audioUrl: item.filePath ? normalizeResourceUrl(item.filePath, baseUrl, 'mp3') : undefined
          }))
        }
        break

      case 'album_row':
        if (Array.isArray(block.items)) {
          block.items = block.items.map((item) => ({
            ...item,
            coverUrl: normalizeResourceUrl(item.coverUrl, baseUrl, 'cover')
          }))
        }
        break

      default:
        // Generic block fallback
        if ('coverUrl' in block && typeof block.coverUrl === 'string') {
          block.coverUrl = normalizeResourceUrl(block.coverUrl, baseUrl, 'cover')
        }
        if ('avatarUrl' in block && typeof block.avatarUrl === 'string') {
          block.avatarUrl = normalizeResourceUrl(block.avatarUrl, baseUrl, 'avatar')
        }
        break
    }

    return block
  })

  return {
    version: feedData.version || '1.0.0',
    updatedAt: feedData.updatedAt || new Date().toISOString(),
    items: normalizedItems
  }
}

/**
 * 确保 D1 app_settings 表存在
 */
let _appSettingsTableEnsured = false
async function ensureAppSettingsTable(db: D1Database): Promise<void> {
  if (_appSettingsTableEnsured) return
  _appSettingsTableEnsured = true
  try {
    await db.prepare(`
      CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `).run()
  } catch (e) {
    console.warn('ensureAppSettingsTable notice:', e)
  }
}

/**
 * 校验前端提交的切片数组格式
 */
function validateFeedItems(rawItems: any[]): { valid: boolean; error?: string; items?: HomeBlock[] } {
  if (!Array.isArray(rawItems)) {
    return { valid: false, error: 'items 必须是一个数组' }
  }

  const items: HomeBlock[] = []
  for (let i = 0; i < rawItems.length; i++) {
    const item = rawItems[i]
    if (!item || typeof item !== 'object') {
      return { valid: false, error: `第 ${i + 1} 个切片必须为有效对象` }
    }

    if (!item.id || typeof item.id !== 'string' || !item.id.trim()) {
      return { valid: false, error: `第 ${i + 1} 个切片缺少有效的 id 字段` }
    }

    if (!item.type || typeof item.type !== 'string' || !item.type.trim()) {
      return { valid: false, error: `第 ${i + 1} 个切片缺少有效的 type 字段` }
    }

    // 格式化与填充默认值
    const sanitized: HomeBlock = {
      ...item,
      id: String(item.id).trim(),
      type: String(item.type).trim(),
      sortOrder: typeof item.sortOrder === 'number' ? item.sortOrder : i + 1,
      visible: typeof item.visible === 'boolean' ? item.visible : true
    }

    items.push(sanitized)
  }

  return { valid: true, items }
}

/**
 * 注册首页切片流路由
 */
export function registerHomeFeedRoutes(app: Hono<AppType>) {

  // ==========================================
  // 1. GET /api/home/feed (公开接口：拉取首页切片流)
  // ==========================================
  app.get('/api/home/feed', async (c) => {
    try {
      const baseUrl = new URL(c.req.url).origin
      let loadedFeed: HomeFeedData | null = null

      // 1. 尝试从 D1 app_settings 表读取
      try {
        await ensureAppSettingsTable(c.env.DB)
        const row = await c.env.DB.prepare(
          'SELECT value, updated_at FROM app_settings WHERE key = ?'
        ).bind('home_feed').first<{ value: string; updated_at?: string }>()

        if (row && row.value) {
          const parsed = JSON.parse(row.value) as HomeFeedData
          if (parsed && Array.isArray(parsed.items) && parsed.items.length > 0) {
            loadedFeed = {
              version: parsed.version || '1.0.0',
              updatedAt: parsed.updatedAt || row.updated_at || new Date().toISOString(),
              items: parsed.items
            }
          }
        }
      } catch (d1Err) {
        console.warn('D1 fetch home_feed warning:', d1Err)
      }

      // 2. 若 D1 未读取到，尝试从 R2 备份 (config/home_feed.json) 读取
      if (!loadedFeed && c.env.BUCKET) {
        try {
          const r2Obj = await c.env.BUCKET.get('config/home_feed.json')
          if (r2Obj) {
            const text = await r2Obj.text()
            const parsed = JSON.parse(text) as HomeFeedData
            if (parsed && Array.isArray(parsed.items) && parsed.items.length > 0) {
              loadedFeed = {
                version: parsed.version || '1.0.0',
                updatedAt: parsed.updatedAt || new Date().toISOString(),
                items: parsed.items
              }
            }
          }
        } catch (r2Err) {
          console.warn('R2 fetch home_feed warning:', r2Err)
        }
      }

      // 3. 若均未配置，则回退到内置的高质量默认切片数据
      if (!loadedFeed) {
        loadedFeed = DEFAULT_HOME_FEED
      }

      // 4. 资源 URL 归一化并下发
      const data = normalizeHomeFeedUrls(loadedFeed, baseUrl)

      return c.json({
        code: 200,
        message: 'success',
        data
      })
    } catch (error: any) {
      console.error('Get home feed error:', error)
      return serverError(c, error)
    }
  })

  // ==========================================
  // 2. POST /api/admin/home/feed (管理员/控制台保存首页切片流)
  //    支持 PUT /api/admin/home/feed 同等处理
  // ==========================================
  const handleSaveHomeFeed = async (c: any) => {
    try {
      const body = await c.req.json().catch(() => null)
      if (!body || typeof body !== 'object') {
        return fail(c, 'INVALID_REQUEST_BODY')
      }

      const rawItems = Array.isArray(body) ? body : body.items
      const validation = validateFeedItems(rawItems)
      if (!validation.valid || !validation.items) {
        return fail(c, 'INVALID_PARAMETER', { message: validation.error || '切片数据不合法' })
      }

      const now = new Date().toISOString()
      const version = typeof body.version === 'string' && body.version.trim()
        ? body.version.trim()
        : `v${Date.now()}`

      const feedData: HomeFeedData = {
        version,
        updatedAt: now,
        items: validation.items
      }

      const jsonStr = JSON.stringify(feedData)

      // 1. 保存到 D1 数据库
      await ensureAppSettingsTable(c.env.DB)
      await c.env.DB.prepare(`
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('home_feed', ?, ?)
        ON CONFLICT(key) DO UPDATE SET
          value = excluded.value,
          updated_at = excluded.updated_at
      `).bind(jsonStr, now).run()

      // 2. 同步备份到 R2 存储桶 (config/home_feed.json)
      if (c.env.BUCKET) {
        try {
          await c.env.BUCKET.put('config/home_feed.json', jsonStr, {
            httpMetadata: {
              contentType: 'application/json; charset=utf-8'
            }
          })
        } catch (r2Err) {
          console.warn('R2 backup home_feed warning:', r2Err)
        }
      }

      return c.json({
        code: 200,
        message: 'success',
        data: {
          version: feedData.version,
          updatedAt: feedData.updatedAt,
          count: feedData.items.length
        }
      })
    } catch (error: any) {
      console.error('Save home feed error:', error)
      return serverError(c, error)
    }
  }

  app.post('/api/admin/home/feed', handleSaveHomeFeed)
  app.put('/api/admin/home/feed', handleSaveHomeFeed)

  // ==========================================
  // 3. POST /api/admin/home/feed/reset (重置首页切片流为内置默认)
  //    支持 DELETE /api/admin/home/feed
  // ==========================================
  const handleResetHomeFeed = async (c: any) => {
    try {
      // 1. 从 D1 清理
      await ensureAppSettingsTable(c.env.DB)
      await c.env.DB.prepare('DELETE FROM app_settings WHERE key = ?').bind('home_feed').run()

      // 2. 从 R2 清理
      if (c.env.BUCKET) {
        try {
          await c.env.BUCKET.delete('config/home_feed.json')
        } catch (r2Err) {
          console.warn('R2 delete home_feed warning:', r2Err)
        }
      }

      const baseUrl = new URL(c.req.url).origin
      return c.json({
        code: 200,
        message: '已成功重置首页切片为默认配置',
        data: normalizeHomeFeedUrls(DEFAULT_HOME_FEED, baseUrl)
      })
    } catch (error: any) {
      console.error('Reset home feed error:', error)
      return serverError(c, error)
    }
  }

  app.post('/api/admin/home/feed/reset', handleResetHomeFeed)
  app.delete('/api/admin/home/feed', handleResetHomeFeed)
}
