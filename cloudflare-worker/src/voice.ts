import { Hono } from 'hono'
import type { Bindings } from './types'
import { fail, serverError } from './error'

type AppType = { Bindings: Bindings; Variables: { user: any; token: string } }

let currentTokenIndex = 0

function getGroqKeys(env: Bindings): string[] {
  const custom = (env as any).GROQ_API_KEYS as string | undefined
  if (custom && custom.trim()) {
    const list = custom.split(',').map(s => s.trim()).filter(Boolean)
    if (list.length > 0) return list
  }
  return []
}

// 带自动轮换与 429/5xx 重试的 Groq API 调用包装器
async function callGroqWithRetry<T>(
  env: Bindings,
  execute: (apiKey: string) => Promise<T>,
  maxRetries: number = 3
): Promise<T> {
  const keys = getGroqKeys(env)
  if (keys.length === 0) {
    throw new Error('未配置 GROQ_API_KEYS 环境变量，请在 Cloudflare 环境变量中设置')
  }
  let lastError: any = null

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const key = keys[currentTokenIndex % keys.length]
    currentTokenIndex = (currentTokenIndex + 1) % keys.length

    try {
      return await execute(key)
    } catch (err: any) {
      lastError = err
      const isRateLimit = err?.message?.includes('429') || err?.status === 429
      const isServerErr = err?.status >= 500
      if (isRateLimit || isServerErr) {
        // 轮换到下一个 token 继续尝试
        continue
      }
      throw err
    }
  }

  throw lastError || new Error('所有 Groq API Token 均暂时不可用')
}

// 繁体转简体简化映射字典
const t2sMap: Record<string, string> = {
  '倫': '伦', '傑': '杰', '華': '华', '劉': '刘', '德': '德',
  '學': '学', '友': '友', '張': '张', '麗': '丽', '君': '君',
  '詠': '咏', '琪': '琪', '葉': '叶', '蒨': '倩', '譚': '谭',
  '麟': '麟', '陳': '陈', '奕': '奕', '迅': '迅', '愛': '爱',
  '來': '来', '後': '后', '為': '为', '與': '与', '時': '时',
  '開': '开', '無': '无', '國': '国', '語': '语', '產': '产',
  '長': '长', '點': '点', '變': '变', '電': '电', '動': '动',
  '聽': '听', '這': '这', '過': '过', '寫': '写', '會': '会',
  '經': '经', '關': '关', '們': '们', '傳': '传', '錄': '录',
  '機': '机', '觀': '观', '場': '场', '實': '实', '驗': '验',
  '斷': '断', '種': '种', '類': '类', '難': '难', '優': '优',
  '態': '态', '響': '响', '應': '应', '調': '调', '轉': '转',
  '遙': '遥', '願': '愿', '義': '义', '務': '务', '標': '标',
  '遠': '远', '選': '选', '邊': '边', '處': '处', '風': '风',
  '頭': '头', '門': '门', '間': '间', '題': '题', '讓': '让',
  '識': '识', '設': '设', '緊': '紧', '現': '现', '規': '规',
  '視': '视', '藝': '艺', '價': '价', '證': '证', '獨': '独',
  '劇': '剧', '歲': '岁', '備': '备', '齊': '齐', '秦': '秦',
  '蘇': '苏', '芮': '芮', '姜': '姜', '恒': '恒', '恆': '恒',
  '趙': '赵', '王': '王', '黃': '黄', '鄭': '郑', '凱': '凯',
  '邰': '邰', '啟': '启', '賢': '贤', '鴻': '鸿', '許': '许',
  '靜': '静', '曉': '晓', '萬': '万', '芳': '芳', '樺': '桦',
  '楊': '杨', '千': '千', '嬅': '嬅', '兒': '儿', '謝': '谢',
  '霆': '霆', '鋒': '锋', '冠': '冠', '希': '希', '樂': '乐',
  '麥': '麦', '浚': '浚', '龍': '龙', '鄧': '邓', '欣': '欣',
  '衛': '卫', '蘭': '兰', '吳': '吴', '寶': '宝', '儀': '仪',
  '廣': '广', '羅': '罗', '達': '达', '濤': '涛', '雲': '云',
  '輝': '辉', '銘': '铭', '溫': '温', '鐘': '钟', '鎮': '镇',
  '請': '请', '播': '播', '放': '放', '歌': '歌', '曲': '曲',
  '專': '专', '輯': '辑', '孫': '孙', '燕': '燕', '姿': '姿',
  '蕭': '萧', '騰': '腾', '謙': '谦', '榮': '荣', '浩': '浩',
  '駒': '驹', '強': '强', '健': '健', '陰': '阴', '陽': '阳',
  '單': '单', '雙': '双', '紅': '红', '綠': '绿', '藍': '蓝',
  '夢': '梦', '話': '话', '說': '说', '傷': '伤', '淚': '泪',
  '離': '离', '歸': '归', '別': '别', '約': '约', '驚': '惊',
  '嘆': '叹', '號': '号', '錯': '错', '戀': '恋', '團': '团',
  '隊': '队', '熱': '热', '飛': '飞', '鳥' : '鸟', '歡': '欢',
  '見': '见', '節': '节', '跡': '迹', '簡': '简', '楓': '枫',
  '親': '亲', '東': '东', '西': '西', '南': '南', '北': '北'
}

