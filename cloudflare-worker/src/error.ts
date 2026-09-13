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

  CLAIM_ROSTER_NOT_FOUND: { code: 1301, httpStatus: 404, message: '名录不存在' },
  CLAIM_ROSTER_ALREADY_CLAIMED: { code: 1302, httpStatus: 409, message: '该同学已被认领，如有问题请联系班长' },
  CLAIM_SECURITY_CONFIG_INVALID: { code: 1303, httpStatus: 500, message: '安全问题配置错误，请联系管理员' },
  CLAIM_SECURITY_ANSWER_MISMATCH: { code: 1304, httpStatus: 422, message: '安全问题答案不正确' },
  CLAIM_TOKEN_INVALID: { code: 1305, httpStatus: 401, message: 'claim_token 无效' },
  CLAIM_TOKEN_USED: { code: 1306, httpStatus: 409, message: 'claim_token 已被使用' },
  CLAIM_TOKEN_EXPIRED: { code: 1307, httpStatus: 410, message: 'claim_token 已过期，请重新验证' },
  CLAIM_FINALIZE_FAILED: { code: 1308, httpStatus: 500, message: '认领注册失败，请稍后重试' },
  ROSTER_NOT_CLAIMED: { code: 1309, httpStatus: 409, message: '该名录尚未被认领' },
  ROSTER_ALREADY_EXISTS: { code: 1310, httpStatus: 409, message: '该名录已存在' },
  ROSTER_NOT_FOUND_OR_UNCLAIMED: { code: 1311, httpStatus: 404, message: '名录不存在或未认领' },

  ROLE_INVALID: { code: 1401, httpStatus: 400, message: 'role 不合法' },
  QUESTION_ANSWERS_INVALID: { code: 1402, httpStatus: 400, message: '需要提供三道题目的答案数组' },

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

export function serverError(c: Context<any>, error: unknown, key: ErrorKey = 'INTERNAL_ERROR') {
  const message = error instanceof Error ? error.message : String(error)
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

  const message = String(payload?.message || payload?.error || ERROR_DEFINITIONS.INTERNAL_ERROR.message)
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
