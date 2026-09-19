/**
 * APP LOGIC
 * 负责处理点击、滚动、渲染等逻辑
 * 数据来源: src/js/data.js
 */

// ==================== 本地存储常量 ====================
const STORAGE_KEY = 'music_archive_local_songs';
const STORAGE_VERSION_KEY = 'music_archive_version';
const STORAGE_VERSION = '1.0';

// ==================== IndexedDB 数据库 ====================
const DB_NAME = 'MusicArchiveDB';
const DB_VERSION = 1;
const STORE_NAME = 'audioFiles';

const API_CONFIG = {
    apiBase: window.MOODY_CONFIG?.API_BASE || 'https://m-api.changgepd.ccwu.cc',
    itunes: { enabled: false }
};

const API_BASE = API_CONFIG.apiBase;
window.API_BASE = API_BASE;

// ==================== 界面常数 (用户可自定义) ====================
// [Modified] 欢迎页背景图库改为动态获取，初始为空，通过 fetch 更新
let dynamicWelcomeImages = [];

/**
 * 获取欢迎页背景图列表并缓存
 */
async function fetchWelcomeImages() {
    try {
        const resp = await fetch(`${API_BASE}/api/welcome-images`);
        if (!resp.ok) throw new Error('Fetch failed');
        const result = await resp.json();
        if (result.code === 200 && Array.isArray(result.data)) {
            dynamicWelcomeImages = result.data;
            console.log(`[UI] 加载了 ${dynamicWelcomeImages.length} 张动态背景图`);
        }
    } catch (err) {
        console.warn('[UI] 动态背景图加载失败，回退到默认图', err);
    }
}

/**
 * 获取欢迎页背景图 (随机挑选)
 */
function getWelcomeBackground() {
    if (!dynamicWelcomeImages || dynamicWelcomeImages.length === 0) {
        return 'src/assets/images/landing_cover.png';
    }
    const randomIndex = Math.floor(Math.random() * dynamicWelcomeImages.length);
    return `${API_BASE}/storage/welcome_covers/${dynamicWelcomeImages[randomIndex]}`;
}

const CATEGORIES = ['华语', '欧美', '港台', '摇滚', '民谣', 'R&B', '音乐综艺'];

console.log("%c [MOODY] 系统就绪 (v12.58 - 最终修正镜像名)", "font-size: 14px; color: #d4af37; font-weight: bold; background: #1a1a1a; padding: 4px 8px; border-radius: 4px;");

// [V12.40] 终极核心名识别逻辑 (深度治理版：涵盖更多简繁、组合别名、后缀剔除)
const getCoreName = (name) => {
    if (!name) return "";

    // 1. 扩容映射表 (重点补全用户反馈的死角)
    const stMap = {
        "陳奕迅": "陈奕迅", "張惠妹": "张惠妹", "鄧紫棋": "邓紫棋", "范曉萱": "范晓萱",
        "林俊傑": "林俊杰", "動力火車": "动力火车", "張靚穎": "张靓颖",
        "飛兒樂團": "飞儿乐团", "飛兒乐团": "飞儿乐团", "F.I.R": "飞儿乐团", "FIR": "飞儿乐团",
        "費玉清": "费玉清", "费玉清": "费玉清", "順子": "顺子",
        "孫燕姿": "孙燕姿", "伍佰": "伍佰", "五百": "伍佰", "許嵩": "许嵩",
        "姜育恆": "姜育恒", "李聖傑": "李圣杰", "梁靜茹": "梁静茹",
        "羅大佑": "罗大佑", "南拳媽媽": "南拳妈妈", "陶喆": "陶喆",
        "David Tao": "陶喆", "Jay Chou": "周杰伦",
        // 12.40 新增反馈死角
        "黃品源": "黄品源", "齊秦": "齐秦", "齊豫": "齐豫", "羽·泉": "羽泉",
        "伍佰 & China Blue": "伍佰", "伍佰&China Blue": "伍佰", "羽泉": "羽泉",
        "張震嶽": "张震岳", "張學友": "张学友",
        // 12.45 处理用户反馈死角 (简繁/重影)
        "徐佳瑩": "徐佳莹", "徐佳莹": "徐佳莹",
        "鄧麗君": "邓丽君", "邓丽君": "邓丽君",
        "鄧紫棋": "邓紫棋", "邓紫棋": "邓紫棋",
        "曹格": "曹格", "Gary Chaw": "曹格",
        "Beyond": "Beyond"
    };

    // 2. 预处理：剔除已知组合后缀、feat后缀
    let core = name.split(/[\(\（]/)[0].trim();
    core = core.split(/\s*&\s*China\s*Blue/i)[0].trim();
    core = core.split(/\s+feat\.?\s+/i)[0].trim();

    // 3. 执行映射过滤
    core = stMap[core] || core;

    // 4. 彻底移除所有标点符号、空格、零宽子符、中间点 (\u200B, · 等)
    core = core.replace(/[.,·\/#!$%\^&\*;:{}=\-_`~()？。，、！…—\s\u200B-\u200D\uFEFF]/g, "");

    return core.trim().toLowerCase();
};


/**
 * 打开 IndexedDB 数据库
 */
function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onerror = () => {
            console.error('IndexedDB 打开失败:', request.error);
            reject(request.error);
        };

        request.onsuccess = () => {
            console.log('✓ IndexedDB 已打开');
            resolve(request.result);
        };

        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                const objectStore = db.createObjectStore(STORE_NAME, { keyPath: 'songName' });
                objectStore.createIndex('artistName', 'artistName', { unique: false });
                console.log('✓ IndexedDB 对象存储已创建');
            }
        };
    });
}

/**
 * 保存音频文件到 IndexedDB
 */
async function saveAudioToIndexedDB(songName, artistName, fileName, audioBlob) {
    try {
        const db = await openDB();
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const objectStore = transaction.objectStore(STORE_NAME);

        const record = {
            songName: songName,
            artistName: artistName,
            fileName: fileName,
            audioBlob: audioBlob,
            audioUrl: null, // 懒加载：只在需要时生成 DataURL
            uploadDate: new Date().toISOString()
        };

        const request = objectStore.put(record);

        return new Promise((resolve, reject) => {
            request.onsuccess = () => {
                console.log(`✓ 已保存到 IndexedDB: ${songName}`);
                resolve(true);
            };
            request.onerror = () => {
                console.error('保存到 IndexedDB 失败:', request.error);
                reject(request.error);
            };
        });
    } catch (error) {
        console.error('IndexedDB 保存失败:', error);
        throw error;
    }
}

/**
 * 从 IndexedDB 加载所有音频文件
 */
async function loadAllAudioFromIndexedDB() {
    try {
        console.log('正在打开 IndexedDB...');
        const db = await openDB();
        console.log('IndexedDB 已打开，开始读取音频文件...');

        const transaction = db.transaction([STORE_NAME], 'readonly');
        const objectStore = transaction.objectStore(STORE_NAME);
        const request = objectStore.getAll();

        return new Promise((resolve, reject) => {
            request.onsuccess = async () => {
                const records = request.result;
                console.log(`✓ 从 IndexedDB 读取到 ${records.length} 个音频文件`);

                // 将 Blob 转换为 DataURL
                const results = [];
                for (const record of records) {
                    console.log(`正在转换: ${record.songName} - Blob 大小: ${record.audioBlob.size} bytes`);
                    const audioUrl = await blobToDataURL(record.audioBlob);
                    results.push({
                        songName: record.songName,
                        artistName: record.artistName,
                        fileName: record.fileName,
                        audioUrl: audioUrl,
                        uploadDate: record.uploadDate
                    });
                    console.log(`✓ 转换完成: ${record.songName}`);
                }
                console.log(`✓ 所有音频文件转换完成，共 ${results.length} 个`);
                resolve(results);
            };
            request.onerror = () => {
                console.error('从 IndexedDB 加载失败:', request.error);
                reject(request.error);
            };
        });
    } catch (error) {
        console.error('IndexedDB 加载失败:', error);
        return [];
    }
}

/**
 * 从 IndexedDB 删除音频文件
 */
async function deleteAudioFromIndexedDB(songName) {
    try {
        const db = await openDB();
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const objectStore = transaction.objectStore(STORE_NAME);
        const request = objectStore.delete(songName);

        return new Promise((resolve, reject) => {
            request.onsuccess = () => {
                console.log(`✓ 已从 IndexedDB 删除: ${songName}`);
                resolve(true);
            };
            request.onerror = () => {
                console.error('从 IndexedDB 删除失败:', request.error);
                reject(request.error);
            };
        });
    } catch (error) {
        console.error('IndexedDB 删除失败:', error);
        throw error;
    }
}

/**
 * 将 Blob 转换为 DataURL
 */
