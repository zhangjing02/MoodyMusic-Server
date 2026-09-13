/**
 * Worker Upload Handler - V2 (智能匹配版本)
 * 核心原则：
 * 1. 名录（D1）是唯一显示依据
 * 2. 磁盘文件只是"点亮"作用
 * 3. 不创建新的艺人/专辑/歌曲记录
 * 4. 使用智能匹配逻辑匹配歌名
 */

import { Hono } from 'hono';
import type { Bindings } from './types';
import { errorBody, serverError } from './error';

/**
 * NormalizeTitle 归一化标题（从 Go 代码移植）
 * 移除标点符号及空格，统一小写，简繁体统一，用于模糊匹配
 */
function normalizeTitle(s: string): string {
  s = s.toLowerCase().trim();

  // 统一各种标点符号（包括中文标点）
  s = s.replace(/[ \t\n\r\-_—·、，,。．；;：:！!？?（）\(\)\[\]【】《》〈〉]/g, '');

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
    // 只保留中文、英文字母和数字
    const isCJK = (code >= 0x4e00 && code <= 0x9fa5);
    const isEnglish = (code >= 0x0061 && code <= 0x007a); // a-z
    const isDigit = (code >= 0x0030 && code <= 0x0039);   // 0-9

    if (isCJK || isEnglish || isDigit) {
      result += t2sMap[char] || char;
    }
  }
  return result;
}

/**
 * 从文件名提取歌名
 * 支持格式：
 * - 歌曲名-歌手-专辑.mp3
 * - 歌手-序号.歌曲名.mp3
 * - 歌曲名.mp3
 * - 01. 歌曲名-歌手-专辑.mp3
 */
function extractSongTitle(filename: string): string {
  let name = filename.replace(/\.(mp3|MP3)$/, '');

  // 移除开头的序号
  name = name.replace(/^\d+[\.\s]*/, '');

  // 按连字符分割
  const parts = name.split('-').map(p => p.trim());

  if (parts.length >= 3) {
    // 格式：歌曲名-歌手-专辑
    return parts[0].trim();
  } else if (parts.length === 2) {
    // 两种可能：
    // 1. 歌曲名-歌手/专辑
    // 2. 歌手-序号.歌曲名

    // 检查哪一部分包含序号（如 "05."）
    const part0HasNumber = /^\d+\./.test(parts[0]);
    const part1HasNumber = /^\d+\./.test(parts[1]);

    if (part1HasNumber) {
      // 格式：歌手-序号.歌曲名，返回第二部分
      let title = parts[1].replace(/^\d+\.\s*/, ''); // 移除序号
      return title;
    } else if (part0HasNumber) {
      // 格式：序号.歌曲名-歌手，返回第一部分
      let title = parts[0].replace(/^\d+\.\s*/, ''); // 移除序号
      return title;
    } else {
      // 默认：假设是歌曲名-歌手格式
      return parts[0];
    }
  }

  // 没有连字符，移除可能的序号前缀
  name = name.replace(/^\d+[\.\s]*/, '');
  return name.trim();
}

interface MatchContext {
  artistCache?: Map<string, number | null>;
  albumCache?: Map<string, number | null>;
  albumSongsCache?: Map<number, Array<{ id: number; title: string; file_path: string }>>;
}

/**
 * 智能匹配歌曲记录（使用 NormalizeTitle 与内存上下文缓存）
 */
