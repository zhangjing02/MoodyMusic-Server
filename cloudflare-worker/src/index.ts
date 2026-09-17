import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { registerUploadRoutes } from './upload'
import { registerAuthRoutes, authMiddleware, requireAdmin } from './auth'
import { registerPushRoutes } from './push'
import { registerAlbumSocialRoutes } from './album_social'
import { registerHomeFeedRoutes } from './home_feed'
import { registerAppVersionRoutes } from './app_version'
import { registerCommunityRoutes } from './community'
import { registerPlaylistRoutes } from './playlists'
import type { Bindings } from './types'
import { fail, normalizeLegacyErrorResponse, serverError } from './error'

const app = new Hono<{ Bindings: Bindings; Variables: { user: any; token: string } }>()

/**
 * NormalizeTitle 归一化标题（用于繁简体模糊匹配）
 * 移除标点符号及空格，统一小写，简繁体统一，保留英文字母和数字
 */
function normalizeTitle(s: string): string {
  s = s.toLowerCase().trim();

  // 统一各种标点符号（包括中文标点）
  s = s.replace(/[ \t\n\r\-_—·、，,。．；;：:！!？?（）\(\)\[\]【】《》〈⟩]/g, '');

  // 简繁体映射（扩展版）
  const t2sMap: Record<string, string> = {
    // 常用繁体字
    '愛': '爱', '來': '来', '後': '后', '為': '为',
    '與': '与', '時': '时', '開': '开', '無': '无',
    '國': '国', '語': '语', '產': '产', '學': '学',
    '長': '长', '點': '点', '變': '变', '電': '电',
    '動': '动', '聽': '听', '這': '这', '過': '过',
    '寫': '写', '會': '会', '經': '经', '關': '关',
    '們': '们', '傳': '传', '錄': '录', '機': '机',
    '觀': '观', '場': '场', '實': '实', '驗': '验',
    '斷': '断', '種': '种', '類': '类',
    '難': '难', '優': '优', '態': '态', '響': '响',
    '應': '应', '繫': '续', '調': '调', '轉': '转',
    '遙': '遥', '麵': '面', '彎': '弯', '單': '单',
    '願': '愿', '義': '义', '務': '务', '標': '标',
    // 补充常用繁体字
    '遠': '远', '選': '选', '邊': '边', '處': '处',
    '風': '风', '頭': '头', '門': '门', '間': '间',
    '題': '题', '導': '导', '讓': '让', '識': '识',
    '設': '设', '屬': '属', '據': '据', '築': '筑',
    '緊': '紧', '陳': '陈', '蓋': '盖', '舉': '举',
    '壓': '压', '質': '质', '儘': '尽', '護': '护',
    '戲': '戏', '臺': '台', '鄉': '乡', '現': '现',
    '規': '规', '視': '视', '藝': '艺', '價': '价',
    '證': '证', '獨': '独', '劇': '剧',
    '歲': '岁', '備': '备', '敵': '敌'
  };

  let result = '';
  for (const char of s) {
    const code = char.charCodeAt(0);
    // 保留：中文（使用更宽泛的 CJK 范围）、英文字母（a-z）、数字（0-9）
    const isCJK = (code >= 0x4e00 && code <= 0x9fff) || // CJK Unified Ideographs
                   (code >= 0x3400 && code <= 0x4dbf);   // CJK Extension A
    const isEnglish = (code >= 0x0061 && code <= 0x007a); // a-z
    const isDigit = (code >= 0x0030 && code <= 0x0039);   // 0-9

    if (isCJK || isEnglish || isDigit) {
      result += t2sMap[char] || char;
    }
  }
  return result;
}

/**
 * Normalizes resource URLs to be absolute and correctly prefixed
 */
function normalizeResourceUrl(path: string | null | undefined, baseUrl: string, type: 'avatar' | 'cover' | 'mp3' | 'lrc'): string {
  if (!path) {
    if (type === 'avatar') return '/src/assets/images/avatars/default.png';
    if (type === 'cover') return '/src/assets/images/vinyl_default.png';
    return '';
  }

  if (path.startsWith('http')) return path;
  if (path.startsWith('/src/')) return path;

  // Ensure absolute path from Worker origin
  let finalPath = path;
  if (!path.startsWith('/storage/')) {
    // If it's a raw R2 key, prefix with /storage/
    finalPath = `/storage/${path.startsWith('/') ? path.slice(1) : path}`;
  }
  
  return baseUrl + finalPath;
}

// Global CORS for all routes (API and Storage)
app.use('/*', cors({
  origin: '*',
  allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowHeaders: ['Content-Type', 'Authorization'],
}))

app.use('/api/*', async (c, next) => {
  await next()
  c.res = await normalizeLegacyErrorResponse(c.res)
})

app.get('/', (c) => c.text('MOODY API Edge Worker is running!'))

// ==========================================
// Auth Routes（用户认证系统）- 注册在 admin 路由之前
// ==========================================
registerAuthRoutes(app)
registerPushRoutes(app)
registerAlbumSocialRoutes(app, authMiddleware)
registerHomeFeedRoutes(app)
registerAppVersionRoutes(app)
registerCommunityRoutes(app, authMiddleware)
registerPlaylistRoutes(app, authMiddleware)

// ==========================================
// Admin 路由保护（暂时开放，后续按需开启）
// Token 仅用于用户个人功能（评论、收藏、关注等）
// ==========================================
// app.use('/api/admin/*', authMiddleware)
// app.use('/api/admin/*', requireAdmin)

// ==========================================
// 1. Storage Proxy (R2 Direct Access & CDN Cache)
// Equivalent to Go's /storage/* proxy
// ==========================================
app.get('/storage/*', async (c) => {
  const pathPrefix = '/storage/'
  // e.g. /storage/music/Artist/Album/Song.mp3 -> music/Artist/Album/Song.mp3
  const key = decodeURIComponent(c.req.path.slice(pathPrefix.length))

  if (!key) {
    return fail(c, 'STORAGE_OBJECT_KEY_MISSING')
  }

  // ---- 解析客户端 Range 请求头 ----
  const rangeHeader = c.req.header('range')
  let rangeOpts: R2GetOptions | undefined

  if (rangeHeader) {
    // 格式: "bytes=start-end" 或 "bytes=start-"
    const match = rangeHeader.match(/^bytes=(\d+)-(\d*)$/)
    if (match) {
      const offset = parseInt(match[1], 10)
      const endStr = match[2]
      if (endStr) {
        rangeOpts = { range: { offset, length: parseInt(endStr, 10) - offset + 1 } }
      } else {
        rangeOpts = { range: { offset } }
      }
    }
  }

  // ---- 有 Range 请求：直接去 R2 取分片，不走 CDN cache ----
  if (rangeOpts) {
    const object = await c.env.BUCKET.get(key, rangeOpts)
    if (object === null) {
      return fail(c, 'STORAGE_OBJECT_NOT_FOUND')
    }

    const headers = new Headers()
    object.writeHttpMetadata(headers)
    headers.set('etag', object.httpEtag)
    headers.set('Cache-Control', 'public, max-age=2592000')
    headers.set('Accept-Ranges', 'bytes')

    // 构造 Content-Range 响应头
    const fileSize = object.size
    const rangeResult = (object as any).range as { offset?: number; length?: number } | undefined
    const start = rangeResult?.offset ?? 0
    const length = rangeResult?.length ?? fileSize
    const end = start + length - 1
    headers.set('Content-Range', `bytes ${start}-${end}/${fileSize}`)
    headers.set('Content-Length', String(length))

    return new Response(object.body, { status: 206, headers })
  }

  // ---- 无 Range 请求：走 CDN cache 逻辑 ----
  const cacheUrl = new URL(c.req.url)
  const cacheKey = new Request(cacheUrl.toString(), c.req)
  const cache = caches.default

  let response = await cache.match(cacheKey)
  if (response) {
    // 缓存命中时也要声明支持 Range 请求
    const cachedHeaders = new Headers(response.headers)
    cachedHeaders.set('Accept-Ranges', 'bytes')
    return new Response(response.body, { status: response.status, headers: cachedHeaders })
  }

  const object = await c.env.BUCKET.get(key)
  if (object === null) {
    return fail(c, 'STORAGE_OBJECT_NOT_FOUND')
  }

  const headers = new Headers()
  object.writeHttpMetadata(headers)
  headers.set('etag', object.httpEtag)
  // Cache the media objects at the Edge for 30 days
  headers.set('Cache-Control', 'public, max-age=2592000')
  // 声明支持 Range 请求，让浏览器知道可以 seek
  headers.set('Accept-Ranges', 'bytes')

  response = new Response(object.body, { headers })

  // Cache it in the background
  c.executionCtx.waitUntil(cache.put(cacheKey, response.clone()))

  return response
})