function blobToDataURL(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

/**
 * 获取 IndexedDB 使用情况
 */
async function getIndexedDBUsage() {
    try {
        if (navigator.storage && navigator.storage.estimate) {
            const estimate = await navigator.storage.estimate();
            const usageMB = (estimate.usage / (1024 * 1024)).toFixed(2);
            const quotaMB = (estimate.quota / (1024 * 1024)).toFixed(2);
            return { usage: usageMB, quota: quotaMB };
        }
        return null;
    } catch (error) {
        console.error('获取存储信息失败:', error);
        return null;
    }
}

// --- DOM Elements ---
const dom = {
    list: document.getElementById('artistList'), index: document.getElementById('indexBar'),
    vCover: document.getElementById('vCover'), vTitle: document.getElementById('vTitle'), vMeta: document.getElementById('vMeta'),
    vTabs: document.getElementById('vTabs'), vSongs: document.getElementById('vSongs'),
    search: document.getElementById('searchInput'), catList: document.getElementById('categoryList')
};

// --- State ---
let viewState = { sIdx: 0, aIdx: 0, category: '华语', search: '', viewMode: 'artist' }; // viewMode: 'artist' | 'local'
let allArtistsData = [];
// [New] 预加载定时器
let prefetchTimeout = null;

// 缓存获取的图片URL
const imageCache = {
    artists: new Map(),  // artistName -> imageUrl
    albums: new Map()    // artistName+albumTitle -> imageUrl
};

// 本地歌曲映射 { "歌曲名 - 歌手名": { fileName, audioUrl, uploadDate } }
const localSongsMap = new Map();

// ==================== 本地存储功能 ====================
/**
 * 保存本地歌曲到 IndexedDB（异步）
 * 注意：这个函数现在是异步的，需要使用 await
 */
async function saveLocalSongsToStorage() {
    try {
        console.log('开始保存到 IndexedDB，localSongsMap 大小:', localSongsMap.size);

        // localSongsMap 中存储的 audioUrl 是 DataURL 格式
        // 需要转换为 Blob 保存到 IndexedDB
        const savePromises = [];

        for (const [key, value] of localSongsMap.entries()) {
            if (value.audioUrl && !value._savedToIndexedDB) {
                console.log(`准备保存: ${value.songName}`);

                const savePromise = (async () => {
                    try {
                        // 将 DataURL 转换为 Blob
                        const blob = dataURLToBlob(value.audioUrl);
                        console.log(`Blob 转换完成，大小: ${blob.size} bytes`);

                        await saveAudioToIndexedDB(
                            value.songName,
                            value.artistName,
                            value.fileName,
                            blob
                        );
                        // 标记已保存，避免重复保存
                        value._savedToIndexedDB = true;
                        console.log(`✓ 已保存到 IndexedDB: ${value.songName}`);
                    } catch (error) {
                        console.error(`保存 ${value.songName} 失败:`, error);
                    }
                })();
                savePromises.push(savePromise);
            } else if (value._savedToIndexedDB) {
                console.log(`跳过已保存: ${value.songName}`);
            }
        }

        await Promise.all(savePromises);

        // 获取存储使用情况
        const usage = await getIndexedDBUsage();
        if (usage) {
            console.log(`IndexedDB 使用: ${usage.usage}MB / ${usage.quota}MB`);
            if (parseFloat(usage.usage) > parseFloat(usage.quota) * 0.9) {
                showNotification(`警告：存储空间即将用尽 (${usage.usage}MB)`);
            }
        }

        console.log(`✓ 已保存 ${localSongsMap.size} 首本地歌曲到 IndexedDB`);
    } catch (error) {
        console.error('保存到 IndexedDB 失败:', error);
        if (error.name === 'QuotaExceededError') {
            showNotification('存储空间不足，无法保存歌曲');
        } else {
            showNotification('保存失败，请重试');
        }
    }
}

/**
 * 将 DataURL 转换为 Blob
 */
function dataURLToBlob(dataURL) {
    const parts = dataURL.split(',');
    const mime = parts[0].match(/:(.*?);/)[1];
    const bstr = atob(parts[1]);
    let n = bstr.length;
    const u8arr = new Uint8Array(n);
    while (n--) {
        u8arr[n] = bstr.charCodeAt(n);
    }
    return new Blob([u8arr], { type: mime });
}

/**
 * 从 IndexedDB 加载本地歌曲（异步）
 */
async function loadLocalSongsFromStorage() {
    try {
        const audioFiles = await loadAllAudioFromIndexedDB();

        let loadedCount = 0;
        audioFiles.forEach((file) => {
            const key = `${file.songName} - ${file.artistName}`;
            localSongsMap.set(key, {
                fileName: file.fileName,
                audioUrl: file.audioUrl,
                uploadDate: file.uploadDate,
                songName: file.songName,
                artistName: file.artistName,
                _savedToIndexedDB: true  // 标记已保存
            });
            loadedCount++;
        });

        // 同步到播放器
        if (window.playerState && window.playerState.uploadedFiles) {
            localSongsMap.forEach((value) => {
                window.playerState.uploadedFiles.set(value.songName, value.audioUrl);
            });
        }

        console.log(`✓ 已加载 ${loadedCount} 首本地歌曲`);
        return loadedCount;
    } catch (error) {
        console.error('从 IndexedDB 加载失败:', error);
        showNotification('加载本地歌曲失败');
        return 0;
    }
}

/**
 * 清除所有本地存储的歌曲（异步）
 */
async function clearLocalSongsStorage() {
    try {
        // 清除 IndexedDB
        const db = await openDB();
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const objectStore = transaction.objectStore(STORE_NAME);
        await new Promise((resolve, reject) => {
            const request = objectStore.clear();
            request.onsuccess = () => {
                console.log('✓ 已清除 IndexedDB 中的音频数据');
                resolve();
            };
            request.onerror = () => reject(request.error);
        });

        // 清除 localSongsMap
        localSongsMap.clear();

        console.log('✓ 已清除所有本地存储的歌曲数据');
        showNotification('已清除所有本地歌曲');
    } catch (error) {
        console.error('清除存储失败:', error);
    }
}

// ==================== 单个歌曲上传功能 ====================
/**
 * 为指定歌曲上传音频文件
 */
function uploadSongForTrack(e, songName, artistName) {
    e.stopPropagation();
    // 创建一个隐藏的文件输入
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'audio/*';
    input.style.display = 'none';

    input.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const audioUrl = event.target.result;
            const key = `${songName} - ${artistName}`;

            // 保存到本地歌曲映射
            localSongsMap.set(key, {
                fileName: file.name,
                audioUrl: audioUrl,
                uploadDate: new Date().toISOString(),
                songName: songName,
                artistName: artistName
            });

            // 同步到播放器的 uploadedFiles
            if (window.playerState && window.playerState.uploadedFiles) {
                window.playerState.uploadedFiles.set(songName, audioUrl);
            }

            // 显示通知
            showNotification(`已上传: ${songName}`);

            // 保存到 IndexedDB（异步）
            saveLocalSongsToStorage().catch(error => {
                console.error('保存到 IndexedDB 失败:', error);
            });

            // 更新当前视图
            if (viewState.viewMode === 'local') {
                renderLocalMusicView();
            } else {
                updateView();
            }
        };
        reader.readAsDataURL(file);
    };

    document.body.appendChild(input);
    input.click();
    document.body.removeChild(input);
}

/**
 * 检查歌曲是否有本地上传文件 (从 IndexedDB 加载)
 */
function isFileUploaded(songName, artistName) {
    const exactKey = `${songName} - ${artistName}`;
    const bulkKey = `${songName} - 本地音乐`;

    return localSongsMap.has(exactKey) ||
        localSongsMap.has(bulkKey) ||
        (window.playerState && window.playerState.uploadedFiles && window.playerState.uploadedFiles.has(songName));
}

/**
 * 检查歌曲是否有本地文件 (包括本地上传和服务器扫描)
 */
function hasLocalFile(songName, artistName, songData) {
    // 1. 检查 IndexedDB 本地上传的文件
    if (isFileUploaded(songName, artistName)) {
        return true;
    }

    // 2. 检查服务器扫描的文件 (通过 initApp 注入的 path 属性)
    if (songData && typeof songData === 'object' && songData.path) {
        return true;
    }

    return false;
}

/**
 * 获取歌曲的音频URL
 */
function getSongAudioUrl(songName, artistName) {
    // 优先检查本地映射 - 支持多种 key 格式
    const exactKey = `${songName} - ${artistName}`;
    const bulkKey = `${songName} - 本地音乐`;

    if (localSongsMap.has(exactKey)) {
        return localSongsMap.get(exactKey).audioUrl;
    } else if (localSongsMap.has(bulkKey)) {
        return localSongsMap.get(bulkKey).audioUrl;
    }

    // 检查播放器的上传文件
    if (window.playerState && window.playerState.uploadedFiles.has(songName)) {
        return window.playerState.uploadedFiles.get(songName);
    }

    return null;
}

/**
 * 显示通知
 */
function showNotification(message) {
    if (window.playerState && typeof window.showNotification === 'function') {
        // 使用 player.js 的通知函数
        window.showNotification(message);
    } else {
        // 备用通知
        console.log('通知:', message);
    }
}

// ==================== 本地音乐视图 ====================
/**
 * 渲染本地音乐视图
 */
function renderLocalMusicView() {
    // 隐藏专辑相关的元素
    dom.vCover.style.display = 'none';

    // 显示本地音乐标题
    dom.vTitle.textContent = '本地音乐';
    dom.vMeta.textContent = `${localSongsMap.size} 首歌曲`;

    // 清空专辑标签
    dom.vTabs.innerHTML = '';

    // 渲染本地歌曲列表
    dom.vSongs.innerHTML = '';

    if (localSongsMap.size === 0) {
        dom.vSongs.innerHTML = `
            <tr>
                <td colspan="3" style="text-align:center; padding:40px; color:#555;">
                    <div style="font-size:48px; margin-bottom:10px;">🎵</div>
                    <div>还没有本地音乐</div>
                    <div style="font-size:0.85rem; margin-top:10px;">暂无本地音频文件</div>
                </td>
            </tr>
        `;
        return;
    }

    // 按上传时间倒序排列
    const songs = Array.from(localSongsMap.values()).sort((a, b) => {
        return new Date(b.uploadDate) - new Date(a.uploadDate);
    });

    songs.forEach((song, i) => {
        const tr = document.createElement('tr');
        tr.className = 'st-row';
        tr.innerHTML = `
            <td class="st-cell st-num">${String(i + 1).padStart(2, '0')}</td>
            <td class="st-cell st-title">
                <div class="song-info">
                    <div class="song-name">
                        ${song.songName}
                        <span class="song-source local" title="本地文件">本地</span>
                    </div>
                    <div class="song-artist">${song.artistName}</div>
                </div>
            </td>
            <td class="st-cell st-actions">
                <button class="act-btn delete" onclick="deleteLocalSong(event, '${song.songName}', '${song.artistName}')" title="删除">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        <line x1="10" y1="11" x2="10" y2="17"/>
                        <line x1="14" y1="11" x2="14" y2="17"/>
                    </svg>
                </button>
            </td>
        `;

        tr.addEventListener('click', () => {
            // [Modified] 移除 UI 抢跑逻辑，等待播放成功后由 player.js 统一更新
            // document.querySelectorAll('.st-row').forEach(el => el.classList.remove('active'));
            // tr.classList.add('active');

            // 尝试播放本地音乐
            console.log(`尝试播放本地音乐: ${song.songName} - ${song.artistName}`);
            if (window.audioPlayer && window.audioPlayer.play) {
                // 参数顺序：song, artist, album, audioUrl, lyrics
                window.audioPlayer.play(song.songName, song.artistName, '本地音乐', song.audioUrl, '');
            } else {
                console.error('audioPlayer 对象未就绪');
                showNotification('播放器未就绪，请稍后重试');
            }
        });

        dom.vSongs.appendChild(tr);
    });
}

/**
 * 播放本地歌曲
 */
function playLocalSong(e, songName, artistName) {
    e.stopPropagation();
    // [Modified] 移除 UI 抢跑逻辑
    // document.querySelectorAll('.st-row').forEach(el => el.classList.remove('active'));
    // const row = e.currentTarget.closest('.st-row');
    // row.classList.add('active');

    const key = `${songName} - ${artistName}`;
    const song = localSongsMap.get(key);
    if (!song) return;

    // 调用播放器
    if (window.audioPlayer && window.audioPlayer.play) {
        window.audioPlayer.play(songName, artistName, '本地音乐', song.audioUrl);
    }
}

