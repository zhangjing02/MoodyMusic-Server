import type { Context } from 'hono'

type ErrorDefinition = {
  code: number
  httpStatus: number
  message: string
}

export const ERROR_DEFINITIONS = {
  INVALID_REQUEST_BODY: { code: 1001, httpStatus: 400, message: '请求体格式错误' },
  MISSING_PARAMETER: { code: 1002, httpStatus: 400, message: '缺少必要参数' },
  INVALID_PARAMETER: { code: 1003, httpStatus: 400, message: '参数格式错误' },
  INVALID_FIELD: { code: 1004, httpStatus: 400, message: '字段值不合法' },
  NO_VALID_FIELDS: { code: 1005, httpStatus: 400, message: '没有可更新的有效字段' },
  INTERNAL_ERROR: { code: 9000, httpStatus: 500, message: '服务器内部错误' },

  UNAUTHENTICATED: { code: 1101, httpStatus: 401, message: '未登录，请先登录' },
  TOKEN_INVALID: { code: 1102, httpStatus: 401, message: 'Token 无效' },
  TOKEN_EXPIRED_OR_INVALID: { code: 1103, httpStatus: 401, message: 'Token 已过期或无效，请重新登录' },
  ADMIN_FORBIDDEN: { code: 1104, httpStatus: 403, message: '需要管理员权限' },
  MASTER_FORBIDDEN: { code: 1105, httpStatus: 403, message: '需要最高管理员权限' },
  FORBIDDEN: { code: 1106, httpStatus: 403, message: '权限不足' },
  NOT_FOUND: { code: 1600, httpStatus: 404, message: '未找到请求的资源' },

  LOGIN_FAILED: { code: 1201, httpStatus: 401, message: '用户名或密码错误' },
  REFRESH_TOKEN_INVALID: { code: 1202, httpStatus: 401, message: '刷新失败，请重新登录' },
  USER_NOT_FOUND: { code: 1203, httpStatus: 404, message: '用户不存在' },
  EMAIL_INVALID: { code: 1204, httpStatus: 400, message: '邮箱格式不正确' },
  SEND_CODE_FAILED: { code: 1212, httpStatus: 400, message: '验证码发送失败，请稍后重试' },
  VERIFY_CODE_FAILED: { code: 1213, httpStatus: 400, message: '验证码无效或已过期' },
  RATE_LIMITED: { code: 1214, httpStatus: 429, message: '请求过于频繁，请稍后再试' },
  EMAIL_ALREADY_REGISTERED: { code: 1215, httpStatus: 409, message: '该邮箱已被注册' },
  INVALID_USERNAME: { code: 1216, httpStatus: 400, message: '用户名需在 2-20 位字符，支持中文汉字、英文字母、数字与下划线' },
  USERNAME_ALREADY_EXISTS: { code: 1217, httpStatus: 409, message: '该用户名已被占用，请换一个用户名' },
  DEFAULT_USERNAME_TAKEN: { code: 1218, httpStatus: 409, message: '默认用户名已被占用，请手动输入专属用户名' },
  RESET_EMAIL_NOT_BOUND: { code: 1205, httpStatus: 403, message: '该账号未绑定邮箱，请联系班长（管理员）重置密码' },
  RESET_REQUEST_NOT_FOUND: { code: 1206, httpStatus: 401, message: '未找到有效的重置请求，请重新申请' },
  RESET_CODE_EXPIRED: { code: 1207, httpStatus: 410, message: '验证码已过期，请重新申请' },
  RESET_CODE_MISMATCH: { code: 1208, httpStatus: 422, message: '验证码不正确' },
  PASSWORD_HASH_INVALID: { code: 1209, httpStatus: 400, message: '密码哈希格式错误' },
  PASSWORD_UPDATE_FAILED: { code: 1210, httpStatus: 500, message: '密码更新失败，请稍后重试' },
  SESSION_CREATE_FAILED: { code: 1211, httpStatus: 500, message: '登录失败：未获取到会话信息' },

  ROLE_INVALID: { code: 1401, httpStatus: 400, message: 'role 不合法' },

  STORAGE_OBJECT_KEY_MISSING: { code: 1501, httpStatus: 400, message: '缺少对象 key' },
  STORAGE_OBJECT_NOT_FOUND: { code: 1502, httpStatus: 404, message: '对象不存在' },

  QUERY_MISSING: { code: 1601, httpStatus: 400, message: '缺少查询参数' },
  ARTIST_NOT_FOUND: { code: 1602, httpStatus: 404, message: '艺人不存在' },
  ALBUM_NOT_FOUND: { code: 1603, httpStatus: 404, message: '专辑不存在' },
  SONG_NOT_FOUND: { code: 1604, httpStatus: 404, message: '歌曲不存在' },

  UPLOAD_NO_FILES: { code: 1701, httpStatus: 400, message: '未检测到上传的文件' },
  UPLOAD_EMPTY_FILES: { code: 1702, httpStatus: 400, message: '没有有效的文件' },
  UPLOAD_FAILED: { code: 1703, httpStatus: 500, message: '上传失败' },
} as const satisfies Record<string, ErrorDefinition>

