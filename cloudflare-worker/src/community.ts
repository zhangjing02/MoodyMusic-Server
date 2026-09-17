import { Hono } from 'hono'
import { createClient } from '@supabase/supabase-js'
import type { Bindings } from './types'

type AppType = { Bindings: Bindings; Variables: { user: any; token: string } }

function getSupabase(env: Bindings) {
  if (!env.SUPABASE_URL || !env.SUPABASE_ANON_KEY) return null
  return createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_KEY || env.SUPABASE_ANON_KEY)
}

function isDevelopMasterRole(role?: string | null): boolean {
  return role === 'develop_master'
}

function isGlobalAdminRole(role?: string | null): boolean {
  return role === 'admin' || isDevelopMasterRole(role)
}

/**
 * 确保数据库表和初始数据存在
 */
async function ensureCommunityTables(db: D1Database) {
  try {
    await db.prepare(`
      CREATE TABLE IF NOT EXISTS system_notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        author_name TEXT DEFAULT '音信官方',
        is_pinned INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `).run()

    await db.prepare(`
      CREATE TABLE IF NOT EXISTS community_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        author_name TEXT NOT NULL,
        author_avatar TEXT,
        is_task INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        is_pinned INTEGER DEFAULT 0,
        comment_count INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `).run()

    await db.prepare(`
      CREATE TABLE IF NOT EXISTS community_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        author_name TEXT NOT NULL,
        author_avatar TEXT,
        content TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `).run()

    try {
      await db.prepare(`CREATE INDEX IF NOT EXISTS idx_posts_category ON community_posts(category)`).run()
      await db.prepare(`CREATE INDEX IF NOT EXISTS idx_posts_user ON community_posts(user_id)`).run()
      await db.prepare(`CREATE INDEX IF NOT EXISTS idx_comments_post ON community_comments(post_id)`).run()
    } catch (_: any) {}
  } catch (e) {
    console.error('ensureCommunityTables error:', e)
  }
}

/**
 * 注册社区留言板与系统公告所有路由
 */
