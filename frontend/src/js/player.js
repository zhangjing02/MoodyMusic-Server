/**
 * 音乐播放器模块
 * 实现完整的播放器功能：本地文件上传、播放控制、播放列表、歌词显示、收藏
 */

console.log('🎵 player.js 已加载');

// ==================== LRC 歌词同步模块 ====================
// 自实现的 LRC 歌词解析和同步系统
const LyricsSync = {
    currentLyrics: null,  // 当前解析后的歌词数据
    currentIndex: -1,     // 当前激活的歌词行索引

    /**
     * 解析 LRC 格式歌词
     * @param {string} lrcText - LRC 格式的歌词文本
     * @returns {Array} 解析后的歌词数组，每项包含 {time: 秒, text: 歌词}
     */
    parseLRC(lrcText) {
        if (!lrcText) return [];

        const lines = [];
        const lrcLines = lrcText.split('\n');

        for (let line of lrcLines) {
            // 增强型正则：匹配 [mm:ss.ms] 或 [mm:ss] 甚至 [m:s.ms]
            // 支持 . 或 : 作为毫秒分隔符，支持 2-3 位毫秒
            const match = line.match(/\[(\d{1,3}):(\d{2})(?:[.:](\d{2,3}))?\](.*)/);
            if (match) {
                const minutes = parseInt(match[1]);
                const seconds = parseInt(match[2]);
                const msStr = match[3] || '000';
                const milliseconds = parseInt(msStr.padEnd(3, '0').substring(0, 3));
                const time = minutes * 60 + seconds + milliseconds / 1000;
                const text = match[4].trim();

                if (text || line.trim()) { // 允许带时间戳的空行（用于停顿）
                    lines.push({ time, text });
                }
            }
        }

        // 按时间排序
        lines.sort((a, b) => a.time - b.time);
        console.log('✓ LRC 歌词解析完成，共', lines.length, '行');
        return lines;
    },

    /**
     * 根据当前时间获取应该高亮的歌词行索引
     * @param {number} currentTime - 当前播放时间（秒）
     * @returns {number} 歌词行索引，-1 表示没有匹配的
     */
    getCurrentLineIndex(currentTime) {
        if (!this.currentLyrics || this.currentLyrics.length === 0) return -1;

        let index = -1;
        for (let i = 0; i < this.currentLyrics.length; i++) {
            if (this.currentLyrics[i].time <= currentTime) {
                index = i;
            } else {
                break;
            }
        }
        return index;
    },

    /**
     * 加载歌词
     * @param {string} lrcText - LRC 格式的歌词文本
     */
    load(lrcText) {
        this.currentLyrics = this.parseLRC(lrcText);
        this.currentIndex = -1;
    },

    /**
     * 重置歌词
     */
    reset() {
        this.currentLyrics = null;
        this.currentIndex = -1;
    }
};
window.LyricsSync = LyricsSync;


// ==================== 客户端遥测 (Client Telemetry) ====================
async function reportClientError(type, songId, message) {
    // 防止本地开发环境误报
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') return;

    try {
        await fetch(`${window.API_BASE || ''}/api/report-error`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, songId: parseInt(songId) || 0, message })
        });
    } catch (e) {
        console.warn('遥测上报失败:', e);
    }
}
window.reportClientError = reportClientError;

// ==================== 播放器状态管理 ====================
const playerState = {
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    volume: 0.7,
    playMode: 'sequence',
    isRoaming: false,  // 随心漫游模式标记
    currentSong: null,
    currentArtist: null,
    currentAlbum: null,
    currentLrcPath: null, // 新增：保存当前播放歌曲的歌词路径
    _skipCount: 0,     // 连续跳过计数器（防死循环）
    playlist: [],
    favorites: [],
    uploadedFiles: new Map(),
    lyricsOffset: 0  // 歌词时间偏移量（秒），正数延后，负数提前
};

// 将 playerState 暴露到全局
window.playerState = playerState;

// ==================== 资源可用性缓存 (Resource Availability Cache) ====================
window.resourceAvailabilityCache = new Map();

// ==================== 加载状态管理 ====================
let _prefetchedUrl = null; // 已预加载的 URL
let _prefetchAudio = null; // 预加载用的 Audio 对象
let _loadingBar = null;    // 加载进度条 DOM 元素
let _fakeTimer = null;     // 模拟进度定时器
let _fakeProgress = 0;     // 当前模拟进度

function setLoadingState(isLoading) {
    const progressBg = document.querySelector('.pb-progress-bg');
    if (!progressBg) return;

    if (isLoading) {
        // 创建或重用进度条元素
        if (!_loadingBar) {
            _loadingBar = document.createElement('div');
            _loadingBar.className = 'pb-loading-bar';
            progressBg.appendChild(_loadingBar);
        }
        _loadingBar.classList.remove('done');
        _loadingBar.style.opacity = '1';
        _loadingBar.style.width = '0%';
        _fakeProgress = 0;

        // 启动模拟缓慢爬升：先慢后快，最终停在 ~70%
        clearInterval(_fakeTimer);
        _fakeTimer = setInterval(() => {
            // 每次增量随当前进度递减，模拟减速效果
            if (_fakeProgress < 25) {
                _fakeProgress += 1.5;       // 0~25%：较慢启动
            } else if (_fakeProgress < 50) {
                _fakeProgress += 1.0;       // 25~50%：稍快
            } else if (_fakeProgress < 70) {
                _fakeProgress += 0.4;       // 50~70%：趋缓
            } else {
                // 70% 后几乎停滞，等待真实完成
                _fakeProgress += 0.1;
                if (_fakeProgress >= 85) {
                    clearInterval(_fakeTimer);
                    _fakeTimer = null;
                }
            }
            if (_loadingBar) {
                _loadingBar.style.width = _fakeProgress + '%';
            }
        }, 80);
    } else {
        finishLoading();
    }
}

// 真实缓冲进度更新：取模拟值和真实值的较大者
function updateLoadingProgress(percent) {
    if (!_loadingBar) return;
    const realProgress = Math.max(5, Math.min(90, percent));
    if (realProgress > _fakeProgress) {
        _fakeProgress = realProgress;
        _loadingBar.style.width = _fakeProgress + '%';
    }
}

// 加载完成：快速冲到100% → 淡出消失
function finishLoading() {
    if (!_loadingBar) return;
    clearInterval(_fakeTimer);
    _fakeTimer = null;
    _fakeProgress = 0;
    _loadingBar.classList.add('done');
    // 淡出动画结束后重置
    setTimeout(() => {
        if (_loadingBar) {
            _loadingBar.classList.remove('done');
            _loadingBar.style.width = '0%';
            _loadingBar.style.opacity = '0';
        }
    }, 600);
}


// [Race Condition Guard] 播放代次计数器、定时器与网络请求物理中断控制器
// 每次发起新的播放请求时递增，并物理取消上一次进行中的 HEAD 检查和歌词请求
let _playGeneration = 0;
let _autoSkipTimer = null;
let _retryTimer = null;
let _mediaLoadingWatchdogTimer = null;
let _activeResourceAbortController = null;
let _activeLyricsAbortController = null;

function clearMediaLoadingWatchdog() {
    if (_mediaLoadingWatchdogTimer) {
        clearTimeout(_mediaLoadingWatchdogTimer);
        _mediaLoadingWatchdogTimer = null;
    }
}

function nextPlayGeneration() {
    _playGeneration++;
    clearMediaLoadingWatchdog();

    // 1. 物理掐断上一次未完成的资源预检网络请求
    if (_activeResourceAbortController) {
        try {
            _activeResourceAbortController.abort('New song selected');
        } catch (e) {}
        _activeResourceAbortController = null;
    }

    // 2. 物理掐断上一次未完成的歌词网络请求
    if (_activeLyricsAbortController) {
        try {
            _activeLyricsAbortController.abort('New song selected');
        } catch (e) {}
        _activeLyricsAbortController = null;
    }

    // 3. 物理掐断当前 HTML5 Audio 的网络流缓冲
    if (typeof player !== 'undefined' && player && player.audio) {
        try {
            player.audio.pause();
        } catch (e) {}
    }

    // 4. 清理定时器
    if (_autoSkipTimer) {
        clearTimeout(_autoSkipTimer);
        _autoSkipTimer = null;
    }
    if (_retryTimer) {
        clearTimeout(_retryTimer);
        _retryTimer = null;
    }

    console.log(`[Generation Lock] 🔒 Active generation bumped to: ${_playGeneration}, previous network requests physically aborted.`);
    return _playGeneration;
}
window.nextPlayGeneration = nextPlayGeneration;
window._getPlayGeneration = () => _playGeneration;

/**
 * 检查资源可用性 (HEAD 请求)
 * @param {string} url - 资源 URL
 * @returns {Promise<boolean>} - 是否可用
 */
async function checkResourceAvailability(url) {
    if (!url) return false;

    // 如果是 Data URL 或 Blob URL，直接认为可用
    if (url.startsWith('data:') || url.startsWith('blob:')) {
        return true;
    }

    // 检查缓存
    if (window.resourceAvailabilityCache.has(url)) {
        const cached = window.resourceAvailabilityCache.get(url);
        // TTL: 5分钟 (300000 ms)
        if (Date.now() - cached.timestamp < 300000) {
            console.log(`[Cache Hit] ${url} => ${cached.available}`);
            return cached.available;
        }
    }

    // 实时检查
    // console.log(`[Resource Check] Checking: ${url}`); // Muted for cleaner console
    const controller = new AbortController();
    _activeResourceAbortController = controller;
    let isHeadTimeout = false;
    const timeoutId = setTimeout(() => {
        isHeadTimeout = true;
        controller.abort('HEAD timeout (3s)');
    }, 3000); // 3秒超时

    try {
        // 使用 HEAD 请求只检查头信息，支持主动物理取消
        const response = await fetch(url, {
            method: 'HEAD',
            signal: controller.signal,
            cache: 'no-cache' // 确保不读取浏览器 HTTP 缓存
        });

        clearTimeout(timeoutId);
        if (_activeResourceAbortController === controller) {
            _activeResourceAbortController = null;
        }

        // 仅明确返回 404 Not Found 时断定资源不存在；其他状态码（如 403/405/500/502 等）对于公网音频不应粗暴断定不存在
        let available = response.ok;
        if (!available && url.startsWith('http') && response.status !== 404) {
            console.warn(`[Resource Check] HEAD returned HTTP ${response.status}, allowing audio element pass-through:`, url);
            available = true;
        }

        if (window.resourceAvailabilityCache) {
            window.resourceAvailabilityCache.set(url, {
                available: available,
                timestamp: Date.now()
            });
        }

        // console.log(`[Resource Check] Result: ${available}`); // Muted
        return available;
    } catch (e) {
        clearTimeout(timeoutId);
        if (_activeResourceAbortController === controller) {
            _activeResourceAbortController = null;
        }

        // [Physical Cancellation] 仅当用户主动切换新歌曲触发的中断（非 HEAD 超时），才静默退出
        if (e.name === 'AbortError' && !isHeadTimeout) {
            console.log(`[Resource Check] 🛑 HEAD request physically aborted by user navigation for: ${url}`);
            return false;
        }

        // [CORS & Network Timeout Fall-through] 
        // 网络 URL (http/https) 若因 HEAD 超时、CORS 响应或网络波动报错，绝不能武断判定资源不存在！
        // 必须放行让原生 audio 标签尝试流式缓冲加载，由底层 8s Watchdog 和 error 事件兜底
        if (url.startsWith('http')) {
            console.warn('[Resource Check] Network resource HEAD failed/timed out, allowing audio element pass-through:', url);
            return true;
        }

        // 本地资源网络错误或超时标记为不可用
        if (window.resourceAvailabilityCache) {
            window.resourceAvailabilityCache.set(url, {
                available: false,
                timestamp: Date.now()
            });
        }
        return false;
    }
}

// 暴露给外部使用 (如 app.js 的预加载)
window.checkResourceAvailability = checkResourceAvailability;

// ==================== DOM 元素 ====================
const player = {
    audio: document.getElementById('audioPlayer'),
    playPauseBtn: document.getElementById('playPauseBtn'),
    prevBtn: document.getElementById('prevBtn'),
    nextBtn: document.getElementById('nextBtn'),
    modeBtn: document.getElementById('modeBtn'),
    volumeBtn: document.getElementById('volumeBtn'),
    volumeSlider: document.getElementById('volumeSlider'),
    volumeFill: document.getElementById('volumeFill'),
    favoriteBtn: document.getElementById('favoriteBtn'),
    progressContainer: document.getElementById('progressContainer'),
    progressBar: document.getElementById('pBar'),
    progressHandle: document.getElementById('progressHandle'),
    pTitle: document.getElementById('pTitle'),
    pTitleOverlay: document.getElementById('pTitleOverlay'),
    pTime: document.getElementById('pTime'),
    pThumb: document.getElementById('pThumb'),
    vinylRecord: document.getElementById('vinylRecord'),
    vinylCover: document.getElementById('vinylCover'),
    vinylContainer: document.querySelector('.vinyl-container'),
    tonearm: document.getElementById('tonearm'),
    playlistContent: document.getElementById('playlistContent'),
    lyricsContent: document.getElementById('lyricsContent'),
    playlistToggle: document.getElementById('playlistToggle'),
    lyricsToggle: document.getElementById('lyricsToggle'),
    albumLyrics: document.getElementById('albumLyrics'),
    uploadInput: document.getElementById('audioUpload'),
    uploadedCount: document.getElementById('uploadedCount'),
    // 歌词调整相关 (这些将在 initPlayer 中二次确认，防止 null)
    lyricAdjBtn: null,
    lyricModal: null,
    lyricRawText: null,
    modalCurrentTime: null
};

/**
 * 延迟绑定 DOM 元素，确保在 DOMContentLoaded 后运行
 */
function bindDOMElements() {
    player.audio = document.getElementById('audioPlayer');
    player.roamBtn = document.getElementById('roamBtn');
    player.playPauseBtn = document.getElementById('playPauseBtn');
    player.prevBtn = document.getElementById('prevBtn');
    player.nextBtn = document.getElementById('nextBtn');
    player.modeBtn = document.getElementById('modeBtn');
    player.volumeBtn = document.getElementById('volumeBtn');
    player.volumeSlider = document.getElementById('volumeSlider');
    player.volumeFill = document.getElementById('volumeFill');
    player.favoriteBtn = document.getElementById('favoriteBtn');
    player.progressContainer = document.getElementById('progressContainer');
    player.progressBar = document.getElementById('pBar');
    player.progressHandle = document.getElementById('progressHandle');
    player.pTitle = document.getElementById('pTitle');
    player.pTitleOverlay = document.getElementById('pTitleOverlay');
    player.pTime = document.getElementById('pTime');
    player.pThumb = document.getElementById('pThumb');
    player.vinylRecord = document.getElementById('vinylRecord');
    player.vinylCover = document.getElementById('vinylCover');
    player.vinylContainer = document.querySelector('.vinyl-container');
    player.tonearm = document.getElementById('tonearm');
    player.playlistContent = document.getElementById('playlistContent');
    player.lyricsContent = document.getElementById('lyricsContent');
    player.playlistToggle = document.getElementById('playlistToggle');
    player.lyricsToggle = document.getElementById('lyricsToggle');
    player.albumLyrics = document.getElementById('albumLyrics');
    player.uploadInput = document.getElementById('audioUpload');
    player.uploadedCount = document.getElementById('uploadedCount');

    // 歌词调整弹窗相关
    player.lyricAdjBtn = document.getElementById('lyricAdjBtn');
    player.lyricModal = document.getElementById('lyricModal');
    player.lyricRawText = document.getElementById('lyricRawText');
    player.closeLyricModal = document.getElementById('closeLyricModal');
    player.cancelLyricUpdate = document.getElementById('cancelLyricUpdate');
    player.saveLyricUpdate = document.getElementById('saveLyricUpdate');
    player.btnShiftForward = document.getElementById('btnShiftForward');
    player.btnShiftBackward = document.getElementById('btnShiftBackward');
    player.shiftAmount = document.getElementById('shiftAmount');
    player.btnAutoFormat = document.getElementById('btnAutoFormat');
    player.btnManualTag = document.getElementById('btnManualTag');
    player.modalPlayPause = document.getElementById('modalPlayPause');
    player.modalCurrentTime = document.getElementById('modalCurrentTime');

    // 元数据助手按钮
    player.btnInsertTitle = document.getElementById('btnInsertTitle');
    player.btnInsertArtist = document.getElementById('btnInsertArtist');
    player.btnInsertAlbum = document.getElementById('btnInsertAlbum');
    player.btnInsertOffset = document.getElementById('btnInsertOffset');
}