function toSimplified(text: string | null | undefined): string {
  if (!text) return ''
  let res = ''
  for (const ch of text) {
    res += t2sMap[ch] || ch
  }
  return res
}

// 常见语音输入同音/谐音曲目与歌手先验纠错表
const commonSongAliases: Record<string, string> = {
  '白话铃': '白桦林', '白话林': '白桦林', '白华林': '白桦林', '百花林': '白桦林',
  '那些花': '那些花儿', '那些花二': '那些花儿',
  '气里香': '七里香', '七里箱': '七里香',
  '东风坡': '东风破',
  '平凡直路': '平凡之路',
  '生如雪花': '生如夏花',
  '蓝脸花': '蓝莲花'
}

const commonArtistAliases: Record<string, string> = {
  '朴素': '朴树', '朴书': '朴树', '璞树': '朴树',
  '周花键': '周华健', '周华建': '周华健', '周化健': '周华健',
  '李宗胜': '李宗盛', '李中盛': '李宗盛',
  '陈易迅': '陈奕迅', '陈异讯': '陈奕迅', '陈一迅': '陈奕迅',
  '张雪友': '张学友', '张学有': '张学友',
  '汪蜂': '汪峰', '汪风': '汪峰',
  '许微': '许巍', '许伟': '许巍',
  '孙燕子': '孙燕姿',
  '邓丽均': '邓丽君',
  '王妃': '王菲',
  '莫问蔚': '莫文蔚', '莫文微': '莫文蔚',
  '田福珍': '田馥甄', '田馥珍': '田馥甄',
  '陶吉吉': '陶喆', '陶哲': '陶喆',
  '五百': '伍佰', '伍百': '伍佰',
  '崔建': '崔健',
  '梁静儒': '梁静茹',
  '林俊捷': '林俊杰',
  '周洁伦': '周杰伦',
  '刘得华': '刘德华',
  '童安哥': '童安格', '童安歌': '童安格'
}

const famousSongToArtist: Record<string, string> = {
  '白桦林': '朴树',
  '生如夏花': '朴树',
  '那些花儿': '朴树',
  '平凡之路': '朴树',
  'NEW BOY': '朴树',
  '其实你不懂我的心': '童安格',
  '明天你是否依然爱我': '童安格',
  '让生命等候': '童安格',
  '忘不了': '童安格',
  '把根留住': '童安格',
  '七里香': '周杰伦',
  '晴天': '周杰伦',
  '青花瓷': '周杰伦',
  '东风破': '周杰伦',
  '告白气球': '周杰伦',
  '十年': '陈奕迅',
  '红豆': '王菲',
  '吻别': '张学友',
  '冰雨': '刘德华',
  '忘情水': '刘德华',
  '朋友': '周华健',
  '山丘': '李宗盛',
  '蓝莲花': '许巍'
}

export interface PlayQueueItemDto {
  songTitle: string
  artistName: string
  albumTitle: string
  coverUrl: string
  audioUrl: string
  lrcPath?: string | null
}

export interface VoiceDispatchResponseData {
  recognizedText: string
  intentSummary: string
  playType: string
  playlist: PlayQueueItemDto[]
  startIndex: number
}

function ensureAbsoluteUrl(path: string | null | undefined, baseUrl: string): string {
  if (!path) return ''
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  if (path.startsWith('/')) return `${baseUrl}${path}`
  return `${baseUrl}/${path}`
}