/**
 * 删除本地歌曲
 */
async function deleteLocalSong(e, songName, artistName) {
    e.stopPropagation();
    const key = `${songName} - ${artistName}`;

    if (confirm(`确定要删除 "${songName}" 吗？`)) {
        // 从 IndexedDB 删除
        try {
            await deleteAudioFromIndexedDB(songName);
        } catch (error) {
            console.error('从 IndexedDB 删除失败:', error);
        }

        localSongsMap.delete(key);

        // 也 from 播放器中删除
        if (window.playerState && window.playerState.uploadedFiles) {
            window.playerState.uploadedFiles.delete(songName);
        }

        showNotification(`已删除: ${songName}`);

        renderLocalMusicView();
    }
}

/**
 * 切换到本地音乐视图
 */
function showLocalMusicView() {
    viewState.viewMode = 'local';
    viewState.sIdx = -1; // 取消艺术家选择

    // 更新侧边栏选中状态
    document.querySelectorAll('.artist-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.local-music-item').forEach(el => el.classList.add('active'));

    renderLocalMusicView();
}

/**
 * 切换回艺术家视图
 */
function showArtistView() {
    viewState.viewMode = 'artist';

    // 更新侧边栏选中状态
    document.querySelectorAll('.local-music-item').forEach(el => el.classList.remove('active'));

    // 如果有选中的艺术家，显示其内容
    if (viewState.sIdx >= 0 && allArtistsData[viewState.sIdx]) {
        updateView();
    }
}

// ==================== 图片获取 API ====================
/**
 * 从 iTunes API 获取艺术家图片
 */
/**
 * 从 iTunes API 获取艺术家图片 (已废弃)
 */
async function fetchArtistImage(artistName) {
    return null;
}

/**
 * 从 iTunes API 获取专辑封面
 */
/**
 * 从 iTunes API 获取专辑封面 (已废弃)
 */
async function fetchAlbumCover(artistName, albumTitle) {
    return null;
}

/**
 * 预加载所有艺术家的图片
 */
/**
 * 预加载所有艺术家的图片 (已废弃)
 */
async function preloadArtistImages() {
    return;
}

/**
 * 预加载当前艺术家的所有专辑封面
 * 策略：
 * 1. 立即加载前3张专辑封面（高优先级）
 * 2. 其余封面使用 requestIdleCallback 延迟加载（低优先级）
 */
async function preloadAlbumCovers(artistName) {
    const artist = allArtistsData.find(a => a.name === artistName);
    if (!artist) return;

    // [Fix] 移除 iTunes 相关检查
    // if (!API_CONFIG.itunes.enabled) { return; }

    const albums = artist.albums || []; // 安全防御
    const priorityAlbums = albums.slice(0, 3); // 前3张专辑
    const lazyAlbums = albums.slice(3); // 其余专辑

    // 1. 立即加载前3张专辑封面
    for (const album of priorityAlbums) {
        preloadSingleAlbumCover(artistName, album);
    }

    // 2. 使用 requestIdleCallback 延迟加载其余封面
    if (lazyAlbums.length > 0 && 'requestIdleCallback' in window) {
        requestIdleCallback(() => {
            lazyAlbums.forEach(album => {
                preloadSingleAlbumCover(artistName, album);
            });
        }, { timeout: 2000 });
    } else {
        // 浏览器不支持 requestIdleCallback，使用 setTimeout 降级
        setTimeout(() => {
            lazyAlbums.forEach(album => {
                preloadSingleAlbumCover(artistName, album);
            });
        }, 1000);
    }
}

/**
 * 预加载单张专辑封面
 * @param {string} artistName - 艺术家名称
 * @param {Object} album - 专辑对象
 */
function preloadSingleAlbumCover(artistName, album) {
    const cacheKey = `${artistName}|${album.title}`;

    // 检查是否已缓存
    if (imageCache.albums.has(cacheKey)) {
        return;
    }

    // [Fix] 如果已经有本地高画质封面，直接使用并缓存，跳过 iTunes 请求
    if (album.cover && (album.cover.startsWith('src/') || album.cover.startsWith('file://') || album.cover.startsWith('data:'))) {
        imageCache.albums.set(cacheKey, album.cover);
        return;
    }

    // 创建新的 Image 对象进行预加载（不显示在页面上）
    const img = new Image();

    img.onload = () => {
        console.log(`✓ 专辑封面预加载成功: ${artistName} - ${album.title}`);
        // 更新数据中的 cover 字段
        album.cover = img.src;
        // 缓存图片 URL
        imageCache.albums.set(cacheKey, img.src);
    };

    img.onerror = () => {
        console.warn(`✗ 专辑封面预加载失败: ${artistName} - ${album.title}`);
    };

    // [Fix] 移除 iTunes fetch
    // fetchAlbumCover(artistName, album.title).then(...)
}

/**
 * [New] 渲染高质感欢迎界面
 */
async function renderWelcomeScreen() {
    // 异步拉取一次背景图列表（如果还没有的话）
    if (dynamicWelcomeImages.length === 0) {
        await fetchWelcomeImages();
    }

    // 显示默认封面（不喧宾夺主，保持氛围）
    dom.vCover.style.display = 'block';
    dom.vCover.src = 'src/assets/images/vinyl_default.png';
    dom.vCover.style.opacity = '0.8'; // 稍微降低不透明度，使其更自然

    dom.vTabs.innerHTML = '';

    // 清空歌曲列表
    dom.vSongs.innerHTML = '';

    // 设置欢迎页标题和元数据
    dom.vTitle.innerHTML = `<span style="letter-spacing: 2px;">MOODY ARCHIVE</span>`;
    dom.vMeta.textContent = 'High Fidelity Local Musical Experience';

    // 插入大图背景
    dom.vSongs.innerHTML = `
        <tr>
            <td colspan="3" style="padding: 0; border: none;">
                <div class="welcome-container" style="
                    width: 100%;
                    background-image: url('${getWelcomeBackground()}');
                    background-size: cover;
                    background-position: center;
                    background-repeat: no-repeat;
                    image-rendering: -webkit-optimize-contrast;
                    border-radius: 12px;
                    box-shadow: 0 20px 50px rgba(0,0,0,0.5);
                    position: relative;
                    overflow: hidden;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                ">
                    <div style="
                        background: rgba(0,0,0,0.3);
                        backdrop-filter: blur(2px);
                        padding: 20px 40px;
                        border-radius: 8px;
                        border: 1px solid rgba(255,255,255,0.1);
                        text-align: center;
                    ">
                        <h2 style="margin: 0; font-family: 'Noto Serif SC', serif; color: #fff; text-shadow: 0 2px 10px rgba(0,0,0,0.8);">沉浸于纯粹的音乐时光</h2>
                        <div class="welcome-sub" style="margin-top: 10px; color: rgba(255,255,255,0.8); letter-spacing: 1px;">SELECT AN ARTIST TO START</div>
                    </div>
                </div>
            </td>
        </tr>
    `;
}

// --- Grouping Helper --- 
// [Added] 智能计算拼音首字母，确保“未证人员”也能归位
// [V12.34] 使用更鲁棒的汉字对比法，确保 Pinyin 映射 100% 准确
function getAutoLetter(name) {
    if (!name) return '#';
    const firstChar = name.charAt(0).toUpperCase();
    if (/^[A-Z]/.test(firstChar)) return firstChar;

    // 常见多音字姓氏直接特殊映射（例如：曾轶可 -> Z）
    const surnameMap = {
        '曾': 'Z',
        '单': 'S',
        '仇': 'Q',
        '区': 'O',
        '解': 'X',
        '查': 'Z',
        '朴': 'P',
        '乐': 'Y',
        '洗': 'X'
    };
    if (surnameMap[name.charAt(0)]) {
        return surnameMap[name.charAt(0)];
    }

    // 拼音区间对应表 (常用简体/繁体兼容首字符)
    const charMap = [
        ['啊', 'A'], ['八', 'B'], ['擦', 'C'], ['搭', 'D'], ['蛾', 'E'],
        ['发', 'F'], ['噶', 'G'], ['哈', 'H'], ['击', 'J'], ['咔', 'K'],
        ['垃', 'L'], ['妈', 'M'], ['拿', 'N'], ['哦', 'O'], ['妑', 'P'],
        ['七', 'Q'], ['然', 'R'], ['撒', 'S'], ['他', 'T'], ['屲', 'W'],
        ['昔', 'X'], ['压', 'Y'], ['匝', 'Z']
    ];

    // 从后往前找，找到第一个 localeCompare >= 的字符
    for (let i = charMap.length - 1; i >= 0; i--) {
        if (name.localeCompare(charMap[i][0], 'zh-CN') >= 0) {
            return charMap[i][1];
        }
    }
    return '#';
}

// [Added] 获取姓名首字/首字母作为头像占位
function getInitials(name) {
    if (!name) return '?';
    // 优先取第一个汉字或字母
    return name.charAt(0).toUpperCase();
}

// [Added] 根据姓名生成固定颜色
function getAvatarColor(name) {
    const colors = [
        '#f44336', '#e91e63', '#9c27b0', '#673ab7', '#3f51b5',
        '#2196f3', '#03a9f4', '#00bcd4', '#009688', '#4caf50',
        '#8bc34a', '#cddc39', '#ffeb3b', '#ffc107', '#ff9800', '#ff5722'
    ];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % colors.length;
    return colors[index];
}