// ==================== 初始化 ====================
async function initPlayer() {
    console.log('初始化播放器...');

    // 重新绑定所有 DOM 元素，确保它们已加载
    bindDOMElements();

    // 初始化存储模块
    if (typeof initStorage === 'function') {
        initStorage();
    }

    if (!player.audio) {
        console.error('音频播放器未找到');
        return;
    }

    // 验证所有关键DOM元素
    const elementsToCheck = ['audio', 'playPauseBtn', 'prevBtn', 'nextBtn', 'modeBtn'];
    elementsToCheck.forEach(key => {
        if (!player[key]) {
            console.warn(`元素未找到: ${key}`);
        } else {
            console.log(`✓ ${key} 已找到`);
        }
    });

    // 从存储加载音量设置
    const savedVolume = Settings.loadVolume();
    player.audio.volume = savedVolume;
    playerState.volume = savedVolume;
    updateVolumeIcon(savedVolume);
    if (player.volumeFill) {
        player.volumeFill.style.width = `${savedVolume * 100}%`;
    }
    console.log(`✓ 已加载音量设置: ${savedVolume}`);

    // 从存储加载播放模式
    const savedPlayMode = Settings.loadPlayMode();
    playerState.playMode = savedPlayMode;
    updateModeButton();
    console.log(`✓ 已加载播放模式: ${savedPlayMode}`);

    // 从存储加载收藏列表
    playerState.favorites = Settings.loadFavorites();
    updateFavoriteButton();
    console.log(`✓ 已加载收藏列表: ${playerState.favorites.length} 首`);

    bindPlayerEvents();
    updateModeButton();
    updateVolumeIcon(playerState.volume);

    // 从 localSongsMap 同步已保存的本地歌曲到播放器
    console.log('检查 localSongsMap:', window.localSongsMap);
    console.log('localSongsMap 大小:', window.localSongsMap ? window.localSongsMap.size : 0);

    if (window.localSongsMap && window.localSongsMap.size > 0) {
        let syncCount = 0;
        for (const [key, value] of window.localSongsMap.entries()) {
            console.log(`同步歌曲: ${value.songName}, audioUrl 长度: ${value.audioUrl ? value.audioUrl.length : 0}`);

            // 同步到 uploadedFiles
            playerState.uploadedFiles.set(value.songName, value.audioUrl);

            // 同时添加到播放列表
            await addToPlaylist(value.songName, value.artistName, '本地文件', value.audioUrl, '');

            syncCount++;
        }
        console.log(`✓ 从 IndexedDB 同步了 ${syncCount} 首本地歌曲到播放器`);
        updateUploadedCount(syncCount);

        // 更新播放列表UI
        updatePlaylistUI();
        console.log('✓ 播放列表UI已更新');
    } else {
        console.log('⚠ 没有找到已保存的本地歌曲');
    }

    // 初始化上传计数显示为0
    if (player.uploadedCount && player.uploadedCount.textContent === '') {
        player.uploadedCount.textContent = '0';
        console.log('上传计数初始化为 0');
    }

    // 初始化黑胶唱片默认封面背景
    if (player.vinylCover) {
        const defaultCover = 'https://placehold.co/200x200/222/FFF?text=Music';
        player.vinylCover.style.backgroundImage = `url('${defaultCover}')`;
        if (player.pThumb) {
            player.pThumb.src = defaultCover;
        }
    }

    console.log('播放器初始化完成');
}

function bindPlayerEvents() {
    player.audio.addEventListener('error', (e) => {
        clearMediaLoadingWatchdog();
        console.error('播放出错:', e);
        const errorCode = player.audio.error ? player.audio.error.code : 0;
        let errorMsg = '播放出错';

        switch (errorCode) {
            case 1: errorMsg = '用户终止了获取音频'; break;
            case 2: errorMsg = '网络错误，音频下载失败'; break;
            case 3: errorMsg = '音频解码失败'; break;
            case 4: errorMsg = '无法加载音频 (可能是服务未开启或文件不存在)'; break;
        }

        showNotification(`⚠️ ${errorMsg}，自动跳过...`);
        if (playerState.currentSong) {
            reportClientError('audio', playerState.currentSong.id, errorMsg);
        }
        playerState.isPlaying = false;
        updatePlayPauseButton();

        // 漫游模式防卡死：遇到音频异常直接切下一首漫游（永不停止）
        if (window.RoamingManager && window.RoamingManager.isActive) {
            setTimeout(() => {
                if (window.RoamingManager && window.RoamingManager.isActive) {
                    window.RoamingManager.playNext();
                }
            }, 300);
            return;
        }

        // 自动跳过到下一首（带防死循环保护）
        if (playerState._skipCount < playerState.playlist.length) {
            playerState._skipCount++;
            setTimeout(() => playNext(), 300);
        } else {
            console.warn('[Player] 已连续跳过全部曲目，停止播放');
            playerState._skipCount = 0;
        }
    });

    player.audio.addEventListener('loadedmetadata', () => {
        playerState.duration = player.audio.duration;
        updateTimeDisplay();
    });

    // 监听真实缓冲进度，更新加载进度条
    player.audio.addEventListener('progress', () => {
        if (player.audio.buffered.length > 0 && player.audio.duration > 0) {
            const bufferedEnd = player.audio.buffered.end(player.audio.buffered.length - 1);
            const percent = (bufferedEnd / player.audio.duration) * 100;
            updateLoadingProgress(percent);
        }
    });


    player.audio.addEventListener('playing', () => {
        clearMediaLoadingWatchdog();
        setLoadingState(false);
    });

    player.audio.addEventListener('timeupdate', () => {
        if (player.audio.currentTime > 0) {
            clearMediaLoadingWatchdog();
        }
        playerState.currentTime = player.audio.currentTime;
        updateProgressBar();
        updateTimeDisplay();
        updateLyricsSync();

        // 预加载下一首：当前歌曲剩余 15 秒时触发
        if (playerState.duration > 0 && playerState.currentTime > 0) {
            const remaining = playerState.duration - playerState.currentTime;
            if (remaining < 15 && remaining > 0) {
                prefetchNextSong();
            }
        }
    });

    player.audio.addEventListener('ended', () => {
        clearMediaLoadingWatchdog();
        handleSongEnded();
    });

    player.audio.addEventListener('play', () => {
        console.log('[Event] Audio play');
        playerState.isPlaying = true;
        updatePlayPauseButton();
    });

    player.audio.addEventListener('pause', () => {
        console.log('[Event] Audio pause');
        clearMediaLoadingWatchdog();
        playerState.isPlaying = false;
        updatePlayPauseButton();
    });

    // 进度条拖动
    let isDragging = false;
    if (player.progressContainer) {
        player.progressContainer.addEventListener('mousedown', (e) => {
            isDragging = true;
            // 阻止文字选中等原生行为
            e.preventDefault();
            document.body.style.userSelect = 'none';
            handleProgressSeek(e);
        });

        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                handleProgressSeek(e);
            }
        });

        document.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                document.body.style.userSelect = '';
                // 使用 _seekPercent 精确跳转，避免读 DOM style 被 timeupdate 覆盖的问题
                if (_seekPercent >= 0 && playerState.duration) {
                    player.audio.currentTime = _seekPercent * playerState.duration;
                }
                // 重置，允许 timeupdate 继续刷新进度条
                _seekPercent = -1;
            }
        });

        // 支持触摸设备
        player.progressContainer.addEventListener('touchstart', (e) => {
            isDragging = true;
            e.preventDefault();
            handleProgressSeek(e.touches[0]);
        }, { passive: false });

        document.addEventListener('touchmove', (e) => {
            if (isDragging) {
                handleProgressSeek(e.touches[0]);
            }
        }, { passive: true });

        document.addEventListener('touchend', () => {
            if (isDragging) {
                isDragging = false;
                if (_seekPercent >= 0 && playerState.duration) {
                    player.audio.currentTime = _seekPercent * playerState.duration;
                }
                _seekPercent = -1;
            }
        });
    }

    // 音量控制
    let isVolumeDragging = false;
    if (player.volumeSlider) {
        player.volumeSlider.addEventListener('mousedown', (e) => {
            isVolumeDragging = true;
            handleVolumeChange(e);
        });

        document.addEventListener('mousemove', (e) => {
            if (isVolumeDragging) {
                handleVolumeChange(e);
            }
        });

        document.addEventListener('mouseup', () => {
            isVolumeDragging = false;
        });
    }

    // 控制按钮
    if (player.roamBtn) {
        player.roamBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (window.RoamingManager) {
                window.RoamingManager.toggle();
            }
        });
    }
    if (player.playPauseBtn) player.playPauseBtn.addEventListener('click', togglePlayPause);
    if (player.prevBtn) player.prevBtn.addEventListener('click', playPrevious);
    if (player.nextBtn) player.nextBtn.addEventListener('click', playNext);
    if (player.modeBtn) player.modeBtn.addEventListener('click', cyclePlayMode);
    if (player.favoriteBtn) {
        player.favoriteBtn.addEventListener('click', toggleFavorite);
        // 注入 SVG 心形图标（跨平台一致）
        const heartSpan = player.favoriteBtn.querySelector('.heart-icon');
        if (heartSpan) {
            heartSpan.innerHTML = '<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';
        }
    }
    if (player.volumeBtn) player.volumeBtn.addEventListener('click', toggleMute);

    // 面板折叠
    if (player.playlistToggle) {
        player.playlistToggle.addEventListener('click', () => {
            if (player.playlistContent) {
                player.playlistContent.classList.toggle('collapsed');
                player.playlistToggle.classList.toggle('collapsed');
            }
        });
    }
    if (player.lyricsToggle) {
        player.lyricsToggle.addEventListener('click', () => {
            if (player.lyricsContent) {
                player.lyricsContent.classList.toggle('collapsed');
                player.lyricsToggle.classList.toggle('collapsed');
            }
        });
    }

    // 专辑页歌词拖拽调整偏移
    if (player.albumLyrics) {
        setupLyricsDrag();
    }

    // 文件上传
    if (player.uploadInput) {
        player.uploadInput.addEventListener('change', handleFileUpload);
    }

    // 歌词调整弹窗事件
    if (player.lyricAdjBtn) player.lyricAdjBtn.addEventListener('click', openLyricAdjuster);
    if (player.closeLyricModal) player.closeLyricModal.addEventListener('click', () => player.lyricModal.classList.remove('active'));
    if (player.cancelLyricUpdate) player.cancelLyricUpdate.addEventListener('click', () => player.lyricModal.classList.remove('active'));
    if (player.btnShiftForward) player.btnShiftForward.addEventListener('click', () => adjustLyricTime(1)); // 提前
    if (player.btnShiftBackward) player.btnShiftBackward.addEventListener('click', () => adjustLyricTime(-1)); // 延后
    if (player.saveLyricUpdate) player.saveLyricUpdate.addEventListener('click', saveLyricUpdate);

    // 高级编辑功能
    if (player.btnAutoFormat) player.btnAutoFormat.addEventListener('click', autoFormatLyrics);
    if (player.btnManualTag) player.btnManualTag.addEventListener('click', manualTagCurrentLine);
    if (player.modalPlayPause) player.modalPlayPause.addEventListener('click', togglePlayPause);

    // 元数据插入事件
    if (player.btnInsertTitle) player.btnInsertTitle.addEventListener('click', () => insertMetadataTag('ti', playerState.currentSong));
    if (player.btnInsertArtist) player.btnInsertArtist.addEventListener('click', () => insertMetadataTag('ar', playerState.currentArtist));
    if (player.btnInsertAlbum) player.btnInsertAlbum.addEventListener('click', () => insertMetadataTag('al', playerState.currentAlbum));
    if (player.btnInsertOffset) player.btnInsertOffset.addEventListener('click', () => insertMetadataTag('offset', '0'));

    // 预览面板点击事件 (事件委托)
    const previewPanel = document.getElementById('lyricPreviewPanel');
    if (previewPanel) {
        previewPanel.addEventListener('click', (e) => {
            const line = e.target.closest('.lyric-preview-line');
            if (!line) return;

            const index = parseInt(line.getAttribute('data-index'));
            const time = parseFloat(line.getAttribute('data-time'));

            if (TapSyncState.active) {
                // 如果是打点模式，点击对应行进行打点
                handlePreviewLineTap(index);
            } else if (!isNaN(time)) {
                // 普通模式：点击跳转进度
                player.audio.currentTime = time;
                if (!playerState.isPlaying) togglePlayPause();
                showNotification(`已跳转至 ${formatTime(time)}`);
            }
        });
    }

    // 逐句打点模式
    const btnTapSync = document.getElementById('btnTapSync');
    const btnUndoTap = document.getElementById('btnUndoTap');
    if (btnTapSync) btnTapSync.addEventListener('click', () => {
        if (TapSyncState.active) exitTapSyncMode();
        else enterTapSyncMode();
    });
    if (btnUndoTap) btnUndoTap.addEventListener('click', undoTapMark);

    // 快捷键支持 (全局但限弹窗激活)
    document.addEventListener('keydown', handleEditorShortcuts);

    // 监听页面休眠/切出唤醒与网络重连，实现漫游模式生命周期保活
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            console.log('[Lifecycle] 页面恢复前台可见');
            if (window.RoamingManager && window.RoamingManager.isActive) {
                // 1. 恢复前台时立即补充在后台消耗的漫游预缓冲
                window.RoamingManager.fillQueue();
                // 2. 检查播放器是否在后台播放完毕但未推进切歌
                if (player && player.audio) {
                    if (player.audio.ended || (playerState.isPlaying && player.audio.paused)) {
                        console.log('[Lifecycle] 唤醒检测：音频已结束或处于停滞，推进下一首');
                        window.RoamingManager.playNext();
                    }
                }
            }
        }
    });

    window.addEventListener('online', () => {
        console.log('[Network] 网络已重新连接');
        if (window.RoamingManager && window.RoamingManager.isActive) {
            window.RoamingManager.fillQueue();
            if (player && player.audio && player.audio.paused && playerState.isPlaying) {
                window.RoamingManager.playNext();
            }
        }
    });
}

// ==================== 歌词拖拽调整 ====================
let lyricsDragState = {
    isDragging: false,
    startY: 0,
    startOffset: 0
};

