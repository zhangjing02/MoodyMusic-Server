import { Hono } from 'hono'

export async function sendPushMessage(env: any, payload: any) {
  const appKey = env?.JPUSH_APP_KEY || '0c279e2a4de3471067c84370'
  const masterSecret = env?.JPUSH_MASTER_SECRET || '3cf5ad961ce519f14d757f43'
  const auth = btoa(`${appKey}:${masterSecret}`)

  const response = await fetch('https://api.jpush.cn/v3/push', {
    method: 'POST',
    headers: {
      'Authorization': `Basic ${auth}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  })

  return await response.json()
}

export function registerPushRoutes(app: Hono<any>) {
  // Push message to Android devices via JPush REST API
  app.post('/api/admin/push/message', async (c) => {
    try {
      const body = await c.req.json()
      
      // Construct JPush API payload
      const payload = {
        platform: "android",
        audience: body.audience || "all",
        notification: {
          android: {
            alert: body.message || "这是一条测试推送消息",
            title: body.title || "MOODY Music",
            extras: body.extras || {}
          }
        },
        message: body.silent_message ? {
          msg_content: body.silent_message,
          extras: body.extras || {}
        } : undefined
      }

      const result = await sendPushMessage(c.env, payload)

      return c.json({
        code: 200,
        message: 'Push successful',
        data: result
      })
    } catch (error: any) {
      console.error('Push exception:', error)
      return c.json({ code: 500, message: error.message }, 500)
    }
  })
}