// --- Initialization ---
async function initApp() {
    console.log('[V12.82] 开始初始化 (骨架驱动)...');

    // [Fix] 强制重置一次性的缓存，以清除之前的占位残留 (针对误报的“本地”标签) - V7 终极纯净版
    if (!localStorage.getItem('moody_v7_atomic_cleanup')) {
        console.log('[MOODY] 正在执行全域物理资产同步 (前端清场 V7)...');
        try {
            await clearLocalSongsStorage();
            localStorage.setItem('moody_v7_atomic_cleanup', 'true');
            console.log('[MOODY] 物理清场同步完成，正在重载...!');
            setTimeout(() => location.reload(), 500);
        } catch (e) {
            console.error('[MOODY] 前端清场失败:', e);
        }
        return; // 防止未清理完就执行后续逻辑
    }

    // 清理旧版可能遗留的临时缓存
    try {
        Object.keys(sessionStorage).forEach(k => {
            if (k.startsWith('moody_artist_')) sessionStorage.removeItem(k);
        });
    } catch (e) {}

    // 1. 从后端加载轻量化骨架 (仅限艺人) - [V13.0 Speedup + D1 Quota Fix]
    try {
        // [D1 Quota Fix] 优先使用 sessionStorage 缓存，同一会话内不重复拉取骨架数据
        const cachedSkeleton = sessionStorage.getItem('moody_skeleton_cache');
        if (cachedSkeleton) {
            allArtistsData = JSON.parse(cachedSkeleton);
            console.log(`[MOODY] 骨架数据命中会话缓存: ${allArtistsData.length} 位艺人 (节省 D1 读取)`);
        } else {
            // [D1 Quota Fix] 移除 &t=${Date.now()} 缓存击穿，允许 Cloudflare Edge 缓存
            const skeletonResponse = await fetch(`${API_BASE}/api/skeleton?light=true`);
            if (skeletonResponse.ok) {
                const res = await skeletonResponse.json();
                const rawArtists = (res.data && res.data.artists) ? res.data.artists : (res.data || []);
                allArtistsData = rawArtists.filter(a => (a.albumCount || 0) > 0);

                if (allArtistsData.length > 0) {
                    // 存入 sessionStorage 供后续刷新复用
                    try { sessionStorage.setItem('moody_skeleton_cache', JSON.stringify(allArtistsData)); } catch (e) {}
                    console.log(`[MOODY] 已快速载入 ${allArtistsData.length} 位有效艺人骨架 (已过滤空壳)`);
                } else {
                    console.warn('[MOODY] 数据库骨架为空。请确保已执行过初始扫描。');
                    dom.vMeta.innerHTML = '<span style="color:var(--accent)">无名录数据</span> - 请执行治理接口';
                }
            }
        }
    } catch (error) {
        console.error('[MOODY] 核心骨架加载失败:', error);
        allArtistsData = [];
    }

    // 2. 移除旧版本的 /api/songs 全量扫描拉取 (不再需要前端合并，全权交给按需加载)

    // 3. 移除旧的 Hybrid Merge 逻辑，因为后端现在直接输出对齐后的数据

    // 4. 数据整理与排序
    allArtistsData.forEach(a => {
        if (!a.group) a.group = getAutoLetter(a.name);
    });

    // [V12.37] 深度去重审计 (Final Final Audit)
    // 防止因 ID 错乱或简繁体差异导致的兜底失败
    const uniqueArtists = [];
    const seenCores = new Set();

    allArtistsData.forEach(artist => {
        const core = getCoreName(artist.name);
        if (!seenCores.has(core)) {
            seenCores.add(core);
            uniqueArtists.push(artist);
        } else {
            // 如果核心名重复，尝试将专辑合并到已存在的对象中（物理去重补丁）
            const existing = uniqueArtists.find(a => getCoreName(a.name) === core);
            if (existing && artist.albums) {
                artist.albums.forEach(alb => {
                    const albCore = getCoreName(alb.title);
                    if (!existing.albums.find(ea => getCoreName(ea.title) === albCore)) {
                        existing.albums.push(alb);
                    }
                });
            }
            console.log(`[MOODY Audit] 已在渲染前拦截并合并冲突艺人: ${artist.name}`);
        }
    });
    if (Array.isArray(uniqueArtists)) {
        allArtistsData = uniqueArtists;
    } else {
        console.error('[MOODY Audit] CRITICAL: uniqueArtists is not an array, falling back to original.');
    }

    if (!allArtistsData || allArtistsData.length === 0) {
        console.error('[MOODY] 错误: 没有可用数据!');
        return;
    }

    // 执行排序
    allArtistsData.sort((a, b) => {
        if (a.group !== b.group) return a.group.localeCompare(b.group);
        return a.name.localeCompare(b.name, 'zh-CN');
    });

    console.log('[MOODY] 系统初始化完成，载入', allArtistsData.length, '位艺术家');

    // 4. 加载本地 IndexedDB 手动上传的内容
    try {
        const loadedCount = await loadLocalSongsFromStorage();
        if (loadedCount > 0) {
            console.log(`[MOODY] 恢复了 ${loadedCount} 首本地上传歌曲`);
        }
    } catch (error) {
        console.error('[MOODY] IndexedDB 加载失败:', error);
    }

    // 5. 事件与 UI 初始化逻辑维持不变
    document.addEventListener('focus', (e) => {
        if (e.target.closest('.artist-item, .st-row, .cat-chip, .tab, .act-btn, .idx-char')) {
            e.target.blur();
        }
    }, { capture: true, passive: true });

    // [V3.0] 移动端侧边栏菜单切换逻辑
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const mobileOverlay = document.getElementById('mobileOverlay');
    if (mobileMenuBtn && mobileOverlay) {
        mobileMenuBtn.addEventListener('click', () => {
            document.body.classList.add('sidebar-open');
        });
        mobileOverlay.addEventListener('click', () => {
            document.body.classList.remove('sidebar-open');
        });
    }

    renderCategories();
    renderIndexBar();
    filterAndRender();
    preloadArtistImages();

    // [V3.0 + D1 Quota Fix] 实现防抖搜索与后端全局检索（含缓存与最小长度保护）
    let searchTimeout = null;
    const searchResultCache = new Map(); // [D1 Quota Fix] 搜索结果缓存 (key -> {data, ts})
    const SEARCH_CACHE_TTL = 60000; // 60秒缓存有效期

    dom.search.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        viewState.search = query.toLowerCase();

        // 1. 如果搜索框为空，恢复侧边栏显示，隐藏搜索面板
        if (!query) {
            clearTimeout(searchTimeout);
            dom.list.style.display = 'block';
            dom.index.style.display = 'flex';
            // 移除可能存在的搜索结果容器
            const existingResults = document.getElementById('searchResults');
            if (existingResults) existingResults.remove();

            filterAndRender();
            return;
        }

        // [D1 Quota Fix] 最少输入 2 个字符才发起后端搜索，避免单字符触发全表扫描
        if (query.length < 2) {
            return;
        }

        // 2. 防抖处理 [D1 Quota Fix] 从 300ms 增加到 500ms
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(async () => {
            try {
                // [D1 Quota Fix] 优先检查缓存
                const cacheKey = query.toLowerCase();
                const cached = searchResultCache.get(cacheKey);
                if (cached && (Date.now() - cached.ts) < SEARCH_CACHE_TTL) {
                    console.log(`[Search] 命中缓存: "${query}" (节省 D1 读取)`);
                    renderSearchResults(cached.data);
                    return;
                }

                const response = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}`);
                const res = await response.json();

                if (response.ok && res.code === 200) {
                    // 存入缓存
                    searchResultCache.set(cacheKey, { data: res.data, ts: Date.now() });
                    // 清理过期缓存项（最多保留 50 条）
                    if (searchResultCache.size > 50) {
                        const oldest = searchResultCache.keys().next().value;
                        searchResultCache.delete(oldest);
                    }
                    renderSearchResults(res.data);
                }
            } catch (error) {
                console.error('[Search] 后端检索失败:', error);
            }
        }, 500);
    });

    /**
     * 渲染实时搜索结果预览层
     */
    function renderSearchResults(data) {
        // 隐藏原始列表和索引条
        dom.list.style.display = 'none';
        dom.index.style.display = 'none';

        let resultsEl = document.getElementById('searchResults');
        if (!resultsEl) {
            resultsEl = document.createElement('div');
            resultsEl.id = 'searchResults';
            resultsEl.className = 'search-results-panel';
            dom.list.parentNode.insertBefore(resultsEl, dom.list);
        }

        const { artists, albums, songs } = data;

        if (artists.length === 0 && albums.length === 0 && songs.length === 0) {
            resultsEl.innerHTML = '<div class="no-results">未找到匹配项</div>';
            return;
        }

        let html = '';

        if (artists.length > 0) {
            html += `<div class="res-group"><div class="res-label">歌手</div>`;
            artists.forEach(a => {
                html += `<div class="res-item" onclick="handleSearchHit('artist', '${a.name.replace(/'/g, "\\'")}')">${a.name}</div>`;
            });
            html += `</div>`;
        }

        if (albums.length > 0) {
            html += `<div class="res-group"><div class="res-label">专辑</div>`;
            albums.forEach(alb => {
                html += `<div class="res-item" onclick="handleSearchHit('album', '${alb.title.replace(/'/g, "\\'")}')">${alb.title}</div>`;
            });
            html += `</div>`;
        }

        if (songs.length > 0) {
            html += `<div class="res-group"><div class="res-label">歌曲</div>`;
            songs.forEach(s => {
                html += `<div class="res-item" onclick="handleSearchHit('song', '${s.title.replace(/'/g, "\\'")}')">${s.title}</div>`;
            });
            html += `</div>`;
        }

        resultsEl.innerHTML = html;
    }

    /**
     * 处理搜索点击
     */
    window.handleSearchHit = async (type, value) => {
        // [V15.0] 核心交互优化：清除搜索状态，恢复全量列表展示
        dom.search.value = '';
        viewState.search = '';
        dom.list.style.display = 'block';
        dom.index.style.display = 'flex';
        const resultsEl = document.getElementById('searchResults');
        if (resultsEl) resultsEl.remove();

        // 强行触发一次渲染以恢复完整列表，确保后续 findIndex 能命中
        filterAndRender();

        if (type === 'artist') {
            const idx = allArtistsData.findIndex(a => a.name === value);
            if (idx !== -1) selectArtist(idx);
        } else if (type === 'album') {
            for (let i = 0; i < allArtistsData.length; i++) {
                const a = allArtistsData[i];
                const aIdx = a.albums.findIndex(alb => alb.title === value);
                if (aIdx !== -1) {
                    await selectArtist(i); // selectArtist 是异步的(含抓取详情)
                    viewState.aIdx = aIdx;
                    updateView();
                    break;
                }
            }
        } else if (type === 'song') {
            // [V15.0] 歌曲点击：自动跳转并播放
            for (let i = 0; i < allArtistsData.length; i++) {
                const a = allArtistsData[i];
                // 注意：如果 a.albums 还是空的，可能需要先抓取或在此处做模糊匹配
                // 暂时利用 renderSearchResults 时传下来的 data 已经包含了基本结构
                for (let j = 0; j < a.albums.length; j++) {
                    const alb = a.albums[j];
                    const songMatch = alb.songs.find(s => (typeof s === 'string' ? s : s.title) === value);
                    if (songMatch) {
                        await selectArtist(i);
                        viewState.aIdx = j;
                        updateView();

                        // 等待视图渲染完成后触发播放
                        setTimeout(() => {
                            playSong(new Event('click'), songMatch, a.name);
                        }, 100);
                        return;
                    }
                }
            }
        }
    };

    initDragScroll();
    initWheelScroll();

    // 如果是首次加载且没有交互，显示欢迎页
    if (viewState.sIdx === 0 && !window.hasInteracted) {
        viewState.sIdx = -1;
        document.querySelectorAll('.artist-item').forEach(el => el.classList.remove('active'));
        renderWelcomeScreen();
    }

    // [Notion Integration] 监听来自 Notion 的指令
    window.addEventListener('message', (event) => {
        const { type, data } = event.data || {};
        if (type === 'MOODY_REMOTE_CONTROL') {
            const { action, payload } = data;
            console.log('[MOODY Remote] 接收指令:', action, payload);

            if (action === 'SELECT_ARTIST_BY_NAME') {
                const idx = allArtistsData.findIndex(a => getCoreName(a.name) === getCoreName(payload));
                if (idx !== -1) {
                    window.handleSearchHit('artist', allArtistsData[idx].name);
                }
            } else if (action === 'PLAY_PAUSE') {
                const playBtn = document.querySelector('.play-btn');
                if (playBtn) playBtn.click();
            }
        }
    });

    // [Notion Integration] 检测是否为 Notion 模式
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'notion') {
        document.body.classList.add('notion-compact-mode');
        console.log('[MOODY] 已激活 Notion 紧凑模式');
    }

    console.log('[MOODY] App 集成初始化圆满完成');
}