function setupLyricsDrag() {
    const scrollContainer = player.albumLyrics?.querySelector('.lyrics-scroll');
    if (!scrollContainer) return;

    scrollContainer.addEventListener('mousedown', (e) => {
        lyricsDragState.isDragging = true;
        lyricsDragState.startY = e.clientY;
        lyricsDragState.startOffset = playerState.lyricsOffset;
        player.albumLyrics.classList.add('dragging');
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!lyricsDragState.isDragging) return;

        const deltaY = lyricsDragState.startY - e.clientY;
        // 每拖动 100 像素调整 1 秒
        const offsetAdjustment = deltaY / 100;
        playerState.lyricsOffset = lyricsDragState.startOffset + offsetAdjustment;

        // 显示偏移量提示
        showLyricsOffsetHint();
    });

    document.addEventListener('mouseup', () => {
        if (lyricsDragState.isDragging) {
            lyricsDragState.isDragging = false;
            player.albumLyrics?.classList.remove('dragging');
        }
    });
}

let offsetHintTimeout;

// ==================== 歌词调整持久化逻辑 ====================

/**
 * 打开歌词调整弹窗
 */
async function openLyricAdjuster() {
    // 获取当前播放项
    const currentIndex = getCurrentPlaylistIndex();
    const item = currentIndex !== -1 ? playerState.playlist[currentIndex] : null;

    if (!item) {
        showNotification('当前没有正在播放的歌曲');
        return;
    }

    if (!player.lyricModal) return;
    player.lyricModal.classList.add('active');

    // --- 第一步：即时呈现已有内容 (确保响应速度) --- 
    let initialText = item.lyrics || '';

    // 如果内存没有，尝试从 LyricsSync 还原 (最后手段)
    if (!initialText && LyricsSync.currentLyrics && LyricsSync.currentLyrics.length > 0) {
        initialText = LyricsSync.currentLyrics.map(l => {
            const mins = Math.floor(l.time / 60).toString().padStart(2, '0');
            const secs = (l.time % 60).toFixed(2).padStart(5, '0');
            return `[${mins}:${secs}]${l.text}`;
        }).join('\n');
    }

    // 填充并预览
    player.lyricRawText.value = initialText;
    renderEditorPreview(initialText);

    if (!initialText && !playerState.currentLrcPath) {
        showNotification('当前歌曲没有可编辑的歌词内容');
        // 不 return，允许用户手动输入
    }

    // --- 第二步：后台获取最新版本 (不阻塞 UI) ---
    if (playerState.currentLrcPath) {
        console.log(`[LyricSync] 后台尝试获取原始内容: ${playerState.currentLrcPath}`);
        try {
            // 设置 5 秒超时，防止因服务器或网络问题导致永久挂起
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);

            const resp = await fetch(`${window.API_BASE || ''}/api/lyrics/raw?path=${encodeURIComponent(playerState.currentLrcPath)}`, {
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (resp.ok) {
                const text = await resp.text();
                // 只有当用户尚未开始大规模编辑时才覆盖（简单判断：值未变或之前为空）
                if (!player.lyricRawText.value || player.lyricRawText.value === initialText) {
                    player.lyricRawText.value = text;
                    renderEditorPreview(text);
                    console.log(`[LyricSync] 已更新为服务器最新原始内容 (${text.length} 字节)`);
                }
            }
        } catch (err) {
            console.warn('[LyricSync] 后台获取失败:', err);
        }
    }
}

/**
 * 调整歌词时间戳 (整体平移)
 * @param {number} direction - 1 表示提前 (减去时间), -1 表示延后 (加上时间)
 */
function adjustLyricTime(direction) {
    const amountAttr = player.shiftAmount.value || "30";
    const seconds = parseFloat(amountAttr);
    if (isNaN(seconds)) return;

    // 真正的逻辑：
    // 快进 30S (前进) = 时间戳减小 30S
    // 后退 30S (延后) = 时间戳增大 30S
    // 用户说 "快 30S" 对应的是向前平移。
    const offset = direction * seconds * -1; // 因为我们要调整的是文件内容的时间戳

    const rawText = player.lyricRawText.value;
    if (!rawText) return;

    const lines = rawText.split('\n');
    const shiftedLines = lines.map(line => {
        // 匹配 [mm:ss.xx] 或 [mm:ss:xx] 或 [mm:ss.xxx]
        return line.replace(/\[(\d{2,3}):(\d{2})[.:](\d{2,3})\]/g, (match, m, s, ms) => {
            let totalMs = parseInt(m) * 60 * 1000 + parseInt(s) * 1000 + parseInt(ms.padEnd(3, '0').substring(0, 3));
            totalMs += offset * 1000;
            if (totalMs < 0) totalMs = 0;

            const newM = Math.floor(totalMs / 60000);
            const newS = Math.floor((totalMs % 60000) / 1000);
            const newMs = Math.floor(totalMs % 1000);

            // 保持原始精度
            const msStr = ms.length === 2 ?
                String(Math.floor(newMs / 10)).padStart(2, '0') :
                String(newMs).padStart(3, '0');

            return `[${String(newM).padStart(2, '0')}:${String(newS).padStart(2, '0')}.${msStr}]`;
        });
    });

    player.lyricRawText.value = shiftedLines.join('\n');
    showNotification(`已平移 ${offset > 0 ? '延后' : '提前'} ${Math.abs(offset)} 秒`);
}

/**
 * 保存修改到服务器
 */
async function saveLyricUpdate() {
    if (!playerState.currentLrcPath) return;

    const content = player.lyricRawText.value;
    const path = playerState.currentLrcPath;

    try {
        const resp = await fetch(`${window.API_BASE || ''}/api/lyrics/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, content })
        });

        if (!resp.ok) throw new Error('保存失败');

        showNotification('✅ 歌词已成功保存至服务器');
        player.lyricModal.classList.remove('active');

        // --- 实时同步：更新内存状态并让主播放器立即生效 ---
        const currentIndex = getCurrentPlaylistIndex();
        if (currentIndex !== -1) {
            // 1. 同步内存缓存，防止再次播放时读取旧歌词
            playerState.playlist[currentIndex].lyrics = content;
            console.log('[LyricSync] 内存歌词已实时更新');

            // 2. 如果当前正在播放这首歌，立即重新解析并载入预览
            if (playerState.currentSong === playerState.playlist[currentIndex].song) {
                const parsed = LyricsSync.parseLRC(content);
                LyricsSync.load(content);

                // 核心修复：立即重新渲染播放器的歌词 DOM
                if (typeof renderParsedLyrics === 'function') {
                    renderParsedLyrics(parsed);
                }

                // 强制触发一次 UI 高亮更新
                if (typeof updateLyricsSync === 'function') {
                    updateLyricsSync();
                }
                console.log('[LyricSync] 主播放器歌词已通过内存数据实时重绘生效');
            }
        }
    } catch (err) {
        console.error('保存歌词出现异常:', err);
        showNotification('❌ 保存失败，请检查网络或后端权限');
    }
}

/**
 * 智能格式化：尝试匹配网络时间戳或执行线性预估
 */
async function autoFormatLyrics() {
    const rawText = player.lyricRawText.value;
    if (!rawText) return;

    const lines = rawText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length === 0) return;

    showNotification('🔍 正在尝试智能匹配时间戳...');

    // 1. 尝试从 LRCLIB 获取
    const remoteLrc = await fetchLrcFromLib(playerState.currentSong, playerState.currentArtist);
    if (remoteLrc) {
        const remoteLines = LyricsSync.parseLRC(remoteLrc);
        if (remoteLines.length > 0) {
            // 简单的结构套用：如果行数接近，尝试逐行合并时间戳
            // 为了安全，这里我们直接采用远程歌词，或者尝试将远程时间戳注入到用户当前的文本行（如果行数一致）
            if (Math.abs(remoteLines.length - lines.length) <= 5) {
                const merged = lines.map((text, i) => {
                    const timeObj = remoteLines[i] || remoteLines[remoteLines.length - 1];
                    const m = Math.floor(timeObj.time / 60).toString().padStart(2, '0');
                    const s = Math.floor(timeObj.time % 60).toString().padStart(2, '0');
                    const ms = Math.floor((timeObj.time % 1) * 100).toString().padStart(2, '0');
                    return `[${m}:${s}.${ms}]${text}`;
                });
                player.lyricRawText.value = merged.join('\n');
                renderEditorPreview(player.lyricRawText.value);
                showNotification('✅ 已成功从网络库匹配并套用时间戳');
                return;
            } else {
                // 如果行数差异大，询问是否直接替换
                if (confirm('找到网络歌词但与当前文本行数差异较大，是否直接替换为网络版本？')) {
                    player.lyricRawText.value = remoteLrc;
                    renderEditorPreview(remoteLrc);
                    showNotification('✅ 已更新为网络匹配歌词');
                    return;
                }
            }
        }
    }

    // 2. 兜底方案：执行线性预估渲染 (Prior Standard)
    const duration = player.audio.duration;
    if (isNaN(duration) || duration <= 0) {
        // 无时长信息，退回到原有的占位模式
        const placeholderLines = lines.map(line => /^\[\d{2,3}:\d{2}/.test(line) ? line : `[00:00.00]${line}`);
        player.lyricRawText.value = placeholderLines.join('\n');
        showNotification('⚠️ 未获取到歌曲长度，已填充预览占位符');
    } else {
        const effectiveDuration = duration * 0.95; // 预留 5% 尾部
        const formatted = lines.map((line, i) => {
            if (/^\[\d{2,3}:\d{2}/.test(line)) return line;
            const time = (i / lines.length) * effectiveDuration;
            const m = Math.floor(time / 60).toString().padStart(2, '0');
            const s = Math.floor(time % 60).toString().padStart(2, '0');
            const ms = Math.floor((time % 1) * 100).toString().padStart(2, '0');
            return `[${m}:${s}.${ms}]${line}`;
        });
        player.lyricRawText.value = formatted.join('\n');
        showNotification(`✅ 已根据歌曲时长 (${Math.floor(duration)}s) 自动分配先验时间戳`);
    }

    renderEditorPreview(player.lyricRawText.value);
}

/**
 * 从 LRCLIB 获取歌词
 */
async function fetchLrcFromLib(title, artist) {
    try {
        const query = encodeURIComponent(`${title} ${artist}`);
        const url = `https://lrclib.net/api/search?q=${query}`;
        const resp = await fetch(url);
        if (!resp.ok) return null;
        const data = await resp.json();

        // 找一个带歌词且匹配度高的
        const match = data.find(item => item.syncedLyrics);
        return match ? match.syncedLyrics : null;
    } catch (e) {
        console.warn('[SmartFormat] LRCLIB Fetch Failed:', e);
        return null;
    }
}

/**
 * 手动打点：将当前播放时间注入到光标所在行
 */
function manualTagCurrentLine() {
    const textarea = player.lyricRawText;
    const start = textarea.selectionStart;
    const text = textarea.value;

    // 找到光标所在行的起始和结束位置
    const lineStart = text.lastIndexOf('\n', start - 1) + 1;
    const lineEnd = text.indexOf('\n', start);
    const lineContent = text.substring(lineStart, lineEnd === -1 ? text.length : lineEnd);

    const currentTimeMs = Math.floor(player.audio.currentTime * 1000);
    const m = Math.floor(currentTimeMs / 60000);
    const s = Math.floor((currentTimeMs % 60000) / 1000);
    const ms = Math.floor((currentTimeMs % 1000) / 10); // 取两位毫秒

    const timeTag = `[${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(2, '0')}]`;

    // 替换或插入时间戳
    let newLine;
    if (/^\[\d{2,3}:\d{2}[.:]\d{2,3}\]/.test(lineContent)) {
        newLine = lineContent.replace(/^\[\d{2,3}:\d{2}[.:]\d{2,3}\]/, timeTag);
    } else {
        newLine = timeTag + lineContent;
    }

    const newText = text.substring(0, lineStart) + newLine + (lineEnd === -1 ? "" : text.substring(lineEnd));
    textarea.value = newText;

    // 光标自动跳到下一行
    const nextLineStart = lineStart + newLine.length + 1;
    textarea.focus();
    if (nextLineStart <= newText.length) {
        textarea.setSelectionRange(nextLineStart, nextLineStart);
        // 如果下一行是空的，滚动到可视区域
        const rowHeight = 24; // 估计值
        const linesBefore = newText.substring(0, nextLineStart).split('\n').length;
        textarea.scrollTop = (linesBefore - 5) * rowHeight;
    }
}

// ==================== 编辑器实时预览 & 逐句打点 ====================

/**
 * 渲染编辑器预览面板
 * @param {string} lrcText - LRC 格式歌词文本
 */
function renderEditorPreview(lrcText) {
    const panel = document.getElementById('lyricPreviewPanel');
    if (!panel) return;

    if (!lrcText || !lrcText.trim()) {
        panel.innerHTML = '<div class="preview-placeholder">（无歌词内容可供预览）</div>';
        return;
    }

    const lines = LyricsSync.parseLRC(lrcText);
    if (lines.length === 0) {
        // 尝试作为纯文本渲染
        const plainLines = lrcText.split('\n').filter(l => l.trim());
        if (plainLines.length > 0) {
            panel.innerHTML = plainLines.map((text, i) =>
                `<div class="lyric-preview-line" data-index="${i}">${text.replace(/^\[\d{2}:\d{2}[.:]\d{2,3}\]/, '').trim() || text}</div>`
            ).join('');
        } else {
            panel.innerHTML = '<div class="preview-placeholder">无可预览的歌词内容</div>';
        }
        return;
    }

    panel.innerHTML = lines.map((line, i) =>
        `<div class="lyric-preview-line" data-index="${i}" data-time="${line.time}">${line.text}</div>`
    ).join('');

    // 缓存解析结果供同步使用
    panel._parsedLines = lines;
    panel._currentHighlight = -1;
}

/**
 * 同步编辑器预览面板高亮（被 updateProgressBar 驱动）
 * @param {number} currentTime - 当前播放时间（秒）
 */
function syncEditorPreview(currentTime) {
    const panel = document.getElementById('lyricPreviewPanel');
    if (!panel || !panel._parsedLines || TapSyncState.active) return;

    const lines = panel._parsedLines;
    const adjustedTime = currentTime + playerState.lyricsOffset;

    // 计算当前行
    let idx = -1;
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].time <= adjustedTime) idx = i;
        else break;
    }

    // 避免重复更新
    if (idx === panel._currentHighlight) return;
    panel._currentHighlight = idx;

    const items = panel.querySelectorAll('.lyric-preview-line');
    items.forEach((el, i) => {
        el.classList.remove('current', 'played');
        if (i === idx) {
            el.classList.add('current');
        } else if (i < idx) {
            el.classList.add('played');
        }
    });

    // 滚动到当前行
    if (idx >= 0 && items[idx]) {
        const el = items[idx];
        const panelH = panel.offsetHeight;
        const scrollTarget = el.offsetTop - panelH / 2 + el.offsetHeight / 2;
        panel.scrollTo({ top: scrollTarget, behavior: 'smooth' });
    }
}

// ---- 逐句打点模式 ----

const TapSyncState = {
    active: false,
    currentLine: 0,
    timestamps: [],   // 每行的时间戳
    lines: [],        // 纯文本歌词行（去掉时间戳后的）
};

/**
 * 进入逐句打点模式
 */