async function findSongMatch(
  db: D1Database,
  artistName: string,
  albumTitle: string,
  songTitle: string,
  ctx?: MatchContext
): Promise<{ song_id: number; title: string; file_path: string } | null> {
  const artistCache = ctx?.artistCache;
  const albumCache = ctx?.albumCache;
  const albumSongsCache = ctx?.albumSongsCache;

  // 1. 查找艺人 (优先查内存缓存，避免重复全表扫描)
  let artistId: number | null | undefined = artistCache?.get(artistName);
  if (artistId === undefined) {
    const artistResult = await db
      .prepare('SELECT id FROM artists WHERE name = ?')
      .bind(artistName)
      .first<{ id: number }>();
    artistId = artistResult ? artistResult.id : null;
    artistCache?.set(artistName, artistId);
  }

  if (!artistId) {
    return null; // 艺人不存在
  }

  // 2. 查找专辑（优先查内存缓存，支持繁简体模糊匹配）
  const albumKey = `${artistId}_${albumTitle}`;
  let albumId: number | null | undefined = albumCache?.get(albumKey);

  if (albumId === undefined) {
    const albumTitleNorm = normalizeTitle(albumTitle);

    // 2.1 首先尝试精确匹配
    let albumResult = await db
      .prepare('SELECT id FROM albums WHERE artist_id = ? AND title = ?')
      .bind(artistId, albumTitle)
      .first<{ id: number }>();

    // 2.2 如果精确匹配失败，使用繁简体模糊匹配
    if (!albumResult) {
      const albums = await db
        .prepare('SELECT id, title FROM albums WHERE artist_id = ?')
        .bind(artistId)
        .all<{ id: number; title: string }>();

      for (const album of albums.results) {
        const dbTitleNorm = normalizeTitle(album.title);
        if (dbTitleNorm === albumTitleNorm ||
            dbTitleNorm.includes(albumTitleNorm) ||
            albumTitleNorm.includes(dbTitleNorm)) {
          albumResult = album;
          break;
        }
      }
    }

    albumId = albumResult ? albumResult.id : null;
    albumCache?.set(albumKey, albumId);
  }

  if (!albumId) {
    return null; // 专辑不存在
  }

  // 3. 智能匹配歌曲 (优先从专辑曲目缓存中比对，整专仅读一次歌曲列表)
  let songsList = albumSongsCache?.get(albumId);
  if (!songsList) {
    const songsRes = await db
      .prepare('SELECT id, title, file_path FROM songs WHERE album_id = ?')
      .bind(albumId)
      .all<{ id: number; title: string; file_path: string }>();
    songsList = songsRes.results || [];
    albumSongsCache?.set(albumId, songsList);
  }

  const songTitleNorm = normalizeTitle(songTitle);

  // 3.1 内存精确比对
  for (const song of songsList) {
    if (song.title === songTitle) {
      return { song_id: song.id, title: song.title, file_path: song.file_path };
    }
  }

  // 3.2 内存模糊比对（完全归一化或包含）
  for (const song of songsList) {
    const dbTitleNorm = normalizeTitle(song.title);
    if (dbTitleNorm === songTitleNorm) {
      return { song_id: song.id, title: song.title, file_path: song.file_path };
    }
    if (songTitleNorm.includes(dbTitleNorm) || dbTitleNorm.includes(songTitleNorm)) {
      if (dbTitleNorm.length >= 2 && songTitleNorm.length >= 2) {
        return { song_id: song.id, title: song.title, file_path: song.file_path };
      }
    }
  }

  return null; // 未找到匹配
}

/**
 * 全局存储写入安全阀 (GLOBAL STORAGE WRITE SAFETY VALVE)
 * 当三桶集群用量逼近极限 (28.2 GB / 30 GB, 94.0%) 时硬性生效，杜绝撑爆账单风险
 */
export const GLOBAL_STORAGE_SAFETY_VALVE_ACTIVE = true;

/**
 * 主上传处理函数
 */
