/**
 * MOODY MUSIC - 微动画环境氛围与黑胶屏保系统 (ambient-bg.js)
 * 核心逻辑：
 * 1. 常态下完全保持纯净黑胶暗黑界面，不显示任何半透明视频背景，零 GPU 开销
 * 2. 仅在音乐【正在播放中】且鼠标闲置 30 秒时，自动唤醒「沉浸黑胶巨幕屏保 (Zen Mode)」
 * 3. 退出屏保时立即暂停微动视频解码，切回纯粹暗黑界面
 * 4. 侧边栏底部保留场景切换 Dock，方便随时切换喜欢的素材，并可一键手动预览屏保
 */

(function () {
    'use strict';

    // ==================== 微动画素材配置 ====================
    // 优先从生产环境云端服务器 / R2 存储加载动态屏保视频，离线或未就绪时自动平滑回退至本地 assets
    const isLocalHost = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
    const R2_AMBIENT_BASE = (typeof window !== 'undefined' && window.MOODY_CONFIG && window.MOODY_CONFIG.R2_BASE)
        ? `${window.MOODY_CONFIG.R2_BASE}/ambient/`
        : 'https://r2.changgepd.ccwu.cc/ambient/';
    // 本地开发模式下优先直读本地 assets/video，生产部署直连已剔除频谱的 R2 干净视频
    const VIDEO_BASE = isLocalHost ? 'src/assets/video/' : ((typeof window !== 'undefined' && window.AMBIENT_VIDEO_BASE_URL) || R2_AMBIENT_BASE);

    const AMBIENT_SCENES = {
        karen_street_acoustic: {
            id: 'karen_street_acoustic',
            name: '夜市暖灯吉他',
            desc: '暖光灯串、木吉他独奏与闭目沉浸的听歌少女',
            icon: '🎸',
            file: VIDEO_BASE + 'karen_street_acoustic.mp4?v=5.1',
            localFile: 'src/assets/video/karen_street_acoustic.mp4',
            fallbackFile: VIDEO_BASE + 'karen_street_acoustic.webm?v=5.1',
            imageFallback: 'src/assets/images/karen_street_acoustic.jpg?v=5.1'
        },
        karen_midnight_cafe: {
            id: 'karen_midnight_cafe',
            name: '深夜电台录音室',
            desc: '温馨复古录音室、暖色台灯、经典黑胶与咖啡',
            icon: '🎙️',
            file: VIDEO_BASE + 'karen_midnight_cafe.mp4?v=5.0',
            localFile: 'src/assets/video/karen_midnight_cafe.mp4',
            fallbackFile: VIDEO_BASE + 'karen_midnight_cafe.webm?v=5.0',
            imageFallback: 'src/assets/images/karen_midnight_cafe.jpg?v=5.0'
        },
        karen_candle_devotion: {
            id: 'karen_candle_devotion',
            name: '烛光静修小室',
            desc: '暖意烛光、复古台灯与静谧书斋',
            icon: '🕯️',
            file: VIDEO_BASE + 'karen_candle_devotion.mp4?v=5.0',
            localFile: 'src/assets/video/karen_candle_devotion.mp4',
            fallbackFile: VIDEO_BASE + 'karen_candle_devotion.webm?v=5.0',
            imageFallback: 'src/assets/images/karen_candle_devotion.jpg?v=5.0'
        },
        karen_rainy_night: {
            id: 'karen_rainy_night',
            name: '雨夜微光静息',
            desc: '窗外沥沥小雨，室内温柔爵士与安息时光',
            icon: '🌧️',
            file: VIDEO_BASE + 'karen_rainy_night.mp4?v=5.0',
            localFile: 'src/assets/video/karen_rainy_night.mp4',
            fallbackFile: VIDEO_BASE + 'karen_rainy_night.webm?v=5.0',
            imageFallback: 'src/assets/images/karen_rainy_night.jpg?v=5.0'
        },
        karen_mountain_chapel: {
            id: 'karen_mountain_chapel',
            name: '远山圣殿晨曦',
            desc: '远山微风、圣殿晨光与静心时刻',
            icon: '⛪',
            file: VIDEO_BASE + 'karen_mountain_chapel.mp4?v=5.0',
            localFile: 'src/assets/video/karen_mountain_chapel.mp4',
            fallbackFile: VIDEO_BASE + 'karen_mountain_chapel.webm?v=5.0',
            imageFallback: 'src/assets/images/karen_mountain_chapel.jpg?v=5.0'
        },
        karen_morning_grace: {
            id: 'karen_morning_grace',
            name: '晨光初醒赞美',
            desc: '清晨的第一缕温暖日光与醇香咖啡',
            icon: '☕',
            file: VIDEO_BASE + 'karen_morning_grace.mp4?v=5.1',
            localFile: 'src/assets/video/karen_morning_grace.mp4',
            fallbackFile: VIDEO_BASE + 'karen_morning_grace.webm?v=5.1',
            imageFallback: 'src/assets/images/karen_morning_grace.jpg?v=5.1'
        },
        karen_peaceful_rest: {
            id: 'karen_peaceful_rest',
            name: '安息静水边',
            desc: '微风拂过绿野，轻柔抚慰疲惫心灵',
            icon: '🕊️',
            file: VIDEO_BASE + 'karen_peaceful_rest.mp4?v=5.0',
            localFile: 'src/assets/video/karen_peaceful_rest.mp4',
            fallbackFile: VIDEO_BASE + 'karen_peaceful_rest.webm?v=5.0',
            imageFallback: 'src/assets/images/karen_peaceful_rest.jpg?v=5.0'
        },
        karen_worship_jazz: {
            id: 'karen_worship_jazz',
            name: '晚安祷告爵士',
            desc: '温馨窗台、夜间微光与治愈陪伴',
            icon: '🌙',
            file: VIDEO_BASE + 'karen_worship_jazz.mp4?v=5.0',
            localFile: 'src/assets/video/karen_worship_jazz.mp4',
            fallbackFile: VIDEO_BASE + 'karen_worship_jazz.webm?v=5.0',
            imageFallback: 'src/assets/images/karen_worship_jazz.jpg?v=5.0'
        },
        ocean: {
            id: 'ocean',
            name: '深海荧光',
            desc: '静谧荧光水母与深蓝洋流',
            icon: '🌊',
            file: VIDEO_BASE + 'ocean.webm'
        },
        shinjuku: {
            id: 'shinjuku',
            name: '新宿雨夜',
            desc: '新宿街头真实长镜头车水马龙 (5分钟不重复实录)',
            icon: '🌧️',
            file: VIDEO_BASE + 'shinjuku_clean.mp4?v=20260906_1510',
            localFile: 'src/assets/video/shinjuku_clean.mp4',
            fallbackFile: VIDEO_BASE + 'shinjuku_clean.webm?v=20260906_1510',
            imageFallback: 'src/assets/images/shinjuku_clean.jpg'
        },
        cozy_rain: {
            id: 'cozy_rain',
            name: '极简雨窗',
            desc: '纯净微雨划过玻璃窗棂',
            icon: '☕',
            file: VIDEO_BASE + 'cozy_rain.webm'
        },
        cafe_rain: {
            id: 'cafe_rain',
            name: '街角咖啡',
            desc: '复古暖灯与街道雨景',
            icon: '🍂',
            file: VIDEO_BASE + 'cafe_rain.webm'
        },
        sunset: {
            id: 'sunset',
            name: '日落暖阳',
            desc: '天台落日、温暖爵士光影与旋转黑胶唱机',
            icon: '🌅',
            file: VIDEO_BASE + 'sunset_clean_v3.webm?v=20260905_2330',
            localFile: 'src/assets/video/sunset_clean_v3.webm',
            fallbackFile: VIDEO_BASE + 'sunset_clean_v3.mp4?v=20260905_2330',
            imageFallback: 'src/assets/images/sunset_v3.jpg'
        },
        none: {
            id: 'none',
            name: '纯黑胶暗色',
            desc: '关闭微动，极致静谧',
            icon: '🚫',
            file: null
        }
    };

    const SCENE_KEYS = [
        'karen_street_acoustic',
        'karen_midnight_cafe',
        'karen_candle_devotion',
        'karen_rainy_night',
        'karen_mountain_chapel',
        'karen_morning_grace',
        'karen_peaceful_rest',
        'karen_worship_jazz',
        'ocean',
        'shinjuku',
        'cozy_rain',
        'cafe_rain',
        'sunset'
    ];

    // ==================== 全局状态管理 ====================
    let currentSceneId = 'ocean';
    let isZenMode = false;
    let autoZenEnabled = true;
    let idleTimer = null;
    let zenHudTimer = null;
    let lastTrackIdOrSrc = null;
    const IDLE_TIMEOUT = 30000; // 播放中闲置 30 秒切入黑胶屏保

    // DOM 元素缓存
    const dom = {
        videoContainer: null,
        video: null,
        image: null,
        dustParticles: null,
        visualizerContainer: null,
        visualizerCanvas: null,
        switchDock: null,
        switchBtn: null,
        sbAmbIcon: null,
        sbAmbCurrentName: null,
        switchMenu: null,
        menuItems: null,
        zenModeQuickBtn: null,
        autoZenCheck: null,
        zenOverlay: null,
        zenScenePills: null,
        zenExitBtn: null,
        zenVinylDisc: null,
        zenVinylCover: null,
        zenTonearm: null,
        zenTrackAlbum: null,
        zenTrackTitle: null,
        zenTrackArtist: null,
        zenLyricsContainer: null,
        zenCurrentTime: null,
        zenProgressBar: null,
        zenProgressFill: null,
        zenDurationTime: null,
        zenPrevBtn: null,
        zenPlayPauseBtn: null,
        zenPlayIcon: null,
        zenPauseIcon: null,
        zenNextBtn: null
    };

    /**
     * 辅助时间格式化
     */
    function formatTime(secs) {
        if (!secs || isNaN(secs) || secs < 0) return '00:00';
        const m = Math.floor(secs / 60);
        const s = Math.floor(secs % 60);
        return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
    }

    /**
     * 初始化环境氛围系统
     */
    function initAmbientSystem() {
        cacheDOMElements();
        if (!dom.video) return;

        // 确保静音及行内播放属性
        dom.video.muted = true;
        dom.video.defaultMuted = true;
        dom.video.playsInline = true;

        // 1. 初始化素材：如果用户从未手动选过，先随机挑选一个预设
        let savedScene = localStorage.getItem('moody_ambient_scene');
        if (!savedScene || !AMBIENT_SCENES[savedScene]) {
            const randomIdx = Math.floor(Math.random() * SCENE_KEYS.length);
            savedScene = SCENE_KEYS[randomIdx];
            console.log(`[Ambient] 首次启动预设微动背景: ${savedScene}`);
        }
        currentSceneId = savedScene;

        // 2. 自动屏保开关 (默认开启)
        const savedAutoZen = localStorage.getItem('moody_auto_zen');
        autoZenEnabled = savedAutoZen !== 'false';
        if (dom.autoZenCheck) dom.autoZenCheck.checked = autoZenEnabled;

        // 3. 构建切换菜单与屏保内快捷 Pills
        renderSwitchMenu();
        renderZenScenePills();

        // 4. 应用背景场景 (常态下保持 pause，不耗能)
        applyScene(currentSceneId, false);

        // 5. 绑定事件与闲置监听
        bindEvents();

        // 6. 挂载全局对象
        window.AmbientBg = {
            switchScene: (id) => applyScene(id, true),
            enterZen: enterZenMode,
            exitZen: exitZenMode,
            toggleZen: toggleZenMode,
            getCurrentScene: () => AMBIENT_SCENES[currentSceneId]
        };

        console.log('✓ 微动屏保系统就绪 (已设为仅在播放时休眠唤醒)');
    }

    /**
     * 缓存 DOM 元素
     */
    function cacheDOMElements() {
        dom.videoContainer = document.getElementById('ambientBgContainer');
        dom.video = document.getElementById('ambientVideo');
        dom.switchDock = document.getElementById('sidebarAmbientDock');
        dom.switchBtn = document.getElementById('bgSwitchBtn');
        dom.sbAmbIcon = document.getElementById('sbAmbIcon');
        dom.sbAmbCurrentName = document.getElementById('sbAmbCurrentName');
        dom.switchMenu = document.getElementById('bgSwitchMenu');
        dom.menuItems = document.getElementById('bgMenuItems');
        dom.zenModeQuickBtn = document.getElementById('zenModeQuickBtn');
        dom.autoZenCheck = document.getElementById('autoZenCheckbox');
        dom.zenOverlay = document.getElementById('zenOverlay');
        dom.zenScenePills = document.getElementById('zenScenePills');
        dom.zenExitBtn = document.getElementById('zenExitBtn');
        dom.zenVinylDisc = document.getElementById('zenVinylDisc');
        dom.zenVinylCover = document.getElementById('zenVinylCover');
        dom.zenTonearm = document.getElementById('zenTonearm');
        dom.zenTrackTitle = document.getElementById('zenTrackTitle');
        dom.zenLyricsWrapper = document.querySelector('.zen-lyrics-wrapper');
        dom.zenLyricsContainer = document.getElementById('zenLyricsContainer');
        dom.zenCurrentTime = document.getElementById('zenCurrentTime');
        dom.zenProgressBar = document.getElementById('zenProgressBar');
        dom.zenProgressFill = document.getElementById('zenProgressFill');
        dom.zenDurationTime = document.getElementById('zenDurationTime');
        dom.zenPrevBtn = document.getElementById('zenPrevBtn');
        dom.zenPlayPauseBtn = document.getElementById('zenPlayPauseBtn');
        dom.zenPlayIcon = document.getElementById('zenPlayIcon');
        dom.zenPauseIcon = document.getElementById('zenPauseIcon');
        dom.zenNextBtn = document.getElementById('zenNextBtn');

        // 沉浸屏保载入过渡页 DOM 缓存
        dom.zenTransitionOverlay = document.getElementById('zenTransitionOverlay');
        dom.zenTransitionIcon = document.getElementById('zenTransitionIcon');
        dom.zenTransitionTitle = document.getElementById('zenTransitionTitle');
        dom.zenTransitionDesc = document.getElementById('zenTransitionDesc');
        dom.zenTransitionTip = document.getElementById('zenTransitionTip');

        // 实景图片与动态音频频谱 DOM 缓存
        dom.image = document.getElementById('ambientImage');
        dom.dustParticles = document.getElementById('ambientDustParticles');
        dom.visualizerContainer = document.getElementById('zenVisualizerContainer');
        dom.visualizerCanvas = document.getElementById('zenVisualizerCanvas');

        if (dom.image) {
            dom.image.addEventListener('error', function () {
                const currentSrc = dom.image.src || '';
                if (currentSrc.includes('r2.changgepd.ccwu.cc') || currentSrc.includes('ambient')) {
                    const localFallback = 'src/assets/images/sunset.jpg';
                    console.warn(`[Ambient] 远端日落素材加载受阻，平滑降级至本地资源: ${localFallback}`);
                    dom.image.src = localFallback;
                }
            });
            dom.image.addEventListener('load', function () {
                if (isZenMode && isTransitionActive) {
                    hideZenTransition();
                }
            });
        }

        // 远端微动视频加载容错降级机制：若远端资源暂未上传或网络抖动，自动平滑回退至本地资源
        if (dom.video) {
            dom.video.addEventListener('error', function () {
                const currentSrc = dom.video.src || '';
                if (currentSrc.includes('r2.changgepd.ccwu.cc') || currentSrc.includes('storage/ambient')) {
                    const filename = currentSrc.split('/').pop().split('?')[0];
                    const localFallback = `src/assets/video/${filename}`;
                    console.warn(`[Ambient] 远端微动素材加载受阻，平滑回退至本地资源: ${localFallback}`);
                    dom.video.src = localFallback;
                    dom.video.load();
                    if (isZenMode) {
                        dom.video.play().catch(() => {});
                    }
                }
            });

            // 当视频首帧实际开始渲染并流畅播放时，平滑揭开过渡页，告别黑屏等待
            dom.video.addEventListener('playing', function () {
                if (isZenMode && isTransitionActive) {
                    hideZenTransition();
                }
            });
            dom.video.addEventListener('timeupdate', function () {
                if (isZenMode && isTransitionActive && dom.video.currentTime > 0.05) {
                    hideZenTransition();
                }
            });
        }
    }

    /**
     * 渲染浮动菜单中的背景选项 (简约低调单行排版，无多余说明文本)
     */
    function renderSwitchMenu() {
        if (!dom.menuItems) return;
        dom.menuItems.innerHTML = Object.values(AMBIENT_SCENES).map(scene => `
            <button class="bg-menu-item ${scene.id === currentSceneId ? 'active' : ''}" data-scene="${scene.id}">
                <div class="bg-item-left">
                    <span class="bg-item-icon">${scene.icon}</span>
                    <span class="bg-item-name">${scene.name}</span>
                </div>
                <span class="bg-item-check">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                </span>
            </button>
        `).join('');

        dom.menuItems.querySelectorAll('.bg-menu-item').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const sceneId = btn.getAttribute('data-scene');
                applyScene(sceneId, true);
                closeSwitchMenu();
            });
        });
    }

    /**
     * 渲染 Zen Mode 顶部的快捷场景切换 Pills
     */
    function renderZenScenePills() {
        if (!dom.zenScenePills) return;
        dom.zenScenePills.innerHTML = Object.values(AMBIENT_SCENES).map(scene => `
            <button class="zen-pill-btn ${scene.id === currentSceneId ? 'active' : ''}" data-scene="${scene.id}" title="${scene.desc}">
                ${scene.icon} ${scene.name}
            </button>
        `).join('');

        dom.zenScenePills.querySelectorAll('.zen-pill-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const sceneId = btn.getAttribute('data-scene');
                applyScene(sceneId, true);
                showZenHud(3500);
            });
        });
    }

    /**
     * 应用场景
     */
    function applyScene(sceneId, save = true) {
        const scene = AMBIENT_SCENES[sceneId];
        if (!scene) return;
        currentSceneId = sceneId;

        if (save) {
            localStorage.setItem('moody_ambient_scene', sceneId);
        }

        // 切换背景介质 (支持 MP4/WebM 动态视频 与 1080P 高清实景插画)
        if (scene.type === 'image' && scene.file) {
            if (dom.video) {
                dom.video.removeAttribute('data-loaded-scene');
                dom.video.pause();
                dom.video.style.display = 'none';
            }
            if (dom.image) {
                dom.image.src = scene.file;
                dom.image.style.display = 'block';
            }
            if (dom.dustParticles) {
                dom.dustParticles.style.display = (scene.id === 'sunset') ? 'block' : 'none';
            }
        } else if (scene.file) {
            // 核心体验保障：如果有海报图，先在底层常驻显示海报，杜绝视频解码等待时的黑屏底衬
            if (dom.image) {
                if (scene.imageFallback) {
                    dom.image.src = scene.imageFallback;
                    dom.image.style.display = 'block';
                } else {
                    dom.image.style.display = 'none';
                }
            }
            if (dom.dustParticles) {
                dom.dustParticles.style.display = 'none';
            }
            if (dom.video) {
                dom.video.style.display = 'block';
                if (dom.video.getAttribute('data-loaded-scene') !== sceneId) {
                    dom.video.setAttribute('data-loaded-scene', sceneId);
                    dom.video.src = scene.file;
                    dom.video.muted = true;
                    dom.video.load();
                    // 仅在屏保激活状态下才启动解码播放，常态下保持 pause
                    if (isZenMode) {
                        dom.video.play().catch(() => {});
                    } else {
                        dom.video.pause();
                    }
                }
            }
        } else {
            // 'none' 纯黑胶暗色
            if (dom.video) {
                dom.video.removeAttribute('data-loaded-scene');
                dom.video.pause();
                dom.video.style.display = 'none';
            }
            if (dom.image) {
                dom.image.style.display = 'none';
            }
            if (dom.dustParticles) {
                dom.dustParticles.style.display = 'none';
            }
        }

        // 若在屏保激活状态下切换场景，同步呈现优雅过渡页
        if (isZenMode && scene && scene.id !== 'none') {
            showZenTransition(scene, '正在切换视听画卷...');
        }

        // 更新侧边栏底部 Dock 的名称和图标
        if (dom.sbAmbIcon) dom.sbAmbIcon.textContent = scene.icon;
        if (dom.sbAmbCurrentName) dom.sbAmbCurrentName.textContent = scene.name;

        // 更新菜单项与 Pills 的高亮
        if (dom.menuItems) {
            dom.menuItems.querySelectorAll('.bg-menu-item').forEach(el => {
                el.classList.toggle('active', el.getAttribute('data-scene') === sceneId);
            });
        }
        if (dom.zenScenePills) {
            dom.zenScenePills.querySelectorAll('.zen-pill-btn').forEach(el => {
                el.classList.toggle('active', el.getAttribute('data-scene') === sceneId);
            });
        }
    }

    /**
     * 展开/收起背景菜单
     */
    function toggleSwitchMenu(e) {
        if (e) e.stopPropagation();
        if (!dom.switchMenu || !dom.switchDock) return;
        const isOpen = dom.switchMenu.classList.contains('active');
        if (isOpen) {
            closeSwitchMenu();
        } else {
            dom.switchDock.classList.add('open');
            dom.switchMenu.classList.add('active');
        }
    }

    function closeSwitchMenu() {
        if (dom.switchDock) dom.switchDock.classList.remove('open');
        if (dom.switchMenu) dom.switchMenu.classList.remove('active');
    }

    /**
     * 唤醒并保持 Zen HUD
     */
    function showZenHud(duration = 3500) {
        if (!isZenMode || !dom.zenOverlay) return;
        dom.zenOverlay.classList.add('zen-show-hud');
        clearTimeout(zenHudTimer);
        zenHudTimer = setTimeout(() => {
            if (isZenMode && dom.zenOverlay) {
                dom.zenOverlay.classList.remove('zen-show-hud');
            }
        }, duration);
    }

    // ==================== 音频频谱可视化 (audioMotion-analyzer 专业库) ====================
    let audioMotion = null; // audioMotion-analyzer 实例

    /**
     * 用 audioMotion-analyzer 初始化并启动频谱渲染
     */
    function startVisualizer() {
        // 1. 如果实例已存在，只需确保 AudioContext 唤醒并恢复动画循环（绝不重新创建 MediaElementSource）
        if (audioMotion) {
            try {
                if (audioMotion.audioCtx && audioMotion.audioCtx.state === 'suspended') {
                    audioMotion.audioCtx.resume().catch(() => {});
                }
                audioMotion.start();
            } catch (e) {}
            return;
        }

        const audioEl = document.getElementById('audioPlayer');
        if (!audioEl) return;

        // 等待 AudioMotionAnalyzer 全局类加载（script 动态加载时的保护）
        if (typeof AudioMotionAnalyzer === 'undefined') {
            setTimeout(startVisualizer, 200);
            return;
        }

        try {
            // 2. 初始化 audioMotion 实例（注意：此处不可直接传入未注册的 gradient 名称，必须使用默认值初始构建）
            audioMotion = new AudioMotionAnalyzer(null, {
                canvas: dom.visualizerCanvas,   // 复用现有 Canvas
                source: audioEl,                // 首次且唯一一次绑定 <audio> 元素
                connectSpeakers: true,          // 同时接通扬声器
                smoothing: 0.82,
                mode: 2,                        // 1/6 八度频段，柱状图密度与 YouTube 原版一致
                minFreq: 30,
                maxFreq: 11000,
                minDecibels: -70,               // 关键：适度抬高噪音门限，声音微弱或静默时高度绝对归零，无微弱冒头
                barSpace: 0.30,                 // 柱间距
                roundBars: false,               // 关键：平齐柱身，无凸出圆头，落下时与地面齐平并彻底消失
                showPeaks: false,               // 不显示浮动峰值帽
                fillAlpha: 0.82,                // 半透明柔顺度
                lineWidth: 0,
                showScaleX: false,
                showScaleY: false,
                showBgColor: false,             // 背景透明
                overlay: true,                  // 叠加在视频画卷之上
                reflexRatio: 0,                 // 无倒影
                mirror: 0,
                weightingFilter: 'D',           // D 加权，贴近人耳听觉感知
            });

            // 3. 构建成功后，注册并应用专有的 moody-white 半透明柔白渐变
            audioMotion.registerGradient('moody-white', {
                bgColor: 'transparent',
                colorStops: [
                    { pos: 0.0, color: 'rgba(255,255,255,0.85)' },
                    { pos: 0.5, color: 'rgba(255,255,255,0.55)' },
                    { pos: 1.0, color: 'rgba(255,255,255,0.10)' }
                ]
            });
            audioMotion.gradient = 'moody-white';

            // 启动渲染循环
            audioMotion.start();
            console.log('✓ [Visualizer] audioMotion-analyzer 已就绪并启动 (mode=2, flush-bars, moody-white)');
        } catch (err) {
            console.warn('[Visualizer] audioMotion-analyzer 初始化异常，启用无底点纯净兜底:', err);
            _startFallbackVisualizer();
        }
    }

    function stopVisualizer() {
        // 关键：退出屏保时仅停止渲染动画循环，保留 AudioContext 与 MediaElementSource，避免再次进入时 InvalidStateError
        if (audioMotion) {
            try { audioMotion.stop(); } catch (e) {}
        }
        // 彻底清空 Canvas，绝不残留任何柱身与微小头部
        if (dom.visualizerCanvas) {
            const ctx = dom.visualizerCanvas.getContext('2d');
            if (ctx) ctx.clearRect(0, 0, dom.visualizerCanvas.width, dom.visualizerCanvas.height);
        }
        // 清理 fallback 动画帧
        if (_fallbackAnimId) {
            cancelAnimationFrame(_fallbackAnimId);
            _fallbackAnimId = null;
        }
        _isFallbackRunning = false;
    }

    // ==================== Fallback 自绘频谱（仅在库加载异常时兜底，静默时绝对 0 绘制）====================
    let _audioCtxFallback = null;
    let _analyserFallback = null;
    let _freqDataFallback = null;
    let _fallbackAnimId = null;
    let _isFallbackRunning = false;
    let _smoothedHeights = new Float32Array(80);

    function _startFallbackVisualizer() {
        if (_isFallbackRunning) return;
        _isFallbackRunning = true;

        const audio = document.getElementById('audioPlayer');
        if (audio && !audio._sourceConnected) {
            try {
                const Ctx = window.AudioContext || window.webkitAudioContext;
                _audioCtxFallback = new Ctx();
                _analyserFallback = _audioCtxFallback.createAnalyser();
                _analyserFallback.fftSize = 512;
                _analyserFallback.smoothingTimeConstant = 0.82;
                const src = _audioCtxFallback.createMediaElementSource(audio);
                src.connect(_analyserFallback);
                _analyserFallback.connect(_audioCtxFallback.destination);
                audio._sourceConnected = true;
                _freqDataFallback = new Uint8Array(_analyserFallback.frequencyBinCount);
            } catch (e) {}
        }
        _renderFallback();
    }

    function _renderFallback() {
        if (!_isFallbackRunning) return;
        _fallbackAnimId = requestAnimationFrame(_renderFallback);

        const canvas = dom.visualizerCanvas;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const dpr = window.devicePixelRatio || 1;
        const W = canvas.width / dpr;
        const H = canvas.height / dpr;
        ctx.clearRect(0, 0, W, H);

        const audio = document.getElementById('audioPlayer');
        const playing = audio && !audio.paused && audio.currentTime > 0;

        // 核心要求：当没有音频播放、处于静默或未就绪时，彻底保持全透空白，绝对不画任何闲置虚线或多余小头部
        if (!playing || !_analyserFallback || !_freqDataFallback) {
            return;
        }

        _analyserFallback.getByteFrequencyData(_freqDataFallback);

        const BAR_N = 80, SPACING = 3;
        const totalSpacing = (BAR_N - 1) * SPACING;
        const bw = Math.max(2.5, (W - totalSpacing) / BAR_N);

        ctx.save();
        ctx.beginPath();
        ctx.rect(0, 0, W, H);
        ctx.clip();

        for (let i = 0; i < BAR_N; i++) {
            const p = i / (BAR_N - 1);
            const bin = Math.floor(Math.pow(p, 1.3) * Math.min(_freqDataFallback.length - 1, 210));
            const eq = 0.85 + Math.pow(p, 0.7) * 1.65;
            let val = (_freqDataFallback[bin] / 255) * eq;
            val = Math.pow(Math.min(val, 1), 1.5) * 1.35;
            let target = val > 0.04 ? Math.min(0.96, val) * H * 0.92 : 0;

            _smoothedHeights[i] += (target > _smoothedHeights[i])
                ? (target - _smoothedHeights[i]) * 0.4
                : (target - _smoothedHeights[i]) * 0.15;

            const bh = _smoothedHeights[i];
            // 关键：低于 2px 视为静默，完全不绘制，彻底消除地面残留微小头部
            if (bh < 2.0) continue;

            const x = i * (bw + SPACING);
            const y = H - bh;

            const grad = ctx.createLinearGradient(0, y, 0, H);
            grad.addColorStop(0, 'rgba(255,255,255,0.82)');
            grad.addColorStop(0.55, 'rgba(255,255,255,0.48)');
            grad.addColorStop(1, 'rgba(255,255,255,0.08)');
            ctx.fillStyle = grad;
            ctx.fillRect(x, y, bw, bh); // 平齐直柱
        }
        ctx.restore();
    }


    let zenTransitionTimer = null;
    let isTransitionActive = false;

    /**
     * 呈现沉浸屏保载入优雅过渡页（彻底消除黑屏等待）
     */
    function showZenTransition(scene, customTip) {
        if (!dom.zenTransitionOverlay || !scene) return;
        isTransitionActive = true;
        clearTimeout(zenTransitionTimer);

        if (dom.zenTransitionIcon) dom.zenTransitionIcon.textContent = scene.icon || '🌙';
        if (dom.zenTransitionTitle) dom.zenTransitionTitle.textContent = scene.name || '沉浸视听';
        if (dom.zenTransitionDesc) dom.zenTransitionDesc.textContent = scene.desc || '';
        if (dom.zenTransitionTip) dom.zenTransitionTip.textContent = customTip || '沉浸视听画卷载入中...';

        dom.zenTransitionOverlay.classList.add('active');

        // 安全兜底计时器：防止弱网或极端情况下视频加载超时卡住过渡页 (最长显示 2.5 秒后平滑揭开)
        zenTransitionTimer = setTimeout(() => {
            hideZenTransition();
        }, 2500);
    }

    /**
     * 隐去沉浸屏保载入过渡页
     */
    function hideZenTransition(immediate = false) {
        if (!dom.zenTransitionOverlay) return;
        isTransitionActive = false;
        clearTimeout(zenTransitionTimer);

        if (immediate) {
            dom.zenTransitionOverlay.classList.remove('active');
        } else {
            // 稍作微延迟平滑渐隐，保证视觉柔顺度
            setTimeout(() => {
                if (!isTransitionActive && dom.zenTransitionOverlay) {
                    dom.zenTransitionOverlay.classList.remove('active');
                }
            }, 80);
        }
    }

    /**
     * 进入 Zen Mode (黑胶沉浸屏保)
     */
    function enterZenMode() {
        if (isZenMode) return;
        isZenMode = true;
        document.body.classList.add('zen-active');
        closeSwitchMenu();

        const scene = AMBIENT_SCENES[currentSceneId];

        // 核心体验优化：在黑屏加载微动背景前，先唤出优雅过渡页，杜绝生硬黑屏
        if (scene && scene.id !== 'none') {
            const isVideoReady = dom.video && !dom.video.paused && dom.video.currentTime > 0.1 && dom.video.readyState >= 3;
            if (!isVideoReady) {
                showZenTransition(scene, '正在呈现沉浸画卷 · 步入禅意微光...');
            }
        }

        // 默认先浮现一次 HUD，4秒后隐去
        showZenHud(4000);

        // 同步当前曲目、封面、歌词与播放状态
        syncZenStateWithPlayer(true);

        // 唤醒微动画视频解码播放
        if (currentSceneId !== 'none' && dom.video && AMBIENT_SCENES[currentSceneId]?.type !== 'image') {
            dom.video.muted = true;
            dom.video.play().catch(() => {});
        }

        // 启动所有屏保场景通用的实时音频动态频谱图
        startVisualizer();
    }

    /**
     * 退出 Zen Mode
     */
    function exitZenMode() {
        if (!isZenMode) return;
        isZenMode = false;
        document.body.classList.remove('zen-active');
        clearTimeout(zenHudTimer);
        if (dom.zenOverlay) dom.zenOverlay.classList.remove('zen-show-hud');

        // 立即隐去载入过渡页
        hideZenTransition(true);

        // 退出屏保后，立即暂停微动画视频，释放 GPU/CPU
        if (dom.video) {
            dom.video.pause();
        }

        // 停止音频频谱渲染循环，释放 GPU/CPU
        stopVisualizer();

        // 退出后重新启动闲置计时器
        resetIdleTimer();
    }

    /**
     * 切换 Zen Mode
     */
    function toggleZenMode() {
        if (isZenMode) {
            exitZenMode();
        } else {
            enterZenMode();
        }
    }

    /**
     * 重置闲置计时器 (恢复为：仅当音乐【正在播放】时才触发屏保)
     */
    function resetIdleTimer() {
        clearTimeout(idleTimer);
        if (!autoZenEnabled || isZenMode) return;

        // 仅在音乐处于播放状态时，闲置计时才生效
        const audio = document.getElementById('audioPlayer');
        const isPlaying = audio && !audio.paused && window.playerState && window.playerState.isPlaying;
        if (!isPlaying) return;

        idleTimer = setTimeout(() => {
            const audioNow = document.getElementById('audioPlayer');
            const isPlayingNow = audioNow && !audioNow.paused && window.playerState && window.playerState.isPlaying;
            if (isPlayingNow && autoZenEnabled && !isZenMode) {
                console.log('[Zen Mode] 播放中闲置 30 秒，切入黑胶沉浸屏保');
                enterZenMode();
            }
        }, IDLE_TIMEOUT);
    }

    /**
     * 同步 Zen Mode 界面与播放器数据
     */
    function syncZenStateWithPlayer(forceLyricsRebuild = false) {
        const audio = document.getElementById('audioPlayer');
        const state = window.playerState || {};
        const isPlaying = audio && !audio.paused;

        // 1. 同步黑胶转动与唱针
        if (dom.zenVinylDisc) {
            dom.zenVinylDisc.classList.toggle('playing', isPlaying);
        }

        // 2. 同步播放/暂停按钮图标
        if (dom.zenPlayIcon && dom.zenPauseIcon) {
            dom.zenPlayIcon.style.display = isPlaying ? 'none' : 'block';
            dom.zenPauseIcon.style.display = isPlaying ? 'block' : 'none';
        }

        // 3. 同步封面
        const vCover = document.getElementById('vCover');
        const pThumb = document.getElementById('pThumb');
        let coverSrc = '';
        if (pThumb && pThumb.src && !pThumb.src.endsWith('/')) {
            coverSrc = pThumb.src;
        } else if (vCover && vCover.src && !vCover.src.endsWith('/') && vCover.style.display !== 'none') {
            coverSrc = vCover.src;
        }
        if (dom.zenVinylCover && coverSrc && dom.zenVinylCover.src !== coverSrc) {
            dom.zenVinylCover.src = coverSrc;
        }

        // 4. 同步歌曲信息
        const vTitle = document.getElementById('vTitle');
        const vMeta = document.getElementById('vMeta');
        const pTitleOverlay = document.getElementById('pTitleOverlay');

        let songTitle = 'MOODY';
        if (state.currentSong?.title) {
            songTitle = state.currentSong.title;
        } else if (pTitleOverlay && pTitleOverlay.textContent && pTitleOverlay.textContent !== 'No Track Playing') {
            songTitle = pTitleOverlay.textContent;
        } else if (vTitle && vTitle.textContent && vTitle.textContent !== 'Select Artist') {
            songTitle = vTitle.textContent;
        }

        // 仅显示歌名：剥离后缀 " - 歌手名" 以及可能携带的连字符
        if (songTitle.includes(' - ')) {
            songTitle = songTitle.split(' - ')[0].trim();
        } else if (songTitle.includes(' — ')) {
            songTitle = songTitle.split(' — ')[0].trim();
        }

        if (dom.zenTrackTitle) dom.zenTrackTitle.textContent = songTitle;

        // 5. 同步时间与进度条（拖动期间跳过，防止与拖拽视觉冲突）
        if (audio && audio.duration && !dom._zenProgressDragging?.()) {
            const cur = audio.currentTime || 0;
            const dur = audio.duration || 0;
            if (dom.zenCurrentTime) dom.zenCurrentTime.textContent = formatTime(cur);
            if (dom.zenDurationTime) dom.zenDurationTime.textContent = formatTime(dur);
            if (dom.zenProgressFill) dom.zenProgressFill.style.width = `${Math.min(100, (cur / dur) * 100)}%`;
        }

        // 6. 重构歌词列表
        const currentSrc = audio ? audio.src : '';
        if (forceLyricsRebuild || currentSrc !== lastTrackIdOrSrc) {
            lastTrackIdOrSrc = currentSrc;
            buildZenLyrics();
        }

        // 7. 高亮并滚动当前歌词行
        syncZenLyricsHighlight();
    }

    /**
     * 生成 Zen Mode 中的大歌词 DOM
     */
    function buildZenLyrics() {
        if (!dom.zenLyricsContainer) return;
        const lyricsSync = window.LyricsSync;
        if (!lyricsSync || !lyricsSync.currentLyrics || lyricsSync.currentLyrics.length === 0) {
            dom.zenLyricsContainer.innerHTML = '';
            if (dom.zenLyricsWrapper) dom.zenLyricsWrapper.style.display = 'none';
            return;
        }
        if (dom.zenLyricsWrapper) dom.zenLyricsWrapper.style.display = 'block';

        dom.zenLyricsContainer.innerHTML = lyricsSync.currentLyrics.map((line, idx) => `
            <div class="zen-lyric-line" data-index="${idx}" data-time="${line.time}">
                ${line.text}
            </div>
        `).join('');

        // 点击歌词跳转
        dom.zenLyricsContainer.querySelectorAll('.zen-lyric-line').forEach(lineEl => {
            lineEl.addEventListener('click', (e) => {
                e.stopPropagation();
                const targetTime = parseFloat(lineEl.getAttribute('data-time'));
                const audio = document.getElementById('audioPlayer');
                if (audio && !isNaN(targetTime)) {
                    audio.currentTime = targetTime;
                }
            });
        });
    }

    /**
     * 同步歌词高亮与平滑滚动
     */
    function syncZenLyricsHighlight() {
        if (!isZenMode || !dom.zenLyricsContainer) return;
        const lyricsSync = window.LyricsSync;
        if (!lyricsSync || !lyricsSync.currentLyrics) return;

        const activeIndex = lyricsSync.currentIndex;
        const lines = dom.zenLyricsContainer.querySelectorAll('.zen-lyric-line');
        if (lines.length === 0) return;

        let activeLine = null;
        lines.forEach((line, i) => {
            if (i === activeIndex) {
                line.classList.add('active');
                activeLine = line;
            } else {
                line.classList.remove('active');
            }
        });

        if (activeLine) {
            const container = dom.zenLyricsContainer;
            const containerHeight = container.offsetHeight;
            const lineTop = activeLine.offsetTop;
            const lineHeight = activeLine.offsetHeight;
            const targetScrollTop = lineTop - containerHeight / 2 + lineHeight / 2;

            container.scrollTo({
                top: targetScrollTop,
                behavior: 'smooth'
            });
        }
    }

    /**
     * 绑定各类用户与系统交互事件
     */
    function bindEvents() {
        // --- 1. 侧边栏底部 Dock 点击开关 ---
        if (dom.switchBtn) {
            dom.switchBtn.addEventListener('click', toggleSwitchMenu);
        }

        // 点击外部关闭菜单
        document.addEventListener('click', (e) => {
            if (dom.switchDock && !dom.switchDock.contains(e.target)) {
                closeSwitchMenu();
            }
        });

        // 菜单内立即进入屏保按钮
        if (dom.zenModeQuickBtn) {
            dom.zenModeQuickBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                enterZenMode();
            });
        }

        // 自动屏保复选框
        if (dom.autoZenCheck) {
            dom.autoZenCheck.addEventListener('change', (e) => {
                autoZenEnabled = e.target.checked;
                localStorage.setItem('moody_auto_zen', autoZenEnabled ? 'true' : 'false');
                resetIdleTimer();
            });
        }

        // --- 2. Zen Mode 退出按钮 ---
        if (dom.zenExitBtn) {
            dom.zenExitBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                exitZenMode();
            });
        }

        // --- 3. 点击 Zen 遮罩空白区域退出 ---
        if (dom.zenOverlay) {
            dom.zenOverlay.addEventListener('click', (e) => {
                if (e.target.closest('button') || e.target.closest('.zen-progress-bar') || e.target.closest('.zen-lyric-line') || e.target.closest('.zen-scene-pills')) {
                    return;
                }
                exitZenMode();
            });
        }

        // --- 4. Zen Mode 下的播放控制 ---
        if (dom.zenPlayPauseBtn) {
            dom.zenPlayPauseBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const playBtn = document.getElementById('playPauseBtn');
                if (playBtn) playBtn.click();
            });
        }
        if (dom.zenPrevBtn) {
            dom.zenPrevBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const prevBtn = document.getElementById('prevBtn');
                if (prevBtn) prevBtn.click();
            });
        }
        if (dom.zenNextBtn) {
            dom.zenNextBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const nextBtn = document.getElementById('nextBtn');
                if (nextBtn) nextBtn.click();
            });
        }

        // 进度条拖动/点击寻道（支持鼠标拖拽 + 触摸）
        if (dom.zenProgressBar) {
            let zenIsDragging = false;
            let zenSeekPercent = -1;

            // 用于计算位置的公共函数
            const calcZenPct = (clientX) => {
                const rect = dom.zenProgressBar.getBoundingClientRect();
                return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
            };

            // 拖动时实时更新进度条视觉
            const updateZenFill = (pct) => {
                if (dom.zenProgressFill) {
                    dom.zenProgressFill.style.width = `${pct * 100}%`;
                }
                const audio = document.getElementById('audioPlayer');
                if (audio && audio.duration && dom.zenCurrentTime) {
                    dom.zenCurrentTime.textContent = formatTime(pct * audio.duration);
                }
            };

            // --- 鼠标事件 ---
            dom.zenProgressBar.addEventListener('mousedown', (e) => {
                e.stopPropagation();
                e.preventDefault();
                zenIsDragging = true;
                zenSeekPercent = calcZenPct(e.clientX);
                updateZenFill(zenSeekPercent);
                document.body.style.userSelect = 'none';
            });

            document.addEventListener('mousemove', (e) => {
                if (zenIsDragging) {
                    zenSeekPercent = calcZenPct(e.clientX);
                    updateZenFill(zenSeekPercent);
                }
            });

            document.addEventListener('mouseup', () => {
                if (zenIsDragging) {
                    zenIsDragging = false;
                    document.body.style.userSelect = '';
                    const audio = document.getElementById('audioPlayer');
                    if (audio && audio.duration && zenSeekPercent >= 0) {
                        audio.currentTime = zenSeekPercent * audio.duration;
                    }
                    zenSeekPercent = -1;
                }
            });

            // --- 触摸事件 ---
            dom.zenProgressBar.addEventListener('touchstart', (e) => {
                e.stopPropagation();
                e.preventDefault();
                zenIsDragging = true;
                zenSeekPercent = calcZenPct(e.touches[0].clientX);
                updateZenFill(zenSeekPercent);
            }, { passive: false });

            document.addEventListener('touchmove', (e) => {
                if (zenIsDragging) {
                    zenSeekPercent = calcZenPct(e.touches[0].clientX);
                    updateZenFill(zenSeekPercent);
                }
            }, { passive: true });

            document.addEventListener('touchend', () => {
                if (zenIsDragging) {
                    zenIsDragging = false;
                    const audio = document.getElementById('audioPlayer');
                    if (audio && audio.duration && zenSeekPercent >= 0) {
                        audio.currentTime = zenSeekPercent * audio.duration;
                    }
                    zenSeekPercent = -1;
                }
            });

            // 将 zenIsDragging 挂到 dom 上，供 syncZenStateWithPlayer 检测
            dom._zenProgressDragging = () => zenIsDragging;
        }

        // --- 5. 全局键盘快捷键 ---
        document.addEventListener('keydown', (e) => {
            if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;

            // Z 或 z：一键切换屏保模式
            if (e.key === 'z' || e.key === 'Z') {
                e.preventDefault();
                toggleZenMode();
                return;
            }

            // Esc：如果在 Zen Mode，快速退出
            if (e.key === 'Escape' && isZenMode) {
                e.preventDefault();
                exitZenMode();
                return;
            }

            // 空格键：在 Zen Mode 下也可切换播放/暂停
            if (e.key === ' ' && isZenMode) {
                e.preventDefault();
                const playBtn = document.getElementById('playPauseBtn');
                if (playBtn) playBtn.click();
                showZenHud(3500);
            }
        });

        // --- 6. 用户闲置与鼠标移动探测 ---
        const handleUserActivity = () => {
            if (isZenMode) {
                showZenHud(3500);
            } else {
                resetIdleTimer();
            }
        };

        ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll'].forEach(evtName => {
            window.addEventListener(evtName, handleUserActivity, { passive: true });
        });

        // --- 7. 监听音频播放器事件 ---
        const audio = document.getElementById('audioPlayer');
        if (audio) {
            audio.addEventListener('play', () => {
                resetIdleTimer();
                if (audioMotion && audioMotion.audioCtx && audioMotion.audioCtx.state === 'suspended') {
                    audioMotion.audioCtx.resume().catch(() => {});
                }
                if (isZenMode) {
                    syncZenStateWithPlayer();
                    if (currentSceneId !== 'none' && dom.video) dom.video.play().catch(() => {});
                }
            });
            audio.addEventListener('pause', () => {
                clearTimeout(idleTimer);
                if (isZenMode) {
                    syncZenStateWithPlayer();
                }
            });
            audio.addEventListener('timeupdate', () => {
                if (isZenMode) {
                    syncZenStateWithPlayer();
                }
            });
            audio.addEventListener('ended', () => {
                if (isZenMode) {
                    syncZenStateWithPlayer();
                }
            });
        }

        // --- 8. 监听歌词异步加载完成事件，Zen 模式下立即重建歌词列表 ---
        // 解决：歌词通过网络异步加载时，切歌瞬间 buildZenLyrics() 检测到空歌词后隐藏区域，
        // 后续歌词加载完成却无人通知 Zen Mode 重绘的竞态问题。
        window.addEventListener('moody:lyricsLoaded', (e) => {
            if (isZenMode) {
                console.log(`[Zen Lyrics] 收到歌词加载完成通知 (source: ${e.detail?.source})，重建 Zen 歌词列表`);
                buildZenLyrics();
            }
        });

        // --- 9. 智能节电：浏览器后台 Tab 切换时暂停微动背景 ---
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (dom.video) dom.video.pause();
            } else {
                if (isZenMode && currentSceneId !== 'none' && dom.video && dom.video.paused) {
                    dom.video.play().catch(() => {});
                }
            }
        });

        // --- 9. AudioContext 唤醒 (audioMotion-analyzer 内部已处理 resize，此处只需唤醒 context) ---
        document.addEventListener('click', () => {
            if (audioMotion && audioMotion.audioCtx && audioMotion.audioCtx.state === 'suspended') {
                audioMotion.audioCtx.resume().catch(() => {});
            }
        });

        // 启动初始计时器
        resetIdleTimer();
    }

    // 页面就绪后自启动
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAmbientSystem);
    } else {
        initAmbientSystem();
    }

})();