function enterTapSyncMode() {
    const textarea = player.lyricRawText;
    if (!textarea || !textarea.value.trim()) {
        showNotification('请先加载或输入歌词文本');
        return;
    }

    const rawText = textarea.value;
    // 提取纯文本行（去掉已有时间戳）
    const textLines = rawText.split('\n')
        .map(l => l.trim())
        .filter(l => l.length > 0)
        .map(l => {
            // 去掉 [mm:ss.ms] 前缀，保留 [ti:xxx] 等元信息标签
            if (/^\[\d{2,3}:\d{2}[.:]\d{2,3}\]/.test(l)) {
                return l.replace(/^\[\d{2,3}:\d{2}[.:]\d{2,3}\]/, '').trim();
            }
            // 跳过空白的纯时间戳行
            if (/^\[.*\]$/.test(l) && !/^\[ti:|^\[ar:|^\[al:/.test(l)) return null;
            return l;
        })
        .filter(l => l !== null && l.length > 0);

    if (textLines.length === 0) {
        showNotification('没有可打点的歌词行');
        return;
    }

    TapSyncState.active = true;
    TapSyncState.currentLine = 0;
    TapSyncState.timestamps = new Array(textLines.length).fill(null);
    TapSyncState.lines = textLines;

    // 更新预览面板为打点模式视图
    const panel = document.getElementById('lyricPreviewPanel');
    if (panel) {
        panel.innerHTML = textLines.map((text, i) =>
            `<div class="lyric-preview-line tap-pending" data-index="${i}">${text}</div>`
        ).join('');
        // 标记第一行为等待状态
        const firstLine = panel.querySelector('[data-index="0"]');
        if (firstLine) {
            firstLine.classList.remove('tap-pending');
            firstLine.classList.add('tap-waiting');
        }
    }

    // UI 更新
    const tapBtn = document.getElementById('btnTapSync');
    const undoBtn = document.getElementById('btnUndoTap');
    if (tapBtn) { tapBtn.classList.add('active'); tapBtn.textContent = '⏱ 打点中...'; }
    if (undoBtn) undoBtn.style.display = '';

    showNotification('逐句打点模式已开启 — 按 [空格] 标记当前行');
}

/**
 * 执行一次打点（空格键触发）
 */
function tapMark() {
    if (!TapSyncState.active) return;
    if (TapSyncState.currentLine >= TapSyncState.lines.length) return;

    const currentTime = player.audio.currentTime;
    const idx = TapSyncState.currentLine;

    // 记录时间戳
    TapSyncState.timestamps[idx] = currentTime;

    // 更新预览面板
    const panel = document.getElementById('lyricPreviewPanel');
    if (panel) {
        const items = panel.querySelectorAll('.lyric-preview-line');

        // 当前行标记为已打点
        if (items[idx]) {
            items[idx].classList.remove('tap-waiting');
            items[idx].classList.add('tapped');
            // 显示时间戳
            const m = Math.floor(currentTime / 60).toString().padStart(2, '0');
            const s = Math.floor(currentTime % 60).toString().padStart(2, '0');
            const ms = Math.floor((currentTime % 1) * 100).toString().padStart(2, '0');
            items[idx].setAttribute('data-time-tag', `[${m}:${s}.${ms}]`);
        }

        // 下一行标记为等待
        TapSyncState.currentLine++;
        if (TapSyncState.currentLine < TapSyncState.lines.length) {
            if (items[TapSyncState.currentLine]) {
                items[TapSyncState.currentLine].classList.remove('tap-pending');
                items[TapSyncState.currentLine].classList.add('tap-waiting');
                // 滚动到下一行
                const el = items[TapSyncState.currentLine];
                const panelH = panel.offsetHeight;
                panel.scrollTo({ top: el.offsetTop - panelH / 2 + el.offsetHeight / 2, behavior: 'smooth' });
            }
        } else {
            // 全部打点完成
            showNotification('🎉 所有歌词已打点完成！正在生成 LRC...');
            setTimeout(() => exitTapSyncMode(), 500);
        }
    }
}

/**
 * 撤销上次打点
 */
function undoTapMark() {
    if (!TapSyncState.active || TapSyncState.currentLine <= 0) return;

    TapSyncState.currentLine--;
    const idx = TapSyncState.currentLine;
    TapSyncState.timestamps[idx] = null;

    const panel = document.getElementById('lyricPreviewPanel');
    if (panel) {
        const items = panel.querySelectorAll('.lyric-preview-line');
        // 恢复当前行之后的行状态
        if (items[idx + 1]) {
            items[idx + 1].classList.remove('tap-waiting');
            items[idx + 1].classList.add('tap-pending');
        }
        if (items[idx]) {
            items[idx].classList.remove('tapped');
            items[idx].classList.add('tap-waiting');
            items[idx].removeAttribute('data-time-tag');
            // 滚回
            const panelH = panel.offsetHeight;
            panel.scrollTo({ top: items[idx].offsetTop - panelH / 2 + items[idx].offsetHeight / 2, behavior: 'smooth' });
        }
    }

    showNotification(`已撤销，回退到第 ${idx + 1} 行`);
}

/**
 * 退出打点模式并生成 LRC
 */
function exitTapSyncMode() {
    if (!TapSyncState.active) return;

    // 组装 LRC 文本
    const lrcLines = TapSyncState.lines.map((text, i) => {
        const t = TapSyncState.timestamps[i];
        if (t !== null) {
            const m = Math.floor(t / 60).toString().padStart(2, '0');
            const s = Math.floor(t % 60).toString().padStart(2, '0');
            const ms = Math.floor((t % 1) * 100).toString().padStart(2, '0');
            return `[${m}:${s}.${ms}]${text}`;
        }
        return `[00:00.00]${text}`; // 未打点的行用占位时间
    });

    // 写回 textarea
    if (player.lyricRawText) {
        player.lyricRawText.value = lrcLines.join('\n');
    }

    // 重新渲染预览面板（切回正常同步模式）
    renderEditorPreview(lrcLines.join('\n'));

    // 重置状态
    TapSyncState.active = false;
    TapSyncState.currentLine = 0;
    TapSyncState.timestamps = [];
    TapSyncState.lines = [];

    // UI 恢复
    const tapBtn = document.getElementById('btnTapSync');
    const undoBtn = document.getElementById('btnUndoTap');
    if (tapBtn) { tapBtn.classList.remove('active'); tapBtn.textContent = '⏱ 逐句打点'; }
    if (undoBtn) undoBtn.style.display = 'none';

    showNotification('✅ LRC 已生成并填入文本框，可保存或继续编辑');
}

/**
 * 编辑器快捷键处理
 */
function handleEditorShortcuts(e) {
    if (!player.lyricModal || !player.lyricModal.classList.contains('active')) return;

    // 空格键：在打点模式下执行打点（阻止默认行为）
    if (e.code === 'Space' && TapSyncState.active) {
        e.preventDefault();
        e.stopPropagation();
        tapMark();
        return;
    }

    // Alt + T: 打点
    if (e.altKey && e.key.toLowerCase() === 't') {
        e.preventDefault();
        manualTagCurrentLine();
    }
}
function showLyricsOffsetHint() {
    if (!player.albumLyrics) return;

    let hint = document.getElementById('lyricsOffsetHint');
    if (!hint) {
        hint = document.createElement('div');
        hint.id = 'lyricsOffsetHint';
        hint.style.cssText = `
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(96, 165, 250, 0.9);
            color: #fff;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.75rem;
            z-index: 10;
            pointer-events: none;
        `;
        player.albumLyrics.appendChild(hint);
    }

    const offsetText = playerState.lyricsOffset >= 0 ? `+${playerState.lyricsOffset.toFixed(1)}s` : `${playerState.lyricsOffset.toFixed(1)}s`;
    hint.textContent = `偏移: ${offsetText}`;

    clearTimeout(offsetHintTimeout);
    offsetHintTimeout = setTimeout(() => {
        hint.remove();
    }, 2000);
}

// ==================== 文件上传 ====================
function handleFileUpload(e) {
    console.log('文件上传事件触发');
    const files = Array.from(e.target.files);
    console.log('选择的文件:', files.map(f => ({ name: f.name, type: f.type, size: f.size })));

    if (files.length === 0) {
        console.warn('没有选择文件');
        return;
    }

    let processedCount = 0;
    const audioFiles = files.filter(f => f.type.startsWith('audio/'));

    if (audioFiles.length === 0) {
        showNotification('未找到音频文件');
        return;
    }

    audioFiles.forEach((file, index) => {
        console.log('正在读取文件:', file.name);
        const reader = new FileReader();
        reader.onload = async (event) => {  // 改为 async
            const audioUrl = event.target.result;
            const fileName = file.name.replace(/\.[^/.]+$/, '');
            console.log('文件读取完成:', fileName);
            playerState.uploadedFiles.set(fileName, audioUrl);

            // [New] 更新可用性缓存，标记为可用
            window.resourceAvailabilityCache.set(audioUrl, {
                available: true,
                timestamp: Date.now()
            });

            // 同步到 app.js 的 localSongsMap（用于本地音乐视图）
            if (window.localSongsMap) {
                // 使用文件名作为歌名，歌手名留空或设为 '本地音乐'
                // 注意：这里与专辑页面上传的单个歌曲不同，批量上传时没有明确的艺术家信息
                const key = `${fileName} - 本地音乐`;
                window.localSongsMap.set(key, {
                    fileName: file.name,
                    audioUrl: audioUrl,
                    uploadDate: new Date().toISOString(),
                    songName: fileName,
                    artistName: '本地音乐',
                    _bulkUpload: true  // 标记为批量上传
                });
                // 更新侧边栏显示
                const localMusicCount = document.querySelector('.local-music-item .a-count');
                if (localMusicCount) {
                    localMusicCount.textContent = `${window.localSongsMap.size} 首歌曲`;
                }
            }

            processedCount++;
            console.log('已存储文件:', fileName, '当前上传数:', processedCount);

            // 自动添加到播放列表（等待异步完成）
            const addedIndex = await addToPlaylist(fileName, '本地音乐', '本地文件', audioUrl, '');
            console.log('歌曲已添加到播放列表，索引:', addedIndex);

            // 如果是第一个文件，自动播放
            if (index === 0) {
                console.log('自动播放第一首歌曲');
                playSongAtIndex(addedIndex);
            }

            // 当所有文件都处理完成后更新UI和保存到IndexedDB
            if (processedCount === audioFiles.length) {
                console.log('所有文件处理完成');
                updateUploadedCount(processedCount);
                showNotification(`已添加 ${processedCount} 个音频文件到播放列表`);
                console.log('当前uploadedFiles Map内容:', Array.from(playerState.uploadedFiles.keys()));
                console.log('当前播放列表内容:', playerState.playlist);

                // 保存到 IndexedDB（异步）
                if (window.saveLocalSongsToStorage) {
                    try {
                        await window.saveLocalSongsToStorage();
                        console.log('✓ 已保存到 IndexedDB');
                    } catch (error) {
                        console.error('保存到 IndexedDB 失败:', error);
                    }
                }
            }
        };
        reader.onerror = (error) => {
            console.error('文件读取失败:', file.name, error);
        };
        reader.readAsDataURL(file);
    });
}

function updateUploadedCount(count) {
    if (player.uploadedCount) {
        const currentCount = parseInt(player.uploadedCount.textContent) || 0;
        const newCount = currentCount + count;
        player.uploadedCount.textContent = newCount;
    }
}

// ==================== 播放控制 ====================
function togglePlayPause() {
    if (!playerState.currentSong) {
        showNotification('请先选择一首歌曲');
        return;
    }

    if (playerState.isPlaying) {
        player.audio.pause();
    } else {
        player.audio.play();
    }
}

function updatePlayPauseButton() {
    if (!player.playPauseBtn) return;

    // 获取路径元素
    const path = player.playPauseBtn.querySelector('.play-pause-path');
    if (!path) return;

    // YouTube 风格路径定义 (针对 36x36 viewBox)
    const playPath = "M11,10 L18,13.74 L18,22.26 L11,26 Z M18,13.74 L26,18 L26,18 L18,22.26 Z";
    const pausePath = "M11,10 L17,10 L17,26 L11,26 Z M19,10 L25,10 L25,26 L19,26 Z";

    if (playerState.isPlaying) {
        player.playPauseBtn.classList.add('playing');
        path.setAttribute('d', pausePath);

        if (player.vinylRecord) player.vinylRecord.classList.add('playing');
        if (player.vinylContainer) player.vinylContainer.classList.add('playing');
    } else {
        player.playPauseBtn.classList.remove('playing');
        path.setAttribute('d', playPath);

        if (player.vinylRecord) player.vinylRecord.classList.remove('playing');
        if (player.vinylContainer) player.vinylContainer.classList.remove('playing');
    }

    // [New] 同步专辑视图中的指示器动画状态
    if (playerState.currentSong) {
        updateAlbumViewActiveState(playerState.currentSong, playerState.currentArtist);
    }
}

// 手动插值动画已改为 CSS 过渡，此处移除原有函数

function playPrevious() {
    if (window.RoamingManager && (window.RoamingManager.isActive || playerState.isRoaming)) {
        window.RoamingManager.playPrevious();
        return;
    }
    if (playerState.playlist.length === 0) return;
    const currentIndex = getCurrentPlaylistIndex();
    let prevIndex = currentIndex > 0 ? currentIndex - 1 : playerState.playlist.length - 1;
    if (playerState.playMode === 'shuffle') {
        prevIndex = Math.floor(Math.random() * playerState.playlist.length);
    }
    playSongAtIndex(prevIndex);
}

function playNext() {
    if (window.RoamingManager && (window.RoamingManager.isActive || playerState.isRoaming)) {
        window.RoamingManager.playNext();
        return;
    }
    if (playerState.playlist.length === 0) return;

    // 防御性保护：如果播放列表仅有 1 首歌且漫游管理器存在，绝不陷入单曲死循环，转交漫游引擎拉取新歌
    if (playerState.playlist.length === 1 && window.RoamingManager) {
        console.warn('[Player] 列表仅1首且触发 playNext，转交漫游引擎拉取新歌');
        window.RoamingManager.playNext();
        return;
    }

    const currentIndex = getCurrentPlaylistIndex();
    let nextIndex;

    if (playerState.playMode === 'sequence') {
        // 顺序播放：到最后一首就停止
        if (currentIndex >= playerState.playlist.length - 1) {
            return; // 停止播放
        }
        nextIndex = currentIndex + 1;
    } else if (playerState.playMode === 'shuffle') {
        nextIndex = Math.floor(Math.random() * playerState.playlist.length);
    } else {
        // loop 或 single 模式，循环播放
        nextIndex = (currentIndex + 1) % playerState.playlist.length;
    }

    playSongAtIndex(nextIndex);
}

function handleSongEnded() {
    if (window.RoamingManager && (window.RoamingManager.isActive || playerState.isRoaming)) {
        // 漫游模式下歌曲播放完毕，永不停止，自动切到下一首漫游随机歌曲
        window.RoamingManager.playNext();
        return;
    }
    if (playerState.playMode === 'single') {
        // 单曲循环：重新播放当前歌曲
        player.audio.currentTime = 0;
        player.audio.play();
    } else {
        playNext();
    }
}

function getCurrentPlaylistIndex() {
    if (!playerState.currentSong) return -1;
    return playerState.playlist.findIndex(
        item => item.song === playerState.currentSong &&
            item.artist === playerState.currentArtist
    );
}

async function playSongAtIndex(index, expectedGen = null) {
    console.log('[UI Trace] playSongAtIndex() called with index:', index, 'expectedGen:', expectedGen);
    if (index < 0 || index >= playerState.playlist.length) return;
    const item = playerState.playlist[index];

    // [Race Condition Guard] 获取本次执行的代次
    // 如果外部传入了代次（来自 playAlbum 或主动切歌），直接沿用；否则生成新代次
    const myGeneration = expectedGen !== null ? expectedGen : nextPlayGeneration();

    if (myGeneration !== _playGeneration) {
        console.log(`[Race Guard] Stale play request for index ${index} (gen ${myGeneration} vs current ${_playGeneration}), aborting.`);
        return false;
    }

    // === 自动跳过辅助函数 ===
    const autoSkipToNext = (reason) => {
        if (myGeneration !== _playGeneration) {
            console.log(`[AutoSkip Guard] Superseded generation, ignoring auto-skip for: "${item.song}"`);
            return false;
        }
        console.warn(`[AutoSkip] ${reason}: "${item.song}"`);

        // 漫游模式防卡死：单曲资源不可用时，永不停止，自动切下一首漫游
        if (window.RoamingManager && window.RoamingManager.isActive) {
            if (_autoSkipTimer) clearTimeout(_autoSkipTimer);
            _autoSkipTimer = setTimeout(() => {
                if (window.RoamingManager && window.RoamingManager.isActive) {
                    window.RoamingManager.playNext();
                }
            }, 300);
            return false;
        }

        if (playerState._skipCount < playerState.playlist.length) {
            playerState._skipCount++;
            // 计算下一首的索引（与 playNext 逻辑一致）
            let nextIdx;
            if (playerState.playMode === 'shuffle') {
                nextIdx = Math.floor(Math.random() * playerState.playlist.length);
            } else {
                nextIdx = (index + 1) % playerState.playlist.length;
                // 顺序模式到头了就停
                if (playerState.playMode === 'sequence' && index >= playerState.playlist.length - 1) {
                    console.warn('[AutoSkip] 已到列表末尾，停止播放');
                    playerState._skipCount = 0;
                    return false;
                }
            }
            if (_autoSkipTimer) clearTimeout(_autoSkipTimer);
            _autoSkipTimer = setTimeout(() => {
                if (myGeneration === _playGeneration) {
                    playSongAtIndex(nextIdx, myGeneration);
                }
            }, 200);
        } else {
            console.warn('[AutoSkip] 已连续跳过全部曲目，停止播放');
            showNotification('当前专辑暂无可播放的歌曲');
            playerState._skipCount = 0;
        }
        return false;
    };

    // 1. 资源完整性检查：URL 缺失直接跳过（无需等待，立即判定）
    if (!item.audioUrl) {
        // 过期请求静默退出，不影响新点击的状态
        if (myGeneration !== _playGeneration) return false;
        // 清除当前行的乐观高亮（不恢复旧歌曲），等 autoSkip 后由下一首确定高亮
        _clearStaleHighlight();
        return autoSkipToNext('音频地址缺失');
    }

    // 显示加载状态
    setLoadingState(true);

    // 2. 资源可用性预检 (Web Audio API / Data URL 除外)
    // [V14.2] 本地开发环境相对路径统一代理修正与集群域名规范化
    let finalAudioUrl = item.audioUrl;
    if (finalAudioUrl && finalAudioUrl.includes('r2.changgepd.ccwu.cc')) {
        finalAudioUrl = finalAudioUrl.replace('https://r2.changgepd.ccwu.cc', 'https://pub-ade3407baf1041b49b5949a2539067f7.r2.dev');
    }
    const apiBase = window.API_BASE || window.MOODY_CONFIG?.API_BASE || '';
    if (finalAudioUrl && !finalAudioUrl.startsWith('http') && apiBase) {
        finalAudioUrl = `${apiBase}${finalAudioUrl.startsWith('/') ? '' : '/'}${finalAudioUrl}`;
    }
    // 统一为所有直连音频注入时间戳，强力击穿 CDN 历史跨域头缺失脏缓存
    if (finalAudioUrl && finalAudioUrl.startsWith('http') && !finalAudioUrl.includes('?t=') && !finalAudioUrl.includes('&t=')) {
        const separator = finalAudioUrl.includes('?') ? '&' : '?';
        finalAudioUrl = `${finalAudioUrl}${separator}t=${Date.now()}`;
    }

    // [Defense 5] 漫游模式下已通过严格 playableFilter 过滤，跳过 HEAD 网络预检，实现秒级无缝切歌并防止后台 Autoplay 权限超时
    let isAvailable = true;
    if (!playerState.isRoaming) {
        isAvailable = await checkResourceAvailability(finalAudioUrl);

        // [Race Guard] 异步等待后检查代次，用户可能已点击新歌曲
        if (myGeneration !== _playGeneration) {
            setLoadingState(false);
            console.log(`[Race Guard] Generation mismatch after HEAD check, aborting "${item.song}"`);
            return false;
        }
    }

    // [Retry] 首次预检失败时，清除该 URL 的缓存并重试一次
    // 给容错空间，避免因缓存旧的失败结果而误判
    if (!isAvailable) {
        console.warn(`[Retry] HEAD check failed for "${item.song}", clearing cache and retrying once...`);
        if (window.resourceAvailabilityCache) {
            window.resourceAvailabilityCache.delete(finalAudioUrl);
        }
        if (_retryTimer) clearTimeout(_retryTimer);
        await new Promise(resolve => {
            _retryTimer = setTimeout(resolve, 500);
        });

        // 重试后再次检查代次
        if (myGeneration !== _playGeneration) {
            setLoadingState(false);
            console.log(`[Race Guard] Generation mismatch after retry wait, aborting "${item.song}"`);
            return false;
        }

        isAvailable = await checkResourceAvailability(finalAudioUrl);

        // 重试后再次检查代次
        if (myGeneration !== _playGeneration) {
            setLoadingState(false);
            console.log(`[Race Guard] Generation mismatch after retry, aborting "${item.song}"`);
            return false;
        }
    }

    if (!isAvailable) {
        setLoadingState(false);
        // 清除乐观高亮（不恢复旧歌曲），autoSkipToNext 会高亮下一首
        _clearStaleHighlight();
        return autoSkipToNext('资源不可用（重试后仍失败）');
    }

    player.audio.src = finalAudioUrl;
    playerState.currentSong = item.song;
    playerState.currentArtist = item.artist;
    playerState.currentAlbum = item.album;
    playerState.currentLrcPath = item.lrcPath; // 关键修复：确保路径被全局缓存

    // [Watchdog] 启动 8 秒媒体流加载超时保护，防止弱网/跨域阻断导致的假死
    clearMediaLoadingWatchdog();
    const watchdogGen = myGeneration;
    _mediaLoadingWatchdogTimer = setTimeout(() => {
        if (watchdogGen === _playGeneration && (player.audio.currentTime === 0 || player.audio.readyState < 2)) {
            console.warn(`[Watchdog] 媒体流加载超时(8s): "${item.song}", 自动切歌`);
            showNotification(`⚠️ 音频加载超时，正在跳过...`);
            clearMediaLoadingWatchdog();
            try {
                player.audio.pause();
                player.audio.removeAttribute('src');
                player.audio.load();
            } catch (err) {}
            setLoadingState(false);
            _clearStaleHighlight();
            autoSkipToNext('媒体流加载超时(8s)');
        }
    }, 8000);

    // [Modified] 必须等待播放结果，否则函数会立即返回 true
    try {
        await player.audio.play();

        // [Race Guard] play() 本身也是异步的，play 完成后再次检查代次
        if (myGeneration !== _playGeneration) {
            player.audio.pause();
            setLoadingState(false);
            console.log(`[Race Guard] Generation mismatch after play(), stopping "${item.song}"`);
            return false;
        }

        // 播放成功，移除加载状态
        setLoadingState(false);

        // ========== [Commit Phase] 播放成功后才更新 UI 和状态 ==========
        console.log(`[Player] Play successful, updating UI for: ${item.song}`);

        // 更新悬浮标题显示歌曲名
        if (player.pTitleOverlay) {
            player.pTitleOverlay.textContent = `${item.song} - ${item.artist}`;
        }
        // 保留 pTitle 用于其他用途（如果有）
        if (player.pTitle) {
            player.pTitle.textContent = `${item.song} - ${item.artist}`;
        }

        // 获取专辑封面 URL
        // [V14.2] 本地开发环境封面代理修正
        let coverUrl = item.artworkUrl;
        if (coverUrl && !coverUrl.startsWith('http') && window.API_BASE) {
            coverUrl = `${window.API_BASE}${coverUrl.startsWith('/') ? '' : '/'}${coverUrl}`;
        }
        coverUrl = coverUrl || `https://ui-avatars.com/api/?name=${encodeURIComponent(item.song)}&background=333&color=fff&size=100`;

        // 更新黑胶唱片中间的标签封面
        if (player.pThumb) {
            player.pThumb.src = coverUrl;
        }

        // 更新黑胶唱片背景封面（半透明效果）
        if (player.vinylCover) {
            player.vinylCover.style.backgroundImage = `url('${coverUrl}')`;
        }

        // 更新主播放器播放列表的高亮
        updatePlaylistActive(index);

        // 加载歌词
        loadLyrics(item);

        // 更新收藏按钮状态
        updateFavoriteButton();

        // [Explicit Sync] 确保 UI 按钮和指示器状态同步更新
        updatePlayPauseButton();

        // [Critical Sync] 同步更新专辑页面的歌曲选中状态 (现在是播放成功后的 commit)
        updateAlbumViewActiveState(item.song, item.artist);

        // 播放成功，重置连续跳过计数
        playerState._skipCount = 0;

        // 保存最后播放的歌曲
        Settings.saveLastPlayed({
            song: item.song,
            artist: item.artist,
            album: item.album
        });

        return true;
    } catch (err) {
        // [Race Guard] 播放异常时先检查代次
        if (myGeneration !== _playGeneration) {
            setLoadingState(false);
            console.log(`[Race Guard] Generation mismatch in catch, ignoring error for "${item.song}"`);
            return false;
        }

        console.error('播放失败 (Play Promise Reject):', err);

        if (err.name === 'NotAllowedError') {
            showNotification('浏览器限制自动播放，请手动点击播放按钮');
        } else if (err.name === 'NotSupportedError') {
            const fileName = item.audioUrl.split('/').pop();
            showNotification(`格式不支持或源无效: ${decodeURIComponent(fileName)}`);
            console.error('Failed URL:', item.audioUrl);
        } else {
            showNotification(`播放失败: ${err.message}`);
        }

        // [No Rollback] 失败时清除乐观高亮，但不恢复旧歌曲高亮
        // 这样比"回滚到上一首"更符合直觉：播放失败就是没有高亮，autoSkipToNext 会高亮下一首
        _clearStaleHighlight();

        clearMediaLoadingWatchdog();
        setLoadingState(false);
        playerState.isPlaying = false;
        updatePlayPauseButton();
        return autoSkipToNext('play() 失败，跳到下一首');
    }
}

// 清除当前行的乐观高亮，但不恢复任何旧状态
// 区别于 clearAlbumViewActiveState（后者会尝试恢复旧歌曲高亮）
function _clearStaleHighlight() {
    const rows = document.querySelectorAll('.st-row');
    rows.forEach(row => {
        row.classList.remove('active', 'playing');
        const bars = row.querySelector('.playing-bars');
        if (bars) bars.remove();
    });
}

// 同步更新专辑页面的歌曲选中状态 (Injects Playing Indicator Immediately)
window.updateAlbumViewActiveState = function (songName, artistName, optimistic = false) {
    if (!songName) return;
    const rows = document.querySelectorAll('.st-row');
    let matchedCount = 0;

    rows.forEach(row => {
        const songNameEl = row.querySelector('.song-name');
        if (songNameEl) {
            // 精准匹配：只取第一个文本节点的内容进行匹配，排除 source 等标签
            let currentTitle = "";
            const nodes = Array.from(songNameEl.childNodes);
            for (let node of nodes) {
                if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
                    currentTitle = node.textContent.trim();
                    break;
                }
            }

            // 备选方案：如果 textNode 失败，尝试 split
            if (!currentTitle) {
                currentTitle = songNameEl.innerText.split('\n')[0].split('\t')[0].trim();
            }

            if (currentTitle === songName) {
                matchedCount++;
                // [Zero-Latency Feedback] 无论是乐观更新还是确认播放，第 0 毫秒立即赋予完整的点亮状态与波浪条
                row.classList.add('active', 'playing');

                // 立即注入指示器 HTML（如果不存在）
                let bars = row.querySelector('.playing-bars');
                if (!bars) {
                    bars = document.createElement('span');
                    bars.className = 'playing-bars';
                    bars.innerHTML = '<span></span><span></span><span></span><span></span>';
                    songNameEl.appendChild(bars);
                }
                return;
            }
        }
        row.classList.remove('active', 'playing');
        const bars = row.querySelector('.playing-bars');
        if (bars) bars.remove();
    });

    if (matchedCount > 0) {
        console.log(`[Indicator] Sync: "${songName}", Matched: ${matchedCount}, Optimistic: ${optimistic}`);
    }
}

// [Optimistic UI] 外部可调用的高亮清除函数（供 app.js 等外部模块使用）
// 注意：只负责清除，不恢复旧歌曲高亮 —— 恢复逻辑由播放成功的 Commit Phase 负责
// 移除了旧的"恢复 playerState.currentSong 高亮"逻辑，避免在竞态情况下覆盖用户新点击的高亮
window.clearAlbumViewActiveState = function () {
    _clearStaleHighlight();
    console.log('[Indicator] Cleared stale optimistic highlight (no rollback).');
}

// ==================== 进度条 ====================
// 用于记录当前拖动到的百分比 (0~1)，-1 表示未在拖动状态
let _seekPercent = -1;

function updateProgressBar() {
    if (!playerState.duration || !player.progressBar) return;
    // 拖动期间屏蔽 timeupdate 覆盖，避免进度条被播放进度打架拉回
    if (_seekPercent >= 0) return;
    const percent = (playerState.currentTime / playerState.duration) * 100;
    player.progressBar.style.width = `${percent}%`;

    // 同步到歌词弹窗的时间显示
    if (player.modalCurrentTime && player.lyricModal.classList.contains('active')) {
        player.modalCurrentTime.textContent = formatTime(playerState.currentTime);
        // 驱动编辑器预览面板实时滚动
        syncEditorPreview(playerState.currentTime);
    }
}

function handleProgressSeek(e) {
    if (!player.progressContainer) return;
    const rect = player.progressContainer.getBoundingClientRect();
    const percent = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    // 用模块变量记录当前拖动位置，松手时由 mouseup 读取精确 seek
    _seekPercent = percent;
    if (player.progressBar) {
        player.progressBar.style.width = `${percent * 100}%`;
    }
    if (player.pTime) {
        player.pTime.textContent = formatTime(percent * playerState.duration) + ' / ' + formatTime(playerState.duration);
    }
}

// ==================== 音量控制 ====================
// 保存切换静音前的音量
let previousVolume = 0.7;

function toggleMute() {
    if (playerState.volume === 0) {
        // 恢复音量
        const newVolume = previousVolume > 0 ? previousVolume : 0.7;
        playerState.volume = newVolume;
        if (player.audio) player.audio.volume = newVolume;
        if (player.volumeFill) player.volumeFill.style.width = `${newVolume * 100}%`;
        updateVolumeIcon(newVolume);
    } else {
        // 静音
        previousVolume = playerState.volume;
        playerState.volume = 0;
        if (player.audio) player.audio.volume = 0;
        if (player.volumeFill) player.volumeFill.style.width = '0%';
        updateVolumeIcon(0);
    }
}

function handleVolumeChange(e) {
    if (!player.volumeSlider) return;
    const rect = player.volumeSlider.getBoundingClientRect();
    const percent = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    playerState.volume = percent;
    if (player.audio) player.audio.volume = percent;
    if (player.volumeFill) player.volumeFill.style.width = `${percent * 100}%`;

    // 保存音量设置到存储
    Settings.saveVolume(percent);

    // 更新音量图标
    updateVolumeIcon(percent);
}

function updateVolumeIcon(percent) {
    if (!player.volumeBtn) return;

    const icons = {
        muted: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
            <line x1="23" y1="9" x2="17" y2="15"/>
            <line x1="17" y1="9" x2="23" y2="15"/>
        </svg>`,
        low: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
            <path d="M15.54 8.46c.78-.78 2.05-.78 2.83 0"/>
        </svg>`,
        high: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
            <path d="M15.54 8.46c.78-.78 2.05-.78 2.83 0"/>
            <path d="M19.07 5c1.56-1.56 4.09-1.56 5.66 0"/>
        </svg>`
    };

    if (percent === 0) {
        player.volumeBtn.innerHTML = icons.muted;
    } else if (percent < 0.5) {
        player.volumeBtn.innerHTML = icons.low;
    } else {
        player.volumeBtn.innerHTML = icons.high;
    }
}

// ==================== 播放模式 ====================
function cyclePlayMode() {
    if (playerState.isRoaming) {
        showNotification('当前处于随心漫游模式，已自动随机切歌');
        return;
    }
    const modes = ['sequence', 'loop', 'single', 'shuffle'];
    const currentIndex = modes.indexOf(playerState.playMode);
    playerState.playMode = modes[(currentIndex + 1) % modes.length];
    updateModeButton();

    // 保存播放模式到存储
    Settings.savePlayMode(playerState.playMode);

    showNotification(getModeText(playerState.playMode));
}

function updateModeButton() {
    if (!player.modeBtn) return;
    const modeEmojis = {
        'sequence': '→',   // 顺序播放
        'loop': '↻',       // 列表循环
        'single': '1',      // 单曲循环
        'shuffle': '⇄'     // 随机播放
    };
    player.modeBtn.textContent = modeEmojis[playerState.playMode];
    player.modeBtn.setAttribute('data-mode', getModeText(playerState.playMode));
}

function getModeText(mode) {
    const texts = {
        'sequence': '顺序播放',
        'loop': '列表循环',
        'single': '单曲循环',
        'shuffle': '随机播放'
    };
    return texts[mode] || mode;
}

// ==================== 专辑封面获取 ====================
async function fetchArtworkFromAPI(song, artist) {
    return null; // Totally disabled external fetch
}



// ==================== 播放列表 ====================
async function addToPlaylist(song, artist, album, audioUrl, lyrics = '') {
    const existingIndex = playerState.playlist.findIndex(
        item => item.song === song && item.artist === artist
    );

    if (existingIndex !== -1) {
        // 歌曲已存在，更新 audioUrl 和其他信息
        playerState.playlist[existingIndex].audioUrl = audioUrl;
        playerState.playlist[existingIndex].album = album;
        if (lyrics) {
            playerState.playlist[existingIndex].lyrics = lyrics;
        }
        updatePlaylistUI();
        return existingIndex;
    }

    // 添加新歌曲
    const playlistItem = { song, artist, album, audioUrl, lyrics, artworkUrl: null };
    playerState.playlist.push(playlistItem);
    updatePlaylistUI();
    showNotification(`已添加: ${song}`);

    // 异步获取专辑封面
    if (artist && song) {
        fetchArtworkFromAPI(song, artist).then(artworkUrl => {
            if (artworkUrl) {
                playlistItem.artworkUrl = artworkUrl;
                console.log(`专辑封面获取成功: ${song} - ${artist}`);

                // 如果当前正在播放这首歌，更新播放器封面
                if (playerState.currentSong === song && playerState.currentArtist === artist) {
                    if (player.pThumb) player.pThumb.src = artworkUrl;
                }
                // 更新播放列表UI
                updatePlaylistUI();
            }
        });
    }

    return playerState.playlist.length - 1;
}

function updatePlaylistUI() {
    console.log('[UI Trace] updatePlaylistUI() called. Current playlist size:', playerState.playlist.length);
    if (!player.playlistContent) return;
    if (playerState.playlist.length === 0) {
        player.playlistContent.innerHTML = '<div class="playlist-empty">暂无播放中的歌曲</div>';
        return;
    }

    player.playlistContent.innerHTML = playerState.playlist.map((item, index) => {
        const artworkSrc = item.artworkUrl ||
            `https://ui-avatars.com/api/?name=${encodeURIComponent(item.song)}&background=333&color=fff&size=60`;
        return `
        <div class="playlist-item ${item.song === playerState.currentSong ? 'active' : ''} ${playerState.isPlaying && item.song === playerState.currentSong ? 'playing' : ''}"
             data-index="${index}">
            <div class="playlist-artwork">
                <img src="${artworkSrc}" alt="${item.song}" onerror="this.src='https://ui-avatars.com/api/?name=${encodeURIComponent(item.song)}&background=333&color=fff&size=60'">
            </div>
            <div class="playlist-info">
                <div class="playlist-title">${item.song}</div>
                <div class="playlist-artist">${item.artist} · ${item.album}</div>
            </div>
            <div class="playlist-remove" onclick="removeFromPlaylist(${index}, event)">×</div>
        </div>
    `;
    }).join('');

    player.playlistContent.querySelectorAll('.playlist-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (!e.target.classList.contains('playlist-remove')) {
                const index = parseInt(item.getAttribute('data-index'));
                playSongAtIndex(index);
            }
        });
    });
}