export async function handleUpload(
  request: Request,
  env: Bindings
): Promise<Response> {
  if (GLOBAL_STORAGE_SAFETY_VALVE_ACTIVE) {
    return Response.json({
      code: 423,
      error_key: 'STORAGE_WRITE_LOCKED',
      message: '🚨 存储安全阀已激活：三桶存储用量已达 28.2 GB (94.0%) 警戒红线，全局禁止写入新文件！'
    }, { status: 423 });
  }

  try {
    // 1. 解析表单数据
    const formData = await request.formData();
    const allFiles = formData.getAll('files') as unknown[];
    const files = allFiles.filter((f): f is File => f instanceof File);
    const artistOverride = formData.get('artistOverride') as string;
    const albumOverride = formData.get('albumOverride') as string;
    const titleOverride = formData.get('titleOverride') as string; // 新增：接收标题标签

    if (!files || files.length === 0) {
      return Response.json(errorBody('UPLOAD_NO_FILES'), { status: 400 });
    }

    const validFiles = files.filter((f) => f.size > 0);
    if (validFiles.length === 0) {
      return Response.json(errorBody('UPLOAD_EMPTY_FILES'), { status: 400 });
    }

    const artistName = artistOverride?.trim() || 'Unknown Artist';
    const albumTitle = albumOverride?.trim() || 'Unknown Album';

    console.log(`📤 开始智能匹配上传: 艺人="${artistName}", 专辑="${albumTitle}", 文件数=${validFiles.length}`);

    const results: Array<{
      filename: string;
      song_title: string;
      match: boolean;
      song_id?: number;
      file_path?: string;
      message: string;
    }> = [];

    let matchedCount = 0;
    let unmatchedCount = 0;

    // 2. 逐个处理文件
    // 初始化批量上传内存匹配缓存上下文
    const matchCtx: MatchContext = {
      artistCache: new Map(),
      albumCache: new Map(),
      albumSongsCache: new Map(),
    };

    for (let i = 0; i < validFiles.length; i++) {
      const file = validFiles[i];
      const filename = file.name;

      // 优先使用标题标签，其次才从文件名提取
      let songTitle: string;
      if (titleOverride && titleOverride.trim()) {
        songTitle = titleOverride.trim();
        console.log(`  [${i + 1}/${validFiles.length}] 处理: ${filename} -> 使用标题标签="${songTitle}"`);
      } else {
        songTitle = extractSongTitle(filename);
        console.log(`  [${i + 1}/${validFiles.length}] 处理: ${filename} -> 从文件名提取="${songTitle}"`);
      }

      // 智能匹配歌曲记录（复用 matchCtx 内存缓存，避免重复全表扫描）
      const match = await findSongMatch(env.DB, artistName, albumTitle, songTitle, matchCtx);

      if (!match) {
        // 调试：输出归一化后的结果
        const normalizedTitle = normalizeTitle(songTitle);
        console.log(`    ❌ 匹配失败，归一化结果: "${normalizedTitle}"`);
        console.log(`    提示: 检查专辑名="${albumTitle}" 和歌名="${songTitle}" 是否与数据库匹配`);
      }

      if (match) {
        // 找到匹配：上传文件并点亮
        const r2Key = `music/${artistName}/${albumTitle}/s_${match.song_id}.mp3`;

        try {
          await env.BUCKET.put(r2Key, file.stream(), {
            httpMetadata: {
              contentType: 'audio/mpeg',
            },
          });

          // 更新 D1 的 file_path（点亮歌曲）
          await env.DB.prepare(
            'UPDATE songs SET file_path = ? WHERE id = ?'
          ).bind(r2Key, match.song_id).run();

          matchedCount++;
          results.push({
            filename: filename,
            song_title: match.title,
            match: true,
            song_id: match.song_id,
            file_path: r2Key,
            message: `✅ 点亮成功: ${match.title} (ID: ${match.song_id})`,
          });

          console.log(`    ✅ 匹配成功: ${match.title} -> ${r2Key}`);
        } catch (error: any) {
          results.push({
            filename: filename,
            song_title: songTitle,
            match: false,
            message: `❌ 上传失败: ${error.message}`,
          });
          console.error(`    ❌ 上传失败:`, error);
        }
      } else {
        // 未找到匹配：仍然上传文件，但不会在页面显示
        const r2Key = `music/${artistName}/${albumTitle}/${filename}`;

        try {
          await env.BUCKET.put(r2Key, file.stream(), {
            httpMetadata: {
              contentType: 'audio/mpeg',
            },
          });

          unmatchedCount++;
          results.push({
            filename: filename,
            song_title: songTitle,
            match: false,
            file_path: r2Key,
            message: `⚠️ 未找到匹配（已上传但不会显示）`,
          });

          console.log(`    ⚠️ 未匹配: ${songTitle} -> 已上传但不显示`);
        } catch (error: any) {
          results.push({
            filename: filename,
            song_title: songTitle,
            match: false,
            message: `❌ 上传失败: ${error.message}`,
          });
          console.error(`    ❌ 上传失败:`, error);
        }
      }
    }

    // 3. 返回结果
    return Response.json({
      code: 200,
      message: `上传完成: 匹配 ${matchedCount} 首，未匹配 ${unmatchedCount} 首`,
      data: {
        total: validFiles.length,
        matched: matchedCount,
        unmatched: unmatchedCount,
        results,
      },
    });
  } catch (error: any) {
    console.error('❌ 上传处理失败:', error);
    return Response.json(
      errorBody('UPLOAD_FAILED', { message: `上传失败: ${error.message}` }),
      { status: 500 }
    );
  }
}