// ==========================================
// 2. Welcome Images
// Equivalent to Go's /api/welcome-images
// ==========================================
app.get('/api/welcome-images', async (c) => {
  try {
    const list = await c.env.BUCKET.list({
      prefix: 'welcome_covers/'
    })

    const images = list.objects
      .filter((obj) => obj.key.match(/\.(jpg|jpeg|png|webp|gif)$/i))
      .map((obj) => {
        // Return only the filename as expected by app.js getWelcomeBackground
        return obj.key.split('/').pop() || ''
      })
      .filter(name => name !== '')

    // Shuffle and pick up to 10 images smoothly
    const shuffled = images.sort(() => 0.5 - Math.random())
    const selected = shuffled.slice(0, 10)

    if (selected.length === 0) {
      // Internal fallback
      selected.push('landing_cover.png')
    }

    return c.json({
      code: 200,
      message: 'success',
      data: selected
    })
  } catch (error: any) {
    console.error('Welcome images error:', error)
    return serverError(c, error)
  }
})

// ==========================================
// 3. Artists Skeleton List
// Equivalant to Go's /api/skeleton
// ==========================================
app.get('/api/skeleton', async (c) => {
  try {
    const groupFilter = c.req.query('group')
    // V3.0: Join with albums to get counts
    const query = `
      SELECT 
        a.id, a.name, a.region, a.photo_url,
        COUNT(al.id) as album_count
      FROM artists a
      LEFT JOIN albums al ON a.id = al.artist_id
      GROUP BY a.id, a.name, a.region, a.photo_url
      ORDER BY a.name ASC
    `
    const { results } = await c.env.DB.prepare(query).all()
    const baseUrl = new URL(c.req.url).origin

    let artists = results.map((row: any) => {
      let groupChar = '#'
      if (row.name && row.name.length > 0) {
        groupChar = row.name.charAt(0).toUpperCase()
      }
      
      return {
        id: `db_${row.id}`,
        name: row.name,
        group: groupChar,
        category: row.region || '华语',
        avatar: normalizeResourceUrl(row.photo_url, baseUrl, 'avatar'),
        albumCount: row.album_count || 0
      }
    })

    if (groupFilter) {
      artists = artists.filter(a => a.group.toLowerCase() === groupFilter.toLowerCase())
    }

    c.header('Cache-Control', 'public, s-maxage=3600, stale-while-revalidate=86400')

    return c.json({
      code: 200,
      message: 'success',
      data: { artists }
    })
  } catch (error: any) {
    return serverError(c, error)
  }
})

// ==========================================
// 4. Nested Songs Tree
// Equivalant to Go's /api/songs
// ==========================================
app.get('/api/songs', async (c) => {
  try {
    const queryArtistId = c.req.query('artistId')
    const queryArtistName = c.req.query('artist')
    const queryAlbum = c.req.query('album')

    // Building a base flat query
    let sql = `
      SELECT 
        a.id AS artist_id, a.name AS artist_name, a.region, a.photo_url,
        al.id AS album_id, al.title AS album_title, al.release_date, al.cover_url,
        s.title AS song_title, s.file_path, s.lrc_path, s.track_index
      FROM artists a
      LEFT JOIN albums al ON a.id = al.artist_id
      LEFT JOIN songs s ON al.id = s.album_id
      WHERE 1=1
    `
    const params: any[] = []

    if (queryArtistId) {
      sql += ` AND a.id = ?`
      params.push(queryArtistId.replace('db_', ''))
    } else if (queryArtistName) {
      sql += ` AND a.name LIKE ?`
      params.push(`%${queryArtistName}%`)
    }

    if (queryAlbum) {
      // 先在 SQL 中做粗过滤（大幅减少 D1 行扫描），再在 JS 中做精确繁简体匹配
      sql += ` AND al.title LIKE ?`
      params.push(`%${queryAlbum}%`)
    }

    sql += ` ORDER BY a.name ASC, al.release_date ASC, s.track_index ASC`

    const { results } = await c.env.DB.prepare(sql).bind(...params).all()

    // 如果有专辑查询参数，进行繁简体过滤
    let filteredResults = results as any[]
    if (queryAlbum) {
      const normalizedQuery = normalizeTitle(queryAlbum)
      filteredResults = (results as any[]).filter((row: any) => {
        if (!row.album_title) return false
        const normalizedTitle = normalizeTitle(row.album_title)
        // 匹配规则：完全相等或包含关系
        return normalizedTitle === normalizedQuery ||
               normalizedTitle.includes(normalizedQuery) ||
               normalizedQuery.includes(normalizedTitle)
      })
    } else {
      filteredResults = results as any[]
    }

    // Process flat rows into hierarchical structure
    const artistMap = new Map<number, any>()
    const baseUrl = new URL(c.req.url).origin

    for (const row of filteredResults) {
      if (!row.artist_id) continue

      if (!artistMap.has(row.artist_id)) {
        artistMap.set(row.artist_id, {
          id: `db_${row.artist_id}`,
          name: row.artist_name,
          category: row.region || '华语',
          avatar: normalizeResourceUrl(row.photo_url, baseUrl, 'avatar'),
          group: row.artist_name ? row.artist_name.charAt(0).toUpperCase() : '#',
          albums: new Map<number, any>()
        })
      }

      const artist = artistMap.get(row.artist_id)

      if (row.album_id) {
        if (!artist.albums.has(row.album_id)) {
          artist.albums.set(row.album_id, {
            title: row.album_title,
            year: row.release_date || '未知',
            cover: normalizeResourceUrl(row.cover_url, baseUrl, 'cover'),
            songs: []
          })
        }

        if (row.song_title) {
          const album = artist.albums.get(row.album_id)
          album.songs.push({
            title: row.song_title,
            path: row.file_path,
            lrc_path: row.lrc_path,
            TrackIndex: row.track_index
          })
        }
      }
    }

    // Convert Maps to Arrays
    const library = Array.from(artistMap.values()).map(artist => ({
      ...artist,
      albums: Array.from(artist.albums.values())
    }))

    return c.json({
      code: 200,
      message: 'success',
      data: library
    })
  } catch (error: any) {
    return serverError(c, error)
  }
})