function updatePlaylistActive(index) {
    if (!player.playlistContent) return;
    player.playlistContent.querySelectorAll('.playlist-item').forEach((item, i) => {
        item.classList.toggle('active', i === index);
        item.classList.toggle('playing', i === index && playerState.isPlaying);
    });
}

// 移除播放列表项（全局函数）
window.removeFromPlaylist = function (index, e) {
    if (e) e.stopPropagation();
    if (index < 0 || index >= playerState.playlist.length) return;

    const item = playerState.playlist[index];
    playerState.playlist.splice(index, 1);

    if (item.song === playerState.currentSong) {
        player.audio.pause();
        playerState.currentSong = null;
        playerState.isPlaying = false;
        updatePlayPauseButton();
    }

    updatePlaylistUI();
    showNotification(`已移除: ${item.song}`);
};

// ==================== 歌词 ====================
async function fetchLyricsFromAPI(song, artist) {
    try {
        const encodedArtist = encodeURIComponent(artist);
        const encodedSong = encodeURIComponent(song);
        const response = await fetch(`https://api.lyrics.ovh/v1/${encodedArtist}/${encodedSong}`);

        if (!response.ok) {
            if (response.status === 404) {
                console.log(`未找到歌词: ${song} - ${artist}`);
                return null;
            }
            throw new Error(`API 请求失败: ${response.status}`);
        }

        const data = await response.json();
        return data.lyrics || null;
    } catch (error) {
        console.error('获取歌词失败:', error);
        return null;
    }
}

