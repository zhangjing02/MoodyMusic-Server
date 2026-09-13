import { Hono } from 'hono'
import { createClient } from '@supabase/supabase-js'
import type { Bindings } from './types'
import { fail, serverError } from './error'

type AppType = { Bindings: Bindings; Variables: { user: any; token: string } }

/**
 * 专辑社交功能 (基于 Supabase 存储，D1 班级隔离)
 */
export function registerAlbumSocialRoutes(app: Hono<AppType>, authMiddleware: any) {
  
  const getSupabase = (env: Bindings) => createClient(env.SUPABASE_URL || 'https://placeholder.supabase.co', env.SUPABASE_ANON_KEY || 'anon')

  /**
   * 辅助函数：从 D1 获取当前用户的班级 ID
   */
  async function getUserClassId(db: D1Database, userId: number): Promise<string | null> {
    const result = await db.prepare(
      'SELECT class_id FROM student_roster WHERE profile_id = ?'
    ).bind(userId).first() as { class_id: string } | null
    return result?.class_id || null
  }

  // 1. 获取专辑社交聚合内容 (主贴 + 平铺回复)
  // 对应 Android: GET /api/albums/{albumId}/social_content
  // 强制认证，强制班级隔离
  app.get('/api/albums/:id/social_content', authMiddleware, async (c) => {
    try {
      const albumId = c.req.param('id')
      const user = c.get('user')
      const db = c.env.DB
      const supabase = getSupabase(c.env)

      // 1. 获取用户班级
      const classId = await getUserClassId(db, user.id)
      if (!classId) {
        // 游客或未认领座位的用户不能查看社交内容
        return c.json({
          code: 403,
          message: '只有认领了座位的班级成员才能查看讨论',
          data: null
        }, 403)
      }

      // 2. 从 Supabase 获取该专辑、该班级的所有评论
      const { data, error } = await supabase
        .from('album_comments')
        .select(`
          id,
          album_id,
          user_id,
          class_id,
          content,
          created_at,
          user_profiles:user_id (id, username, avatar_url)
        `)
        .eq('album_id', albumId)
        .eq('class_id', classId)
        .order('created_at', { ascending: true }) // 按时间正序，最早的做主贴

      if (error) throw error

      if (!data || data.length === 0) {
        return c.json({
          code: 200,
          message: '暂无讨论',
          data: null
        })
      }

      // 3. 组织数据结构：第一条为 Post，其余为 Replies
      const mainPost: any = data[0]
      const mainAuthor = Array.isArray(mainPost.user_profiles) ? mainPost.user_profiles[0] : mainPost.user_profiles
      const replies = data.slice(1).map((item: any) => {
        const itemAuthor = Array.isArray(item.user_profiles) ? item.user_profiles[0] : item.user_profiles
        return {
          id: item.id,
          album_id: item.album_id,
          user_id: item.user_id,
          class_id: item.class_id,
          content: item.content,
          created_at: item.created_at,
          author: {
            username: itemAuthor?.username || '未知用户',
            avatar_url: itemAuthor?.avatar_url
          }
        }
      })

      return c.json({
        code: 200,
        message: 'success',
        data: {
          id: mainPost.id,
          album_id: mainPost.album_id,
          user_id: mainPost.user_id,
          class_id: mainPost.class_id,
          content: mainPost.content,
          created_at: mainPost.created_at,
          author: {
            username: mainAuthor?.username || '未知用户',
            avatar_url: mainAuthor?.avatar_url
          },
          replies: replies
        }
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // 2. 发起讨论 (主贴)
  // 对应 Android: POST /api/albums/{albumId}/posts
  app.post('/api/albums/:id/posts', authMiddleware, async (c) => {
    try {
      const albumId = c.req.param('id')
      const user = c.get('user')
      const { content } = await c.req.json() as { content: string }
      const db = c.env.DB

      const classId = await getUserClassId(db, user.id)
      if (!classId) return fail(c, 'FORBIDDEN', { message: '请先认领座位加入班级' })

      if (!content || content.trim().length === 0) {
        return fail(c, 'MISSING_PARAMETER', { message: '内容不能为空' })
      }

      const supabase = getSupabase(c.env)
      const { data, error } = await supabase
        .from('album_comments')
        .insert([{ 
          album_id: albumId, 
          user_id: user.supabase_uid, 
          class_id: classId,
          content: content.trim() 
        }])
        .select()

      if (error) throw error

      // 触发 JPush 信号
      sendSocialPush(c, albumId, classId)

      return c.json({ code: 200, message: '发布成功', data: data?.[0] })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  // 3. 发表回复
  // 对应 Android: POST /api/albums/posts/{postId}/comments
  // 实际上由于我们简化了逻辑，回复也是往 album_comments 表塞数据，只需关联同样的 album_id 和 class_id
  app.post('/api/albums/posts/:postId/comments', authMiddleware, async (c) => {
    try {
      const user = c.get('user')
      const { content } = await c.req.json() as { content: string }
      const db = c.env.DB

      const classId = await getUserClassId(db, user.id)
      if (!classId) return fail(c, 'FORBIDDEN', { message: '请先认领座位加入班级' })

      // 获取专辑 ID（从 body 或通过查询 postId 获得，这里为了简单要求 Android 在后续逻辑中保证一致性或由后端反查）
      // 在当前的 Android 实现中，LibraryFragment 已经持有 currentAlbumId
      // 我们暂定通过查询该 postId 对应的条目来获取 album_id
      const postId = c.req.param('postId')
      const supabase = getSupabase(c.env)
      
      const { data: parentData } = await supabase
        .from('album_comments')
        .select('album_id')
        .eq('id', postId)
        .single()
      
      const albumId = parentData?.album_id
      if (!albumId) return fail(c, 'NOT_FOUND', { message: '讨论不存在' })

      const { data, error } = await supabase
        .from('album_comments')
        .insert([{ 
          album_id: albumId, 
          user_id: user.supabase_uid, 
          class_id: classId,
          content: content.trim() 
        }])
        .select()

      if (error) throw error

      // 触发 JPush 信号
      sendSocialPush(c, albumId, classId)

      return c.json({ code: 200, message: '回复成功', data: data?.[0] })
    } catch (error: any) {
      return serverError(c, error)
    }
  })

  /**
   * 内部函数：发送 JPush 刷新信号
   */
  function sendSocialPush(c: any, albumId: string, classId: string) {
    if (c.env.JPUSH_APP_KEY && c.env.JPUSH_MASTER_SECRET) {
      c.executionCtx.waitUntil(
        fetch('https://api.jpush.cn/v3/push', {
          method: 'POST',
          headers: {
            'Authorization': `Basic ${btoa(`${c.env.JPUSH_APP_KEY}:${c.env.JPUSH_MASTER_SECRET}`)}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            platform: 'all',
            audience: { tag: [`album_${albumId}_class_${classId}`] },
            message: {
              msg_content: 'refresh_comments',
              extras: { 
                album_id: albumId, 
                class_id: classId,
                action: 'FETCH_NEW' 
              }
            },
            options: { time_to_live: 60 }
          })
        }).catch(err => console.error('JPush error:', err))
      )
    }
  }
}