// --- 滚轮横向滚动支持 ---
function initWheelScroll() {
    // 为横向滚动区域添加滚轮事件转换
    const horizontalScrollElements = [dom.catList, dom.vTabs];

    horizontalScrollElements.forEach(element => {
        element.addEventListener('wheel', (e) => {
            // 检测是否是横向滚动（触摸板/触控条）
            if (e.deltaY !== 0 && Math.abs(e.deltaX) < Math.abs(e.deltaY)) {
                // 将纵向滚动转换为横向滚动
                e.preventDefault();
                element.scrollLeft += e.deltaY;
            }
        }, { passive: false });
    });
}

// --- Interactions ---
function initDragScroll() {
    const slider = dom.catList;
    let isDown = false;
    let startX;
    let scrollLeft;

    slider.addEventListener('mousedown', (e) => {
        isDown = true;
        dom.startClickX = e.clientX;
        startX = e.pageX - slider.offsetLeft;
        scrollLeft = slider.scrollLeft;
    });

    slider.addEventListener('mouseleave', () => { isDown = false; });

    slider.addEventListener('mouseup', () => { isDown = false; });

    slider.addEventListener('mousemove', (e) => {
        if (!isDown) return;
        e.preventDefault();
        const x = e.pageX - slider.offsetLeft;
        const walk = (x - startX) * 1.5;
        slider.scrollLeft = scrollLeft - walk;
    });
}

// Handle Category Click with Auto-Center
function handleCategoryClick(catName, e) {
    if (Math.abs(e.clientX - dom.startClickX) > 5) return;

    viewState.category = catName;
    viewState.search = '';
    dom.search.value = '';

    filterAndRender();
    renderCategories();

    requestAnimationFrame(() => {
        const allChips = dom.catList.querySelectorAll('.cat-chip');
        let targetChip = null;
        for (let chip of allChips) {
            if (chip.textContent === catName) {
                targetChip = chip;
                break;
            }
        }
        if (targetChip) {
            const containerWidth = dom.catList.offsetWidth;
            const chipLeft = targetChip.offsetLeft;
            const chipWidth = targetChip.offsetWidth;
            const scrollLeft = chipLeft - (containerWidth / 2) + (chipWidth / 2);
            dom.catList.scrollTo({ left: scrollLeft, behavior: 'smooth' });
        }
    });
}

// --- Rendering ---

function renderCategories() {
    dom.catList.innerHTML = '';
    CATEGORIES.forEach(cat => {
        const chip = document.createElement('div');
        chip.className = `cat-chip ${viewState.category === cat ? 'active' : ''}`;
        chip.textContent = cat;
        chip.addEventListener('click', (e) => handleCategoryClick(cat, e));
        dom.catList.appendChild(chip);
    });
}

function filterAndRender() {
    let result = allArtistsData;

    if (viewState.category === '本地') {
        // 过滤出品种中包含本地路径或 localSongsMap 中存在的艺人
        result = result.filter(a => {
            // 检查是否有任何一首歌具有物理路径
            const hasPhysical = a.albums.some(alb => alb.songs.some(s => typeof s !== 'string' && s.path));
            if (hasPhysical) return true;

            // 检查 localSongsMap (手动上传的)
            const hasUploaded = Array.from(localSongsMap.values()).some(ls => ls.artistName === a.name);
            return hasUploaded;
        });
    } else if (viewState.category === '华语') {
        // [V12.80] 大华语汇总逻辑：包含所有中文属性分类
        const mandarinSet = ['华语', '港台', '摇滚', '民谣', 'R&B'];
        result = result.filter(s => mandarinSet.includes((s.category || '').trim()));
    } else {
        // [V12.80] 精准过滤逻辑：用于“欧美”或特定的风格页签
        result = result.filter(s => (s.category || '').trim() === viewState.category);
    }

    if (viewState.search) {
        result = result.filter(s => s.name.toLowerCase().includes(viewState.search));
    }

    // [V12.12] 终极过滤：移除所有未知艺术家
    result = result.filter(r => !r.name.includes('未知艺术家') && !r.name.includes('Unknown Artist'));

    // [V12.72] 移除过时的英文字符拦截器，召回 Beyond, F.I.R 等以字母开头的核心艺人

    // [V12.72] 统一全局 Pinyin 严格排序 (确保与索引条 1:1 动态对齐)
    result.sort((a, b) => {
        const charA = getAutoLetter(a.name);
        const charB = getAutoLetter(b.name);
        if (charA !== charB) return charA.localeCompare(charB);
        return a.name.localeCompare(b.name, 'zh-CN');
    });

    renderSidebar(result);
    if (result.length > 0) {
        const currentSelected = allArtistsData[viewState.sIdx];
        const stillExists = currentSelected ? result.find(r => r.id === currentSelected.id) : null;
        if (!stillExists) {
            selectArtist(allArtistsData.indexOf(result[0]));
        }
    } else {
        dom.list.innerHTML = '<div style="padding:20px; color:#555; text-align:center">No artists found</div>';
    }
    updateActiveLetter();
}

function updateActiveLetter() {
    if (viewState.sIdx < 0 || !allArtistsData[viewState.sIdx]) return;
    const artist = allArtistsData[viewState.sIdx];
    // 将分组字符（可能是汉字如"张"）转换为拼音首字母（如"Z"）再与 A-Z 指示器比较
    const targetLetter = getAutoLetter(artist.group || artist.name);
    const charEls = document.querySelectorAll('.idx-char');
    charEls.forEach(el => {
        if (el.textContent === targetLetter) el.classList.add('active-target');
        else el.classList.remove('active-target');
    });
}

function renderSidebar(data) {
    dom.list.innerHTML = '';

    // 添加"本地音乐"入口在顶部
    const localMusicItem = document.createElement('div');
    localMusicItem.className = `artist-item local-music-item ${viewState.viewMode === 'local' ? 'active' : ''}`;
    localMusicItem.innerHTML = `
        <div class="a-img local-music-icon">🎵</div>
        <div class="a-info">
            <div class="a-name">本地音乐</div>
            <div class="a-count">${localSongsMap.size} 首歌曲</div>
        </div>
    `;
    localMusicItem.onclick = () => {
        showLocalMusicView();
        localMusicItem.blur();
        if (document.activeElement) {
            document.activeElement.blur();
        }
    };
    dom.list.appendChild(localMusicItem);

    // 添加分割线
    const separator = document.createElement('div');
    separator.className = 'sidebar-separator';
    dom.list.appendChild(separator);

    // 添加艺术家列表
    let lastGroup = null; // [Modified] Init to null to capture first group
    data.forEach((s, i) => {
        let isFirstInGroup = false;
        const currentAtoZ = getAutoLetter(s.name);
        if (currentAtoZ !== lastGroup) {
            lastGroup = currentAtoZ;
            isFirstInGroup = true;
        }

        const originalIdx = allArtistsData.indexOf(s);
        const isActive = (originalIdx === viewState.sIdx && viewState.viewMode === 'artist');
        const item = document.createElement('div');
        item.className = `artist-item ${isActive ? 'active' : ''}`;

        // [V12.30] Strict A-Z Anchor ID (Collision-Free)
        // [V12.72] 注入显性 A-Z 分组标题与锚点 ID
        if (isFirstInGroup) {
            const groupHeader = document.createElement('div');
            groupHeader.className = 'group-header';
            groupHeader.textContent = lastGroup;
            groupHeader.id = `group-${lastGroup}`;
            if (i > 0) groupHeader.style.marginTop = '24px';
            dom.list.appendChild(groupHeader);
        }

        item.dataset.id = s.id || '';
        item.dataset.name = s.name || '';

        item.onclick = (e) => {
            e.stopPropagation();
            viewState.viewMode = 'artist';
            selectArtist(s);
            item.blur();
            if (document.activeElement) {
                document.activeElement.blur();
            }
        };
        // [Modified] 智能头像系统：优先使用真实明星头像，否则优雅降级为高质感字母头像
        const hasCustomAvatar = s.avatar && !s.avatar.includes('default.png') && !s.avatar.includes('landing_cover.png');
        const isVariety = s.category === '音乐综艺';
        const rawArtistId = (s.id || '').toString().replace(/\D/g, '');
        const localAvatar = rawArtistId ? `/src/assets/images/avatars/artists/artist_${rawArtistId}.jpg` : null;

        let avatarHtml;
        if (isVariety) {
            // [New] 综艺专属高清品牌图标
            const varietyLogos = {
                '中国好声音': '/storage/covers/variety/china_voice_logo.png',
                '我是歌手': '/storage/covers/variety/i_am_singer_logo.png',
                '蒙面唱将猜猜猜': '/storage/covers/variety/masked_singer_logo.png'
            };
            const varietyColors = { '中国好声音': '#d4af37', '我是歌手': '#315efb', '蒙面唱将猜猜猜': '#c01c28' };
            const vLogo = varietyLogos[s.name];
            const vColor = varietyColors[s.name] || '#444';

            if (vLogo) {
                const finalLogo = vLogo.startsWith('http') ? vLogo : (vLogo.startsWith('/') ? API_BASE + vLogo : API_BASE + '/' + vLogo);
                avatarHtml = `<div class="a-img" style="background: ${vColor}; overflow: hidden; border: 2px solid rgba(255,255,255,0.15); box-shadow: 0 4px 12px rgba(0,0,0,0.4)">
                    <img src="${finalLogo}" style="width:100%; height:100%; object-fit: contain; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5))">
                </div>`;
            } else {
                avatarHtml = `<div class="a-img a-letter-avatar" style="background: ${vColor}">${getInitials(s.name)}</div>`;
            }
        }
        else if (hasCustomAvatar) {
            const avatarUrl = s.avatar.startsWith('http') ? s.avatar : (s.avatar.startsWith('/') ? API_BASE + s.avatar : API_BASE + '/' + s.avatar);
            avatarHtml = `<img data-src="${avatarUrl}" class="a-img" alt="${s.name}">`;
        }
        else if (localAvatar) {
            avatarHtml = `<img data-src="${localAvatar}" class="a-img" alt="${s.name}">`;
        }
        else {
            avatarHtml = `<div class="a-img a-letter-avatar" style="background: ${getAvatarColor(s.name)}">${getInitials(s.name)}</div>`;
        }

        // [New] 本地资源高亮提示
        // [V12.60] 适配按需加载架构：使用后端预计算的统计值
        const uploadedCount = Array.from(localSongsMap.values()).filter(ls => ls.artistName === s.name).length;
        const totalLocal = (s.localCount || 0) + uploadedCount;

        const countBadge = totalLocal > 0
            ? `<div class="a-count"><span class="badge local-badge">本地 ${totalLocal}</span> · ${s.albumCount || 0} 专辑</div>`
            : `<div class="a-count">${s.albumCount || 0} 专辑 · ${s.category}</div>`;

        item.innerHTML = `
            ${avatarHtml}
            <div class="a-info">
                <div class="a-name">${s.name}</div>
                ${countBadge}
            </div>`;
        dom.list.appendChild(item);
    });

    // 启动懒加载观察
    if (window.LazyLoader) {
        const images = dom.list.querySelectorAll('img[data-src]');
        window.LazyLoader.observeMany(images);
    }
}