/**
 * 更新歌词调整按钮的可见性
 * @param {boolean} hasLyrics 
 */
function updateLyricAdjBtnVisibility(hasLyrics) {
    if (player.lyricAdjBtn) {
        player.lyricAdjBtn.style.display = hasLyrics ? 'flex' : 'none';
        if (hasLyrics) {
            console.log('[UI] 歌词编辑按钮已显示');
        }
    }
}

async function loadLyrics(item) {
    if (!player.lyricsContent) return;

    // 初始状态：根据已有元数据初步判断
    const initialHasLyrics = !!(item.lrcPath || item.lyrics || (window.getLrcLyrics && window.getLrcLyrics(item.artist, item.song)));
    updateLyricAdjBtnVisibility(initialHasLyrics);
    if (player.lyricAdjBtn) player.lyricAdjBtn.classList.remove('active');

    // 重置歌词同步模块
    LyricsSync.reset();

    // 显示加载状态（底部面板）
    player.lyricsContent.innerHTML = `
        <div class="lyrics-empty">
            <div style="margin-bottom: 10px;">正在获取歌词...</div>
            <div style="font-size: 0.75rem; color: #666;">从歌词库获取</div>
        </div>
    `;

    // 显示加载状态（专辑页）
    if (player.albumLyrics) {
        player.albumLyrics.innerHTML = `<div class="lyrics-empty">正在获取歌词...</div>`;
    }

    let lrcText = null;

    // 1. 优先尝试从后端返回的静默路径加载
    if (item.lrcPath) {
        let fetchUrl = item.lrcPath;
        if (fetchUrl.includes('r2.changgepd.ccwu.cc')) {
            fetchUrl = fetchUrl.replace('https://r2.changgepd.ccwu.cc', 'https://pub-ade3407baf1041b49b5949a2539067f7.r2.dev');
        }
        const apiBase = window.API_BASE || window.MOODY_CONFIG?.API_BASE || '';
        if (!fetchUrl.startsWith('http') && !fetchUrl.startsWith('/storage/')) {
            fetchUrl = `${apiBase}/storage/${fetchUrl}`;
        } else if (fetchUrl.startsWith('/storage/')) {
            fetchUrl = `${apiBase}${fetchUrl}`;
        }

        // 核心修复：增加时间戳防止浏览器强效缓存旧歌词
        const separator = fetchUrl.includes('?') ? '&' : '?';
        const cacheBusterUrl = `${fetchUrl}${separator}t=${Date.now()}`;

        console.log(`[Lyrics] 尝试从后端路径加载 (带缓存击穿): ${cacheBusterUrl}`);
        const lyricsController = new AbortController();
        _activeLyricsAbortController = lyricsController;

        try {
            const response = await fetch(cacheBusterUrl, { signal: lyricsController.signal });
            if (_activeLyricsAbortController === lyricsController) {
                _activeLyricsAbortController = null;
            }

            if (response.ok) {
                lrcText = await response.text();
                console.log(`✓ 成功从远程加载歌词: ${fetchUrl}`);
                try {
                    renderParsedLyrics(LyricsSync.parseLRC(lrcText));
                    LyricsSync.load(lrcText);
                    updateLyricAdjBtnVisibility(true); // 文件加载成功，显示按钮
                    // 通知 Zen 沉浸模式重建歌词列表
                    window.dispatchEvent(new CustomEvent('moody:lyricsLoaded', { detail: { source: 'lrcPath' } }));
                } catch (parseErr) {
                    console.error('[Lyrics] 解析 LRC 失败:', parseErr);
                    if (item.id) reportClientError('lyric', item.id, `歌词解析失败: ${parseErr.message}`);
                }
                return;
            } else {
                if (item.id) reportClientError('lyric', item.id, `云端响应错误: ${response.status} ${item.lrcPath}`);
            }
        } catch (e) {
            if (_activeLyricsAbortController === lyricsController) {
                _activeLyricsAbortController = null;
            }
            if (e.name === 'AbortError') {
                console.log(`[Lyrics] 🛑 Lyrics request physically aborted for: ${item.song}`);
                return;
            }
            console.warn(`[Lyrics] 远程加载失败: ${item.lrcPath}`, e);
            if (item.id) reportClientError('lyric', item.id, `远程加载网络异常: ${e.message}`);
        }
    }

    // 2. 其次从 LRC 歌词数据库查找 (硬编码库)
    if (item.artist && item.song && window.getLrcLyrics) {
        lrcText = window.getLrcLyrics(item.artist, item.song);
        if (lrcText) {
            console.log(`✓ 从内置歌词库找到: ${item.artist}-${item.song}`);
            renderParsedLyrics(LyricsSync.parseLRC(lrcText));
            LyricsSync.load(lrcText);
            updateLyricAdjBtnVisibility(true); // 内置库加载成功，显示按钮
            // 通知 Zen 沉浸模式重建歌词列表
            window.dispatchEvent(new CustomEvent('moody:lyricsLoaded', { detail: { source: 'localDB' } }));
            return;
        }
    }

    // 降级处理：尝试从本地歌词数据库查找（旧格式）
    let lyrics = item.lyrics || '';
    if (!lyrics && item.artist && item.song && window.LYRICS_DB) {
        const dbKey = `${item.artist}-${item.song}`;
        if (window.LYRICS_DB[dbKey]) {
            lyrics = window.LYRICS_DB[dbKey];
            console.log(`✓ 从本地歌词库找到: ${dbKey}`);
        }
    }

    // 如果本地没有，尝试从 API 获取
    if (!lyrics && item.artist && item.song) {
        console.log(`正在从API获取歌词: ${item.song} - ${item.artist}`);
        lyrics = await fetchLyricsFromAPI(item.song, item.artist);

        // 如果获取到歌词，更新到播放列表项中
        if (lyrics) {
            item.lyrics = lyrics;
            console.log('歌词获取成功');
            updateLyricAdjBtnVisibility(true); // API 获取成功，显示按钮
        }
    }

    if (lyrics) {
        // 尝试解析为 LRC 格式
        const parsedLyrics = LyricsSync.parseLRC(lyrics);
        if (parsedLyrics.length > 0) {
            renderParsedLyrics(parsedLyrics);
            LyricsSync.load(lyrics);
        } else {
            // 纯文本歌词，直接显示
            renderPlainLyrics(lyrics);
        }
        // 通知 Zen 沉浸模式重建歌词列表
        window.dispatchEvent(new CustomEvent('moody:lyricsLoaded', { detail: { source: 'api' } }));
    } else {
        // 底部面板
        player.lyricsContent.innerHTML = `
            <div class="lyrics-empty">
                <div style="margin-bottom: 10px;">未找到歌词</div>
                <div style="font-size: 0.75rem; color: #666;">提示: 歌词库中没有找到 "${item.song}" 的歌词</div>
            </div>
        `;

        // 专辑页
        if (player.albumLyrics) {
            player.albumLyrics.innerHTML = `<div class="lyrics-empty">未找到歌词</div>`;
        }
    }
}

/**
 * 渲染解析后的 LRC 歌词
 */
function renderParsedLyrics(lines) {
    console.log('渲染 LRC 歌词，共', lines.length, '行');

    // 底部面板歌词（每个字独立包装）
    if (player.lyricsContent) {
        player.lyricsContent.innerHTML = lines.map((line, index) => {
            const chars = line.text.split('').map((char, charIndex) =>
                `<span class="lyric-char" data-char-index="${charIndex}">${char}</span>`
            ).join('');
            return `<div class="lyrics-line" data-time="${line.time}" data-index="${index}">${chars}</div>`;
        }).join('');
    }

    // 专辑页歌词（每个字独立包装）
    if (player.albumLyrics) {
        player.albumLyrics.innerHTML = lines.map((line, index) => {
            const chars = line.text.split('').map((char, charIndex) =>
                `<span class="lyric-char" data-char-index="${charIndex}">${char}</span>`
            ).join('');
            return `<div class="ms-lyrics-item" data-time="${line.time}" data-index="${index}">${chars}</div>`;
        }).join('');
    }
}

/**
 * 渲染纯文本歌词
 */
function renderPlainLyrics(lyrics) {
    const lines = lyrics.split('\n').filter(line => line.trim());

    // 底部面板歌词
    if (player.lyricsContent) {
        player.lyricsContent.innerHTML = lines.map((line, index) => {
            return `<div class="lyrics-line" data-index="${index}">${line}</div>`;
        }).join('');
    }

    // 专辑页歌词
    if (player.albumLyrics) {
        player.albumLyrics.innerHTML = lines.map((line, index) => {
            return `<div class="ms-lyrics-item" data-index="${index}">${line}</div>`;
        }).join('');
    }
}

// ==================== 歌词同步高亮 ====================

// 歌词颜色配置
const LYRICS_COLORS = {
    active: '#64b5f6',           // 当前激活行的颜色（浅蓝色）
    inactive: 'rgba(255, 255, 255, 0.4)',  // 未激活行的颜色
    bgActive: 'rgba(100, 181, 246, 0.1)'   // 当前行的背景色
};