export type ErrorKey = keyof typeof ERROR_DEFINITIONS

type ErrorOptions = {
  message?: string
  details?: Record<string, unknown>
  httpStatus?: number
}

export function errorBody(key: ErrorKey | string, options: ErrorOptions = {}) {
  const definition = (ERROR_DEFINITIONS as any)[key] || {
    code: 1003,
    httpStatus: 400,
    message: options.message || '操作失败'
  }
  return {
    code: definition.code,
    error_key: key,
    message: options.message || definition.message,
    ...(options.details ? { details: options.details } : {}),
  }
}

export function fail(c: Context<any>, key: ErrorKey | string, options: ErrorOptions = {}) {
  const definition = (ERROR_DEFINITIONS as any)[key] || {
    code: 1003,
    httpStatus: 400,
    message: options.message || '操作失败'
  }
  return c.json(
    errorBody(key, options),
    (options.httpStatus || definition.httpStatus) as any
  )
}

export function sanitizeErrorMessage(message?: string): string {
  if (!message) return '服务器异常，请稍后重试'
  const lower = message.toLowerCase()
  if (
    lower.includes('d1_error') ||
    lower.includes('row read limit') ||
    lower.includes('exceeded d1') ||
    lower.includes('sqlite') ||
    lower.includes('sql') ||
    lower.includes('database is locked') ||
    lower.includes('no such table') ||
    lower.includes('no such column') ||
    lower.includes('syntax error') ||
    lower.includes('constraint failed') ||
    lower.includes('internal server error') ||
    lower.includes('cloudflare') ||
    lower.includes('worker') ||
    lower.includes('fetch failed') ||
    lower.includes('network error')
  ) {
    return '服务器异常，请稍后重试'
  }
  return message
}

export function serverError(c: Context<any>, arg1: unknown, arg2?: any) {
  if (arg1 instanceof Error) {
    console.error('[ServerError]', arg1)
  } else {
    console.error('[ServerError]', arg1, arg2)
  }

  if (typeof arg1 === 'string') {
    const key = arg1 as ErrorKey
    const rawMessage = arg2?.error || arg2?.message || (typeof arg2 === 'string' ? arg2 : undefined)
    const message = sanitizeErrorMessage(rawMessage)
    return fail(c, key, { message })
  }
  const rawMessage = arg1 instanceof Error ? arg1.message : String(arg1)
  const message = sanitizeErrorMessage(rawMessage)
  const key = (arg2 as ErrorKey) || 'INTERNAL_ERROR'
  return fail(c, key, { message })
}

export async function normalizeLegacyErrorResponse(response: Response): Promise<Response> {
  if (response.status < 400) return response

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) return response

  const clone = response.clone()
  let payload: any
  try {
    payload = await clone.json()
  } catch {
    return response
  }

  if (payload?.error_key && typeof payload.code === 'number') {
    return response
  }

  const rawMessage = String(payload?.message || payload?.error || ERROR_DEFINITIONS.INTERNAL_ERROR.message)
  const message = sanitizeErrorMessage(rawMessage)
  const key = inferErrorKey(response.status, message)
  const nextBody = errorBody(key, { message })
  const headers = new Headers(response.headers)
  headers.delete('content-length')

  return new Response(JSON.stringify(nextBody), {
    status: response.status,
    headers,
  })
}

function inferErrorKey(status: number, message: string): ErrorKey {
  const lower = message.toLowerCase()

  if (lower.includes('song not found') || message.includes('未找到歌曲')) return 'SONG_NOT_FOUND'
  if (lower.includes('album not found') || message.includes('未找到专辑')) return 'ALBUM_NOT_FOUND'
  if (message.includes('未找到艺人')) return 'ARTIST_NOT_FOUND'
  if (lower.includes('object not found')) return 'STORAGE_OBJECT_NOT_FOUND'
  if (lower.includes('no valid') || message.includes('无有效')) return 'NO_VALID_FIELDS'
  if (lower.includes('missing') || message.includes('缺少') || message.includes('参数')) return 'MISSING_PARAMETER'
  if (status === 401) return 'TOKEN_EXPIRED_OR_INVALID'
  if (status === 403) return 'ADMIN_FORBIDDEN'
  if (status === 404) return 'ALBUM_NOT_FOUND'
  if (status === 409) return 'INVALID_FIELD'
  if (status === 400) return 'INVALID_PARAMETER'
  return 'INTERNAL_ERROR'
}