// [V12.22] High-Performance Fisheye 2.0 (No Reflow, Visual-Only)
function renderIndexBar() {
    dom.index.innerHTML = '';
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

    chars.forEach(g => {
        const d = document.createElement('div');
        d.className = 'idx-char';
        d.textContent = g;
        d.dataset.group = g;
        dom.index.appendChild(d);
    });

    const BASE_FONT = 11;
    const MAX_FONT = 26;
    const CHAR_HEIGHT = 14;
    const RADIUS = 80;

    const updateFisheye = (clientY) => {
        const children = Array.from(dom.index.children);

        // 1. Calculate font sizes based on distance to mouse
        const fontSizes = children.map(child => {
            const childRect = child.getBoundingClientRect();
            const centerY = childRect.top + childRect.height / 2;
            const dist = Math.abs(clientY - centerY);
            if (dist < RADIUS) {
                const ratio = 1 - (dist / RADIUS);
                return BASE_FONT + (MAX_FONT - BASE_FONT) * Math.pow(Math.sin((ratio * Math.PI) / 2), 2);
            }
            return BASE_FONT;
        });

        // 2. Determine "target" char
        let closestIdx = -1;
        let minDist = Infinity;
        children.forEach((child, i) => {
            const childRect = child.getBoundingClientRect();
            const d = Math.abs(clientY - (childRect.top + childRect.height / 2));
            if (d < minDist) {
                minDist = d;
                closestIdx = i;
            }
            child.classList.remove('active-target');
        });
        if (closestIdx !== -1) children[closestIdx].classList.add('active-target');

        // 3. Calculate Push Displacement (translateY) based on font size expansion
        const scales = fontSizes.map(fs => fs / BASE_FONT);
        const displacements = new Array(children.length).fill(0);

        // Push up from center
        for (let i = closestIdx - 1; i >= 0; i--) {
            const expansionThis = CHAR_HEIGHT * (scales[i] - 1);
            const expansionNext = CHAR_HEIGHT * (scales[i + 1] - 1);
            displacements[i] = displacements[i + 1] - (expansionThis / 2 + expansionNext / 2);
        }
        // Push down from center
        for (let i = closestIdx + 1; i < children.length; i++) {
            const expansionThis = CHAR_HEIGHT * (scales[i] - 1);
            const expansionPrev = CHAR_HEIGHT * (scales[i - 1] - 1);
            displacements[i] = displacements[i - 1] + (expansionThis / 2 + expansionPrev / 2);
        }

        // 4. Batch update styles — use font-size for crisp rendering instead of scale
        children.forEach((child, i) => {
            child.style.fontSize = `${fontSizes[i]}px`;
            child.style.transform = `translateY(${displacements[i]}px)`;
        });
    };

    const resetFisheye = () => {
        Array.from(dom.index.children).forEach(child => {
            child.style.transform = '';
            child.style.fontSize = '';
            child.classList.remove('active-target');
        });
    };

    // --- Interactive Logic ---
    dom.index.onpointermove = (e) => {
        if (!dom.index.hasPointerCapture(e.pointerId)) {
            requestAnimationFrame(() => updateFisheye(e.clientY));
        }
    };

    dom.index.onpointerleave = () => {
        if (!dom.index.hasPointerCapture(window.lastPointerId)) {
            resetFisheye();
        }
    };

    dom.index.onpointerdown = (e) => {
        e.preventDefault();
        window.lastPointerId = e.pointerId;
        dom.index.setPointerCapture(e.pointerId);

        updateFisheye(e.clientY);
        scrollToGroupAt(e.clientX, e.clientY);

        dom.index.onpointermove = (mv) => {
            mv.preventDefault();
            requestAnimationFrame(() => updateFisheye(mv.clientY));
            scrollToGroupAt(mv.clientX, mv.clientY);
        };

        dom.index.onpointerup = (up) => {
            dom.index.onpointermove = (e) => requestAnimationFrame(() => updateFisheye(e.clientY));
            dom.index.onpointerup = null;
            resetFisheye();
            dom.index.releasePointerCapture(up.pointerId);
        };
    };
}

// Helper for index scrolling (V12.28 Industry Standard - Blind Touch)
// [V12.34] 索引导航核心逻辑 - 修复锚点识别与滑动冲突
const scrollToGroupAt = (clientX, clientY) => {
    const now = Date.now();
    if (dom.lastScrollTime && now - dom.lastScrollTime < 30) return;
    dom.lastScrollTime = now;

    // 1. Precise Hit Detection
    let hitEl = document.elementFromPoint(clientX, clientY);
    let targetChar = null;

    if (hitEl && (hitEl.classList.contains('idx-char') || hitEl.closest('.idx-char'))) {
        const charEl = hitEl.classList.contains('idx-char') ? hitEl : hitEl.closest('.idx-char');
        targetChar = charEl.dataset.group;
    } else {
        // Fallback: Proximity search within indexBar
        const rect = dom.index.getBoundingClientRect();
        if (clientX >= rect.left - 50 && clientX <= rect.right + 50) {
            const children = Array.from(dom.index.children);
            let minDist = Infinity;
            children.forEach(child => {
                const cRect = child.getBoundingClientRect();
                const centerY = cRect.top + cRect.height / 2;
                const dist = Math.abs(clientY - centerY);
                if (dist < minDist) {
                    minDist = dist;
                    targetChar = child.dataset.group;
                }
            });
        }
    }

    if (!targetChar) return;

    // 2. Scan anchors
    // 定向获取具有 group-ID 的歌手项，并记录其物理高度
    const anchors = Array.from(dom.list.querySelectorAll('[id^="group-"]'))
        .map(el => ({
            char: el.id.replace('group-', '').toUpperCase(),
            top: el.offsetTop
        }))
        .filter(g => g.char.length > 0)
        .sort((a, b) => a.char.localeCompare(b.char));

    if (anchors.length === 0) {
        console.warn("[V12.34] CRITICAL: No group anchors found in #artistList!");
        // console.warn("CRITICAL: No group anchors found in #artistList!");
        return;
    }

    // 3. Match logic (Ceiling search)
    const match = anchors.find(g => g.char >= targetChar);

    if (match) {
        // [V12.35] Silent scroll for production
        dom.list.scrollTo({
            top: match.top,
            behavior: 'auto'
        });
    } else {
        const last = anchors[anchors.length - 1];
        dom.list.scrollTo({
            top: last.top,
            behavior: 'auto'
        });
    }
};

// ==================== 骨架屏高级流光渲染 ====================
function renderTableSkeleton(count = 8) {
    const widths = ['52%', '38%', '65%', '46%', '58%', '34%', '48%', '42%'];
    let html = '';
    for (let i = 0; i < count; i++) {
        const w = widths[i % widths.length];
        const numStr = String(i + 1).padStart(2, '0');
        html += `
            <tr class="st-row skeleton-row">
                <td class="st-cell st-num">${numStr}</td>
                <td class="st-cell st-title">
                    <div class="skeleton-title-wrap">
                        <div class="skeleton-shimmer skeleton-song-name" style="width: ${w};"></div>
                        <div class="skeleton-shimmer skeleton-badge"></div>
                    </div>
                </td>
            </tr>
        `;
    }
    dom.vSongs.innerHTML = html;
}

function renderTabsSkeleton(count = 5) {
    const widths = [90, 115, 75, 100, 125];
    let html = '';
    for (let i = 0; i < count; i++) {
        html += `<div class="skeleton-tab-pill" style="width: ${widths[i % widths.length]}px;"></div>`;
    }
    dom.vTabs.innerHTML = html;
}