/**
 * 高亮指定索引的歌词行
 * @param {number} index - 要高亮的歌词行索引
 * @param {number} progress - 当前进度（0-1之间），用于逐字高亮
 */
function highlightLyricLine(index, progress = 1) {
    if (index < 0) return;

    // 计算应该高亮到第几个字
    const currentLine = LyricsSync.currentLyrics?.[index];
    const totalChars = currentLine?.text?.length || 0;
    const activeCharIndex = Math.floor(progress * totalChars);

    // 底部面板高亮
    if (player.lyricsContent) {
        const lines = player.lyricsContent.querySelectorAll('.lyrics-line');
        lines.forEach((el, i) => {
            if (i === index) {
                el.classList.add('active');

                // 逐字高亮
                const chars = el.querySelectorAll('.lyric-char');
                chars.forEach((charEl, charIndex) => {
                    if (charIndex < activeCharIndex) {
                        charEl.classList.add('played');
                        charEl.classList.remove('active');
                    } else if (charIndex === activeCharIndex) {
                        charEl.classList.add('active');
                        charEl.classList.remove('played');
                    } else {
                        charEl.classList.remove('active', 'played');
                    }
                });

                // 平滑滚动到当前行
                const container = player.lyricsContent;
                const containerHeight = container.offsetHeight;
                const elOffsetTop = el.offsetTop;
                const elHeight = el.offsetHeight;
                const scrollTop = elOffsetTop - containerHeight / 2 + elHeight / 2;

                container.scrollTo({
                    top: scrollTop,
                    behavior: 'smooth'
                });
            } else {
                el.classList.remove('active');
                // 重置所有字
                const chars = el.querySelectorAll('.lyric-char');
                chars.forEach(charEl => {
                    charEl.classList.remove('active', 'played');
                });
            }
        });
    }

    // 专辑页高亮
    if (player.albumLyrics) {
        const scrollContainer = player.albumLyrics;
        const items = player.albumLyrics.querySelectorAll('.ms-lyrics-item');

        items.forEach((el, i) => {
            if (i === index) {
                el.classList.add('current');

                // 逐字高亮
                const chars = el.querySelectorAll('.lyric-char');
                chars.forEach((charEl, charIndex) => {
                    if (charIndex < activeCharIndex) {
                        charEl.classList.add('played');
                        charEl.classList.remove('active');
                    } else if (charIndex === activeCharIndex) {
                        charEl.classList.add('active');
                        charEl.classList.remove('played');
                    } else {
                        charEl.classList.remove('active', 'played');
                    }
                });

                // 平滑滚动到当前行
                const containerHeight = scrollContainer.offsetHeight;
                const elOffsetTop = el.offsetTop;
                const elHeight = el.offsetHeight;
                const scrollTop = elOffsetTop - containerHeight / 2 + elHeight / 2;

                scrollContainer.scrollTo({
                    top: scrollTop,
                    behavior: 'smooth'
                });
            } else {
                el.classList.remove('current');
                // 重置所有字
                const chars = el.querySelectorAll('.lyric-char');
                chars.forEach(charEl => {
                    charEl.classList.remove('active', 'played');
                });
            }
        });
    }
}

/**
 * 更新歌词同步（在 timeupdate 事件中调用）
 */
function updateLyricsSync() {
    if (!playerState.duration) return;

    // 应用歌词偏移量
    const currentTime = playerState.currentTime + playerState.lyricsOffset;

    // 使用自己的 LyricsSync 模块获取当前应该高亮的行
    const newIndex = LyricsSync.getCurrentLineIndex(currentTime);

    // 计算当前行的进度（用于逐字高亮）
    let progress = 1;
    if (newIndex >= 0 && LyricsSync.currentLyrics) {
        const currentLine = LyricsSync.currentLyrics[newIndex];
        const nextLine = LyricsSync.currentLyrics[newIndex + 1];

        if (currentLine && nextLine) {
            // 计算当前行的时间范围
            const lineDuration = nextLine.time - currentLine.time;
            const elapsed = currentTime - currentLine.time;
            progress = Math.max(0, Math.min(1, elapsed / lineDuration));
        } else if (currentLine) {
            // 最后一行，假设每行持续时间约 4 秒
            const estimatedDuration = 4;
            const elapsed = currentTime - currentLine.time;
            progress = Math.max(0, Math.min(1, elapsed / estimatedDuration));
        }
    }

    // 只在索引变化时更新行高亮，但每次都更新字进度
    if (newIndex !== LyricsSync.currentIndex) {
        LyricsSync.currentIndex = newIndex;
    }

    // 每次都更新高亮（包含字进度）
    highlightLyricLine(newIndex, progress);
}

// ==================== 收藏 ====================
// ==================== 收藏 ====================
function toggleFavorite() {
    if (!playerState.currentSong) {
        showNotification('请先播放一首歌曲');
        return;
    }

    // 防御性校验
    if (!playerState.currentSong || !playerState.currentArtist) {
        console.warn('❌ 无法收藏: 歌曲信息不完整', playerState.currentSong, playerState.currentArtist);
        showNotification('歌曲信息不完整，无法收藏');
        return;
    }

    const favorite = {
        song: playerState.currentSong,
        artist: playerState.currentArtist,
        album: playerState.currentAlbum || '未知专辑'
    };

    // 使用 Storage 模块的 isFavorite 进行检查
    const isFav = Settings.isFavorite(favorite.song, favorite.artist);

    if (isFav) {
        // 移除收藏
        const success = Settings.removeFavorite(favorite.song, favorite.artist);
        if (success) {
            // 同步更新本地 state
            const index = playerState.favorites.findIndex(
                f => f.song === favorite.song && f.artist === favorite.artist
            );
            if (index >= 0) playerState.favorites.splice(index, 1);

            if (player.favoriteBtn) {
                player.favoriteBtn.classList.remove('active');
            }
            showNotification('已取消收藏');
        }
    } else {
        // 添加收藏
        const added = Settings.addFavorite(favorite);
        if (added) {
            playerState.favorites = Settings.loadFavorites();
            if (player.favoriteBtn) {
                player.favoriteBtn.classList.add('active');
            }
            showNotification('已添加到收藏');
            createRisingStar();
        } else {
            showNotification('已在收藏列表中');
        }
    }
}

/**
 * 更新收藏按钮状态
 */
function updateFavoriteButton() {
    if (!playerState.currentSong || !player.favoriteBtn) return;

    if (!playerState.currentArtist) {
        // 如果没有艺术家信息，视为未收藏，防止误判
        player.favoriteBtn.classList.remove('active');
        return;
    }

    const isFavorite = Settings.isFavorite(playerState.currentSong, playerState.currentArtist);

    // Debug Log: 帮助排查 "全部点赞" 问题
    // console.log(`[Favorite Check] Song: ${playerState.currentSong}, Artist: ${playerState.currentArtist}, isFavorite: ${isFavorite}`);

    if (isFavorite) {
        player.favoriteBtn.classList.add('active');
    } else {
        player.favoriteBtn.classList.remove('active');
    }
}

function createRisingStar() {
    const btn = player.favoriteBtn;
    if (!btn) return;

    // 1. 添加弹跳 class（CSS 驱动）
    btn.classList.remove('like-bounce');
    void btn.offsetWidth; // 强制 reflow 重置动画
    btn.classList.add('like-bounce');

    // 动画结束后移除 class
    setTimeout(() => btn.classList.remove('like-bounce'), 500);

    // 2. 微粒子爆裂（6 个小点向外射出）
    const container = document.getElementById('starContainer');
    if (!container) return;
    container.innerHTML = '';

    const colors = ['#ff4757', '#ff6b81', '#ffa502', '#ff6348'];
    for (let i = 0; i < 6; i++) {
        const dot = document.createElement('div');
        dot.className = 'like-particle';
        dot.style.background = colors[i % colors.length];
        container.appendChild(dot);

        const angle = (i / 6) * Math.PI * 2 + (Math.random() - 0.5) * 0.5;
        const distance = 18 + Math.random() * 12;
        const endX = Math.cos(angle) * distance;
        const endY = Math.sin(angle) * distance;

        dot.animate([
            { transform: 'translate(-50%, -50%) scale(1)', opacity: 1 },
            { transform: `translate(calc(-50% + ${endX}px), calc(-50% + ${endY}px)) scale(0)`, opacity: 0 }
        ], {
            duration: 400 + Math.random() * 200,
            easing: 'cubic-bezier(0, 0.8, 0.5, 1)',
            fill: 'forwards'
        }).onfinish = () => dot.remove();
    }
}


// ==================== 工具函数 ====================
function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function updateTimeDisplay() {
    if (!player.pTime) return;
    const current = formatTime(playerState.currentTime);
    const total = formatTime(playerState.duration);
    player.pTime.textContent = `${current} / ${total}`;
}

