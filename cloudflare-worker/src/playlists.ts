import { Hono } from 'hono'
import type { Bindings } from './types'
import { fail, serverError } from './error'

type AppType = { Bindings: Bindings; Variables: { user: any; token: string } }

/**
 * 确保播放列表相关的表存在（防未迁移环境）
 */
async function ensureTables(db: D1Database) {
  await db.exec(`
    CREATE TABLE IF NOT EXISTS user_playlists (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      description TEXT,
      theme_color TEXT DEFAULT 'DEFAULT',
      cover_url TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS user_playlist_songs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      playlist_id INTEGER NOT NULL,
      song_id INTEGER NOT NULL,
      title TEXT NOT NULL,
      artist_name TEXT,
      album_title TEXT,
      cover_url TEXT,
      file_path TEXT,
      duration INTEGER DEFAULT 0,
      sort_order INTEGER DEFAULT 0,
      added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(playlist_id, song_id)
    );

    CREATE INDEX IF NOT EXISTS idx_user_playlists_user_id ON user_playlists(user_id);
    CREATE INDEX IF NOT EXISTS idx_user_playlist_songs_pid ON user_playlist_songs(playlist_id);
  `)
}

export function registerPlaylistRoutes(app: Hono<AppType>, authMiddleware: any) {
  // 1. 获取当前用户的所有播放列表（含每张歌单歌曲数量）
  app.get('/api/user/playlists', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      const db = c.env.DB
      await ensureTables(db)

      const query = `
        SELECT 
          p.id,
          p.user_id,
          p.name,
          p.description,
          p.theme_color,
          p.cover_url,
          p.created_at,
          p.updated_at,
          COUNT(s.id) as song_count
        FROM user_playlists p
        LEFT JOIN user_playlist_songs s ON p.id = s.playlist_id
        WHERE p.user_id = ?
        GROUP BY p.id
        ORDER BY p.updated_at DESC, p.id DESC
      `
      const { results } = await db.prepare(query).bind(user.id).all()

      return c.json({
        code: 200,
        message: 'success',
        data: results || []
      })
    } catch (e: any) {
      return serverError(c, 'DATABASE_QUERY_FAILED', { error: e.message })
    }
  })

  // 2. 创建新播放列表
  app.post('/api/user/playlists', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      const db = c.env.DB
      await ensureTables(db)

      const body = await c.req.json().catch(() => ({}))
      const name = (body.name || '').trim()
      if (!name) {
        return c.json({ code: 400, message: '播放列表名称不能为空', data: null }, 400)
      }
      const description = (body.description || '').trim()
      const themeColor = (body.theme_color || body.themeColor || 'DEFAULT').trim()
      const coverUrl = (body.cover_url || body.coverUrl || '').trim()

      const now = new Date().toISOString()
      const insertRes = await db.prepare(`
        INSERT INTO user_playlists (user_id, name, description, theme_color, cover_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `).bind(user.id, name, description, themeColor, coverUrl, now, now).run()

      const playlistId = insertRes.meta.last_row_id

      return c.json({
        code: 200,
        message: '创建成功',
        data: {
          id: playlistId,
          user_id: user.id,
          name,
          description,
          theme_color: themeColor,
          cover_url: coverUrl,
          song_count: 0,
          created_at: now,
          updated_at: now
        }
      })
    } catch (e: any) {
      return serverError(c, 'PLAYLIST_CREATE_FAILED', { error: e.message })
    }
  })

  // 3. 修改播放列表基本信息
  app.put('/api/user/playlists/:id', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      const playlistId = Number(c.req.param('id'))
      const db = c.env.DB
      await ensureTables(db)

      const body = await c.req.json().catch(() => ({}))
      const name = (body.name || '').trim()
      const description = body.description !== undefined ? body.description.trim() : null
      const themeColor = (body.theme_color || body.themeColor || '').trim()

      const existing = await db.prepare(
        'SELECT * FROM user_playlists WHERE id = ? AND user_id = ?'
      ).bind(playlistId, user.id).first() as any

      if (!existing) {
        return c.json({ code: 404, message: '播放列表不存在', data: null }, 404)
      }

      const updatedName = name || existing.name
      const updatedDesc = description !== null ? description : existing.description
      const updatedTheme = themeColor || existing.theme_color
      const now = new Date().toISOString()

      await db.prepare(`
        UPDATE user_playlists
        SET name = ?, description = ?, theme_color = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
      `).bind(updatedName, updatedDesc, updatedTheme, now, playlistId, user.id).run()

      return c.json({
        code: 200,
        message: '更新成功',
        data: {
          id: playlistId,
          user_id: user.id,
          name: updatedName,
          description: updatedDesc,
          theme_color: updatedTheme,
          updated_at: now
        }
      })
    } catch (e: any) {
      return serverError(c, 'PLAYLIST_UPDATE_FAILED', { error: e.message })
    }
  })

  // 4. 删除播放列表
  app.delete('/api/user/playlists/:id', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      const playlistId = Number(c.req.param('id'))
      const db = c.env.DB
      await ensureTables(db)

      // 验证归属
      const existing = await db.prepare(
        'SELECT id FROM user_playlists WHERE id = ? AND user_id = ?'
      ).bind(playlistId, user.id).first()

      if (!existing) {
        return c.json({ code: 404, message: '播放列表不存在', data: null }, 404)
      }

      await db.batch([
        db.prepare('DELETE FROM user_playlist_songs WHERE playlist_id = ?').bind(playlistId),
        db.prepare('DELETE FROM user_playlists WHERE id = ?').bind(playlistId)
      ])

      return c.json({
        code: 200,
        message: '播放列表已删除',
        data: { id: playlistId }
      })
    } catch (e: any) {
      return serverError(c, 'PLAYLIST_DELETE_FAILED', { error: e.message })
    }
  })

  // 5. 获取指定播放列表的歌曲清单
  app.get('/api/user/playlists/:id/songs', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      const playlistId = Number(c.req.param('id'))
      const db = c.env.DB
      await ensureTables(db)

      const playlist = await db.prepare(
        'SELECT * FROM user_playlists WHERE id = ? AND user_id = ?'
      ).bind(playlistId, user.id).first() as any

      if (!playlist) {
        return c.json({ code: 404, message: '播放列表不存在', data: null }, 404)
      }

      const { results: songs } = await db.prepare(`
        SELECT 
          id,
          playlist_id,
          song_id,
          title,
          artist_name,
          album_title,
          cover_url,
          file_path,
          duration,
          sort_order,
          added_at
        FROM user_playlist_songs
        WHERE playlist_id = ?
        ORDER BY sort_order ASC, added_at DESC, id DESC
      `).bind(playlistId).all()

      return c.json({
        code: 200,
        message: 'success',
        data: {
          playlist,
          songs: songs || []
        }
      })
    } catch (e: any) {
      return serverError(c, 'GET_PLAYLIST_SONGS_FAILED', { error: e.message })
    }
  })

  // 6. 向指定播放列表中添加单曲
  app.post('/api/user/playlists/:id/songs', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      const playlistId = Number(c.req.param('id'))
      const db = c.env.DB
      await ensureTables(db)

      const playlist = await db.prepare(
        'SELECT id FROM user_playlists WHERE id = ? AND user_id = ?'
      ).bind(playlistId, user.id).first()

      if (!playlist) {
        return c.json({ code: 404, message: '播放列表不存在', data: null }, 404)
      }

      const body = await c.req.json().catch(() => ({}))
      const songId = Number(body.song_id || body.songId)
      const title = (body.title || '').trim()
      if (!songId || !title) {
        return c.json({ code: 400, message: '缺少歌曲 ID 或歌名', data: null }, 400)
      }

      const artistName = (body.artist_name || body.artistName || '').trim()
      const albumTitle = (body.album_title || body.albumTitle || '').trim()
      const coverUrl = (body.cover_url || body.coverUrl || '').trim()
      const filePath = (body.file_path || body.filePath || '').trim()
      const duration = Number(body.duration || 0)
      const now = new Date().toISOString()

      // 插入或忽略已有记录
      await db.prepare(`
        INSERT INTO user_playlist_songs (
          playlist_id, song_id, title, artist_name, album_title, cover_url, file_path, duration, added_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(playlist_id, song_id) DO UPDATE SET
          title = excluded.title,
          artist_name = excluded.artist_name,
          album_title = excluded.album_title,
          cover_url = excluded.cover_url,
          file_path = excluded.file_path,
          duration = excluded.duration
      `).bind(playlistId, songId, title, artistName, albumTitle, coverUrl, filePath, duration, now).run()

      // 更新歌单更新时间与第一首封面（如果歌单未设自定义封面）
      await db.prepare(`
        UPDATE user_playlists 
        SET updated_at = ?,
            cover_url = CASE WHEN (cover_url IS NULL OR cover_url = '') THEN ? ELSE cover_url END
        WHERE id = ?
      `).bind(now, coverUrl, playlistId).run()

      return c.json({
        code: 200,
        message: '歌曲已收录',
        data: {
          playlist_id: playlistId,
          song_id: songId,
          title
        }
      })
    } catch (e: any) {
      return serverError(c, 'ADD_SONG_TO_PLAYLIST_FAILED', { error: e.message })
    }
  })

  // 7. 从指定播放列表中移除单曲
  app.delete('/api/user/playlists/:id/songs/:songId', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      const playlistId = Number(c.req.param('id'))
      const songId = Number(c.req.param('songId'))
      const db = c.env.DB
      await ensureTables(db)

      const playlist = await db.prepare(
        'SELECT id FROM user_playlists WHERE id = ? AND user_id = ?'
      ).bind(playlistId, user.id).first()

      if (!playlist) {
        return c.json({ code: 404, message: '播放列表不存在', data: null }, 404)
      }

      await db.prepare(
        'DELETE FROM user_playlist_songs WHERE playlist_id = ? AND song_id = ?'
      ).bind(playlistId, songId).run()

      const now = new Date().toISOString()
      await db.prepare('UPDATE user_playlists SET updated_at = ? WHERE id = ?').bind(now, playlistId).run()

      return c.json({
        code: 200,
        message: '歌曲已从列表移除',
        data: { playlist_id: playlistId, song_id: songId }
      })
    } catch (e: any) {
      return serverError(c, 'REMOVE_SONG_FROM_PLAYLIST_FAILED', { error: e.message })
    }
  })

  // 8. 查询指定歌曲被收录进了当前用户的哪些歌单（用于边听歌边展示勾选状态）
  app.get('/api/user/playlists/memberships/:songId', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      const songId = Number(c.req.param('songId'))
      const db = c.env.DB
      await ensureTables(db)

      const query = `
        SELECT s.playlist_id
        FROM user_playlist_songs s
        INNER JOIN user_playlists p ON s.playlist_id = p.id
        WHERE p.user_id = ? AND s.song_id = ?
      `
      const { results } = await db.prepare(query).bind(user.id, songId).all()
      const playlistIds = (results || []).map((r: any) => Number(r.playlist_id))

      return c.json({
        code: 200,
        message: 'success',
        data: {
          song_id: songId,
          playlist_ids: playlistIds
        }
      })
    } catch (e: any) {
      return serverError(c, 'QUERY_MEMBERSHIPS_FAILED', { error: e.message })
    }
  })
}