// ==========================================
// 5. Global Search
// Equivalant to Go's /api/search
// ==========================================
app.get('/api/search', async (c) => {
  try {
    const q = c.req.query('q')
    if (!q) {
      return fail(c, 'QUERY_MISSING', {
        message: "missing query parameter 'q'",
        details: { required: ['q'] },
      })
    }
    const likeQuery = `%${q}%`

    const normalizedQ = q.replace(/[()（）\s]/g, '');
    const stmtArtists = c.env.DB.prepare(`
      SELECT 
        id, name, region, photo_url,
        (SELECT COUNT(*) FROM albums WHERE artist_id = artists.id) as album_count
      FROM artists 
      WHERE name LIKE ? OR REPLACE(REPLACE(REPLACE(REPLACE(name, '(', ''), ')', ''), '（', ''), '）', '') LIKE ?
      LIMIT 30
    `).bind(likeQuery, `%${normalizedQ}%`)
    const stmtAlbums = c.env.DB.prepare(`
      SELECT id, title, artist_id as ArtistID, cover_url as CoverURL 
      FROM albums 
      WHERE title LIKE ? OR REPLACE(REPLACE(REPLACE(REPLACE(title, '(', ''), ')', ''), '（', ''), '）', '') LIKE ?
      LIMIT 30
    `).bind(likeQuery, `%${normalizedQ}%`)
    const stmtSongs = c.env.DB.prepare(`
      SELECT id, title, artist_id as ArtistID, album_id as Album_ID, file_path as FilePath 
      FROM songs 
      WHERE title LIKE ? OR REPLACE(REPLACE(REPLACE(REPLACE(title, '(', ''), ')', ''), '（', ''), '）', '') LIKE ?
      LIMIT 30
    `).bind(likeQuery, `%${normalizedQ}%`)

    // Run searches concurrently in D1
    const [resArtists, resAlbums, resSongs] = await c.env.DB.batch([stmtArtists, stmtAlbums, stmtSongs])

    const baseUrl = new URL(c.req.url).origin
    const results = {
      artists: (resArtists.results || []).map((a: any) => ({
        ...a,
        photo_url: normalizeResourceUrl(a.photo_url, baseUrl, 'avatar'),
        albumCount: a.album_count || 0
      })),
      albums: (resAlbums.results || []).map((al: any) => ({
        ...al,
        CoverURL: normalizeResourceUrl(al.CoverURL, baseUrl, 'cover')
      })),
      songs: resSongs.results || []
    }

    return c.json({
      code: 200,
      message: `找到 ${results.artists.length + results.albums.length + results.songs.length} 条相关结果`,
      data: results
    })
  } catch (error: any) {
    return serverError(c, error)
  }
})

// ==========================================
// 6. Debug: List R2 Objects
// ==========================================
app.get('/api/debug/r2', async (c) => {
  try {
    let allMp3s: string[] = []
    let truncated = true
    let cursor: string | undefined = undefined
    let totalObjects = 0

    // Scan up to 5000 objects to get a better picture
    for (let i = 0; i < 5 && truncated; i++) {
        const list = await c.env.BUCKET.list({ limit: 1000, cursor })
        totalObjects += list.objects.length
        
        const mp3s = list.objects
          .filter(obj => obj.key.toLowerCase().endsWith('.mp3'))
          .map(obj => obj.key)
        
        allMp3s = allMp3s.concat(mp3s)
        truncated = list.truncated
        cursor = list.truncated ? list.cursor : undefined
    }

    // Get prefix statistics
    const prefixes = new Map<string, number>()
    allMp3s.forEach(key => {
        const parts = key.split('/')
        if (parts.length > 1) {
            const prefix = parts[0]
            prefixes.set(prefix, (prefixes.get(prefix) || 0) + 1)
        } else {
            prefixes.set('(root)', (prefixes.get('(root)') || 0) + 1)
        }
    })

    return c.json({
      scanned_objects: totalObjects,
      total_mp3_found: allMp3s.length,
      is_truncated: truncated,
      prefixes: Object.fromEntries(prefixes),
      keys: allMp3s
    })
  } catch (error: any) {
    return c.json({ error: error.message }, 500)
  }
})

// ==========================================
// 7. Debug: List D1 Paths
// ==========================================
// ==========================================
// 8. Debug: Full Audit (D1 vs R2)
// ==========================================
app.get('/api/debug/audit', async (c) => {
  try {
    // 1. Get all MP3 keys from R2
    let allR2Keys = new Set<string>()
    let truncated = true
    let cursor: string | undefined = undefined
    
    for (let i = 0; i < 10 && truncated; i++) {
        const list = await c.env.BUCKET.list({ limit: 1000, cursor })
        list.objects.forEach(obj => {
          if (obj.key.toLowerCase().endsWith('.mp3')) {
            allR2Keys.add(obj.key)
          }
        })
        truncated = list.truncated
        cursor = list.truncated ? list.cursor : undefined
    }

    // 2. Get all file_paths from D1
    const { results: songs } = await c.env.DB.prepare('SELECT id, title, file_path FROM songs WHERE file_path IS NOT NULL AND file_path != ""').all()
    
    // 3. Compare
    const audit = (songs as any[]).map(song => {
      const path = song.file_path
      // We know R2 has "music/" prefix
      const expectedKey = path.startsWith('music/') ? path : `music/${path}`
      const exists = allR2Keys.has(expectedKey)
      
      return {
        id: song.id,
        title: song.title,
        db_path: path,
        expected_r2_key: expectedKey,
        found_in_r2: exists
      }
    })

    const summary = {
      total_db_songs_with_path: songs.length,
      total_r2_mp3s: allR2Keys.size,
      matched: audit.filter(a => a.found_in_r2).length,
      missing_in_r2: audit.filter(a => !a.found_in_r2).length,
      sample_matched: audit.filter(a => a.found_in_r2).slice(0, 10),
      sample_missing: audit.filter(a => !a.found_in_r2).slice(0, 20)
    }

    return c.json(summary)
  } catch (error: any) {
    return c.json({ error: error.message }, 500)
  }
})