async function selectArtist(target) {
    let artist = null;
    let idx = -1;

    if (typeof target === 'object' && target !== null) {
        artist = target;
        idx = allArtistsData.findIndex(a => a.id === artist.id || a.name === artist.name);
    } else if (typeof target === 'number') {
        idx = target;
        artist = allArtistsData[idx];
    }

    if (!artist) {
        console.warn('[MOODY] selectArtist 未找到对应艺人:', target);
        return;
    }

    if (viewState.sIdx === idx && viewState.viewMode === 'artist') return;

    viewState.sIdx = idx >= 0 ? idx : allArtistsData.indexOf(artist);
    viewState.aIdx = 0;
    viewState.viewMode = 'artist';

    // 移动端点击歌手后自动收起侧边栏
    if (document.body.classList.contains('sidebar-open')) {
        document.body.classList.remove('sidebar-open');
    }

    // 1. 立即激活侧边栏高亮 (零延迟响应)
    document.querySelectorAll('.artist-item').forEach(el => el.classList.remove('active'));
    const matchedEl = dom.list.querySelector(`.artist-item[data-id="${artist.id}"]`) ||
                      dom.list.querySelector(`.artist-item[data-name="${artist.name}"]`);
    if (matchedEl) matchedEl.classList.add('active');

    // 2. 立即退出欢迎界面，展示高级流光骨架屏
    dom.vCover.style.display = 'block';
    dom.vTitle.textContent = artist.name;
    dom.vMeta.textContent = `${artist.name} · 正在读取专辑名录...`;
    renderTabsSkeleton(5);
    renderTableSkeleton(8);

    // 3. 严格直连真实后台 API 拉取该艺人的实时专辑与歌曲数据
    let lastErr = null;
    if (!artist.albums || artist.albums.length === 0) {
        const artistIdRaw = (artist.id || "").toString().replace(/\D/g, '');
        const targetUrl = `${API_BASE}/api/songs?artistId=${artistIdRaw}&artist=${encodeURIComponent(artist.name)}`;

        // [D1 Quota Fix] 仅在网络错误/非200状态时重试，HTTP 200 返回空专辑是合法状态不重试
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                const res = await fetch(targetUrl);
                if (res.ok) {
                    const json = await res.json();
                    const detailData = json.data && json.data.length > 0 ? json.data[0] : null;
                    if (detailData && detailData.albums && detailData.albums.length > 0) {
                        // 过滤掉 0 歌曲空专辑，并按专辑名称防重
                        const validAlbs = detailData.albums.filter(alb => alb.songs && alb.songs.length > 0);
                        const seenAlbTitles = new Set();
                        artist.albums = [];
                        for (const alb of validAlbs) {
                            const normTitle = (alb.title || '').trim().toLowerCase();
                            if (!seenAlbTitles.has(normTitle)) {
                                seenAlbTitles.add(normTitle);
                                artist.albums.push(alb);
                            }
                        }
                        console.log(`✓ 真实后台实时名录已同步 [${artist.name}]: 共 ${artist.albums.length} 张专辑 (已过滤空壳与重名)`);
                    } else {
                        console.log(`[MOODY] ${artist.name}: 后台返回空专辑列表 (该艺人可能暂无专辑数据)`);
                    }
                    lastErr = null;
                    break; // [D1 Quota Fix] HTTP 200 无论数据是否为空都不重试
                } else {
                    const errData = await res.json().catch(() => null);
                    lastErr = errData?.message || `后台服务返回 HTTP ${res.status}`;
                }
            } catch (e) {
                lastErr = e.message || '网络连接异常';
            }

            if (attempt < 3 && lastErr) {
                await new Promise(r => setTimeout(r, attempt * 300));
            }
        }

        if (lastErr && (!artist.albums || artist.albums.length === 0)) {
            console.warn(`[MOODY] 真实后台拉取失败: ${lastErr}`);
        }
    }

    // 4. 数据就绪后，渲染专辑与曲目
    if (artist.albums && artist.albums.length > 0) {
        const firstAlbum = artist.albums[0];
        if (dom.vCover && firstAlbum.cover) {
            dom.vCover.style.opacity = '1';
            dom.vCover.classList.remove('lazy-loading');
            dom.vCover.src = firstAlbum.cover.startsWith('http') ? firstAlbum.cover : (firstAlbum.cover.startsWith('/') ? encodeURI(firstAlbum.cover) : firstAlbum.cover);
        }

        updateView();
    } else {
        dom.vMeta.textContent = `${artist.name} · 后台接口连接受阻`;
        const isD1Limit = lastErr && lastErr.includes('daily row read limit');
        const errDesc = isD1Limit
            ? 'Cloudflare D1 每日免费读取额度已超限（500万次读取限制），请等待明日配额重置或升级计划。'
            : (lastErr || '未能成功拉取数据');
        dom.vSongs.innerHTML = `
            <tr>
                <td colspan="2" style="text-align:center; padding:60px 20px; color:#888">
                    <div style="font-size:1.1rem; color:#f59e0b; margin-bottom:8px;">⚠️ 远端后台接口暂时受阻</div>
                    <div style="font-size:0.85rem; color:#aaa; max-width:480px; margin:0 auto 16px auto; line-height:1.6;">
                        ${errDesc}
                    </div>
                    <a href="javascript:void(0)" onclick="selectArtist(${viewState.sIdx})" style="display:inline-block; padding:6px 18px; background:rgba(212,175,55,0.15); border:1px solid rgba(212,175,55,0.3); border-radius:6px; color:var(--accent); text-decoration:none; font-size:0.85rem;">点击重新拉取</a>
                </td>
            </tr>
        `;
    }

    // 自动滚动到侧边栏选中的艺人
    requestAnimationFrame(() => {
        const activeItem = dom.list.querySelector('.artist-item.active');
        if (activeItem) {
            activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    });

    // 预加载其余封面
    preloadAlbumCovers(artist.name);
}

let lastUpdateId = 0;
async function updateView() {
    const currentUpdateId = ++lastUpdateId;

    if (viewState.sIdx === -1 || !allArtistsData[viewState.sIdx]) return;
    const artist = allArtistsData[viewState.sIdx];
    const album = (artist.albums && artist.albums[viewState.aIdx]) ? artist.albums[viewState.aIdx] : null;
    if (!album) return; // 安全防御

    // 显示专辑封面（可能在本地音乐视图中被隐藏）
    dom.vCover.style.display = 'block';

    // [V12.0] 云端对齐按钮显示逻辑
    if (dom.cloudSyncBtn) {
        dom.cloudSyncBtn.style.display = 'flex';
        dom.cloudSyncBtn.onclick = () => syncArtistMetadata(artist.name);
    }

    // 更新封面
    // [V12.81] 立即渲染选项卡 (Tabs)，无需等待异步请求，解决切换延迟感
    dom.vTabs.innerHTML = '';
    artist.albums.forEach((al, i) => {
        const btn = document.createElement('div');
        btn.className = 'tab';
        btn.textContent = al.title;
        btn.onclick = () => {
            viewState.aIdx = i;
            updateView();
        };
        dom.vTabs.appendChild(btn);
    });

    requestAnimationFrame(() => {
        const activeBtn = dom.vTabs.children[viewState.aIdx];
        if (activeBtn) {
            activeBtn.classList.add('active');
            activeBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        }
    });

    if (!album) {
        // [BugFix] 艺术家目前没有任何专辑，显示空状态并阻止崩溃
        dom.vCover.src = 'src/assets/images/vinyl_default.png';
        dom.vTitle.textContent = '暂无专辑';
        dom.vYear.textContent = '未知年份';
        dom.vTracks.innerHTML = '<div class="empty-state">尚未收录该歌手的任何专辑或歌曲。</div>';
        dom.albumTitle.textContent = '暂无专辑';
        dom.albumInfo.textContent = `${artist.name} · 0 Tracks`;
        return;
    }

    const cacheKey = `${artist.name}|${album.title}`;
    const coverPath = album.cover ? (album.cover.startsWith('http') ? album.cover : (album.cover.startsWith('/') ? API_BASE + encodeURI(album.cover) : API_BASE + '/' + encodeURI(album.cover))) : '';
    const isCached = album.cover && (imageCache.albums.has(cacheKey) || dom.vCover.src.includes(album.cover));

    dom.vCover.dataset.src = coverPath;
    dom.vCover.dataset.fallback = 'src/assets/images/vinyl_default.png';

    const onCoverLoaded = () => {
        dom.vCover.style.opacity = '1';
        dom.vCover.classList.remove('lazy-loading', 'lazy-error');
        dom.vCover.classList.add('lazy-loaded');
        dom.vCover.style.filter = 'none';
    };

    const onCoverError = () => {
        dom.vCover.classList.remove('lazy-loading');
        dom.vCover.classList.add('lazy-error');
        dom.vCover.src = dom.vCover.dataset.fallback;
        dom.vCover.style.opacity = '1';
    };

    dom.vCover.onload = onCoverLoaded;
    dom.vCover.onerror = onCoverError;

    if (isCached) {
        const cachedUrl = imageCache.albums.get(cacheKey) || coverPath;
        dom.vCover.src = cachedUrl;
        dom.vCover.style.transition = 'none';
        dom.vCover.style.opacity = '1';
        requestAnimationFrame(() => {
            dom.vCover.style.transition = 'opacity 0.3s ease';
        });
    } else if (album.cover) {
        dom.vCover.style.opacity = '0';
        dom.vCover.classList.add('lazy-loading');
        dom.vCover.src = coverPath;
        if (window.LazyLoader) {
            dom.vCover.classList.remove('lazy-loading');
            dom.vCover.style.opacity = '1';
            window.LazyLoader.loadImmediately(dom.vCover);
        }
    } else {
        // [Optimization] 如果没有封面信息，直接使用 fallback
        onCoverError();
    }

    dom.vTitle.textContent = album.title;

    // 优先使用内存中已拉取的歌曲清单（极速秒开且防止因网络抖动清空歌曲）
    let currentSongs = (album.songs && album.songs.length > 0) ? [...album.songs] : [];

    // [D1 Quota Fix] 仅在内存中无歌曲数据时才发起网络请求，避免冗余全表扫描
    if (currentSongs.length === 0) {
        renderTableSkeleton(6);
        try {
            // [D1 Quota Fix] 使用 artistId 参数确保后端走索引查询，而非 artist name 的 LIKE 全表扫描
            const artistIdRaw = (artist.id || "").toString().replace(/\D/g, '');
            const response = await fetch(`${API_BASE}/api/songs?artistId=${artistIdRaw}&album=${encodeURIComponent(album.title)}`);
            if (response.ok) {
                const res = await response.json();
                if (res.code === 200 && res.data && res.data.length > 0) {
                    const artistsRes = res.data;
                    let foundAlbum = null;
                    if (artistsRes.length > 0 && artistsRes[0].albums) {
                        foundAlbum = artistsRes[0].albums.find(a => a.title === album.title) || artistsRes[0].albums[0];
                    }
                    if (foundAlbum && foundAlbum.songs && foundAlbum.songs.length > 0) {
                        currentSongs = foundAlbum.songs;
                        album.songs = currentSongs;
                    }
                }
            }
        } catch (e) {
            console.warn('[MOODY] 异步获取歌曲接口波动，保持已有歌曲列表:', e);
        }
    } else {
        console.log(`[MOODY] 专辑 "${album.title}" 歌曲命中内存缓存 (${currentSongs.length} 首，节省 D1 读取)`);
    }

    dom.vMeta.textContent = `${artist.name} · ${album.year} · ${currentSongs.length} Tracks`;

    // [V12.80] 异步对账：如果在这期间用户已经切换了艺人，直接丢弃结果防止覆盖
    if (currentUpdateId !== lastUpdateId) return;

    dom.vSongs.innerHTML = '';
    if (currentSongs.length === 0) {
        dom.vSongs.innerHTML = '<tr><td colspan="2" style="text-align:center; padding:40px; color:#666">此专辑暂无名录数据</td></tr>';
        return;
    }

    currentSongs.forEach((songData, i) => {
        const songName = typeof songData === 'string' ? songData : songData.title;
        // 三态标签判断逻辑：
        // 1. 本地上传优先
        const isUploaded = isFileUploaded(songName, artist.name);
        // 2. 其次检查服务器流媒体路径
        const isOnServer = (typeof songData === 'object' && songData.path);

        let sourceLabel, sourceTitle, sourceClass;
        let isPlayable = true;

        if (isUploaded) {
            sourceLabel = '本地';
            sourceTitle = '本地已上传文件';
            sourceClass = 'local';
        } else if (isOnServer) {
            sourceLabel = '流媒体';
            sourceTitle = '服务器流媒体文件';
            sourceClass = 'streaming';
        } else {
            sourceLabel = '暂缺';
            sourceTitle = '暂无音频资源';
            sourceClass = 'missing';
            isPlayable = false;
        }

        const tr = document.createElement('tr');
        tr.className = `st-row ${!isPlayable ? 'disabled' : ''}`;
        tr.innerHTML = `
            <td class="st-cell st-num">${String(i + 1).padStart(2, '0')}</td>
            <td class="st-cell st-title">
                <span class="song-name">
                    ${songName}
                    <span class="song-source ${sourceClass}" title="${sourceTitle}">${sourceLabel}</span>
                </span>
            </td>
        `;

        // 添加点击行播放歌曲
        tr.addEventListener('click', (e) => {
            if (!isPlayable) {
                showNotification(`暂无音频资源: ${songName}`);
                return;
            }
            // 移除焦点
            if (document.activeElement) {
                document.activeElement.blur();
            }
            // 调用播放函数
            playSong(e, songData, artist.name);
        });
        dom.vSongs.appendChild(tr);
    });

    // 检查是否有歌曲正在播放，如果是则高亮显示并注入指示器
    if (typeof playerState !== 'undefined' && playerState.currentSong) {
        if (window.updateAlbumViewActiveState) {
            window.updateAlbumViewActiveState(playerState.currentSong, playerState.currentArtist);
        }
    }

    // [New] 预测性预加载
    if (typeof prefetchTimeout !== 'undefined') clearTimeout(prefetchTimeout);

    prefetchTimeout = setTimeout(() => {
        // 再次确认当前视图没有变化
        if (viewState.sIdx === -1 || !allArtistsData[viewState.sIdx]) return;
        const currentArtist = allArtistsData[viewState.sIdx];
        const currentAlbum = currentArtist.albums[viewState.aIdx];

        if (currentArtist.name === artist.name && currentAlbum.title === album.title) {
            // checkAlbumResources(currentArtist.name, currentAlbum); // Disabled for clean console
        }
    }, 2000);
}