/**
 * 注册上传路由
 */
export function registerUploadRoutes(app: Hono<{ Bindings: Bindings; Variables: { user: any; token: string } }>) {
  // 文件上传 API (V2 - 智能匹配版本，上传 MP3)
  app.post('/api/admin/upload', async (c) => {
    const response = await handleUpload(c.req.raw, c.env);
    return response;
  });

  // 检查上传状态
  app.get('/api/admin/upload/status', async (c) => {
    try {
      const { results } = await c.env.DB.prepare(
        'SELECT COUNT(*) as count FROM songs WHERE file_path IS NOT NULL AND file_path != ""'
      ).all();

      return c.json({
        code: 200,
        message: 'success',
        data: {
          total_songs: (results[0] as any)?.count || 0,
        },
      });
    } catch (error: any) {
      return serverError(c, error);
    }
  });

  // 批量纯主键秒级点亮 API (用于定时任务或 R2 同步后高效批处理点亮)
  app.post('/api/admin/songs/batch-light', async (c) => {
    try {
      const body = await c.req.json<{ updates: Array<{ id: number; file_path: string; lrc_path?: string }> }>();
      const updates = body?.updates || [];
      if (!updates || updates.length === 0) {
        return c.json({ code: 400, message: '请传入 updates 数组' }, 400);
      }

      const stmts = [];
      for (const u of updates) {
        if (!u.id || !u.file_path) continue;
        stmts.push(
          c.env.DB.prepare('UPDATE songs SET file_path = ?, lrc_path = ? WHERE id = ?')
            .bind(u.file_path, u.lrc_path || null, u.id)
        );
      }

      if (stmts.length > 0) {
        await c.env.DB.batch(stmts);
      }

      return c.json({
        code: 200,
        message: `成功点亮 ${stmts.length} 首歌曲`,
        data: { count: stmts.length }
      });
    } catch (error: any) {
      return serverError(c, error);
    }
  });

  // 批量熄灭/留白 API (用于下架非录音室版本或问题音频)
  app.post('/api/admin/songs/batch-unlight', async (c) => {
    try {
      const body = await c.req.json<{ song_ids: number[] }>();
      const songIds = body?.song_ids || [];
      if (!songIds || songIds.length === 0) {
        return c.json({ code: 400, message: '请传入 song_ids 数组' }, 400);
      }

      const stmts = [];
      for (const sid of songIds) {
        if (!sid) continue;
        stmts.push(
          c.env.DB.prepare('UPDATE songs SET file_path = NULL, lrc_path = NULL WHERE id = ?')
            .bind(sid)
        );
      }

      if (stmts.length > 0) {
        await c.env.DB.batch(stmts);
      }

      return c.json({
        code: 200,
        message: `成功熄灭/留白 ${stmts.length} 首歌曲`,
        data: { count: stmts.length }
      });
    } catch (error: any) {
      return serverError(c, error);
    }
  });

  // 视觉与图片资产上传 API (新增：支持海报、专辑封面、歌手写真、随笔插图等)
  app.post('/api/admin/assets/upload', async (c) => {
    try {
      const formData = await c.req.formData();
      const rawEntries = formData.getAll('files');
      const files: File[] = [];
      for (const entry of rawEntries) {
        if (typeof entry !== 'string') {
          files.push(entry as File);
        }
      }
      const singleFile = formData.get('file');
      if (singleFile && typeof singleFile !== 'string') {
        files.push(singleFile as File);
      }

      if (files.length === 0) {
        return c.json({ code: 400, message: '请选择要上传的图片文件' }, 400);
      }

      const allFiles = files;

      const category = (formData.get('category') as string) || 'albums';
      const customFilename = (formData.get('filename') as string)?.trim();
      const albumIdStr = formData.get('album_id') as string | null;
      const artistIdStr = formData.get('artist_id') as string | null;

      // 映射存储目录
      let prefix = 'covers/albums';
      if (category === 'hero') prefix = 'covers/hero';
      else if (category === 'albums') prefix = 'covers/albums';
      else if (category === 'artists') prefix = 'artists';
      else if (category === 'articles') prefix = 'articles';
      else if (category === 'welcome') prefix = 'welcome_covers';
      else if (category === 'avatars') prefix = 'avatars';
      else prefix = category;

      const results = [];
      const baseUrl = new URL(c.req.url).origin;

      for (let i = 0; i < allFiles.length; i++) {
        const file = allFiles[i];
        let name = customFilename && allFiles.length === 1 ? customFilename : file.name;
        // 确保带有扩展名
        if (!name.includes('.')) {
          name += '.jpg';
        }

        const r2Key = `${prefix}/${name}`;
        const contentType = file.type || (name.endsWith('.png') ? 'image/png' : 'image/jpeg');

        await c.env.BUCKET.put(r2Key, file.stream(), {
          httpMetadata: {
            contentType: contentType,
            cacheControl: 'public, max-age=2592000',
          },
        });

        const publicUrl = `${baseUrl}/storage/${r2Key}`;

        // 若有关联 album_id，自动更新 D1
        let dbUpdated = false;
        if (albumIdStr && c.env.DB) {
          const albumId = parseInt(albumIdStr);
          if (!isNaN(albumId)) {
            try {
              await c.env.DB.prepare('UPDATE albums SET cover_url = ? WHERE id = ?')
                .bind(r2Key, albumId)
                .run();
              dbUpdated = true;
            } catch (dbErr: any) {
              console.warn(`[AssetUpload] Failed to update album cover_url for album ${albumId}:`, dbErr.message);
            }
          }
        }

        // 若有关联 artist_id，自动更新 D1
        if (artistIdStr && c.env.DB) {
          const artistId = parseInt(artistIdStr);
          if (!isNaN(artistId)) {
            try {
              await c.env.DB.prepare('UPDATE artists SET photo_url = ? WHERE id = ?')
                .bind(r2Key, artistId)
                .run();
              dbUpdated = true;
            } catch (dbErr: any) {
              console.warn(`[AssetUpload] Failed to update artist photo_url for artist ${artistId}:`, dbErr.message);
            }
          }
        }

        results.push({
          key: r2Key,
          filename: name,
          url: publicUrl,
          category,
          size: file.size,
          dbUpdated
        });
      }

      return c.json({
        code: 200,
        message: `成功上传 ${results.length} 个视觉资产`,
        data: {
          total: results.length,
          files: results,
        },
      });
    } catch (error: any) {
      console.error('Asset upload error:', error);
      return serverError(c, error);
    }
  });

  // 获取视觉资产列表 API (用于后台资产库浏览)
  app.get('/api/admin/assets/list', async (c) => {
    try {
      const category = c.req.query('category') || 'all';
      let prefix = '';
      if (category === 'hero') prefix = 'covers/hero/';
      else if (category === 'albums') prefix = 'covers/albums/';
      else if (category === 'artists') prefix = 'artists/';
      else if (category === 'articles') prefix = 'articles/';
      else if (category === 'welcome') prefix = 'welcome_covers/';
      else if (category === 'avatars') prefix = 'avatars/';

      const list = await c.env.BUCKET.list({
        prefix: prefix,
        limit: 100,
      });

      const baseUrl = new URL(c.req.url).origin;
      const items = list.objects
        .filter((obj) => obj.key.match(/\.(jpg|jpeg|png|webp|gif|svg)$/i))
        .map((obj) => ({
          key: obj.key,
          filename: obj.key.split('/').pop() || '',
          size: obj.size,
          uploadedAt: obj.uploaded,
          url: `${baseUrl}/storage/${obj.key}`,
        }));

      return c.json({
        code: 200,
        message: 'success',
        data: {
          total: items.length,
          items,
        },
      });
    } catch (error: any) {
      return serverError(c, error);
    }
  });
}