// ==========================================
// 9. Admin: Stats
// ==========================================
app.get('/api/admin/stats', async (c) => {
  try {
    const stmtArtists = c.env.DB.prepare('SELECT COUNT(*) as count FROM artists')
    const stmtAlbums = c.env.DB.prepare('SELECT COUNT(*) as count FROM albums')
    const stmtSongs = c.env.DB.prepare('SELECT COUNT(*) as count FROM songs')
    
    const [resArtists, resAlbums, resSongs] = await c.env.DB.batch([stmtArtists, stmtAlbums, stmtSongs])
    
    return c.json({
      code: 200,
      message: 'success',
      data: {
        artists: (resArtists.results?.[0] as any)?.count || 0,
        albums: (resAlbums.results?.[0] as any)?.count || 0,
        tracks: (resSongs.results?.[0] as any)?.count || 0
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 10. Admin: Self-healing Fix Paths
// ==========================================
app.post('/api/admin/fix-paths', async (c) => {
  try {
    const result = await c.env.DB.prepare(`
      UPDATE songs 
      SET file_path = 'music/' || file_path 
      WHERE file_path NOT LIKE 'music/%' 
      AND file_path IS NOT NULL 
      AND file_path != ''
    `).run()
    
    return c.json({
      code: 200,
      message: `成功对齐 ${result.meta.changes} 条音频路径前缀`,
      meta: result.meta
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 11. Admin: Cleanup Duplicates
// ==========================================
app.post('/api/admin/cleanup-duplicates', async (c) => {
  try {
    // Identify duplicate albums (same artist_id and title)
    // We want to keep the one that has more songs with paths
    const query = `
      SELECT a.id, a.artist_id, a.title, COUNT(s.id) as song_count
      FROM albums a
      LEFT JOIN songs s ON a.id = s.album_id AND s.file_path IS NOT NULL AND s.file_path != ''
      GROUP BY a.id, a.artist_id, a.title
    `
    const { results } = await c.env.DB.prepare(query).all()
    
    const albumGroups = new Map<string, any[]>()
    for (const row of results as any[]) {
      const key = `${row.artist_id}|${row.title}`
      if (!albumGroups.has(key)) albumGroups.set(key, [])
      albumGroups.get(key)!.push(row)
    }
    
    let deletedAlbums = 0
    let deletedSongs = 0
    const stmts: D1PreparedStatement[] = []
    
    for (const [key, group] of albumGroups.entries()) {
      if (group.length > 1) {
        // Sort by song_count descending
        group.sort((a, b) => b.song_count - a.song_count)
        
        // Keep the first one (most lit-up), delete others
        const toKeep = group[0].id
        const toDeleteIds = group.slice(1).map(a => a.id)
        
        for (const id of toDeleteIds) {
          stmts.push(c.env.DB.prepare('DELETE FROM songs WHERE album_id = ?').bind(id))
          stmts.push(c.env.DB.prepare('DELETE FROM albums WHERE id = ?').bind(id))
          deletedAlbums++
        }
      }
    }
    
    if (stmts.length > 0) {
      await c.env.DB.batch(stmts)
    }
    
    return c.json({
      code: 200,
      message: `清理完成：回收了 ${deletedAlbums} 个冗余专辑占位符`,
      data: { deletedAlbums }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 12. Admin: Move Songs to Album
// ==========================================
app.post('/api/admin/songs/move', async (c) => {
  try {
    const { targetAlbumId, songIds, songIdRange } = await c.req.json() as {
      targetAlbumId: number,
      songIds?: number[],
      songIdRange?: [number, number]
    }

    if (!targetAlbumId) {
      return c.json({ code: 400, message: 'Missing targetAlbumId' }, 400)
    }

    let query = 'UPDATE songs SET album_id = ? WHERE '
    const params: any[] = [targetAlbumId]

    if (songIds && songIds.length > 0) {
      query += `id IN (${songIds.map(() => '?').join(',')})`
      params.push(...songIds)
    } else if (songIdRange && songIdRange.length === 2) {
      query += 'id BETWEEN ? AND ?'
      params.push(songIdRange[0], songIdRange[1])
    } else {
      return c.json({ code: 400, message: 'Missing songIds or songIdRange' }, 400)
    }

    const result = await c.env.DB.prepare(query).bind(...params).run()

    return c.json({
      code: 200,
      message: `成功移动 ${result.meta.changes} 首歌曲到专辑 ${targetAlbumId}`,
      meta: result.meta
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 13. Admin: Merge Albums
// ==========================================
app.post('/api/admin/albums/merge', async (c) => {
  try {
    const { sourceId, targetId } = await c.req.json() as { sourceId: number, targetId: number }

    if (!sourceId || !targetId) {
      return c.json({ code: 400, message: 'Missing sourceId or targetId' }, 400)
    }

    // Move all songs from source to target
    const moveSongs = c.env.DB.prepare('UPDATE songs SET album_id = ? WHERE album_id = ?').bind(targetId, sourceId)
    // Delete source album
    const deleteAlbum = c.env.DB.prepare('DELETE FROM albums WHERE id = ?').bind(sourceId)

    const results = await c.env.DB.batch([moveSongs, deleteAlbum])

    return c.json({
      code: 200,
      message: `成功将专辑 ${sourceId} 合并至 ${targetId}`,
      data: {
        songsMoved: results[0].meta.changes
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 14. Admin: Update Album Info
// ==========================================
app.patch('/api/admin/albums/:id', async (c) => {
  try {
    const id = c.req.param('id')
    const body = await c.req.json()
    const allowedFields = ['title', 'release_date', 'cover_url', 'artist_id']
    
    const updates = Object.keys(body)
      .filter(k => allowedFields.includes(k))
      .map(k => `${k} = ?`)
    
    if (updates.length === 0) {
      return c.json({ code: 400, message: 'No valid fields provided' }, 400)
    }

    const query = `UPDATE albums SET ${updates.join(', ')} WHERE id = ?`
    const params = Object.keys(body)
      .filter(k => allowedFields.includes(k))
      .map(k => body[k])
    params.push(id)

    const result = await c.env.DB.prepare(query).bind(...params).run()

    return c.json({
      code: 200,
      message: `成功更新专辑 ${id}`,
      meta: result.meta
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 15. Admin: Batch Update Songs
// ==========================================
app.post('/api/admin/songs/batch-update', async (c) => {
  try {
    const { updates } = await c.req.json() as {
      updates: Array<{ id: number, title?: string, track_index?: number, album_id?: number }>
    }

    if (!updates || !updates.length) {
      return c.json({ code: 400, message: 'Missing updates' }, 400)
    }

    const stmts: D1PreparedStatement[] = []
    for (const item of updates) {
      if (!item.id) continue

      const setClauses: string[] = []
      const params: any[] = []

      if (item.title !== undefined) {
        setClauses.push('title = ?')
        params.push(item.title)
      }
      if (item.track_index !== undefined) {
        setClauses.push('track_index = ?')
        params.push(item.track_index)
      }
      if (item.album_id !== undefined) {
        setClauses.push('album_id = ?')
        params.push(item.album_id)
      }

      if (setClauses.length > 0) {
        params.push(item.id)
        stmts.push(c.env.DB.prepare(`UPDATE songs SET ${setClauses.join(', ')} WHERE id = ?`).bind(...params))
      }
    }

    if (stmts.length === 0) {
      return c.json({ code: 400, message: 'No valid updates found' }, 400)
    }

    await c.env.DB.batch(stmts)

    return c.json({
      code: 200,
      message: `成功批量更新 ${stmts.length} 条歌曲信息`
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 16. Admin: Create Full Song Metadata (Artist + Album + Song)
// [CRITICAL FIX] 用于 Go 后端上传后同步数据到 D1
// ==========================================
app.post('/api/admin/songs/create-full', async (c) => {
  try {
    const { songs } = await c.req.json() as {
      songs: Array<{
        title: string
        artist_name: string
        album_title: string
        file_path: string
        lrc_path?: string
        track_index?: number
        duration?: number
      }>
    }

    if (!songs || !songs.length) {
      return c.json({ code: 400, message: 'Missing songs array' }, 400)
    }

    const stmts: D1PreparedStatement[] = []
    const createdArtists = new Map<string, number>()
    const createdAlbums = new Map<string, number>()
    const createdSongs: number[] = []

    for (const song of songs) {
      // 1. 查找或创建艺人
      let artistId: number
      const artistKey = song.artist_name

      if (createdArtists.has(artistKey)) {
        artistId = createdArtists.get(artistKey)!
      } else {
        const { results: artistResults } = await c.env.DB.prepare('SELECT id FROM artists WHERE name = ?').bind(song.artist_name).all()
        if (artistResults.length > 0) {
          artistId = (artistResults[0] as any).id
        } else {
          // 创建新艺人
          const artistResult = await c.env.DB.prepare('INSERT INTO artists (name, region) VALUES (?, ?)').bind(song.artist_name, '华语').run()
          artistId = artistResult.meta.last_row_id
        }
        createdArtists.set(artistKey, artistId)
      }

      // 2. 查找或创建专辑
      let albumId: number
      const albumKey = `${artistId}-${song.album_title}`

      if (createdAlbums.has(albumKey)) {
        albumId = createdAlbums.get(albumKey)!
      } else {
        const { results: albumResults } = await c.env.DB.prepare('SELECT id FROM albums WHERE artist_id = ? AND title = ?').bind(artistId, song.album_title).all()
        if (albumResults.length > 0) {
          albumId = (albumResults[0] as any).id
        } else {
          // 创建新专辑
          const albumResult = await c.env.DB.prepare('INSERT INTO albums (artist_id, title) VALUES (?, ?)').bind(artistId, song.album_title).run()
          albumId = albumResult.meta.last_row_id
        }
        createdAlbums.set(albumKey, albumId)
      }

      // 3. 创建歌曲记录
      const songResult = await c.env.DB.prepare(
        'INSERT INTO songs (title, album_id, file_path, lrc_path, track_index) VALUES (?, ?, ?, ?, ?)'
      ).bind(
        song.title,
        albumId,
        song.file_path,
        song.lrc_path || null,
        song.track_index || null
      ).run()

      createdSongs.push(songResult.meta.last_row_id)
    }

    return c.json({
      code: 200,
      message: `成功创建 ${createdSongs.length} 首歌曲（艺人: ${createdArtists.size}, 专辑: ${createdAlbums.size}）`,
      data: {
        created_songs: createdSongs.length,
        created_artists: createdArtists.size,
        created_albums: createdAlbums.size,
        song_ids: createdSongs
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 17. Admin: Debug Song by ID
// 调试：查询指定 ID 的歌曲详细信息
// ==========================================
app.get('/api/admin/songs/debug', async (c) => {
  try {
    const id = c.req.query('id')
    if (!id) {
      return c.json({ code: 400, message: 'Missing id parameter' }, 400)
    }

    const song = await c.env.DB.prepare(
      'SELECT id, title, file_path, track_index, album_id FROM songs WHERE id = ?'
    ).bind(id).first()

    if (!song) {
      return c.json({ code: 404, message: 'Song not found' }, 404)
    }

    return c.json({
      code: 200,
      message: 'success',
      data: song
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 17.3 Admin: Fix Jacky Smile Album
// 智能修复张学友 Smile 专辑的乱码标题
// ==========================================
app.post('/api/admin/fix-jacky-smile', async (c) => {
  try {
    // 正确的曲目列表（从参考数据获取）
    const correctSongs = [
      { id: 27661, title: '轻抚你的脸', track_index: 1 },
      { id: 27657, title: '爱的卡帮', track_index: 2 },
      { id: 27663, title: '丝丝记忆', track_index: 3 },
      { id: 27660, title: '局外人', track_index: 4 },
      { id: 27658, title: '怀抱的您', track_index: 5 },
      { id: 27664, title: '甜梦', track_index: 6 },
      { id: 27662, title: '情已逝', track_index: 7 },
      { id: 27666, title: '造梦者', track_index: 8 },
      { id: 27665, title: '温柔', track_index: 9 },
      { id: 27659, title: '交叉算了', track_index: 10 },
      { id: 27656, title: 'Smile Again 玛莉亚', track_index: 11 },
    ]

    const stmts: D1PreparedStatement[] = []

    for (const song of correctSongs) {
      // 使用 UPDATE OR REPLACE 确保数据真正被更新
      stmts.push(
        c.env.DB.prepare(
          'UPDATE songs SET title = ?, track_index = ? WHERE id = ?'
        ).bind(song.title, song.track_index, song.id)
      )
    }

    await c.env.DB.batch(stmts)

    // 验证更新结果
    const verification = await c.env.DB.prepare(
      'SELECT id, title, track_index FROM songs WHERE album_id = 1562 ORDER BY track_index'
    ).all()

    return c.json({
      code: 200,
      message: `修复完成：更新了 ${correctSongs.length} 首歌曲`,
      data: {
        updated_count: correctSongs.length,
        verification: verification.results
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message, stack: error.stack }, 500)
  }
})

// ==========================================
// 17.4 Admin: Get Album Details with Songs
// 获取专辑详情（包含艺人信息和歌曲列表）
// ==========================================
app.get('/api/admin/albums/detail', async (c) => {
  try {
    const album_id = c.req.query('album_id')
    if (!album_id) {
      return c.json({ code: 400, message: 'Missing album_id parameter' }, 400)
    }

    // 查询专辑信息
    const album = await c.env.DB.prepare(
      'SELECT id, title, artist_id, release_date, cover_url FROM albums WHERE id = ?'
    ).bind(album_id).first()

    if (!album) {
      return c.json({ code: 404, message: 'Album not found' }, 404)
    }

    // 查询艺人信息
    const artist = await c.env.DB.prepare(
      'SELECT id, name, region FROM artists WHERE id = ?'
    ).bind((album as any).artist_id).first()

    // 查询歌曲列表
    const songs = await c.env.DB.prepare(
      'SELECT id, title, file_path, lrc_path, track_index, storage_id FROM songs WHERE album_id = ? ORDER BY track_index, id'
    ).bind(album_id).all()

    return c.json({
      code: 200,
      message: 'success',
      data: {
        album: album,
        artist: artist,
        songs: songs.results,
        song_count: songs.results.length
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 17.5 Admin: Delete All Songs in Album
// 删除专辑下所有歌曲（保留专辑本身）
// ==========================================
app.post('/api/admin/songs/delete-all', async (c) => {
  try {
    const { album_id } = await c.req.json() as { album_id?: number }

    if (!album_id) {
      return c.json({ code: 400, message: 'Missing album_id parameter' }, 400)
    }

    // 先统计歌曲数量
    const countResult = await c.env.DB.prepare(
      'SELECT COUNT(*) as count FROM songs WHERE album_id = ?'
    ).bind(album_id).first<{ count: number }>()

    const count = countResult?.count || 0

    // 删除所有歌曲
    const deleteResult = await c.env.DB.prepare(
      'DELETE FROM songs WHERE album_id = ?'
    ).bind(album_id).run()

    return c.json({
      code: 200,
      message: `成功删除专辑 ${album_id} 下的 ${deleteResult.meta.changes} 首歌曲`,
      data: {
        album_id: album_id,
        deleted_count: deleteResult.meta.changes
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 17.6 Admin: Batch Insert Songs to Album
// 批量插入歌曲到指定专辑
// ==========================================
app.post('/api/admin/songs/batch-insert', async (c) => {
  try {
    const { album_id, songs } = await c.req.json() as {
      album_id?: number
      songs?: Array<{
        title: string
        file_path?: string
        lrc_path?: string
        track_index?: number
        storage_id?: string
      }>
    }

    if (!album_id) {
      return c.json({ code: 400, message: 'Missing album_id parameter' }, 400)
    }

    if (!songs || !songs.length) {
      return c.json({ code: 400, message: 'Missing songs array' }, 400)
    }

    // 验证专辑存在
    const album = await c.env.DB.prepare(
      'SELECT id FROM albums WHERE id = ?'
    ).bind(album_id).first()

    if (!album) {
      return c.json({ code: 404, message: 'Album not found' }, 404)
    }

    const stmts: D1PreparedStatement[] = []
    const insertedIds: number[] = []

    for (const song of songs) {
      const stmt = c.env.DB.prepare(
        'INSERT INTO songs (title, file_path, lrc_path, album_id, storage_id, track_index) VALUES (?, ?, ?, ?, ?, ?)'
      ).bind(
        song.title,
        song.file_path || null,
        song.lrc_path || null,
        album_id,
        song.storage_id || 'primary',
        song.track_index || 0
      )
      stmts.push(stmt)

      // 为了获取插入的 ID，我们需要逐个执行
      const result = await stmt.run()
      insertedIds.push(result.meta.last_row_id)
    }

    return c.json({
      code: 200,
      message: `成功插入 ${insertedIds.length} 首歌曲`,
      data: {
        album_id: album_id,
        inserted_count: insertedIds.length,
        song_ids: insertedIds
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 17.7 Admin: Search Albums by Name
// 搜索专辑（支持模糊搜索）
// ==========================================
app.get('/api/admin/albums/search', async (c) => {
  try {
    const keyword = c.req.query('keyword')
    const artist_id = c.req.query('artist_id')
    const limit = c.req.query('limit') || '20'

    if (!keyword && !artist_id) {
      return c.json({ code: 400, message: 'Missing keyword or artist_id parameter' }, 400)
    }

    let query = `
      SELECT a.id, a.title, a.artist_id, a.release_date, a.cover_url,
             ar.name as artist_name,
             COUNT(s.id) as song_count
      FROM albums a
      LEFT JOIN artists ar ON a.artist_id = ar.id
      LEFT JOIN songs s ON a.id = s.album_id
      WHERE 1=1
    `
    const params: any[] = []

    if (keyword) {
      query += ' AND a.title LIKE ?'
      params.push(`%${keyword}%`)
    }

    if (artist_id) {
      query += ' AND a.artist_id = ?'
      params.push(artist_id)
    }

    query += ` GROUP BY a.id ORDER BY ar.name, a.title LIMIT ?`
    params.push(parseInt(limit))

    const albums = await c.env.DB.prepare(query).bind(...params).all()

    return c.json({
      code: 200,
      message: 'success',
      data: {
        count: albums.results.length,
        albums: albums.results
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 17.8 Admin: Delete Album (with all songs)
// 删除专辑及其所有歌曲
// ==========================================
app.post('/api/admin/albums/delete', async (c) => {
  try {
    const { album_id } = await c.req.json() as { album_id?: number }

    if (!album_id) {
      return c.json({ code: 400, message: 'Missing album_id parameter' }, 400)
    }

    // 先统计歌曲数量
    const songsResult = await c.env.DB.prepare(
      'SELECT COUNT(*) as count FROM songs WHERE album_id = ?'
    ).bind(album_id).first<{ count: number }>()

    const songCount = songsResult?.count || 0

    // 删除所有歌曲
    await c.env.DB.prepare('DELETE FROM songs WHERE album_id = ?').bind(album_id).run()

    // 删除专辑
    const albumResult = await c.env.DB.prepare('DELETE FROM albums WHERE id = ?').bind(album_id).run()

    if (albumResult.meta.changes === 0) {
      return c.json({ code: 404, message: 'Album not found' }, 404)
    }

    return c.json({
      code: 200,
      message: `成功删除专辑及其 ${songCount} 首歌曲`,
      data: {
        album_id: album_id,
        deleted_songs: songCount
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 17.1 Admin: Test Single Update
// 测试：单条更新并返回详细信息
// ==========================================
app.post('/api/admin/songs/test-update', async (c) => {
  try {
    const { id, title, track_index } = await c.req.json() as {
      id?: number, title?: string, track_index?: number
    }

    if (!id) {
      return c.json({ code: 400, message: 'Missing id parameter' }, 400)
    }

    // 先查询当前值
    const before = await c.env.DB.prepare(
      'SELECT id, title, file_path, track_index, album_id FROM songs WHERE id = ?'
    ).bind(id).first()

    if (!before) {
      return c.json({ code: 404, message: 'Song not found' }, 404)
    }

    // 执行更新
    const setClauses: string[] = []
    const params: any[] = []

    if (title !== undefined) {
      setClauses.push('title = ?')
      params.push(title)
    }
    if (track_index !== undefined) {
      setClauses.push('track_index = ?')
      params.push(track_index)
    }

    if (setClauses.length === 0) {
      return c.json({ code: 400, message: 'No fields to update' }, 400)
    }

    params.push(id)
    const updateResult = await c.env.DB.prepare(
      `UPDATE songs SET ${setClauses.join(', ')} WHERE id = ?`
    ).bind(...params).run()

    // 查询更新后的值
    const after = await c.env.DB.prepare(
      'SELECT id, title, file_path, track_index, album_id FROM songs WHERE id = ?'
    ).bind(id).first()

    return c.json({
      code: 200,
      message: 'Update completed',
      data: {
        update_success: updateResult.meta.changes > 0,
        rows_changed: updateResult.meta.changes,
        before: before,
        after: after
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message, stack: error.stack }, 500)
  }
})

// ==========================================
// 18. Admin: Cleanup Songs Without Path
// 清理指定专辑中没有 file_path 的歌曲记录
// ==========================================
app.post('/api/admin/songs/cleanup-no-path', async (c) => {
  try {
    const { album_id } = await c.req.json() as { album_id?: number }

    if (!album_id) {
      return c.json({ code: 400, message: 'Missing album_id parameter' }, 400)
    }

    // 删除指定专辑中没有 path 的歌曲
    const deleteStmt = await c.env.DB.prepare(`
      DELETE FROM songs
      WHERE album_id = ?
      AND (file_path IS NULL OR file_path = '' OR file_path = 'music/')
    `).bind(album_id).run()

    return c.json({
      code: 200,
      message: `清理完成：删除了 ${deleteStmt.meta.changes} 条无 path 的歌曲记录`,
      data: {
        deleted_count: deleteStmt.meta.changes,
        album_id: album_id
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 19. Operations-Friendly APIs (运营友好接口)
// 这些接口使用名称而非 ID，方便运营人员使用
// ==========================================

// ==========================================
// 19.1 批量更新歌曲（按名称）
// ==========================================
app.post('/api/admin/ops/songs/batch-update', async (c) => {
  try {
    const { artist_name, album_title, updates, dry_run = false } = await c.req.json() as {
      artist_name?: string
      album_title?: string
      updates?: Array<{ old_title: string, new_title: string, track_index?: number }>
      dry_run?: boolean
    }

    if (!artist_name || !album_title) {
      return c.json({ code: 400, message: '缺少 artist_name 或 album_title 参数' }, 400)
    }

    if (!updates || !updates.length) {
      return c.json({ code: 400, message: '缺少 updates 数组' }, 400)
    }

    // 1. 查找艺人（模糊匹配）
    const artistResult = await c.env.DB.prepare(
      'SELECT id, name FROM artists WHERE name LIKE ?'
    ).bind(`%${artist_name}%`).all()

    if (!artistResult.results.length) {
      return c.json({ code: 404, message: `未找到艺人: ${artist_name}` }, 404)
    }

    const artist = artistResult.results[0] as any

    // 2. 查找专辑（模糊匹配）
    const albumResult = await c.env.DB.prepare(
      'SELECT id, title FROM albums WHERE artist_id = ? AND title LIKE ?'
    ).bind(artist.id, `%${album_title}%`).all()

    if (!albumResult.results.length) {
      return c.json({ code: 404, message: `未找到专辑: ${album_title} (艺人: ${artist.name})` }, 404)
    }

    const album = albumResult.results[0] as any

    // 3. 查找并更新歌曲
    const stmts: D1PreparedStatement[] = []
    const results: any[] = []

    for (const update of updates) {
      const { old_title, new_title, track_index } = update

      // 查找歌曲
      const songResult = await c.env.DB.prepare(
        'SELECT id, title, track_index FROM songs WHERE album_id = ? AND title LIKE ?'
      ).bind(album.id, `%${old_title}%`).all()

      if (!songResult.results.length) {
        results.push({
          old_title,
          status: 'not_found',
          message: `未找到歌曲: ${old_title}`
        })
        continue
      }

      const song = songResult.results[0] as any

      if (dry_run) {
        results.push({
          old_title: song.title,
          new_title,
          track_index: track_index || song.track_index,
          status: 'preview',
          message: `[预览] 将更新: ${song.title} → ${new_title}`
        })
      } else {
        stmts.push(c.env.DB.prepare(
          'UPDATE songs SET title = ?, track_index = ? WHERE id = ?'
        ).bind(new_title, track_index || song.track_index, song.id))

        results.push({
          old_title: song.title,
          new_title,
          status: 'updated',
          message: `已更新: ${song.title} → ${new_title}`
        })
      }
    }

    if (!dry_run && stmts.length > 0) {
      await c.env.DB.batch(stmts)
    }

    return c.json({
      code: 200,
      message: dry_run ? '预览完成' : `成功更新 ${stmts.length} 首歌曲`,
      data: {
        artist: { id: artist.id, name: artist.name },
        album: { id: album.id, title: album.title },
        dry_run,
        results
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 19.2 重命名专辑
// ==========================================
app.post('/api/admin/ops/albums/rename', async (c) => {
  try {
    const { artist_name, old_title, new_title, dry_run = false } = await c.req.json() as {
      artist_name?: string
      old_title?: string
      new_title?: string
      dry_run?: boolean
    }

    if (!artist_name || !old_title || !new_title) {
      return c.json({ code: 400, message: '缺少必要参数: artist_name, old_title, new_title' }, 400)
    }

    // 1. 查找艺人
    const artistResult = await c.env.DB.prepare(
      'SELECT id, name FROM artists WHERE name LIKE ?'
    ).bind(`%${artist_name}%`).first()

    if (!artistResult) {
      return c.json({ code: 404, message: `未找到艺人: ${artist_name}` }, 404)
    }

    // 2. 查找专辑
    const albumResult = await c.env.DB.prepare(
      'SELECT id, title FROM albums WHERE artist_id = ? AND title LIKE ?'
    ).bind((artistResult as any).id, `%${old_title}%`).first()

    if (!albumResult) {
      return c.json({ code: 404, message: `未找到专辑: ${old_title}` }, 404)
    }

    if (dry_run) {
      return c.json({
        code: 200,
        message: '预览完成',
        data: {
          artist: artistResult,
          album: albumResult,
          new_title,
          action: `[预览] 将把专辑 "${(albumResult as any).title}" 重命名为 "${new_title}"`
        }
      })
    }

    // 3. 执行重命名
    await c.env.DB.prepare(
      'UPDATE albums SET title = ? WHERE id = ?'
    ).bind(new_title, (albumResult as any).id).run()

    return c.json({
      code: 200,
      message: `成功将专辑 "${(albumResult as any).title}" 重命名为 "${new_title}"`,
      data: {
        artist: artistResult,
        old_album: albumResult,
        new_title
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 19.3 重命名艺人
// ==========================================
app.post('/api/admin/ops/artists/rename', async (c) => {
  try {
    const { old_name, new_name, dry_run = false } = await c.req.json() as {
      old_name?: string
      new_name?: string
      dry_run?: boolean
    }

    if (!old_name || !new_name) {
      return c.json({ code: 400, message: '缺少必要参数: old_name, new_name' }, 400)
    }

    // 1. 查找艺人
    const artistResult = await c.env.DB.prepare(
      'SELECT id, name FROM artists WHERE name LIKE ?'
    ).bind(`%${old_name}%`).first()

    if (!artistResult) {
      return c.json({ code: 404, message: `未找到艺人: ${old_name}` }, 404)
    }

    if (dry_run) {
      return c.json({
        code: 200,
        message: '预览完成',
        data: {
          artist: artistResult,
          new_name,
          action: `[预览] 将把艺人 "${(artistResult as any).name}" 重命名为 "${new_name}"`
        }
      })
    }

    // 2. 执行重命名
    await c.env.DB.prepare(
      'UPDATE artists SET name = ? WHERE id = ?'
    ).bind(new_name, (artistResult as any).id).run()

    return c.json({
      code: 200,
      message: `成功将艺人 "${(artistResult as any).name}" 重命名为 "${new_name}"`,
      data: {
        old_artist: artistResult,
        new_name
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 19.4 合并专辑（按名称）
// ==========================================
app.post('/api/admin/ops/albums/merge', async (c) => {
  try {
    const { artist_name, source_album_title, target_album_title, dry_run = false } = await c.req.json() as {
      artist_name?: string
      source_album_title?: string
      target_album_title?: string
      dry_run?: boolean
    }

    if (!artist_name || !source_album_title || !target_album_title) {
      return c.json({ code: 400, message: '缺少必要参数: artist_name, source_album_title, target_album_title' }, 400)
    }

    // 1. 查找艺人
    const artistResult = await c.env.DB.prepare(
      'SELECT id, name FROM artists WHERE name LIKE ?'
    ).bind(`%${artist_name}%`).first()

    if (!artistResult) {
      return c.json({ code: 404, message: `未找到艺人: ${artist_name}` }, 404)
    }

    // 2. 查找源专辑和目标专辑
    const sourceResult = await c.env.DB.prepare(
      'SELECT id, title FROM albums WHERE artist_id = ? AND title LIKE ?'
    ).bind((artistResult as any).id, `%${source_album_title}%`).first()

    const targetResult = await c.env.DB.prepare(
      'SELECT id, title FROM albums WHERE artist_id = ? AND title LIKE ?'
    ).bind((artistResult as any).id, `%${target_album_title}%`).first()

    if (!sourceResult) {
      return c.json({ code: 404, message: `未找到源专辑: ${source_album_title}` }, 404)
    }

    if (!targetResult) {
      return c.json({ code: 404, message: `未找到目标专辑: ${target_album_title}` }, 404)
    }

    if ((sourceResult as any).id === (targetResult as any).id) {
      return c.json({ code: 400, message: '源专辑和目标专辑不能相同' }, 400)
    }

    // 3. 统计歌曲数量
    const songCountResult = await c.env.DB.prepare(
      'SELECT COUNT(*) as count FROM songs WHERE album_id = ?'
    ).bind((sourceResult as any).id).first<{ count: number }>()

    const songCount = songCountResult?.count || 0

    if (dry_run) {
      return c.json({
        code: 200,
        message: '预览完成',
        data: {
          artist: artistResult,
          source_album: sourceResult,
          target_album: targetResult,
          songs_to_move: songCount,
          action: `[预览] 将把 ${songCount} 首歌曲从 "${(sourceResult as any).title}" 移动到 "${(targetResult as any).title}"，然后删除源专辑`
        }
      })
    }

    // 4. 执行合并
    await c.env.DB.batch([
      c.env.DB.prepare('UPDATE songs SET album_id = ? WHERE album_id = ?').bind((targetResult as any).id, (sourceResult as any).id),
      c.env.DB.prepare('DELETE FROM albums WHERE id = ?').bind((sourceResult as any).id)
    ])

    return c.json({
      code: 200,
      message: `成功将 ${songCount} 首歌曲从 "${(sourceResult as any).title}" 合并到 "${(targetResult as any).title}"`,
      data: {
        artist: artistResult,
        source_album: sourceResult,
        target_album: targetResult,
        songs_moved: songCount
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 19.5 删除专辑（按名称）
// ==========================================
app.post('/api/admin/ops/albums/delete', async (c) => {
  try {
    const { artist_name, album_title, dry_run = false } = await c.req.json() as {
      artist_name?: string
      album_title?: string
      dry_run?: boolean
    }

    if (!artist_name || !album_title) {
      return c.json({ code: 400, message: '缺少必要参数: artist_name, album_title' }, 400)
    }

    // 1. 查找艺人
    const artistResult = await c.env.DB.prepare(
      'SELECT id, name FROM artists WHERE name LIKE ?'
    ).bind(`%${artist_name}%`).first()

    if (!artistResult) {
      return c.json({ code: 404, message: `未找到艺人: ${artist_name}` }, 404)
    }

    // 2. 查找专辑
    const albumResult = await c.env.DB.prepare(
      'SELECT id, title FROM albums WHERE artist_id = ? AND title LIKE ?'
    ).bind((artistResult as any).id, `%${album_title}%`).first()

    if (!albumResult) {
      return c.json({ code: 404, message: `未找到专辑: ${album_title}` }, 404)
    }

    // 3. 统计歌曲数量
    const songCountResult = await c.env.DB.prepare(
      'SELECT COUNT(*) as count FROM songs WHERE album_id = ?'
    ).bind((albumResult as any).id).first<{ count: number }>()

    const songCount = songCountResult?.count || 0

    if (dry_run) {
      return c.json({
        code: 200,
        message: '预览完成',
        data: {
          artist: artistResult,
          album: albumResult,
          songs_to_delete: songCount,
          action: `[预览] 将删除专辑 "${(albumResult as any).title}" 及其 ${songCount} 首歌曲`
        }
      })
    }

    // 4. 执行删除
    await c.env.DB.batch([
      c.env.DB.prepare('DELETE FROM songs WHERE album_id = ?').bind((albumResult as any).id),
      c.env.DB.prepare('DELETE FROM albums WHERE id = ?').bind((albumResult as any).id)
    ])

    return c.json({
      code: 200,
      message: `成功删除专辑 "${(albumResult as any).title}" 及其 ${songCount} 首歌曲`,
      data: {
        artist: artistResult,
        deleted_album: albumResult,
        deleted_songs: songCount
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 19.6 批量插入歌曲（按名称）
// ==========================================
app.post('/api/admin/ops/songs/batch-insert', async (c) => {
  try {
    const { artist_name, album_title, songs, dry_run = false } = await c.req.json() as {
      artist_name?: string
      album_title?: string
      songs?: Array<{ title: string, file_path?: string, track_index?: number }>
      dry_run?: boolean
    }

    if (!artist_name || !album_title) {
      return c.json({ code: 400, message: '缺少 artist_name 或 album_title 参数' }, 400)
    }

    if (!songs || !songs.length) {
      return c.json({ code: 400, message: '缺少 songs 数组' }, 400)
    }

    // 1. 查找或创建艺人
    let artistId: number
    const artistLookup = await c.env.DB.prepare(
      'SELECT id FROM artists WHERE name LIKE ?'
    ).bind(`%${artist_name}%`).first()

    if (artistLookup) {
      artistId = (artistLookup as any).id
    } else {
      const newArtist = await c.env.DB.prepare(
        'INSERT INTO artists (name, region) VALUES (?, ?)'
      ).bind(artist_name, '华语').run()
      artistId = newArtist.meta.last_row_id
    }

    // 2. 查找或创建专辑
    let albumId: number
    const albumLookup = await c.env.DB.prepare(
      'SELECT id FROM albums WHERE artist_id = ? AND title LIKE ?'
    ).bind(artistId, `%${album_title}%`).first()

    if (albumLookup) {
      albumId = (albumLookup as any).id
    } else {
      const newAlbum = await c.env.DB.prepare(
        'INSERT INTO albums (artist_id, title) VALUES (?, ?)'
      ).bind(artistId, album_title).run()
      albumId = newAlbum.meta.last_row_id
    }

    if (dry_run) {
      return c.json({
        code: 200,
        message: '预览完成',
        data: {
          artist_id: artistId,
          album_id: albumId,
          songs_to_insert: songs.length,
          songs: songs.map(s => ({
            ...s,
            status: 'preview',
            message: `[预览] 将插入歌曲: ${s.title}`
          }))
        }
      })
    }

    // 3. 插入歌曲
    const insertedIds: number[] = []
    for (const song of songs) {
      const result = await c.env.DB.prepare(
        'INSERT INTO songs (title, file_path, album_id, track_index) VALUES (?, ?, ?, ?)'
      ).bind(
        song.title,
        song.file_path || null,
        albumId,
        song.track_index || 0
      ).run()
      insertedIds.push(result.meta.last_row_id)
    }

    return c.json({
      code: 200,
      message: `成功插入 ${insertedIds.length} 首歌曲`,
      data: {
        artist_id: artistId,
        album_id: albumId,
        inserted_count: insertedIds.length,
        song_ids: insertedIds
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 21. Debug: Test Album Query
// 调试：测试专辑查询
// ==========================================
app.get('/api/debug/album-query', async (c) => {
  try {
    const artist = c.req.query('artist')
    const album = c.req.query('album')

    if (!artist || !album) {
      return c.json({ code: 400, message: 'Missing artist or album parameter' }, 400)
    }

    // 执行 SQL 查询
    let sql = `
      SELECT
        a.id AS artist_id, a.name AS artist_name, a.region, a.photo_url,
        al.id AS album_id, al.title AS album_title, al.release_date, al.cover_url,
        s.title AS song_title, s.file_path, s.lrc_path, s.track_index
      FROM artists a
      LEFT JOIN albums al ON a.id = al.artist_id
      LEFT JOIN songs s ON al.id = s.album_id
      WHERE a.name LIKE ?
      ORDER BY al.release_date ASC, s.track_index ASC
    `

    const { results } = await c.env.DB.prepare(sql).bind(`%${artist}%`).all()

    // 繁简体过滤
    const normalizedQuery = normalizeTitle(album)
    const filteredResults = (results as any[]).filter((row: any) => {
      if (!row.album_title) return false
      const normalizedTitle = normalizeTitle(row.album_title)
      return normalizedTitle === normalizedQuery ||
             normalizedTitle.includes(normalizedQuery) ||
             normalizedQuery.includes(normalizedTitle)
    })

    return c.json({
      code: 200,
      message: 'success',
      data: {
        query: { artist, album, normalizedQuery },
        total_results: results.length,
        filtered_results: filteredResults.length,
        sample_results: filteredResults.slice(0, 5)
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// 22. Admin: Cleanup Duplicate Songs in Album
// 清理指定专辑中的重复歌曲
// ==========================================
app.post('/api/admin/albums/cleanup-duplicates', async (c) => {
  try {
    const { album_id, song_ids } = await c.req.json() as {
      album_id?: number
      song_ids?: number[]
    }

    if (!album_id) {
      return c.json({ code: 400, message: 'Missing album_id parameter' }, 400)
    }

    if (!song_ids || !song_ids.length) {
      return c.json({ code: 400, message: 'Missing song_ids array' }, 400)
    }

    // 验证专辑存在
    const album = await c.env.DB.prepare(
      'SELECT id, title FROM albums WHERE id = ?'
    ).bind(album_id).first()

    if (!album) {
      return c.json({ code: 404, message: 'Album not found' }, 404)
    }

    // 获取删除前的歌曲数量
    const beforeCount = await c.env.DB.prepare(
      'SELECT COUNT(*) as count FROM songs WHERE album_id = ?'
    ).bind(album_id).first<{ count: number }>()

    // 执行批量删除
    const stmts: D1PreparedStatement[] = []
    for (const songId of song_ids) {
      stmts.push(c.env.DB.prepare('DELETE FROM songs WHERE id = ? AND album_id = ?').bind(songId, album_id))
    }

    await c.env.DB.batch(stmts)

    // 获取删除后的歌曲数量
    const afterCount = await c.env.DB.prepare(
      'SELECT COUNT(*) as count FROM songs WHERE album_id = ?'
    ).bind(album_id).first<{ count: number }>()

    return c.json({
      code: 200,
      message: `成功删除 ${song_ids.length} 首重复歌曲`,
      data: {
        album_id: album_id,
        album_title: (album as any).title,
        deleted_count: song_ids.length,
        before_count: beforeCount?.count || 0,
        after_count: afterCount?.count || 0,
        deleted_song_ids: song_ids
      }
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// Debug: Supabase Connectivity Test
// 测试 Worker 到 Supabase 的连通性
// ==========================================
app.get('/api/debug/supabase-test', async (c) => {
  try {
    const supabaseUrl = c.env.SUPABASE_URL
    const results: any = {
      supabase_url: supabaseUrl,
      timestamp: new Date().toISOString(),
      tests: {}
    }

    // Test 1: DNS resolution (fetch health endpoint)
    try {
      const healthStart = Date.now()
      const healthResponse = await fetch(`${supabaseUrl}/auth/v1/health`, {
        signal: AbortSignal.timeout(10000),
      })
      const healthTime = Date.now() - healthStart
      const healthText = await healthResponse.text()

      results.tests.health = {
        status: healthResponse.status,
        statusText: healthResponse.statusText,
        time_ms: healthTime,
        body: healthText.substring(0, 500),
        ok: healthResponse.ok
      }
    } catch (err: any) {
      results.tests.health = {
        error: err.message,
        cause: err.cause?.message || null,
        ok: false
      }
    }

    // Test 2: JWKS endpoint
    try {
      const jwksStart = Date.now()
      const jwksResponse = await fetch(`${supabaseUrl}/auth/v1/jwks`, {
        signal: AbortSignal.timeout(10000),
      })
      const jwksTime = Date.now() - jwksStart
      const jwksText = await jwksResponse.text()

      results.tests.jwks = {
        status: jwksResponse.status,
        statusText: jwksResponse.statusText,
        time_ms: jwksTime,
        body: jwksText.substring(0, 500),
        ok: jwksResponse.ok
      }
    } catch (err: any) {
      results.tests.jwks = {
        error: err.message,
        cause: err.cause?.message || null,
        ok: false
      }
    }

    // Test 3: REST API (simple ping)
    try {
      const restStart = Date.now()
      const restResponse = await fetch(`${supabaseUrl}/rest/v1/`, {
        headers: {
          'apikey': c.env.SUPABASE_ANON_KEY || '',
        },
        signal: AbortSignal.timeout(10000),
      })
      const restTime = Date.now() - restStart
      const restText = await restResponse.text()

      results.tests.rest = {
        status: restResponse.status,
        statusText: restResponse.statusText,
        time_ms: restTime,
        body: restText.substring(0, 500),
        ok: true // any response means connectivity works
      }
    } catch (err: any) {
      results.tests.rest = {
        error: err.message,
        cause: err.cause?.message || null,
        ok: false
      }
    }

    return c.json({
      code: 200,
      message: 'Supabase connectivity test completed',
      data: results
    })
  } catch (error: any) {
    return c.json({ code: 500, message: error.message }, 500)
  }
})

// ==========================================
// Upload Routes
// ==========================================
registerUploadRoutes(app)

export default app