/**
 * [New] 检查专辑资源的可用性 (预测性预加载)
 */
function checkAlbumResources(artistName, album) {
    if (!album || !album.songs || !window.checkResourceAvailability) return;

    // console.log(`[Prefetch] 启动专辑资源预检: ${album.title}`);

    const checkTask = () => {
        currentSongs.forEach((songData, i) => {
            const songName = typeof songData === 'string' ? songData : songData.title;
            const songPath = typeof songData === 'string' ? null : songData.path;

            // 构造资源 URL (逻辑需与 player.js 保持一致)
            let audioUrl = null;

            // 1. 检查本地
            const exactKey = `${songName} - ${artistName}`;
            const bulkKey = `${songName} - 本地音乐`;

            if (window.localSongsMap && (window.localSongsMap.has(exactKey) || window.localSongsMap.has(bulkKey))) {
                // 本地存在，无需检查远程
                return;
            }

            // 2. 检查已上传
            if (window.playerState && window.playerState.uploadedFiles && window.playerState.uploadedFiles.has(songName)) {
                return;
            }

            // 3. 构造远程 URL
            if (songPath) {
                const encodedPath = songPath.split(/[\\/]/).map(segment => encodeURIComponent(segment)).join('/');
                audioUrl = `${API_BASE}/storage/${encodedPath}`;
            }

            // 发起检查
            if (audioUrl) {
                window.checkResourceAvailability(audioUrl);
            }
        });
    };

    // 使用 requestIdleCallback 避免阻塞 UI
    if ('requestIdleCallback' in window) {
        requestIdleCallback(checkTask);
    } else {
        setTimeout(checkTask, 1000);
    }
}

async function playSong(e, songData, artist) {
    const name = typeof songData === 'string' ? songData : songData.title;
    e.stopPropagation();

    // 移除焦点，防止出现光标
    if (document.activeElement) {
        document.activeElement.blur();
    }

    // [Generation Lock] 点击瞬间立即获取最新全局代次，前置旧任务（重试/自动跳过/网络预检）全部即刻作废！
    const currentGen = typeof window.nextPlayGeneration === 'function' 
        ? window.nextPlayGeneration() 
        : ++window._playGeneration;

    // 获取专辑信息
    if (!Array.isArray(allArtistsData)) {
        console.error('[MOODY] allArtistsData is not an array!', allArtistsData);
        return;
    }
    const currentArtist = allArtistsData.find(a => a.name === artist);
    if (!currentArtist) {
        console.error(`找不到歌手: ${artist}`);
        return;
    }

    const album = currentArtist.albums[viewState.aIdx];

    // [Optimistic UI] 点击瞬间立即高亮对应歌曲行，无需等待网络
    if (window.updateAlbumViewActiveState) {
        window.updateAlbumViewActiveState(name, artist, /* optimistic= */ true);
    }

    // 直接调用播放器 - 让 playAlbum 来处理音频查找，传入当前代次锁
    if (window.audioPlayer && window.audioPlayer.playAlbum) {
        // 找到点击的歌曲在专辑中的索引 (避免对象引用不一致导致的 -1)
        const songIndex = album.songs.findIndex(s => {
            const sTitle = typeof s === 'string' ? s : s.title;
            return sTitle === name;
        });

        if (songIndex !== -1) {
            await window.audioPlayer.playAlbum(album.songs, artist, album, songIndex, currentGen);
        } else {
            console.warn(`在专辑中找不到歌曲: ${name}`);
            // 兜底方案：如果找不到索引，至少尝试播放这首单曲
            const audioUrl = typeof songData === 'string' ? null : songData.path;
            if (window.audioPlayer.play) {
                await window.audioPlayer.play(name, artist, album.title, audioUrl);
            }
        }
    } else {
        console.error('window.audioPlayer.playAlbum 不存在!');
    }
}

// ==================== 全局导出 ====================
// 导出函数到全局作用域，供 HTML 中的 onclick 调用
window.uploadSongForTrack = uploadSongForTrack;
window.playLocalSong = playLocalSong;
window.deleteLocalSong = deleteLocalSong;
window.showLocalMusicView = showLocalMusicView;
window.showArtistView = showArtistView;
window.initApp = initApp;  // 导出初始化函数

// 导出 IndexedDB 相关函数，供 player.js 调用
window.saveLocalSongsToStorage = saveLocalSongsToStorage;
window.loadLocalSongsFromStorage = loadLocalSongsFromStorage;
window.clearLocalSongsStorage = clearLocalSongsStorage;
window.openDB = openDB;
window.saveAudioToIndexedDB = saveAudioToIndexedDB;
window.loadAllAudioFromIndexedDB = loadAllAudioFromIndexedDB;
window.deleteAudioFromIndexedDB = deleteAudioFromIndexedDB;

// 将本地歌曲映射也导出到全局，方便其他模块访问
window.localSongsMap = localSongsMap;

// Run App（初始化由 HTML 中的脚本统一管理）
// renderIndexBar(); // [Fix] Removed premature call
// initApp() 将在 DOMContentLoaded 时被调用

async function syncLibrary() {
    const btn = document.getElementById('syncBtn');
    const status = document.getElementById('syncStatus');

    if (btn) btn.disabled = true;
    if (status) status.innerText = 'Syncing...';

    try {
        const response = await fetch(`${API_BASE}/api/sync`, { method: 'POST' });
        const res = await response.json();
        if (response.ok && res.code === 200) {
            if (status) status.innerText = 'Success! Reloading...';
            setTimeout(() => { location.reload(); }, 1500);
        } else {
            if (status) status.innerText = res.message || 'Sync failed.';
            if (btn) btn.disabled = false;
        }
    } catch (error) {
        console.error('Sync failed:', error);
        if (status) status.innerText = 'Error: ' + error.message;
        if (btn) btn.disabled = false;
    }
}

// Export functions
window.syncLibrary = syncLibrary;

// [V12.0] 云端对齐函数
async function syncArtistMetadata(artistName) {
    if (!dom.cloudSyncBtn) return;

    const originalText = dom.cloudSyncBtn.innerText;
    dom.cloudSyncBtn.disabled = true;
    dom.cloudSyncBtn.innerHTML = '<span class="loading-spinner"></span> 正在核对云端...';

    try {
        const response = await fetch(`${API_BASE}/api/metadata/sync?artist=${encodeURIComponent(artistName)}`);
        const res = await response.json();

        if (response.ok && res.code === 200) {
            dom.cloudSyncBtn.innerHTML = '✓ 已完成校准';
            dom.cloudSyncBtn.style.background = 'rgba(76, 175, 80, 0.2)';

            // 提示用户刷新以查看新专辑名录
            setTimeout(() => {
                if (confirm(`${res.message}\n是否立即刷新页面以加载更新后的完整名录？`)) {
                    location.reload();
                } else {
                    dom.cloudSyncBtn.disabled = false;
                    dom.cloudSyncBtn.innerHTML = originalText;
                    dom.cloudSyncBtn.style.background = '';
                }
            }, 500);
        } else {
            throw new Error(res.message || '同步失败');
        }
    } catch (error) {
        console.error('Metadata sync failed:', error);
        dom.cloudSyncBtn.innerHTML = '✗ 校准失败';
        dom.cloudSyncBtn.style.background = 'rgba(244, 67, 54, 0.2)';
        setTimeout(() => {
            dom.cloudSyncBtn.disabled = false;
            dom.cloudSyncBtn.innerHTML = originalText;
            dom.cloudSyncBtn.style.background = '';
        }, 3000);
    }
}