export function registerVoiceRoutes(app: Hono<AppType>) {

  /**
   * POST /api/voice/dispatch
   * 一步式端到端语音中继调度：
   * 1. 接收录音音频 (multipart) 或纯文本 (json)
   * 2. 调用 Groq Whisper 转录
   * 3. 调用 Groq LLM 提取意图与智能纠错
   * 4. 在 Cloudflare D1 毫秒级查库组装播放队列
   * 5. 返回绝对 CDN 直链播放清单
   */
  app.post('/api/voice/dispatch', async (c) => {
    try {
      const contentType = c.req.header('content-type') || ''
      let recognizedText = ''
      const baseUrl = new URL(c.req.url).origin

      if (contentType.includes('multipart/form-data')) {
        const formData = await c.req.parseBody()
        const audioFile = formData['file'] as any

        if (!audioFile) {
          return c.json({ code: 400, message: '未接收到音频文件', data: null }, 400)
        }

        // 调用 Groq Whisper 转录
        const whisperPrompt = '华语流行音乐点歌系统。常见歌手与经典名曲：朴树、白桦林、生如夏花、那些花儿、平凡之路、周杰伦、晴天、七里香、青花瓷、花海、陈奕迅、十年、富士山下、张学友、吻别、刘德华、冰雨、王菲、红豆、李宗盛、山丘、莫文蔚、孙燕姿、遇见、林俊杰、江南、五月天、伍佰、挪威的森林、罗大佑、童年、崔健、许巍、蓝莲花、汪峰、童安格、陶喆、王力宏、民谣、摇滚、流行金曲点播。'

        recognizedText = await callGroqWithRetry(c.env, async (apiKey) => {
          const reqBody = new FormData()
          // 兼容 Blob / File
          if (audioFile instanceof Blob) {
            reqBody.append('file', audioFile, 'voice.m4a')
          } else {
            reqBody.append('file', audioFile)
          }
          reqBody.append('model', 'whisper-large-v3')
          reqBody.append('language', 'zh')
          reqBody.append('prompt', whisperPrompt)

          const res = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${apiKey}`
            },
            body: reqBody
          })

          if (!res.ok) {
            const errText = await res.text()
            const err = new Error(`Groq Whisper HTTP ${res.status}: ${errText}`)
            ;(err as any).status = res.status
            throw err
          }

          const data = await res.json() as { text: string }
          return (data.text || '').trim()
        })
      } else {
        // JSON 请求 (纯文本检索场景)
        const json = await c.req.json().catch(() => ({}))
        recognizedText = (json.text || json.query || '').trim()
      }

      if (!recognizedText) {
        return c.json({
          code: 400,
          message: '未能识别到清晰的语音指令，请长按说话',
          data: null
        }, 400)
      }

      // 步骤 2: Groq LLM (llama-3.3-70b-versatile) 意图解析与智能纠偏
      const systemPrompt = `你是一个专业的华语流行音乐意图分析与语音纠错助手。用户通过语音点歌，说出想听的歌曲、歌手、专辑或情绪。
请将用户的输入精准解析为严格的 JSON 格式：
{
  "intent": "song" | "album" | "artist" | "mood",
  "artist": "歌手名或null",
  "title": "歌曲名或null",
  "album": "专辑名或null",
  "reply": "给用户的一句话友好回复"
}
【核心规则】：
1. 音乐库统一采用中国大陆【简体中文】存储，输出的 artist、title、album 必须全部转换为标准简体中文（例如：周杰伦、陈奕迅、刘德华、张学友、朋友、告白气球、朴树、白桦林、童安格、陶喆、王力宏），严禁输出繁体字。
2. 语音同音近音纠错：
   - “白话铃”、“白话林”、“百花林” -> 歌曲《白桦林》（歌手：朴树）
   - “朴素”、“朴书” -> 歌手“朴树”
   - “周花键”、“周华建” -> 歌手“周华健”
   - “那些花”、“那些花二” -> 歌曲《那些花儿》（歌手：朴树）
   - “气里香”、“七里箱” -> 歌曲《七里香》（歌手：周杰伦）
   - “东风坡” -> 歌曲《东风破》（歌手：周杰伦）
   - “平凡直路” -> 歌曲《平凡之路》（歌手：朴树）
   - “陈异讯”、“陈易迅” -> 歌手“陈奕迅”
   - “生如雪花” -> 歌曲《生如夏花》（歌手：朴树）
   - “蓝脸花” -> 歌曲《蓝莲花》（歌手：许巍）
   - 若用户仅说了知名曲目（如《白桦林》、《晴天》、《十年》、《其实你不懂我的心》），且原唱广为人知，请将 artist 自动填充为原唱歌手，方便系统直接定位。
3. 严格只输出纯 JSON，绝不要包含 Markdown 代码块或额外文字。`

      const intentJsonStr = await callGroqWithRetry(c.env, async (apiKey) => {
        const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${apiKey}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            model: 'qwen/qwen3.8-27b',
            messages: [
              { role: 'system', content: systemPrompt },
              { role: 'user', content: recognizedText }
            ],
            temperature: 0.1,
            response_format: { type: 'json_object' }
          })
        })

        if (!res.ok) {
          const errText = await res.text()
          const err = new Error(`Groq LLM HTTP ${res.status}: ${errText}`)
          ;(err as any).status = res.status
          throw err
        }

        const data = await res.json() as any
        return data.choices?.[0]?.message?.content || '{}'
      })

      let parsedIntent: {
        intent?: string
        artist?: string | null
        title?: string | null
        album?: string | null
        reply?: string | null
      } = {}

      try {
        const cleanJson = intentJsonStr.replace(/```json/g, '').replace(/```/g, '').trim()
        parsedIntent = JSON.parse(cleanJson)
      } catch (e) {
        parsedIntent = { intent: 'song', title: recognizedText }
      }

      // 字段简繁转换与先验纠正
      let rawArtist = toSimplified(parsedIntent.artist?.trim() || null)
      let rawTitle = toSimplified(parsedIntent.title?.trim() || null)
      let rawAlbum = toSimplified(parsedIntent.album?.trim() || null)
      const intentType = (parsedIntent.intent || 'song').toLowerCase()

      if (rawTitle && commonSongAliases[rawTitle]) {
        rawTitle = commonSongAliases[rawTitle]
      }
      if (rawArtist && commonArtistAliases[rawArtist]) {
        rawArtist = commonArtistAliases[rawArtist]
      }

      // 华语经典关联
      if (rawTitle && famousSongToArtist[rawTitle] && (!rawArtist || !recognizedText.includes(rawArtist))) {
        rawArtist = famousSongToArtist[rawTitle]
      }

      // 步骤 3: 在 Cloudflare D1 执行带索引的安全检索
      let playlist: PlayQueueItemDto[] = []
      let intentSummary = ''
      let playType = intentType

      // 场景 1: 单曲查询
      if (intentType === 'song') {
        const searchTitle = rawTitle || recognizedText
        let songRows: any[] = []

        if (rawArtist) {
          // 联合歌手 + 曲名检索
          const stmt = c.env.DB.prepare(`
            SELECT s.title as song_title, s.file_path, s.lrc_path, 
                   al.title as album_title, al.cover_url, 
                   a.name as artist_name
            FROM songs s
            JOIN albums al ON s.album_id = al.id
            JOIN artists a ON al.artist_id = a.id
            WHERE (s.title LIKE ? OR s.title LIKE ?)
              AND (a.name LIKE ? OR a.name LIKE ?)
              AND s.file_path IS NOT NULL AND s.file_path != ''
            LIMIT 5
          `).bind(`%${searchTitle}%`, `%${toSimplified(searchTitle)}%`, `%${rawArtist}%`, `%${toSimplified(rawArtist)}%`)

          const res = await stmt.all()
          songRows = res.results || []
        }

        if (songRows.length === 0) {
          // 单独按曲名模糊搜索
          const stmt = c.env.DB.prepare(`
            SELECT s.title as song_title, s.file_path, s.lrc_path, 
                   al.title as album_title, al.cover_url, 
                   a.name as artist_name
            FROM songs s
            JOIN albums al ON s.album_id = al.id
            JOIN artists a ON al.artist_id = a.id
            WHERE (s.title LIKE ? OR s.title LIKE ?)
              AND s.file_path IS NOT NULL AND s.file_path != ''
            LIMIT 10
          `).bind(`%${searchTitle}%`, `%${toSimplified(searchTitle)}%`)

          const res = await stmt.all()
          songRows = res.results || []
        }

        if (songRows.length > 0) {
          const s = songRows[0]
          playlist.push({
            songTitle: toSimplified(s.song_title),
            artistName: toSimplified(s.artist_name),
            albumTitle: toSimplified(s.album_title),
            coverUrl: ensureAbsoluteUrl(s.cover_url, baseUrl),
            audioUrl: ensureAbsoluteUrl(s.file_path, baseUrl),
            lrcPath: s.lrc_path ? ensureAbsoluteUrl(s.lrc_path, baseUrl) : null
          })
          intentSummary = `已为您播放：${playlist[0].artistName} -《${playlist[0].songTitle}》`
        }
      }

      // 场景 2: 歌手专属电台
      else if (intentType === 'artist' && rawArtist) {
        const stmt = c.env.DB.prepare(`
          SELECT s.title as song_title, s.file_path, s.lrc_path, 
                 al.title as album_title, al.cover_url, 
                 a.name as artist_name
          FROM songs s
          JOIN albums al ON s.album_id = al.id
          JOIN artists a ON al.artist_id = a.id
          WHERE (a.name LIKE ? OR a.name LIKE ?)
            AND s.file_path IS NOT NULL AND s.file_path != ''
          LIMIT 100
        `).bind(`%${rawArtist}%`, `%${toSimplified(rawArtist)}%`)

        const res = await stmt.all()
        const rows = (res.results || []) as any[]
        if (rows.length > 0) {
          // 随机挑选前 20 首
          const shuffled = rows.sort(() => 0.5 - Math.random()).slice(0, 20)
          playlist = shuffled.map(s => ({
            songTitle: toSimplified(s.song_title),
            artistName: toSimplified(s.artist_name),
            albumTitle: toSimplified(s.album_title),
            coverUrl: ensureAbsoluteUrl(s.cover_url, baseUrl),
            audioUrl: ensureAbsoluteUrl(s.file_path, baseUrl),
            lrcPath: s.lrc_path ? ensureAbsoluteUrl(s.lrc_path, baseUrl) : null
          }))
          intentSummary = `为您开启：${rawArtist} 专属精选电台（共 ${playlist.length} 首）`
        }
      }

      // 场景 3: 专辑整专
      else if (intentType === 'album' && (rawAlbum || rawTitle)) {
        const searchAlbum = rawAlbum || rawTitle || ''
        const stmt = c.env.DB.prepare(`
          SELECT s.title as song_title, s.file_path, s.lrc_path, s.track_index,
                 al.title as album_title, al.cover_url, 
                 a.name as artist_name
          FROM songs s
          JOIN albums al ON s.album_id = al.id
          JOIN artists a ON al.artist_id = a.id
          WHERE (al.title LIKE ? OR al.title LIKE ?)
            AND s.file_path IS NOT NULL AND s.file_path != ''
          ORDER BY s.track_index ASC
          LIMIT 50
        `).bind(`%${searchAlbum}%`, `%${toSimplified(searchAlbum)}%`)

        const res = await stmt.all()
        const rows = (res.results || []) as any[]
        if (rows.length > 0) {
          playlist = rows.map(s => ({
            songTitle: toSimplified(s.song_title),
            artistName: toSimplified(s.artist_name),
            albumTitle: toSimplified(s.album_title),
            coverUrl: ensureAbsoluteUrl(s.cover_url, baseUrl),
            audioUrl: ensureAbsoluteUrl(s.file_path, baseUrl),
            lrcPath: s.lrc_path ? ensureAbsoluteUrl(s.lrc_path, baseUrl) : null
          }))
          intentSummary = `正在播放专辑：《${playlist[0].albumTitle}》（全 ${playlist.length} 首）`
        }
      }

      // 场景 4: 心情漫游或未命中兜底 (随机抽取 10 首已点亮精选曲目)
      if (playlist.length === 0) {
        playType = 'mood'
        const stmt = c.env.DB.prepare(`
          SELECT s.title as song_title, s.file_path, s.lrc_path, 
                 al.title as album_title, al.cover_url, 
                 a.name as artist_name
          FROM songs s
          JOIN albums al ON s.album_id = al.id
          JOIN artists a ON al.artist_id = a.id
          WHERE s.file_path IS NOT NULL AND s.file_path != ''
          LIMIT 80
        `)
        const res = await stmt.all()
        const rows = (res.results || []) as any[]
        if (rows.length > 0) {
          const shuffled = rows.sort(() => 0.5 - Math.random()).slice(0, 10)
          playlist = shuffled.map(s => ({
            songTitle: toSimplified(s.song_title),
            artistName: toSimplified(s.artist_name),
            albumTitle: toSimplified(s.album_title),
            coverUrl: ensureAbsoluteUrl(s.cover_url, baseUrl),
            audioUrl: ensureAbsoluteUrl(s.file_path, baseUrl),
            lrcPath: s.lrc_path ? ensureAbsoluteUrl(s.lrc_path, baseUrl) : null
          }))
        }
        intentSummary = parsedIntent.reply || `为您挑选了 ${playlist.length} 首精选经典曲目随心听`
      }

      const responseData: VoiceDispatchResponseData = {
        recognizedText,
        intentSummary,
        playType,
        playlist,
        startIndex: 0
      }

      return c.json({
        code: 200,
        message: 'success',
        data: responseData
      })
    } catch (error: any) {
      return serverError(c, error)
    }
  })
}
