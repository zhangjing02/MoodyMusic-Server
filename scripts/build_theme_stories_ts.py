# -*- coding: utf-8 -*-
import json, os, sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

with open(r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts\default_theme_stories.json', 'r', encoding='utf-8') as f:
    stories = json.load(f)

ts_content = """import { Hono } from 'hono'
import type { Bindings } from './types'

type AppType = { Bindings: Bindings; Variables: { user: any; token: string } }

export interface TimelineSection {
  timeLabel: string
  title: string
  sceneStory: string
  emotion: string
  technique: string
  performerNote?: string
}

export interface ThemeStory {
  themeId: string
  issueTag: string
  categoryTag: string
  headline: string
  subtitle: string
  authorDate: string
  heroUrl?: string
  bodyParagraphs: string[]
  quoteEn: string
  quoteZh: string
  scenariosTitle: string
  scenarios: string[]
  benefitsTitle: string
  benefits: string[]
  aboutTitle: string
  aboutDesc: string
  aboutMotto: string
  footerSign: string
  playPillTextActive: string
  playPillTextIdle: string
  isSquareCover: boolean
  posterAspectRatio: number
  timelineTitle: string
  timelineSections: TimelineSection[]
}

export const DEFAULT_THEME_STORIES: Record<string, ThemeStory> = """ + json.dumps(stories, ensure_ascii=False, indent=2) + """;

export function registerThemeStoryRoutes(app: Hono<AppType>) {
  // 1. 获取特定专栏故事 GET /api/theme/story?id=xxx
  app.get('/api/theme/story', async (c) => {
    try {
      const themeId = c.req.query('id') || c.req.query('themeId') || 'snow_cafe_theme'

      // 1. 优先从 R2 存储桶 themes/{themeId}.json 读取
      if (c.env.BUCKET) {
        try {
          const r2Obj = await c.env.BUCKET.get(`themes/${themeId}.json`)
          if (r2Obj) {
            const text = await r2Obj.text()
            const data = JSON.parse(text)
            return c.json({ code: 200, message: 'success', data })
          }
        } catch (r2Err) {
          console.warn('R2 get theme story warning:', r2Err)
        }
      }

      // 2. 其次从 D1 数据库 app_settings (key: theme_story_{themeId}) 读取
      if (c.env.DB) {
        try {
          const row = await c.env.DB.prepare(
            'SELECT value FROM app_settings WHERE key = ?'
          ).bind(`theme_story_${themeId}`).first<{ value: string }>()
          if (row && row.value) {
            const data = JSON.parse(row.value)
            return c.json({ code: 200, message: 'success', data })
          }
        } catch (d1Err) {
          console.warn('D1 get theme story warning:', d1Err)
        }
      }

      // 3. 从内置默认专题字典读取
      const story = DEFAULT_THEME_STORIES[themeId] || DEFAULT_THEME_STORIES['snow_cafe_theme']
      return c.json({ code: 200, message: 'success', data: story })
    } catch (error: any) {
      return c.json({ code: 500, message: error.message }, 500)
    }
  })

  // 2. 管理员保存/更新专栏故事 PUT /api/admin/theme/story
  const handleSaveThemeStory = async (c: any) => {
    try {
      const story = await c.req.json() as ThemeStory
      if (!story || !story.themeId) {
        return c.json({ code: 400, message: '缺少 themeId 参数' }, 400)
      }

      const jsonStr = JSON.stringify(story)
      const now = new Date().toISOString()

      // 1. 保存到 D1
      if (c.env.DB) {
        await c.env.DB.prepare(`
          INSERT INTO app_settings (key, value, updated_at)
          VALUES (?, ?, ?)
          ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        `).bind(`theme_story_${story.themeId}`, jsonStr, now).run()
      }

      // 2. 保存到 R2 themes/{themeId}.json
      if (c.env.BUCKET) {
        try {
          await c.env.BUCKET.put(`themes/${story.themeId}.json`, jsonStr, {
            httpMetadata: {
              contentType: 'application/json; charset=utf-8'
            }
          })
        } catch (r2Err) {
          console.warn('R2 put theme story warning:', r2Err)
        }
      }

      return c.json({
        code: 200,
        message: `成功保存主题 ${story.themeId} 文案`,
        data: story
      })
    } catch (error: any) {
      return c.json({ code: 500, message: error.message }, 500)
    }
  }

  app.post('/api/admin/theme/story', handleSaveThemeStory)
  app.put('/api/admin/theme/story', handleSaveThemeStory)
}
"""

target_file = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\cloudflare-worker\src\theme_stories.ts'
with open(target_file, 'w', encoding='utf-8') as f:
    f.write(ts_content)

print("Generated theme_stories.ts successfully!")