function showNotification(message) {
    console.log('显示通知:', message);
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%) translateY(-100px);
        background: #d4af37;
        color: #000;
        padding: 12px 24px;
        border-radius: 8px;
        font-size: 0.9rem;
        font-weight: 500;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        z-index: 9999;
        opacity: 0;
        transition: all 0.3s ease;
    `;

    console.log('通知元素已创建，添加到body');
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.transform = 'translateX(-50%) translateY(0)';
        notification.style.opacity = '1';
        console.log('通知动画显示');
    }, 10);

    setTimeout(() => {
        notification.style.transform = 'translateX(-50%) translateY(-100px)';
        notification.style.opacity = '0';
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// ==================== 导出 ====================
// ==================== 歌词编辑器增强支撑函数 ====================

/**
 * 插入 LRC 元数据标签到首行
 */
function insertMetadataTag(tag, value) {
    const textarea = player.lyricRawText;
    if (!textarea) return;

    const content = textarea.value;
    const tagStr = `[${tag}:${value || ''}]\n`;

    // 检查是否已存在该标签，如果存在则替换，否则插入最前
    const regex = new RegExp(`\\[${tag}:.*?\\]\\n?`, 'g');
    if (regex.test(content)) {
        textarea.value = content.replace(regex, tagStr);
    } else {
        textarea.value = tagStr + content;
    }

    renderEditorPreview(textarea.value);
    showNotification(`已插入/更新标签: [${tag}]`);
}

/**
 * 打点模式：处理点击预览行进行打点
 */
function handlePreviewLineTap(index) {
    if (!TapSyncState.active) return;

    // 如果点击的是当前等待行，执行正常 tap逻辑
    if (index === TapSyncState.currentLine) {
        tapMark();
    } else if (index < TapSyncState.currentLine) {
        // 如果是已打点的行，支持重打（撤回至该行）
        const diff = TapSyncState.currentLine - index;
        for (let i = 0; i < diff; i++) undoTapMark();
        tapMark();
    } else {
        // 如果点击的是后面的行，直接跳转到那一行开始打点（跳过中间的）
        TapSyncState.currentLine = index;
        updateTapSyncUI();
        tapMark();
    }
}

/**
 * 更新打点模式及状态展示
 */
function updateTapSyncUI() {
    const panel = document.getElementById('lyricPreviewPanel');
    if (!panel) return;

    const items = panel.querySelectorAll('.lyric-preview-line');
    items.forEach((item, i) => {
        item.classList.remove('tap-waiting', 'tapped', 'played');
        if (i < TapSyncState.currentLine) item.classList.add('played');
        else if (i === TapSyncState.currentLine) item.classList.add('tap-waiting');
        else item.classList.add('tap-pending');
    });

    // 自动滚动到当前行
    const currentLineEl = panel.querySelector('.tap-waiting');
    if (currentLineEl) {
        currentLineEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

console.log('✅ 播放器增强增强支撑函数已加载');
// ==================== 下一首预加载 ====================
function prefetchNextSong() {
    if (window.RoamingManager && (window.RoamingManager.isActive || playerState.isRoaming)) {
        // 漫游模式下接近尾声时（剩余 < 15秒），确保后台缓冲队列充满
        window.RoamingManager.fillQueue();
        return;
    }
    if (playerState.playlist.length <= 1) return;
    if (playerState.playMode === 'single') return; // 单曲循环不需要预加载

    const currentIndex = getCurrentPlaylistIndex();
    if (currentIndex < 0) return;

    let nextIndex;
    if (playerState.playMode === 'sequence') {
        if (currentIndex >= playerState.playlist.length - 1) return; // 最后一首不预加载
        nextIndex = currentIndex + 1;
    } else if (playerState.playMode === 'loop') {
        nextIndex = (currentIndex + 1) % playerState.playlist.length;
    } else {
        return; // shuffle 模式无法预测下一首
    }

    const nextItem = playerState.playlist[nextIndex];
    if (!nextItem || !nextItem.audioUrl) return;

    // 避免重复预加载
    if (_prefetchedUrl === nextItem.audioUrl) return;
    _prefetchedUrl = nextItem.audioUrl;

    // 静默预加载：创建隐藏的 Audio 对象加载数据
    if (_prefetchAudio) {
        _prefetchAudio.src = '';
        _prefetchAudio = null;
    }
    _prefetchAudio = new Audio();
    _prefetchAudio.preload = 'auto';
    _prefetchAudio.src = nextItem.audioUrl;
    console.log(`[Prefetch] 🚀 预加载下一首: "${nextItem.song}" (${nextItem.audioUrl.split('/').pop()})`);
}

// ==================== 随心漫游引擎 (RoamingManager) ====================
const RoamingManager = {
    get isActive() {
        return !!playerState.isRoaming;
    },
    queue: [],
    history: [],
    recentSignatures: new Set(),
    isFilling: false,
    _abortGen: 0,

    /**
     * 启动随心漫游模式
     */
    start: async function () {
        console.log('[Roaming] 启动全库随心漫游...');
        const myGen = ++this._abortGen;
        playerState.isRoaming = true;

        // 更新按钮外观状态
        this.updateBtnUI();

        // 互斥保护：清除专辑高亮
        if (window.clearAlbumViewActiveState) {
            window.clearAlbumViewActiveState();
        }

        const btn = document.getElementById('roamBtn');
        if (btn) btn.classList.add('loading');
        setLoadingState(true);

        try {
            // 等待艺人名录就绪（若初次启动尚未载入完成）
            if (!window.allArtistsData || window.allArtistsData.length === 0) {
                console.log('[Roaming] 等待名录数据载入...');
                for (let i = 0; i < 15; i++) {
                    if (window.allArtistsData && window.allArtistsData.length > 0) break;
                    await new Promise(r => setTimeout(r, 200));
                }
            }

            let track = null;
            if (this.queue.length > 0) {
                track = this.queue.shift();
            } else {
                track = await this.pickRandomSong();
            }

            if (myGen !== this._abortGen || !playerState.isRoaming) {
                console.log('[Roaming] 启动操作已被后续动作覆盖');
                return;
            }

            if (track) {
                await this.playRoamingTrack(track, /* recordHistory= */ true);
                // 启动后台预加载队列，维持储备
                this.fillQueue();
            } else {
                console.warn('[Roaming] 首次未获取到有效漫游歌曲，2秒后自动重试');
                showNotification('正在全库寻找音源，请稍候...');
                setTimeout(() => {
                    if (playerState.isRoaming) this.playNext();
                }, 2000);
            }
        } catch (err) {
            console.error('[Roaming] 漫游启动异常:', err);
            showNotification('网络繁忙，正在重试漫游抽歌...');
            setTimeout(() => {
                if (playerState.isRoaming) this.playNext();
            }, 2000);
        } finally {
            if (btn) btn.classList.remove('loading');
            setLoadingState(false);
        }
    },

    /**
     * 停止随心漫游模式
     * @param {boolean} silent 为 true 时不暂停音频（用于由专辑点击直接接管）
     */
    stop: function (silent = false) {
        if (!playerState.isRoaming) {
            this.updateBtnUI();
            return;
        }
        console.log(`[Roaming] 退出随心漫游模式 (silent: ${silent})`);
        this._abortGen++;
        playerState.isRoaming = false;
        this.queue = [];

        this.updateBtnUI();

        if (!silent) {
            if (player && player.audio && !player.audio.paused) {
                player.audio.pause();
                playerState.isPlaying = false;
                updatePlayPauseButton();
            }
        }
    },

    /**
     * 切换漫游状态开关
     */
    toggle: async function () {
        if (this.isActive) {
            this.stop(false);
            showNotification('已退出随心漫游');
        } else {
            await this.start();
            showNotification('✨ 已开启随心漫游 · 全局无尽随机');
        }
    },

    /**
     * 更新侧边栏漫游按钮样式
     */
    updateBtnUI: function () {
        const btn = document.getElementById('roamBtn');
        if (!btn) return;
        if (playerState.isRoaming) {
            btn.classList.add('active');
            btn.setAttribute('title', '随心漫游中 · 点击退出');
        } else {
            btn.classList.remove('active', 'loading');
            btn.setAttribute('title', '随心漫游 · 全局无尽随机播放');
        }
    },

    /**
     * 播放下一首漫游歌曲（无缝循环、永不停止）
     */
    playNext: async function () {
        if (!playerState.isRoaming) return;
        console.log('[Roaming] 切往下一首漫游歌曲...');

        let nextTrack = null;
        if (this.queue.length > 0) {
            nextTrack = this.queue.shift();
        } else {
            nextTrack = await this.pickRandomSong();
        }

        if (nextTrack && playerState.isRoaming) {
            await this.playRoamingTrack(nextTrack, /* recordHistory= */ true);
            this.fillQueue();
        } else if (playerState.isRoaming) {
            console.warn('[Roaming] 缓冲耗尽且快速抽选未命中，1.5秒后重试');
            setTimeout(() => {
                if (playerState.isRoaming) this.playNext();
            }, 1500);
        }
    },

    /**
     * 播放上一首漫游歌曲（从历史栈回退）
     */
    playPrevious: async function () {
        if (!playerState.isRoaming) return;
        if (this.history.length > 0) {
            const prevTrack = this.history.pop();
            console.log(`[Roaming] 回退上一首漫游歌曲: ${prevTrack.song}`);
            await this.playRoamingTrack(prevTrack, /* recordHistory= */ false);
        } else {
            if (player && player.audio) {
                player.audio.currentTime = 0;
                player.audio.play();
            }
        }
    },

    /**
     * 执行播放漫游曲目
     */
    playRoamingTrack: async function (track, recordHistory = true) {
        if (!track || !track.audioUrl) return false;

        // 记录历史（最多保留 50 首）
        if (recordHistory && playerState.currentSong) {
            this.history.push({
                song: playerState.currentSong,
                artist: playerState.currentArtist,
                album: playerState.currentAlbum,
                audioUrl: player.audio ? player.audio.src : '',
                lyrics: '',
                lrcPath: playerState.currentLrcPath,
                artworkUrl: player.pThumb ? player.pThumb.src : ''
            });
            if (this.history.length > 50) this.history.shift();
        }

        const myGen = nextPlayGeneration();
        // 播放列表同步包含当前歌曲与储备队列，彻底消除 playlist.length === 1 的单曲死循环陷阱
        playerState.playlist = [track, ...this.queue];
        updatePlaylistUI();

        console.log(`[Roaming] 正在播放: "${track.song}" - ${track.artist} (Gen: ${myGen})`);
        return playSongAtIndex(0, myGen);
    },

    /**
     * 全库真随机抽选歌曲核心算法
     */
    pickRandomSong: async function () {
        const artists = window.allArtistsData || [];
        if (!artists || artists.length === 0) {
            console.warn('[Roaming] allArtistsData 尚不可用');
            return null;
        }

        // 当前正在播放的曲目签名与队列内待播签名，用于绝对防重复
        const currentSig = playerState.currentSong ? `${playerState.currentSong} - ${playerState.currentArtist}` : '';
        const queuedSigs = new Set(this.queue.map(q => `${q.song} - ${q.artist}`));

        // 最多尝试 20 次跨艺人随机寻找有效歌曲
        for (let attempt = 0; attempt < 20; attempt++) {
            const randomArtist = artists[Math.floor(Math.random() * artists.length)];
            if (!randomArtist) continue;

            // 1. 确保艺人专辑数据已拉取
            let albums = randomArtist.albums;
            if (!albums || albums.length === 0) {
                try {
                    const artistIdRaw = (randomArtist.id || "").toString().replace(/\D/g, '');
                    // 设置 4 秒超时控制器，防止后台上传卡死接口导致 fetch 无限挂起
                    const controller = new AbortController();
                    const fetchTimeout = setTimeout(() => controller.abort(), 4000);
                    const res = await fetch(`${window.API_BASE || ''}/api/songs?artistId=${artistIdRaw}&artist=${encodeURIComponent(randomArtist.name)}`, {
                        signal: controller.signal
                    });
                    clearTimeout(fetchTimeout);

                    if (res.ok) {
                        const json = await res.json();
                        const detail = json.data && json.data.length > 0 ? json.data[0] : null;
                        if (detail && detail.albums && detail.albums.length > 0) {
                            albums = detail.albums.filter(a => a.songs && a.songs.length > 0);
                            randomArtist.albums = albums; // 写入内存缓存，提升后续命中率
                        }
                    }
                } catch (e) {
                    continue;
                }
            }

            if (!albums || albums.length === 0) continue;

            // 2. 严格筛选包含已点亮有效音源的专辑（过滤掉全专辑歌曲均暂缺的空壳）
            const playableFilter = (s) => {
                const sName = typeof s === 'string' ? s : s.title;
                const sPath = typeof s === 'string' ? null : s.path;
                const exactKey = `${sName} - ${randomArtist.name}`;
                const bulkKey = `${sName} - 本地音乐`;
                const hasLocal = (window.localSongsMap && (window.localSongsMap.has(exactKey) || window.localSongsMap.has(bulkKey))) ||
                                 (playerState.uploadedFiles && playerState.uploadedFiles.has(sName));
                return hasLocal || (typeof sPath === 'string' && sPath.trim().length > 0);
            };

            const validAlbums = albums.filter(a => a.songs && a.songs.some(playableFilter));
            if (validAlbums.length === 0) continue;
            const randomAlbum = validAlbums[Math.floor(Math.random() * validAlbums.length)];

            // 3. 仅从已点亮的有效音源歌曲中抽选（100% 杜绝抽选到『暂缺』/未点亮歌曲）
            const playableSongs = randomAlbum.songs.filter(playableFilter);
            if (playableSongs.length === 0) continue;
            const randomSong = playableSongs[Math.floor(Math.random() * playableSongs.length)];
            const songName = typeof randomSong === 'string' ? randomSong : randomSong.title;
            const songPath = typeof randomSong === 'string' ? null : randomSong.path;
            const songLrcPath = typeof randomSong === 'string' ? null : (randomSong.lrcPath || randomSong.lrc_path || null);

            const sig = `${songName} - ${randomArtist.name}`;

            // 4. 【核心防重复保护】
            // (1) 绝对禁止抽选中当前正在播放的同一首歌！
            if (currentSig && sig === currentSig) {
                continue;
            }
            // (2) 绝对禁止抽选中已经在待播队列里的歌曲！
            if (queuedSigs.has(sig)) {
                continue;
            }
            // (3) 前 15 次尝试严格杜绝历史已播歌曲（500 首去重窗口）
            if (this.recentSignatures.has(sig) && attempt < 15) {
                continue;
            }

            // 5. 构造音频地址
            let audioUrl = '';
            const exactKey = `${songName} - ${randomArtist.name}`;
            const bulkKey = `${songName} - 本地音乐`;

            if (window.localSongsMap && window.localSongsMap.has(exactKey)) {
                audioUrl = window.localSongsMap.get(exactKey).audioUrl;
            } else if (window.localSongsMap && window.localSongsMap.has(bulkKey)) {
                audioUrl = window.localSongsMap.get(bulkKey).audioUrl;
            } else if (playerState.uploadedFiles && playerState.uploadedFiles.has(songName)) {
                audioUrl = playerState.uploadedFiles.get(songName);
            } else if (songPath) {
                if (songPath.startsWith('http')) {
                    audioUrl = songPath;
                } else {
                    const encodedPath = songPath.split(/[\\/]/).map(segment => encodeURIComponent(segment)).join('/');
                    audioUrl = `${window.API_BASE || ''}/storage/${encodedPath}?t=${Date.now()}`;
                }
            }

            if (!audioUrl) continue;

            // 6. 构造封面地址
            let albumCoverUrl = randomAlbum.cover || '';
            if (albumCoverUrl && !albumCoverUrl.startsWith('http') && !albumCoverUrl.startsWith('/src/') && window.API_BASE) {
                albumCoverUrl = `${window.API_BASE}${albumCoverUrl.startsWith('/') ? '' : '/'}${albumCoverUrl}`;
            }

            // 记录已播集合（去重容量扩充至 500 首，确保会话内绝不重复）
            this.recentSignatures.add(sig);
            if (this.recentSignatures.size > 500) {
                const firstSig = this.recentSignatures.values().next().value;
                this.recentSignatures.delete(firstSig);
            }

            return {
                song: songName,
                artist: randomArtist.name,
                album: randomAlbum.title,
                audioUrl: audioUrl,
                lyrics: '',
                lrcPath: songLrcPath,
                artworkUrl: albumCoverUrl
            };
        }

        console.warn('[Roaming] 多次抽选未命中可用音源');
        return null;
    },

    /**
     * 后台维持储备缓冲队列 (保持 4 首储备，确保后台/网络波动下持续流畅播放)
     */
    fillQueue: async function () {
        const QUEUE_TARGET = 4;
        if (this.isFilling || !playerState.isRoaming || this.queue.length >= QUEUE_TARGET) return;
        this.isFilling = true;

        try {
            while (playerState.isRoaming && this.queue.length < QUEUE_TARGET) {
                const track = await this.pickRandomSong();
                if (track && playerState.isRoaming) {
                    this.queue.push(track);
                    console.log(`[Roaming Queue] 预缓冲歌曲就绪: "${track.song}" - ${track.artist} (余量: ${this.queue.length})`);
                    // 同步到播放列表 UI（当前歌 + 预缓冲队列）
                    if (playerState.playlist && playerState.playlist.length > 0) {
                        playerState.playlist = [playerState.playlist[0], ...this.queue];
                        updatePlaylistUI();
                    }
                } else {
                    break;
                }
            }
        } catch (e) {
            console.warn('[Roaming Queue] 缓冲填充异常:', e);
        } finally {
            this.isFilling = false;
        }
    }
};

window.RoamingManager = RoamingManager;

window.audioPlayer = {
    play: async (song, artist, album, audioUrl, lyrics) => {
        // 互斥保护：任何直接单曲播放（例如本地音乐或手动指定单曲），自动退出漫游模式
        if (window.RoamingManager && window.RoamingManager.isActive) {
            window.RoamingManager.stop(true);
        }
        let finalUrl = audioUrl;
        if (finalUrl && finalUrl.includes('r2.changgepd.ccwu.cc')) {
            finalUrl = finalUrl.replace('https://r2.changgepd.ccwu.cc', 'https://pub-ade3407baf1041b49b5949a2539067f7.r2.dev');
        }
        if (finalUrl && finalUrl.startsWith('http') && !finalUrl.includes('?t=') && !finalUrl.includes('&t=')) {
            const separator = finalUrl.includes('?') ? '&' : '?';
            finalUrl = `${finalUrl}${separator}t=${Date.now()}`;
        }
        const index = await addToPlaylist(song, artist, album, finalUrl, lyrics);
        return playSongAtIndex(index); // [Modified] 返回播放结果
    },
    // 播放整张专辑 (纯同步构建播放列表 + 单一入口播放，彻底消除异步竞态窗口)
    playAlbum: async (songs, artist, albumInfo, startSongIndex, targetGen = null) => {
        console.log(`[Player] ========== playAlbum Start ==========`);

        // 互斥保护：任何进入专辑播放的动作，自动退出漫游模式
        if (window.RoamingManager && window.RoamingManager.isActive) {
            window.RoamingManager.stop(true);
        }

        // 如果调用方已分配代次（例如 app.js 乐观点击），直接沿用；否则生成新代次
        const myGen = targetGen !== null ? targetGen : nextPlayGeneration();

        if (myGen !== _playGeneration) {
            console.log(`[playAlbum Guard] Generation superseded before setup (gen ${myGen} vs ${_playGeneration}), aborting.`);
            return false;
        }

        // --- 纯同步装配播放列表 ---
        playerState.playlist = [];
        const albumCoverUrl = albumInfo.cover || '';

        for (let i = 0; i < songs.length; i++) {
            const songData = songs[i];
            const songName = typeof songData === 'string' ? songData : songData.title;
            const songPath = typeof songData === 'string' ? null : songData.path;
            // 兼容后端蛇形命名 lrc_path 与前端驼峰命名 lrcPath，防止歌词路径丢失
            const songLrcPath = typeof songData === 'string' ? null : (songData.lrcPath || songData.lrc_path || null);

            let audioUrl = '';
            const exactKey = `${songName} - ${artist}`;
            const bulkKey = `${songName} - 本地音乐`;

            if (window.localSongsMap && window.localSongsMap.has(exactKey)) {
                audioUrl = window.localSongsMap.get(exactKey).audioUrl;
            } else if (window.localSongsMap && window.localSongsMap.has(bulkKey)) {
                audioUrl = window.localSongsMap.get(bulkKey).audioUrl;
            } else if (playerState.uploadedFiles.has(songName)) {
                audioUrl = playerState.uploadedFiles.get(songName);
            } else if (songPath) {
                const apiBase = window.API_BASE || window.MOODY_CONFIG?.API_BASE || '';
                if (songPath.startsWith('http')) {
                    let normalizedPath = songPath;
                    if (normalizedPath.includes('r2.changgepd.ccwu.cc')) {
                        normalizedPath = normalizedPath.replace('https://r2.changgepd.ccwu.cc', 'https://pub-ade3407baf1041b49b5949a2539067f7.r2.dev');
                    }
                    const separator = normalizedPath.includes('?') ? '&' : '?';
                    audioUrl = `${normalizedPath}${separator}t=${Date.now()}`;
                } else {
                    const encodedPath = songPath.split(/[\\/]/).map(segment => encodeURIComponent(segment)).join('/');
                    audioUrl = `${apiBase}/storage/${encodedPath}?t=${Date.now()}`;
                }
            }

            playerState.playlist.push({
                song: songName,
                artist: artist,
                album: albumInfo.title,
                audioUrl: audioUrl,
                lyrics: '',
                lrcPath: songLrcPath || null,
                artworkUrl: albumCoverUrl
            });
        }

        if (myGen !== _playGeneration) {
            console.log(`[playAlbum Guard] Generation superseded after setup (gen ${myGen} vs ${_playGeneration}), aborting.`);
            return false;
        }

        updatePlaylistUI();
        console.log(`========== 开始播放索引 ${startSongIndex} 的歌曲 (Gen: ${myGen}) ==========`);
        return playSongAtIndex(startSongIndex, myGen);
    },
    addToPlaylist,
    playNext,
    playPrevious,
    getState: () => playerState
};

console.log('✅ audioPlayer 对象已导出到 window.audioPlayer');