export function registerCommunityRoutes(app: Hono<AppType>, authMiddleware: any) {

  /**
   * 一键清空所有系统公告、留言板帖子与评论 (管理后台/测试维护)
   * POST /api/admin/community/clear-all
   */
  app.post('/api/admin/community/clear-all', async (c) => {
    try {
      const db = c.env.DB
      await ensureCommunityTables(db)

      await db.batch([
        db.prepare('DELETE FROM community_comments'),
        db.prepare('DELETE FROM community_posts'),
        db.prepare('DELETE FROM system_notices')
      ])

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('community_comments').delete().neq('id', 0)
          await supabase.from('community_posts').delete().neq('id', 0)
          await supabase.from('system_notices').delete().neq('id', 0)
        }
      } catch (err) {
        console.warn('Supabase clear-all warning:', err)
      }

      return c.json({
        code: 200,
        message: '所有公告、留言帖子与评论已全部清空',
        data: null
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '清空失败', data: null }, 500)
    }
  })

  // ==================== 1. 系统公告相关 ====================

  /**
   * 获取公告列表 (公开访问)
   * GET /api/notices
   */
  app.get('/api/notices', async (c) => {
    try {
      const db = c.env.DB
      await ensureCommunityTables(db)

      const result = await db.prepare(`
        SELECT id, title, content, author_name, is_pinned, created_at
        FROM system_notices
        ORDER BY is_pinned DESC, id DESC
      `).all()

      const notices = (result.results || []).map((row: any) => ({
        id: row.id,
        title: row.title,
        content: row.content,
        author_name: row.author_name || '音信官方',
        is_pinned: Boolean(row.is_pinned),
        created_at: row.created_at
      }))

      return c.json({
        code: 200,
        message: 'success',
        data: notices
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '获取公告失败', data: [] }, 500)
    }
  })

  /**
   * 发布公告 (仅管理员/Master - App 端携带 Token)
   * POST /api/notices
   */
  app.post('/api/notices', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      if (!isGlobalAdminRole(user?.role)) {
        return c.json({ code: 403, message: '只有管理员或Master开发者可以发布公告', data: null }, 403)
      }

      const body = await c.req.json()
      const title = (body.title || '').trim()
      const content = (body.content || '').trim()
      const isPinned = body.is_pinned ? 1 : 0
      const authorName = (body.author_name || user.nickname || user.username || '音信官方').trim()

      if (!title || !content) {
        return c.json({ code: 400, message: '标题与内容不能为空', data: null }, 400)
      }

      const db = c.env.DB
      await ensureCommunityTables(db)

      const res = await db.prepare(`
        INSERT INTO system_notices (title, content, author_name, is_pinned, created_at)
        VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
      `).bind(title, content, authorName, isPinned).run()

      const newId = res.meta?.last_row_id || 0

      // 同步到 Supabase
      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('system_notices').insert([{
            id: newId,
            title,
            content,
            author_name: authorName,
            is_pinned: Boolean(isPinned)
          }])
        }
      } catch (err) {
        console.warn('Supabase notice sync insert error:', err)
      }

      return c.json({
        code: 200,
        message: '公告发布成功',
        data: {
          id: newId,
          title,
          content,
          author_name: authorName,
          is_pinned: Boolean(isPinned),
          created_at: new Date().toISOString()
        }
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '发布公告失败', data: null }, 500)
    }
  })

  /**
   * 编辑修改公告 (App 端携带 Token)
   * PUT /api/notices/:id
   */
  app.put('/api/notices/:id', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      if (!isGlobalAdminRole(user?.role)) {
        return c.json({ code: 403, message: '无权编辑公告', data: null }, 403)
      }

      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const body = await c.req.json()
      const title = (body.title || '').trim()
      const content = (body.content || '').trim()
      const authorName = (body.author_name || '音信官方').trim()
      const isPinned = body.is_pinned ? 1 : 0

      if (!title || !content) {
        return c.json({ code: 400, message: '标题与内容不能为空', data: null }, 400)
      }

      const db = c.env.DB
      await db.prepare(`
        UPDATE system_notices
        SET title = ?, content = ?, author_name = ?, is_pinned = ?
        WHERE id = ?
      `).bind(title, content, authorName, isPinned, id).run()

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('system_notices').update({
            title,
            content,
            author_name: authorName,
            is_pinned: Boolean(isPinned)
          }).eq('id', id)
        }
      } catch (err) {
        console.warn('Supabase notice sync update error:', err)
      }

      return c.json({
        code: 200,
        message: '公告修改成功',
        data: { id, title, content, author_name: authorName, is_pinned: Boolean(isPinned) }
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '修改公告失败', data: null }, 500)
    }
  })

  /**
   * 删除公告 (App 端携带 Token)
   * DELETE /api/notices/:id
   */
  app.delete('/api/notices/:id', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      if (!isGlobalAdminRole(user?.role)) {
        return c.json({ code: 403, message: '无权删除公告', data: null }, 403)
      }

      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) {
        return c.json({ code: 400, message: 'ID不合法', data: null }, 400)
      }

      const db = c.env.DB
      await db.prepare('DELETE FROM system_notices WHERE id = ?').bind(id).run()

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('system_notices').delete().eq('id', id)
        }
      } catch (err) {
        console.warn('Supabase notice sync delete error:', err)
      }

      return c.json({ code: 200, message: '公告已删除', data: null })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '删除公告失败', data: null }, 500)
    }
  })

  // ==================== 1.1 Web 管理后台公告专线 (/api/admin/notices) ====================

  /**
   * 获取公告列表 (管理后台)
   * GET /api/admin/notices
   */
  app.get('/api/admin/notices', async (c) => {
    try {
      const db = c.env.DB
      await ensureCommunityTables(db)

      const result = await db.prepare(`
        SELECT id, title, content, author_name, is_pinned, created_at
        FROM system_notices
        ORDER BY is_pinned DESC, id DESC
      `).all()

      const notices = (result.results || []).map((row: any) => ({
        id: row.id,
        title: row.title,
        content: row.content,
        author_name: row.author_name || '音信官方',
        is_pinned: Boolean(row.is_pinned),
        created_at: row.created_at
      }))

      return c.json({ code: 200, message: 'success', data: notices })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '获取后台公告失败', data: [] }, 500)
    }
  })

  /**
   * 发布新公告 (管理后台)
   * POST /api/admin/notices
   */
  app.post('/api/admin/notices', async (c) => {
    try {
      const body = await c.req.json()
      const title = (body.title || '').trim()
      const content = (body.content || '').trim()
      const authorName = (body.author_name || '音信官方').trim()
      const isPinned = body.is_pinned ? 1 : 0

      if (!title || !content) {
        return c.json({ code: 400, message: '标题与内容不能为空', data: null }, 400)
      }

      const db = c.env.DB
      await ensureCommunityTables(db)

      const res = await db.prepare(`
        INSERT INTO system_notices (title, content, author_name, is_pinned, created_at)
        VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
      `).bind(title, content, authorName, isPinned).run()

      const newId = res.meta?.last_row_id || 0

      // 同步到 Supabase
      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('system_notices').insert([{
            id: newId,
            title,
            content,
            author_name: authorName,
            is_pinned: Boolean(isPinned)
          }])
        }
      } catch (err) {
        console.warn('Supabase notice sync error:', err)
      }

      return c.json({
        code: 200,
        message: '公告已成功发布并同步到客户端',
        data: {
          id: newId,
          title,
          content,
          author_name: authorName,
          is_pinned: Boolean(isPinned),
          created_at: new Date().toISOString()
        }
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '发布公告失败', data: null }, 500)
    }
  })

  /**
   * 修改编辑公告 (管理后台)
   * PUT /api/admin/notices/:id
   */
  app.put('/api/admin/notices/:id', async (c) => {
    try {
      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const body = await c.req.json()
      const title = (body.title || '').trim()
      const content = (body.content || '').trim()
      const authorName = (body.author_name || '音信官方').trim()
      const isPinned = body.is_pinned ? 1 : 0

      if (!title || !content) {
        return c.json({ code: 400, message: '标题与内容不能为空', data: null }, 400)
      }

      const db = c.env.DB
      await db.prepare(`
        UPDATE system_notices
        SET title = ?, content = ?, author_name = ?, is_pinned = ?
        WHERE id = ?
      `).bind(title, content, authorName, isPinned, id).run()

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('system_notices').update({
            title,
            content,
            author_name: authorName,
            is_pinned: Boolean(isPinned)
          }).eq('id', id)
        }
      } catch (err) {
        console.warn('Supabase notice sync error:', err)
      }

      return c.json({
        code: 200,
        message: '公告修改已保存',
        data: { id, title, content, author_name: authorName, is_pinned: Boolean(isPinned) }
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '修改公告失败', data: null }, 500)
    }
  })

  /**
   * 快速切换置顶状态 (管理后台)
   * PATCH /api/admin/notices/:id/pin
   */
  app.patch('/api/admin/notices/:id/pin', async (c) => {
    try {
      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const body = await c.req.json()
      const isPinned = body.is_pinned ? 1 : 0

      const db = c.env.DB
      await db.prepare(`
        UPDATE system_notices
        SET is_pinned = ?
        WHERE id = ?
      `).bind(isPinned, id).run()

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('system_notices').update({ is_pinned: Boolean(isPinned) }).eq('id', id)
        }
      } catch (err) {
        console.warn('Supabase notice pin sync error:', err)
      }

      return c.json({
        code: 200,
        message: isPinned ? '已置顶' : '已取消置顶',
        data: { id, is_pinned: Boolean(isPinned) }
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '更新置顶状态失败', data: null }, 500)
    }
  })

  /**
   * 删除公告 (管理后台)
   * DELETE /api/admin/notices/:id
   */
  app.delete('/api/admin/notices/:id', async (c) => {
    try {
      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const db = c.env.DB
      await db.prepare('DELETE FROM system_notices WHERE id = ?').bind(id).run()

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('system_notices').delete().eq('id', id)
        }
      } catch (err) {
        console.warn('Supabase notice delete error:', err)
      }

      return c.json({ code: 200, message: '公告已成功删除', data: null })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '删除公告失败', data: null }, 500)
    }
  })

  // ==================== 1.2 Web 管理后台社区/资源对齐专线 (/api/admin/community/posts) ====================

  /**
   * 获取社区帖子列表 (Web 管理后台无鉴权专线)
   * GET /api/admin/community/posts
   */
  app.get('/api/admin/community/posts', async (c) => {
    try {
      const db = c.env.DB
      await ensureCommunityTables(db)

      const category = c.req.query('category')
      const status = c.req.query('status')

      let query = 'SELECT * FROM community_posts WHERE 1=1'
      const params: any[] = []

      if (category && category !== 'all') {
        query += ' AND category = ?'
        params.push(category)
      }

      if (status) {
        query += ' AND status = ?'
        params.push(status)
      }

      query += ' ORDER BY is_pinned DESC, id DESC LIMIT 200'

      const stmt = db.prepare(query)
      const result = await (params.length > 0 ? stmt.bind(...params) : stmt).all()

      const posts = (result.results || []).map((row: any) => ({
        id: row.id,
        category: row.category,
        title: row.title,
        content: row.content,
        user_id: row.user_id,
        author_name: row.author_name || '音信读者',
        author_avatar: row.author_avatar,
        is_task: Boolean(row.is_task),
        status: row.status || 'pending',
        is_pinned: Boolean(row.is_pinned),
        comment_count: row.comment_count || 0,
        created_at: row.created_at,
        updated_at: row.updated_at
      }))

      return c.json({ code: 200, message: 'success', data: posts })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '获取后台帖子失败', data: [] }, 500)
    }
  })

  /**
   * 更新任务状态 (Web 管理后台一键打钩流转)
   * PATCH /api/admin/community/posts/:id/status
   */
  app.patch('/api/admin/community/posts/:id/status', async (c) => {
    try {
      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const body = await c.req.json()
      const newStatus = (body.status || 'pending').trim()

      const validStatuses = ['pending', 'in_progress', 'completed']
      if (!validStatuses.includes(newStatus)) {
        return c.json({ code: 400, message: '状态值不合法', data: null }, 400)
      }

      const db = c.env.DB
      await ensureCommunityTables(db)

      await db.prepare(`
        UPDATE community_posts
        SET status = ?, updated_at = datetime('now', 'localtime')
        WHERE id = ?
      `).bind(newStatus, id).run()

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('community_posts').update({ status: newStatus }).eq('id', id)
        }
      } catch (_: any) {}

      return c.json({ code: 200, message: '状态已更新', data: { id, status: newStatus } })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '更新状态失败', data: null }, 500)
    }
  })

  /**
   * 删除帖子 (Web 管理后台)
   * DELETE /api/admin/community/posts/:id
   */
  app.delete('/api/admin/community/posts/:id', async (c) => {
    try {
      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const db = c.env.DB
      await ensureCommunityTables(db)

      await db.batch([
        db.prepare('DELETE FROM community_comments WHERE post_id = ?').bind(id),
        db.prepare('DELETE FROM community_posts WHERE id = ?').bind(id)
      ])

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('community_comments').delete().eq('post_id', id)
          await supabase.from('community_posts').delete().eq('id', id)
        }
      } catch (_: any) {}

      return c.json({ code: 200, message: '帖子已成功删除', data: null })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '删除失败', data: null }, 500)
    }
  })

  // ==================== 2. 留言与待办系统相关 ====================

  /**
   * 获取社区帖子与待办列表 (公开访问，支持分类/状态过滤)
   * GET /api/community/posts?category=xxx&status=xxx
   */
  app.get('/api/community/posts', async (c) => {
    try {
      const db = c.env.DB
      await ensureCommunityTables(db)

      const category = c.req.query('category')
      const status = c.req.query('status')

      let query = 'SELECT * FROM community_posts WHERE 1=1'
      const params: any[] = []

      if (category && category !== 'all') {
        query += ' AND category = ?'
        params.push(category)
      }

      if (status) {
        query += ' AND status = ?'
        params.push(status)
      }

      // 置顶优先，最新发帖优先
      query += ' ORDER BY is_pinned DESC, id DESC LIMIT 100'

      const stmt = db.prepare(query)
      const result = await (params.length > 0 ? stmt.bind(...params) : stmt).all()

      const posts = (result.results || []).map((row: any) => ({
        id: row.id,
        category: row.category,
        title: row.title,
        content: row.content,
        user_id: row.user_id,
        author_name: row.author_name || '听风者',
        author_avatar: row.author_avatar,
        is_task: Boolean(row.is_task),
        status: row.status || 'pending',
        is_pinned: Boolean(row.is_pinned),
        comment_count: row.comment_count || 0,
        created_at: row.created_at,
        updated_at: row.updated_at
      }))

      return c.json({
        code: 200,
        message: 'success',
        data: posts
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '获取帖子列表失败', data: [] }, 500)
    }
  })

  /**
   * 获取单条帖子详情
   * GET /api/community/posts/:id
   */
  app.get('/api/community/posts/:id', async (c) => {
    try {
      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const db = c.env.DB
      await ensureCommunityTables(db)

      const row: any = await db.prepare('SELECT * FROM community_posts WHERE id = ?').bind(id).first()
      if (!row) {
        return c.json({ code: 404, message: '内容不存在或已删除', data: null }, 404)
      }

      return c.json({
        code: 200,
        message: 'success',
        data: {
          id: row.id,
          category: row.category,
          title: row.title,
          content: row.content,
          user_id: row.user_id,
          author_name: row.author_name || '听风者',
          author_avatar: row.author_avatar,
          is_task: Boolean(row.is_task),
          status: row.status || 'pending',
          is_pinned: Boolean(row.is_pinned),
          comment_count: row.comment_count || 0,
          created_at: row.created_at,
          updated_at: row.updated_at
        }
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '查询失败', data: null }, 500)
    }
  })

  /**
   * 发布留言/建议/待办任务 (需登录)
   * POST /api/community/posts
   */
  app.post('/api/community/posts', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      if (!user) return c.json({ code: 401, message: '请先登录', data: null }, 401)

      const body = await c.req.json()
      const category = (body.category || 'chat').trim()
      const title = (body.title || '').trim()
      const content = (body.content || '').trim()

      if (!title || !content) {
        return c.json({ code: 400, message: '标题与内容均不能为空', data: null }, 400)
      }

      // 判断是否属于任务属性板块 (资源补齐、Bug提示、页面优化、功能缺失)
      const isTask = ['resource', 'bug', 'ui', 'feature'].includes(category) ? 1 : 0
      const initialStatus = 'pending'

      const db = c.env.DB
      await ensureCommunityTables(db)

      const authorName = user.nickname || user.username || '音信读者'
      const authorAvatar = user.avatar_url || null

      const res = await db.prepare(`
        INSERT INTO community_posts (category, title, content, user_id, author_name, author_avatar, is_task, status, is_pinned, comment_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, datetime('now', 'localtime'), datetime('now', 'localtime'))
      `).bind(category, title, content, user.id, authorName, authorAvatar, isTask, initialStatus).run()

      const newId = res.meta?.last_row_id || 0

      // 同步至 Supabase 向量与关系型数据库
      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('community_posts').insert([{
            id: newId,
            category,
            title,
            content,
            user_id: user.id,
            author_name: authorName,
            author_avatar: authorAvatar,
            is_task: Boolean(isTask),
            status: initialStatus,
            is_pinned: false,
            comment_count: 0
          }])
        }
      } catch (err) {
        console.warn('Supabase post sync:', err)
      }

      return c.json({
        code: 200,
        message: '发布成功',
        data: {
          id: newId,
          category,
          title,
          content,
          user_id: user.id,
          author_name: authorName,
          author_avatar: authorAvatar,
          is_task: Boolean(isTask),
          status: initialStatus,
          is_pinned: false,
          comment_count: 0,
          created_at: new Date().toISOString()
        }
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '发布失败', data: null }, 500)
    }
  })

  /**
   * 打钩 / 更新任务待办状态 (仅管理员/Master)
   * PATCH /api/community/posts/:id/status
   */
  app.patch('/api/community/posts/:id/status', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      if (!isGlobalAdminRole(user?.role)) {
        return c.json({ code: 403, message: '只有开发者或管理员有权打钩标记任务状态', data: null }, 403)
      }

      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const body = await c.req.json()
      const newStatus = (body.status || 'pending').trim()

      const validStatuses = ['pending', 'in_progress', 'completed']
      if (!validStatuses.includes(newStatus)) {
        return c.json({ code: 400, message: '状态值不合法', data: null }, 400)
      }

      const db = c.env.DB
      await db.prepare(`
        UPDATE community_posts
        SET status = ?, updated_at = datetime('now', 'localtime')
        WHERE id = ?
      `).bind(newStatus, id).run()

      const updatedRow: any = await db.prepare('SELECT * FROM community_posts WHERE id = ?').bind(id).first()

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('community_posts').update({ status: newStatus }).eq('id', id)
        }
      } catch (_: any) {}

      return c.json({
        code: 200,
        message: '状态已更新',
        data: {
          id: updatedRow.id,
          category: updatedRow.category,
          title: updatedRow.title,
          content: updatedRow.content,
          user_id: updatedRow.user_id,
          author_name: updatedRow.author_name,
          author_avatar: updatedRow.author_avatar,
          is_task: Boolean(updatedRow.is_task),
          status: updatedRow.status,
          is_pinned: Boolean(updatedRow.is_pinned),
          comment_count: updatedRow.comment_count,
          created_at: updatedRow.created_at,
          updated_at: updatedRow.updated_at
        }
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '更新状态失败', data: null }, 500)
    }
  })

  /**
   * 删除帖子 (Master/管理员可删任意贴，作者本人可删自己的贴)
   * DELETE /api/community/posts/:id
   */
  app.delete('/api/community/posts/:id', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      if (!user) return c.json({ code: 401, message: '请先登录', data: null }, 401)

      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const db = c.env.DB
      const post: any = await db.prepare('SELECT id, user_id FROM community_posts WHERE id = ?').bind(id).first()
      if (!post) {
        return c.json({ code: 404, message: '帖子不存在', data: null }, 404)
      }

      const isMasterOrAdmin = isGlobalAdminRole(user.role)
      const isAuthor = Number(post.user_id) === Number(user.id)

      if (!isMasterOrAdmin && !isAuthor) {
        return c.json({ code: 403, message: '无权删除该内容', data: null }, 403)
      }

      // 同时删除帖子及关联评论
      await db.batch([
        db.prepare('DELETE FROM community_posts WHERE id = ?').bind(id),
        db.prepare('DELETE FROM community_comments WHERE post_id = ?').bind(id)
      ])

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('community_posts').delete().eq('id', id)
          await supabase.from('community_comments').delete().eq('post_id', id)
        }
      } catch (_: any) {}

      return c.json({ code: 200, message: '内容已彻底删除', data: null })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '删除失败', data: null }, 500)
    }
  })

  // ==================== 3. 评论与讨论盖楼相关 ====================

  /**
   * 获取帖子下的全部评论 (公开访问)
   * GET /api/community/posts/:id/comments
   */
  app.get('/api/community/posts/:id/comments', async (c) => {
    try {
      const postId = parseInt(c.req.param('id'), 10)
      if (isNaN(postId)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const db = c.env.DB
      await ensureCommunityTables(db)

      const result = await db.prepare(`
        SELECT id, post_id, user_id, author_name, author_avatar, content, created_at
        FROM community_comments
        WHERE post_id = ?
        ORDER BY id ASC
      `).bind(postId).all()

      const comments = (result.results || []).map((row: any) => ({
        id: row.id,
        post_id: row.post_id,
        user_id: row.user_id,
        author_name: row.author_name || '音信听众',
        author_avatar: row.author_avatar,
        content: row.content,
        created_at: row.created_at
      }))

      return c.json({
        code: 200,
        message: 'success',
        data: comments
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '获取评论失败', data: [] }, 500)
    }
  })

  /**
   * 发表跟帖评论 (需登录)
   * POST /api/community/posts/:id/comments
   */
  app.post('/api/community/posts/:id/comments', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      if (!user) return c.json({ code: 401, message: '请先登录', data: null }, 401)

      const postId = parseInt(c.req.param('id'), 10)
      if (isNaN(postId)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const body = await c.req.json()
      const content = (body.content || '').trim()
      if (!content) {
        return c.json({ code: 400, message: '评论内容不能为空', data: null }, 400)
      }

      const db = c.env.DB
      await ensureCommunityTables(db)

      const authorName = user.nickname || user.username || '音信听众'
      const authorAvatar = user.avatar_url || null

      const res = await db.prepare(`
        INSERT INTO community_comments (post_id, user_id, author_name, author_avatar, content, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
      `).bind(postId, user.id, authorName, authorAvatar, content).run()

      // 更新主贴 comment_count
      await db.prepare(`
        UPDATE community_posts
        SET comment_count = comment_count + 1, updated_at = datetime('now', 'localtime')
        WHERE id = ?
      `).bind(postId).run()

      const newId = res.meta?.last_row_id || 0

      // 同步至 Supabase
      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('community_comments').insert([{
            id: newId,
            post_id: postId,
            user_id: user.id,
            author_name: authorName,
            author_avatar: authorAvatar,
            content
          }])
        }
      } catch (err) {
        console.warn('Supabase comment sync:', err)
      }

      return c.json({
        code: 200,
        message: '评论发表成功',
        data: {
          id: newId,
          post_id: postId,
          user_id: user.id,
          author_name: authorName,
          author_avatar: authorAvatar,
          content,
          created_at: new Date().toISOString()
        }
      })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '发表评论失败', data: null }, 500)
    }
  })

  /**
   * 删除评论 (Master/管理员可删任意评论，作者本人可删自己的评论)
   * DELETE /api/community/comments/:id
   */
  app.delete('/api/community/comments/:id', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      if (!user) return c.json({ code: 401, message: '请先登录', data: null }, 401)

      const id = parseInt(c.req.param('id'), 10)
      if (isNaN(id)) return c.json({ code: 400, message: 'ID不合法', data: null }, 400)

      const db = c.env.DB
      const comment: any = await db.prepare('SELECT id, post_id, user_id FROM community_comments WHERE id = ?').bind(id).first()
      if (!comment) {
        return c.json({ code: 404, message: '评论不存在', data: null }, 404)
      }

      const isMasterOrAdmin = isGlobalAdminRole(user.role)
      const isAuthor = Number(comment.user_id) === Number(user.id)

      if (!isMasterOrAdmin && !isAuthor) {
        return c.json({ code: 403, message: '无权删除该评论', data: null }, 403)
      }

      await db.prepare('DELETE FROM community_comments WHERE id = ?').bind(id).run()

      // 递减主贴评论数
      await db.prepare(`
        UPDATE community_posts
        SET comment_count = MAX(0, comment_count - 1)
        WHERE id = ?
      `).bind(comment.post_id).run()

      try {
        const supabase = getSupabase(c.env)
        if (supabase) {
          await supabase.from('community_comments').delete().eq('id', id)
        }
      } catch (_: any) {}

      return c.json({ code: 200, message: '评论已删除', data: null })
    } catch (e: any) {
      return c.json({ code: 500, message: e.message || '删除失败', data: null }, 500)
    }
  })
}
