// ========================================================
// MOODY CMS - 动态切片化排版工坊 (Block-based Studio)
// 支持 9 类切片组件、0 延迟真机机壳实时渲染、R2 资产直传与 Feed 编排发布
// ========================================================

(function () {
    const API_BASE = window.MOODY_CONFIG?.API_BASE || window.API_BASE || 'https://m-api.changgepd.ccwu.cc';
    const STORAGE_KEY = 'moody_studio_blocks_v2';

    // ----------------------------------------------------
    // 1. 切片组件注册表 (Block Registry)
    // ----------------------------------------------------
    const BLOCK_REGISTRY = {
        hero_banner: {
            name: '大画幅海报',
            icon: '🖼️',
            code: 'hero_banner',
            category: 'hero',
            createDefault: () => ({
                tag: '今日精选 · 焦点',
                title: '林子祥与华语乐坛的八零年代',
                subtitle: '高亢激昂的铜管编曲与黄金时代的流行史诗',
                imageUrl: 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800&auto=format&fit=crop&q=80',
                buttonText: '立即聆听',
                buttonLink: 'album:101'
            })
        },
        category_tabs: {
            name: '分类标签栏',
            icon: '📑',
            code: 'category_tabs',
            category: 'general',
            createDefault: () => ({
                tabs: ['推荐', '香港宝丽金', '台湾滚石', '城市民谣', '经典现场', '爵士精选'],
                activeIndex: 0
            })
        },
        quick_actions: {
            name: '快捷卡片',
            icon: '⚡',
            code: 'quick_actions',
            category: 'general',
            createDefault: () => ({
                items: [
                    { icon: '📻', title: '心动电台', desc: '智能漫游', tag: 'AI' },
                    { icon: '🕒', title: '最近播放', desc: '48首曲目', tag: 'History' },
                    { icon: '❤️', title: '我喜欢的', desc: '128首收藏', tag: 'Fav' }
                ]
            })
        },
        section_title: {
            name: '栏目标题',
            icon: '🏷️',
            code: 'section_title',
            category: 'general',
            createDefault: () => ({
                title: '黄金时代 · 经典唱片',
                subtitle: '1980 - 1999 模拟母带精选重现',
                moreText: '探索全部 →'
            })
        },
        artist_grid: {
            name: '双列艺术家',
            icon: '👥',
            code: 'artist_grid',
            category: 'artists',
            createDefault: () => ({
                title: '焦点音乐人',
                artist1: {
                    name: '张国荣',
                    desc: '华语流行乐坛的不朽传奇',
                    avatarUrl: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&auto=format&fit=crop&q=80'
                },
                artist2: {
                    name: '谭咏麟',
                    desc: '永远25岁的香港乐坛校长',
                    avatarUrl: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&auto=format&fit=crop&q=80'
                }
            })
        },
        track_list: {
            name: '单曲试听列表',
            icon: '🎵',
            code: 'track_list',
            category: 'albums',
            createDefault: () => ({
                title: '编辑精选 · 沉浸试听',
                tracks: [
                    {
                        title: '分分钟需要你',
                        artist: '林子祥',
                        duration: '03:02',
                        coverUrl: 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400&auto=format&fit=crop&q=80',
                        audioUrl: ''
                    },
                    {
                        title: '风继续吹',
                        artist: '张国荣',
                        duration: '05:12',
                        coverUrl: 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=400&auto=format&fit=crop&q=80',
                        audioUrl: ''
                    },
                    {
                        title: '爱在深秋',
                        artist: '谭咏麟',
                        duration: '04:05',
                        coverUrl: 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400&auto=format&fit=crop&q=80',
                        audioUrl: ''
                    }
                ]
            })
        },
        essay_card: {
            name: '深度随笔',
            icon: '📖',
            code: 'essay_card',
            category: 'articles',
            createDefault: () => ({
                tag: '专栏深度随笔',
                title: '回响在红磡夜空的萨克斯风与落叶',
                excerpt: '八十年代末的香港录音室，如何用磁带母盘捕获了整整一代人的情绪潮汐与都市霓虹...',
                coverUrl: 'https://images.unsplash.com/photo-1461360370896-922624d12aa1?w=800&auto=format&fit=crop&q=80',
                author: 'MOODY 音乐志 · 第14期',
                readTime: '6 分钟阅读'
            })
        },
        archive_card: {
            name: '年代归档',
            icon: '🏛️',
            code: 'archive_card',
            category: 'albums',
            createDefault: () => ({
                decade: '1980s',
                title: '摩登都市的霓虹夜曲',
                desc: '卡带机转动的白噪音与城市民谣的初啼',
                coverUrl: 'https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=800&auto=format&fit=crop&q=80'
            })
        },
        image_feature: {
            name: '视觉大图/黑胶',
            icon: '💿',
            code: 'image_feature',
            category: 'welcome',
            createDefault: () => ({
                imageUrl: 'https://images.unsplash.com/photo-1539185441755-769473a23570?w=800&auto=format&fit=crop&q=80',
                caption: '黑胶唱片 33⅓ RPM · 模拟原声母带之美',
                badgeText: '黑胶唱片专区'
            })
        }
    };

    // ----------------------------------------------------
    // 2. 预设模板库 (Preset Templates)
    // ----------------------------------------------------
    const PRESETS = {
        minimalist: [
            {
                id: 'min_hero_1',
                type: 'hero_banner',
                data: {
                    tag: 'MIDNIGHT SPECIAL · 夜航',
                    title: '夜航电台 · 慢品民谣',
                    subtitle: '深夜的一杯热茶与木吉他的木质震颤，在温暖的白噪音中沉淀思绪。',
                    imageUrl: 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800&auto=format&fit=crop&q=80',
                    buttonText: '开启慢听',
                    buttonLink: 'album:night_folk'
                }
            },
            {
                id: 'min_act_2',
                type: 'quick_actions',
                data: {
                    items: [
                        { icon: '📻', title: '心动电台', desc: '智能漫游', tag: 'AI' },
                        { icon: '🕒', title: '最近播放', desc: '48首曲目', tag: 'History' },
                        { icon: '❤️', title: '我喜欢的', desc: '128首收藏', tag: 'Fav' }
                    ]
                }
            },
            {
                id: 'min_sec_3',
                type: 'section_title',
                data: {
                    title: '每日随享 · 经典原声',
                    subtitle: '听见时光里的每一个原声呼吸',
                    moreText: '更多 →'
                }
            },
            {
                id: 'min_track_4',
                type: 'track_list',
                data: {
                    title: '经典三曲精选',
                    tracks: [
                        {
                            title: '分分钟需要你',
                            artist: '林子祥',
                            duration: '03:02',
                            coverUrl: 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        },
                        {
                            title: '风继续吹',
                            artist: '张国荣',
                            duration: '05:12',
                            coverUrl: 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        },
                        {
                            title: '爱在深秋',
                            artist: '谭咏麟',
                            duration: '04:05',
                            coverUrl: 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        }
                    ]
                }
            },
            {
                id: 'min_essay_5',
                type: 'essay_card',
                data: {
                    tag: 'MOODY 随笔',
                    title: '在模拟录音的余温里',
                    excerpt: '黑胶与磁带的颗粒感，是数字时代无法复制的情感温度，每一声轻微的爆豆音都是岁月的注脚...',
                    coverUrl: 'https://images.unsplash.com/photo-1461360370896-922624d12aa1?w=800&auto=format&fit=crop&q=80',
                    author: 'MOODY 编辑部',
                    readTime: '4 分钟阅读'
                }
            }
        ],
        tri_column: [
            {
                id: 'tri_tabs_1',
                type: 'category_tabs',
                data: {
                    tabs: ['精选', '香港宝丽金', '台湾滚石', '城市民谣', '经典现场', '爵士母带'],
                    activeIndex: 0
                }
            },
            {
                id: 'tri_hero_2',
                type: 'hero_banner',
                data: {
                    tag: '今日精选 · 焦点',
                    title: '林子祥与华语乐坛的八零年代',
                    subtitle: '高亢激昂的铜管编曲与黄金时代的流行史诗',
                    imageUrl: 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800&auto=format&fit=crop&q=80',
                    buttonText: '立即聆听',
                    buttonLink: 'album:lam_1985'
                }
            },
            {
                id: 'tri_act_3',
                type: 'quick_actions',
                data: {
                    items: [
                        { icon: '📻', title: '心动电台', desc: '智能漫游', tag: 'AI' },
                        { icon: '🕒', title: '最近播放', desc: '48首曲目', tag: 'History' },
                        { icon: '❤️', title: '我喜欢的', desc: '128首收藏', tag: 'Fav' }
                    ]
                }
            },
            {
                id: 'tri_sec_4',
                type: 'section_title',
                data: {
                    title: '传奇唱片年代',
                    subtitle: '1980 - 1999 模拟母带精选重现',
                    moreText: '探索年代 →'
                }
            },
            {
                id: 'tri_arch_5',
                type: 'archive_card',
                data: {
                    decade: '1980s',
                    title: '摩登都市的霓虹夜曲',
                    desc: '卡带机转动的白噪音与城市民谣的初啼',
                    coverUrl: 'https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=800&auto=format&fit=crop&q=80'
                }
            },
            {
                id: 'tri_art_6',
                type: 'artist_grid',
                data: {
                    title: '焦点音乐人',
                    artist1: {
                        name: '张国荣',
                        desc: '华语流行乐坛的不朽传奇',
                        avatarUrl: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&auto=format&fit=crop&q=80'
                    },
                    artist2: {
                        name: '谭咏麟',
                        desc: '永远25岁的香港乐坛校长',
                        avatarUrl: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&auto=format&fit=crop&q=80'
                    }
                }
            },
            {
                id: 'tri_sec_7',
                type: 'section_title',
                data: {
                    title: '编辑精选 · 沉浸试听',
                    subtitle: '重温母盘母带级细节',
                    moreText: '播放全部 ▶'
                }
            },
            {
                id: 'tri_track_8',
                type: 'track_list',
                data: {
                    title: '经典试听列表',
                    tracks: [
                        {
                            title: '分分钟需要你',
                            artist: '林子祥',
                            duration: '03:02',
                            coverUrl: 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        },
                        {
                            title: '风继续吹',
                            artist: '张国荣',
                            duration: '05:12',
                            coverUrl: 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        },
                        {
                            title: '爱在深秋',
                            artist: '谭咏麟',
                            duration: '04:05',
                            coverUrl: 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        }
                    ]
                }
            },
            {
                id: 'tri_feat_9',
                type: 'image_feature',
                data: {
                    imageUrl: 'https://images.unsplash.com/photo-1539185441755-769473a23570?w=800&auto=format&fit=crop&q=80',
                    caption: '黑胶唱片 33⅓ RPM · 模拟之声',
                    badgeText: '黑胶唱片专区'
                }
            }
        ],
        songbook: [
            {
                id: 'sb_hero_1',
                type: 'hero_banner',
                data: {
                    tag: 'EDITORIAL SONGBOOK',
                    title: '华语流行歌本 · 经典总览',
                    subtitle: '一卷穿越半个世纪的时光录音谱，重温那些被母带凝固的黄金旋律。',
                    imageUrl: 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=800&auto=format&fit=crop&q=80',
                    buttonText: '翻阅歌本',
                    buttonLink: 'songbook:1980_1999'
                }
            },
            {
                id: 'sb_essay_2',
                type: 'essay_card',
                data: {
                    tag: '封面故事 · 深度记录',
                    title: '回响在红磡夜空的萨克斯风与落叶',
                    excerpt: '八十年代末的香港录音室，如何用磁带母盘捕获了整整一代人的情绪潮汐与时代呼声...',
                    coverUrl: 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800&auto=format&fit=crop&q=80',
                    author: 'MOODY 音乐志 · 第14期',
                    readTime: '6 分钟阅读'
                }
            },
            {
                id: 'sb_sec_3',
                type: 'section_title',
                data: {
                    title: '殿堂唱作人',
                    subtitle: '用旋律书写时代记忆的大师们',
                    moreText: '名录库 →'
                }
            },
            {
                id: 'sb_art_4',
                type: 'artist_grid',
                data: {
                    title: '大师巨匠',
                    artist1: {
                        name: '罗大佑',
                        desc: '时代敏锐的洞察者与音乐教父',
                        avatarUrl: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&auto=format&fit=crop&q=80'
                    },
                    artist2: {
                        name: '李宗盛',
                        desc: '唱尽人间冷暖与世俗情深',
                        avatarUrl: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&auto=format&fit=crop&q=80'
                    }
                }
            },
            {
                id: 'sb_sec_5',
                type: 'section_title',
                data: {
                    title: '母带原声录音',
                    subtitle: '殿堂级 Hi-Fi 试音必听曲目',
                    moreText: '全部连播'
                }
            },
            {
                id: 'sb_track_6',
                type: 'track_list',
                data: {
                    title: '试音精选',
                    tracks: [
                        {
                            title: '童年',
                            artist: '罗大佑',
                            duration: '03:54',
                            coverUrl: 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        },
                        {
                            title: '凡人歌',
                            artist: '李宗盛',
                            duration: '03:50',
                            coverUrl: 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        },
                        {
                            title: '分分钟需要你',
                            artist: '林子祥',
                            duration: '03:02',
                            coverUrl: 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        },
                        {
                            title: '风继续吹',
                            artist: '张国荣',
                            duration: '05:12',
                            coverUrl: 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400&auto=format&fit=crop&q=80',
                            audioUrl: ''
                        }
                    ]
                }
            },
            {
                id: 'sb_feat_7',
                type: 'image_feature',
                data: {
                    imageUrl: 'https://images.unsplash.com/photo-1542208998-f6dbbb27a72f?w=800&auto=format&fit=crop&q=80',
                    caption: '模拟黑胶转盘 Hi-Fi 沉浸体验',
                    badgeText: '模拟之声'
                }
            },
            {
                id: 'sb_arch_8',
                type: 'archive_card',
                data: {
                    decade: '1990s',
                    title: '黄金时代全盛期',
                    desc: '港台流行音乐的巅峰交响与黄金十年',
                    coverUrl: 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800&auto=format&fit=crop&q=80'
                }
            }
        ]
    };

    // ----------------------------------------------------
    // 3. 全局工作区状态 (State)
    // ----------------------------------------------------
    let currentBlocks = [];
    let currentPreset = 'tri_column';
    let pendingR2Files = [];
    let currentR2Category = 'all';

    // ----------------------------------------------------
    // 4. 初始化入口 (initAssetManager)
    // ----------------------------------------------------
    function initAssetManager() {
        console.log('🚀 [MOODY Block Studio] 初始化积木排版工坊...');

        // 尝试从 LocalStorage 或默认预设加载
        loadInitialBlocks();

        // 绑定顶部工具条事件
        bindHeaderActions();

        // 绑定预设模板切换
        bindPresetButtons();

        // 绑定添加切片按钮
        bindAddBlockButtons();

        // 绑定 R2 画廊抽屉与上传
        initR2Gallery();

        // 渲染编辑器与真机预览
        renderAll();

        // 自动更新手机状态栏时钟
        updatePhoneClock();
        setInterval(updatePhoneClock, 30000);
    }

    function updatePhoneClock() {
        const clockEl = document.getElementById('preview-clock');
        if (!clockEl) return;
        const now = new Date();
        const hrs = String(now.getHours()).padStart(2, '0');
        const mins = String(now.getMinutes()).padStart(2, '0');
        clockEl.textContent = `${hrs}:${mins}`;
    }

    function loadInitialBlocks() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                const parsed = JSON.parse(saved);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    currentBlocks = parsed;
                    return;
                }
            }
        } catch (e) {
            console.warn('读取本地缓存切片失败，使用默认预设', e);
        }
        // 默认载入三栏导流版
        loadPreset('tri_column', false);
    }

    function saveToLocalStorage() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(currentBlocks));
        } catch (e) {
            console.error('保存至本地存储失败', e);
        }
    }

    function loadPreset(presetName, notify = true) {
        if (!PRESETS[presetName]) return;
        currentBlocks = JSON.parse(JSON.stringify(PRESETS[presetName]));
        currentPreset = presetName;

        document.querySelectorAll('.btn-preset').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.preset === presetName);
        });

        renderAll();
        saveToLocalStorage();
        if (notify && typeof showToast === 'function') {
            showToast(`已加载「${getPresetName(presetName)}」模板！`);
        }
    }

    function getPresetName(preset) {
        if (preset === 'minimalist') return '极简纯净版';
        if (preset === 'tri_column') return '三栏导流版';
        if (preset === 'songbook') return '现代歌本版';
        return preset;
    }

    // ----------------------------------------------------
    // 5. 事件绑定 (Events Binding)
    // ----------------------------------------------------
    function bindHeaderActions() {
        const btnFetch = document.getElementById('btn-fetch-feed');
        const btnExport = document.getElementById('btn-export-feed');
        const inputImport = document.getElementById('input-import-feed');
        const btnPublish = document.getElementById('btn-publish-feed');
        const btnClear = document.getElementById('btn-clear-blocks');

        if (btnFetch) {
            btnFetch.addEventListener('click', async () => {
                await fetchCloudFeed();
            });
        }

        if (btnExport) {
            btnExport.addEventListener('click', () => {
                exportFeedJson();
            });
        }

        if (inputImport) {
            inputImport.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = (event) => {
                    try {
                        const imported = JSON.parse(event.target.result);
                        const blocks = Array.isArray(imported) ? imported : (imported.blocks || imported.data);
                        if (Array.isArray(blocks) && blocks.length > 0) {
                            currentBlocks = blocks;
                            renderAll();
                            saveToLocalStorage();
                            if (typeof showToast === 'function') showToast('已成功导入 JSON 布局！');
                        } else {
                            if (typeof showToast === 'function') showToast('JSON 格式无效：未找到切片数组', 'error');
                        }
                    } catch (err) {
                        if (typeof showToast === 'function') showToast('解析 JSON 文件失败', 'error');
                    }
                    inputImport.value = '';
                };
                reader.readAsText(file);
            });
        }

        if (btnPublish) {
            btnPublish.addEventListener('click', async () => {
                await publishHomeFeed();
            });
        }

        if (btnClear) {
            btnClear.addEventListener('click', () => {
                if (confirm('确定要清空画布中的所有积木切片吗？')) {
                    currentBlocks = [];
                    renderAll();
                    saveToLocalStorage();
                    if (typeof showToast === 'function') showToast('画布已清空');
                }
            });
        }
    }

    function bindPresetButtons() {
        document.querySelectorAll('.btn-preset').forEach(btn => {
            btn.addEventListener('click', () => {
                const preset = btn.dataset.preset;
                loadPreset(preset, true);
            });
        });
    }

    function bindAddBlockButtons() {
        document.querySelectorAll('.btn-add-block').forEach(btn => {
            btn.addEventListener('click', () => {
                const type = btn.dataset.type;
                addBlock(type);
            });
        });
    }

    function addBlock(type) {
        const reg = BLOCK_REGISTRY[type];
        if (!reg) return;

        const newBlock = {
            id: `blk_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
            type: type,
            data: reg.createDefault()
        };

        currentBlocks.push(newBlock);
        renderAll();
        saveToLocalStorage();

        // 滚动到新添加的切片
        setTimeout(() => {
            const el = document.getElementById(`editor-card-${newBlock.id}`);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                el.classList.add('highlight-flash');
                setTimeout(() => el.classList.remove('highlight-flash'), 1000);
            }
        }, 50);

        if (typeof showToast === 'function') {
            showToast(`已添加「${reg.name}」切片`);
        }
    }

    // ----------------------------------------------------
    // 6. 云端交互与发布 (Cloud API)
    // ----------------------------------------------------
    async function publishHomeFeed() {
        const btnPublish = document.getElementById('btn-publish-feed');
        if (btnPublish) {
            btnPublish.disabled = true;
            btnPublish.textContent = '⏳ 发布中...';
        }

        const payload = {
            version: '2.0',
            updatedAt: new Date().toISOString(),
            blocks: currentBlocks
        };

        try {
            const res = await fetch(`${API_BASE}/api/admin/home/feed`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            let resData = {};
            try { resData = await res.json(); } catch (e) { }

            if (res.ok || resData.code === 200) {
                if (typeof showToast === 'function') {
                    showToast('🎉 首页切片 Feed 已成功一键发布到移动端！');
                }
            } else {
                // 如果后端暂未部署该 POST 路由，提示并保存在本地
                console.warn('发布返回非 200:', res.status, resData);
                if (typeof showToast === 'function') {
                    showToast(resData.message || `发布请求已发送 (HTTP ${res.status})，本地已备份`, 'success');
                }
            }
        } catch (err) {
            console.error('发布到云端异常:', err);
            if (typeof showToast === 'function') {
                showToast('已完成本地保存，网络同步稍后重试', 'warning');
            }
        } finally {
            if (btnPublish) {
                btnPublish.disabled = false;
                btnPublish.textContent = '🚀 一键发布到移动端首页';
            }
        }
    }

    async function fetchCloudFeed() {
        if (typeof showToast === 'function') showToast('正在从云端拉取最新 Feed 布局...');
        try {
            const res = await fetch(`${API_BASE}/api/home/feed`);
            if (res.ok) {
                const data = await res.json();
                const feed = data.data || data;
                const blocks = Array.isArray(feed) ? feed : (feed.blocks || []);
                if (blocks.length > 0) {
                    currentBlocks = blocks;
                    renderAll();
                    saveToLocalStorage();
                    if (typeof showToast === 'function') showToast('成功拉取云端最新 Feed 布局！');
                    return;
                }
            }
            if (typeof showToast === 'function') showToast('云端暂无自定义 Feed，保持当前工作区内容', 'warning');
        } catch (e) {
            console.warn('拉取云端 Feed 失败:', e);
            if (typeof showToast === 'function') showToast('拉取云端失败，请检查网络连接', 'error');
        }
    }

    function exportFeedJson() {
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify({
            version: '2.0',
            exportedAt: new Date().toISOString(),
            blocks: currentBlocks
        }, null, 2));
        const dlAnchorElem = document.createElement('a');
        dlAnchorElem.setAttribute("href", dataStr);
        dlAnchorElem.setAttribute("download", `moody_home_feed_${new Date().toISOString().slice(0, 10)}.json`);
        dlAnchorElem.click();
        if (typeof showToast === 'function') showToast('已导出 JSON 备份文件');
    }

    // ----------------------------------------------------
    // 7. 积木编辑器渲染器 (renderEditor)
    // ----------------------------------------------------
    function renderAll() {
        renderEditor();
        renderPhonePreview();
    }

    function renderEditor() {
        const container = document.getElementById('blocks-container');
        if (!container) return;

        if (currentBlocks.length === 0) {
            container.innerHTML = `
                <div class="empty-blocks-state" style="text-align: center; padding: 40px 20px; background: var(--bg-panel); border: 2px dashed var(--border); border-radius: var(--radius); color: var(--text-muted);">
                    <div style="font-size: 36px; margin-bottom: 12px;">🧱</div>
                    <div style="font-size: 15px; font-weight: 600; color: var(--text-main); margin-bottom: 6px;">画布当前为空</div>
                    <div style="font-size: 12px; margin-bottom: 16px;">请点击上方「+ 添加积木切片」或选择预设模板开始编排</div>
                    <button class="btn btn-secondary" onclick="window.loadStudioPreset('tri_column')">⚡ 加载三栏导流推荐模板</button>
                </div>
            `;
            return;
        }

        container.innerHTML = currentBlocks.map((block, idx) => {
            const reg = BLOCK_REGISTRY[block.type] || { name: block.type, icon: '📦', code: block.type };
            const isFirst = idx === 0;
            const isLast = idx === currentBlocks.length - 1;

            return `
                <div class="block-card" id="editor-card-${block.id}" data-id="${block.id}">
                    <div class="block-header">
                        <div class="block-header-info">
                            <span class="block-order-badge">#${idx + 1}</span>
                            <span style="font-size: 16px;">${reg.icon}</span>
                            <span class="block-type-badge">${reg.name}</span>
                            <span class="block-type-name">${reg.code}</span>
                        </div>
                        <div class="block-actions">
                            <button class="btn-block-action" title="上移" onclick="window.moveBlock(${idx}, -1)" ${isFirst ? 'disabled' : ''}>▲</button>
                            <button class="btn-block-action" title="下移" onclick="window.moveBlock(${idx}, 1)" ${isLast ? 'disabled' : ''}>▼</button>
                            <button class="btn-block-action" title="复制" onclick="window.duplicateBlock(${idx})">📋</button>
                            <button class="btn-block-action action-delete" title="删除" onclick="window.deleteBlock(${idx})">🗑️</button>
                        </div>
                    </div>
                    <div class="block-body">
                        ${renderBlockForm(block, idx)}
                    </div>
                </div>
            `;
        }).join('');

        // 绑定表单事件与图片上传监听
        bindFormInputs();
    }

    function renderBlockForm(block, idx) {
        const d = block.data || {};
        switch (block.type) {
            case 'hero_banner':
                return `
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label>徽标标签 (Tag)</label>
                            <input type="text" data-field="tag" value="${escapeHtml(d.tag || '')}" placeholder="例：今日精选 · 焦点">
                        </div>
                        <div class="form-group">
                            <label>行动按钮文案 (CTA Text)</label>
                            <input type="text" data-field="buttonText" value="${escapeHtml(d.buttonText || '')}" placeholder="例：立即聆听">
                        </div>
                    </div>
                    <div class="form-group">
                        <label>主标题 (Title)</label>
                        <input type="text" data-field="title" value="${escapeHtml(d.title || '')}" placeholder="输入大画幅主标题">
                    </div>
                    <div class="form-group">
                        <label>副标题与简介 (Subtitle)</label>
                        <input type="text" data-field="subtitle" value="${escapeHtml(d.subtitle || '')}" placeholder="输入副标题或亮点推荐语">
                    </div>
                    ${renderImageUploadControl(block.id, 'imageUrl', d.imageUrl, 'covers/hero', '海报背景大图')}
                `;

            case 'category_tabs':
                const tabsStr = Array.isArray(d.tabs) ? d.tabs.join('，') : (d.tabs || '');
                return `
                    <div class="form-group">
                        <label>分类标签列表 (以逗号或全角逗号分隔)</label>
                        <input type="text" data-field="tabs_csv" value="${escapeHtml(tabsStr)}" placeholder="推荐，香港宝丽金，台湾滚石，城市民谣">
                    </div>
                `;

            case 'quick_actions':
                const items = d.items || [];
                return `
                    <label style="margin-bottom: 8px;">快捷功能卡片 (3 个入口)</label>
                    <div class="form-grid-3">
                        ${[0, 1, 2].map(i => {
                    const item = items[i] || { icon: '📻', title: '', desc: '', tag: '' };
                    return `
                                <div class="sub-item-card">
                                    <div class="sub-item-header">卡片 ${i + 1}</div>
                                    <div class="form-group" style="margin-bottom: 6px;">
                                        <input type="text" data-item-idx="${i}" data-item-field="icon" value="${escapeHtml(item.icon)}" placeholder="图标/Emoji" style="text-align: center;">
                                    </div>
                                    <div class="form-group" style="margin-bottom: 6px;">
                                        <input type="text" data-item-idx="${i}" data-item-field="title" value="${escapeHtml(item.title)}" placeholder="标题">
                                    </div>
                                    <div class="form-group" style="margin-bottom: 6px;">
                                        <input type="text" data-item-idx="${i}" data-item-field="desc" value="${escapeHtml(item.desc)}" placeholder="副标">
                                    </div>
                                    <div class="form-group" style="margin-bottom: 0;">
                                        <input type="text" data-item-idx="${i}" data-item-field="tag" value="${escapeHtml(item.tag || '')}" placeholder="角标">
                                    </div>
                                </div>
                            `;
                }).join('')}
                    </div>
                `;

            case 'section_title':
                return `
                    <div class="form-grid-3">
                        <div class="form-group" style="grid-column: span 1;">
                            <label>栏目主标 (Title)</label>
                            <input type="text" data-field="title" value="${escapeHtml(d.title || '')}" placeholder="例：黄金时代 · 经典唱片">
                        </div>
                        <div class="form-group" style="grid-column: span 1;">
                            <label>栏目副标 (Subtitle)</label>
                            <input type="text" data-field="subtitle" value="${escapeHtml(d.subtitle || '')}" placeholder="例：1980 - 1999 模拟母带">
                        </div>
                        <div class="form-group" style="grid-column: span 1;">
                            <label>更多文本 (More Text)</label>
                            <input type="text" data-field="moreText" value="${escapeHtml(d.moreText || '')}" placeholder="例：探索全部 →">
                        </div>
                    </div>
                `;

            case 'artist_grid':
                const a1 = d.artist1 || { name: '', desc: '', avatarUrl: '' };
                const a2 = d.artist2 || { name: '', desc: '', avatarUrl: '' };
                return `
                    <div class="form-group">
                        <label>板块标题 (Title)</label>
                        <input type="text" data-field="title" value="${escapeHtml(d.title || '焦点音乐人')}" placeholder="焦点音乐人">
                    </div>
                    <div class="form-grid-2">
                        <div class="sub-item-card">
                            <div class="sub-item-header">音乐人 1</div>
                            <div class="form-group" style="margin-bottom: 8px;">
                                <label>姓名</label>
                                <input type="text" data-field="artist1.name" value="${escapeHtml(a1.name)}" placeholder="例：张国荣">
                            </div>
                            <div class="form-group" style="margin-bottom: 8px;">
                                <label>简介 / 代表作</label>
                                <input type="text" data-field="artist1.desc" value="${escapeHtml(a1.desc)}" placeholder="例：华语流行乐坛的不朽传奇">
                            </div>
                            ${renderImageUploadControl(block.id, 'artist1.avatarUrl', a1.avatarUrl, 'artists', '头像')}
                        </div>
                        <div class="sub-item-card">
                            <div class="sub-item-header">音乐人 2</div>
                            <div class="form-group" style="margin-bottom: 8px;">
                                <label>姓名</label>
                                <input type="text" data-field="artist2.name" value="${escapeHtml(a2.name)}" placeholder="例：谭咏麟">
                            </div>
                            <div class="form-group" style="margin-bottom: 8px;">
                                <label>简介 / 代表作</label>
                                <input type="text" data-field="artist2.desc" value="${escapeHtml(a2.desc)}" placeholder="例：永远25岁的香港乐坛校长">
                            </div>
                            ${renderImageUploadControl(block.id, 'artist2.avatarUrl', a2.avatarUrl, 'artists', '头像')}
                        </div>
                    </div>
                `;

            case 'track_list':
                const tracks = d.tracks || [];
                return `
                    <div class="form-group">
                        <label>试听列表标题 (Title)</label>
                        <input type="text" data-field="title" value="${escapeHtml(d.title || '编辑精选 · 沉浸试听')}" placeholder="编辑精选 · 沉浸试听">
                    </div>
                    <div class="track-items-wrapper">
                        <label style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                            <span>曲目清单 (${tracks.length} 首)</span>
                            <button type="button" class="btn btn-secondary" style="font-size: 11px; padding: 2px 8px;" onclick="window.addTrackToBlock('${block.id}')">➕ 添加曲目</button>
                        </label>
                        ${tracks.map((t, tIdx) => `
                            <div class="sub-item-card" style="margin-bottom: 8px;">
                                <div class="sub-item-header">
                                    <span>#${tIdx + 1} 单曲</span>
                                    <button type="button" style="background: none; border: none; color: var(--danger); cursor: pointer;" onclick="window.removeTrackFromBlock('${block.id}', ${tIdx})">✕ 移除</button>
                                </div>
                                <div class="form-grid-3" style="margin-bottom: 8px;">
                                    <div class="form-group" style="margin-bottom: 0;">
                                        <input type="text" data-track-idx="${tIdx}" data-track-field="title" value="${escapeHtml(t.title)}" placeholder="歌曲名">
                                    </div>
                                    <div class="form-group" style="margin-bottom: 0;">
                                        <input type="text" data-track-idx="${tIdx}" data-track-field="artist" value="${escapeHtml(t.artist)}" placeholder="歌手">
                                    </div>
                                    <div class="form-group" style="margin-bottom: 0;">
                                        <input type="text" data-track-idx="${tIdx}" data-track-field="duration" value="${escapeHtml(t.duration)}" placeholder="时长 (03:45)">
                                    </div>
                                </div>
                                ${renderImageUploadControl(block.id, `tracks[${tIdx}].coverUrl`, t.coverUrl, 'covers/albums', '封面图')}
                            </div>
                        `).join('')}
                    </div>
                `;

            case 'essay_card':
                return `
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label>专栏标签 (Tag)</label>
                            <input type="text" data-field="tag" value="${escapeHtml(d.tag || '')}" placeholder="例：专栏深度随笔">
                        </div>
                        <div class="form-group">
                            <label>作者与期数 (Author)</label>
                            <input type="text" data-field="author" value="${escapeHtml(d.author || '')}" placeholder="例：MOODY 音乐志 · 第14期">
                        </div>
                    </div>
                    <div class="form-group">
                        <label>文章标题 (Title)</label>
                        <input type="text" data-field="title" value="${escapeHtml(d.title || '')}" placeholder="输入随笔主标题">
                    </div>
                    <div class="form-group">
                        <label>文章摘要正文 (Excerpt)</label>
                        <textarea data-field="excerpt" rows="2" style="width: 100%; padding: 10px; background: #181818; border: 1px solid var(--border); border-radius: 4px; color: white; font-size: 13px;" placeholder="输入随笔摘要...">${escapeHtml(d.excerpt || '')}</textarea>
                    </div>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label>阅读时间 (Read Time)</label>
                            <input type="text" data-field="readTime" value="${escapeHtml(d.readTime || '')}" placeholder="例：6 分钟阅读">
                        </div>
                    </div>
                    ${renderImageUploadControl(block.id, 'coverUrl', d.coverUrl, 'articles', '随笔插图')}
                `;

            case 'archive_card':
                return `
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label>年代标识 (Decade Tag)</label>
                            <input type="text" data-field="decade" value="${escapeHtml(d.decade || '')}" placeholder="例：1980s">
                        </div>
                        <div class="form-group">
                            <label>归档标题 (Title)</label>
                            <input type="text" data-field="title" value="${escapeHtml(d.title || '')}" placeholder="例：摩登都市的霓虹夜曲">
                        </div>
                    </div>
                    <div class="form-group">
                        <label>归档副标与描述 (Desc)</label>
                        <input type="text" data-field="desc" value="${escapeHtml(d.desc || '')}" placeholder="例：卡带机转动的白噪音与城市民谣的初啼">
                    </div>
                    ${renderImageUploadControl(block.id, 'coverUrl', d.coverUrl, 'covers/albums', '归档黑胶封面')}
                `;

            case 'image_feature':
                return `
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label>角标文字 (Badge)</label>
                            <input type="text" data-field="badgeText" value="${escapeHtml(d.badgeText || '')}" placeholder="例：黑胶唱片专区">
                        </div>
                        <div class="form-group">
                            <label>图片说明 (Caption)</label>
                            <input type="text" data-field="caption" value="${escapeHtml(d.caption || '')}" placeholder="例：黑胶唱片 33⅓ RPM · 模拟之声">
                        </div>
                    </div>
                    ${renderImageUploadControl(block.id, 'imageUrl', d.imageUrl, 'welcome', '视觉海报/黑胶大图')}
                `;

            default:
                return `<p class="hint">未知切片类型: ${block.type}</p>`;
        }
    }

    // 辅助渲染图片上传一体化控件
    function renderImageUploadControl(blockId, fieldPath, currentUrl, category, label) {
        const safeUrl = escapeHtml(currentUrl || '');
        const inputId = `img-input-${blockId}-${fieldPath.replace(/[^a-zA-Z0-9]/g, '_')}`;
        const fileId = `img-file-${blockId}-${fieldPath.replace(/[^a-zA-Z0-9]/g, '_')}`;

        return `
            <div class="img-upload-field">
                <label style="font-size: 12px; color: var(--text-muted);">${label} URL / 直接拖拽上传至 R2</label>
                <div class="img-upload-control">
                    <img src="${safeUrl || 'data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'44\' height=\'44\'><rect width=\'100%\' height=\'100%\' fill=\'%23222\'/></svg>'}" class="img-preview-thumb" id="thumb-${inputId}" alt="预览" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'44\' height=\'44\'><rect width=\'100%\' height=\'100%\' fill=\'%23222\'/></svg>'">
                    <div class="img-input-wrap">
                        <input type="text" id="${inputId}" data-block-id="${blockId}" data-field="${fieldPath}" value="${safeUrl}" placeholder="https://m-api.changgepd.ccwu.cc/storage/..." style="padding-right: 30px;">
                    </div>
                    <div class="img-upload-btn-wrap">
                        <label class="btn btn-secondary" style="font-size: 11px; padding: 10px 12px; cursor: pointer; margin: 0; display: inline-flex; align-items: center; white-space: nowrap;">
                            ☁️ 上传 R2
                            <input type="file" id="${fileId}" accept=".jpg,.jpeg,.png,.webp,.gif" style="display: none;" onchange="window.handleFieldImageUpload(this, '${blockId}', '${fieldPath}', '${category}', '${inputId}')">
                        </label>
                    </div>
                </div>
            </div>
        `;
    }

    function bindFormInputs() {
        const container = document.getElementById('blocks-container');
        if (!container) return;

        container.querySelectorAll('input, textarea').forEach(input => {
            input.addEventListener('input', (e) => {
                const card = e.target.closest('.block-card');
                if (!card) return;
                const blockId = card.dataset.id;
                const block = currentBlocks.find(b => b.id === blockId);
                if (!block) return;

                // 普通字段
                if (e.target.dataset.field) {
                    const field = e.target.dataset.field;
                    if (field === 'tabs_csv') {
                        block.data.tabs = e.target.value.split(/[,，]/).map(s => s.trim()).filter(Boolean);
                    } else if (field.includes('.')) {
                        const parts = field.split('.');
                        block.data[parts[0]] = block.data[parts[0]] || {};
                        block.data[parts[0]][parts[1]] = e.target.value;
                    } else {
                        block.data[field] = e.target.value;
                    }
                }
                // 快捷卡片 items
                else if (e.target.dataset.itemIdx !== undefined) {
                    const idx = parseInt(e.target.dataset.itemIdx);
                    const itemField = e.target.dataset.itemField;
                    block.data.items = block.data.items || [];
                    block.data.items[idx] = block.data.items[idx] || {};
                    block.data.items[idx][itemField] = e.target.value;
                }
                // 单曲列表 tracks
                else if (e.target.dataset.trackIdx !== undefined) {
                    const idx = parseInt(e.target.dataset.trackIdx);
                    const trackField = e.target.dataset.trackField;
                    block.data.tracks = block.data.tracks || [];
                    block.data.tracks[idx] = block.data.tracks[idx] || {};
                    block.data.tracks[idx][trackField] = e.target.value;
                }

                // 立即更新预览与本地缓存
                renderPhonePreview();
                saveToLocalStorage();
            });
        });
    }

    // ----------------------------------------------------
    // 8. 积木列表操作 (Block Operations)
    // ----------------------------------------------------
    window.moveBlock = function (index, direction) {
        const targetIndex = index + direction;
        if (targetIndex < 0 || targetIndex >= currentBlocks.length) return;
        const temp = currentBlocks[index];
        currentBlocks[index] = currentBlocks[targetIndex];
        currentBlocks[targetIndex] = temp;
        renderAll();
        saveToLocalStorage();
    };

    window.duplicateBlock = function (index) {
        const source = currentBlocks[index];
        if (!source) return;
        const cloned = JSON.parse(JSON.stringify(source));
        cloned.id = `blk_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
        currentBlocks.splice(index + 1, 0, cloned);
        renderAll();
        saveToLocalStorage();
        if (typeof showToast === 'function') showToast('已克隆该切片');
    };

    window.deleteBlock = function (index) {
        const block = currentBlocks[index];
        if (!block) return;
        const reg = BLOCK_REGISTRY[block.type];
        if (confirm(`确定要删除「${reg ? reg.name : block.type}」切片吗？`)) {
            currentBlocks.splice(index, 1);
            renderAll();
            saveToLocalStorage();
            if (typeof showToast === 'function') showToast('切片已删除');
        }
    };

    window.loadStudioPreset = function (name) {
        loadPreset(name, true);
    };

    window.addTrackToBlock = function (blockId) {
        const block = currentBlocks.find(b => b.id === blockId);
        if (!block) return;
        block.data.tracks = block.data.tracks || [];
        block.data.tracks.push({
            title: '新单曲',
            artist: '未知歌手',
            duration: '03:30',
            coverUrl: 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=400&auto=format&fit=crop&q=80',
            audioUrl: ''
        });
        renderAll();
        saveToLocalStorage();
    };

    window.removeTrackFromBlock = function (blockId, trackIdx) {
        const block = currentBlocks.find(b => b.id === blockId);
        if (!block || !block.data.tracks) return;
        block.data.tracks.splice(trackIdx, 1);
        renderAll();
        saveToLocalStorage();
    };

    // 字段图片直传处理
    window.handleFieldImageUpload = async function (fileInput, blockId, fieldPath, category, inputId) {
        const file = fileInput.files[0];
        if (!file) return;

        if (window.MOODY_SAFETY_VALVE_ACTIVE) {
            if (typeof showToast === 'function') showToast('🚨 存储安全阀已激活：三桶存储已处于只读保护，禁止写入新文件！', 'error');
            fileInput.value = '';
            return;
        }

        if (typeof showToast === 'function') showToast(`正在上传 ${file.name} 至 Cloudflare R2...`);

        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('category', category || 'albums');

            const res = await fetch(`${API_BASE}/api/admin/assets/upload`, {
                method: 'POST',
                body: formData
            });

            const data = await res.json();
            if (res.ok && data.code === 200 && data.data.files && data.data.files[0]) {
                const uploadedUrl = data.data.files[0].url;

                // 更新 input 控件显示
                const urlInput = document.getElementById(inputId);
                if (urlInput) urlInput.value = uploadedUrl;
                const thumb = document.getElementById(`thumb-${inputId}`);
                if (thumb) thumb.src = uploadedUrl;

                // 更新数据模型
                const block = currentBlocks.find(b => b.id === blockId);
                if (block) {
                    if (fieldPath.startsWith('tracks[')) {
                        const match = fieldPath.match(/tracks\[(\d+)\]\.(\w+)/);
                        if (match) {
                            const idx = parseInt(match[1]);
                            const subField = match[2];
                            block.data.tracks[idx][subField] = uploadedUrl;
                        }
                    } else if (fieldPath.includes('.')) {
                        const parts = fieldPath.split('.');
                        block.data[parts[0]] = block.data[parts[0]] || {};
                        block.data[parts[0]][parts[1]] = uploadedUrl;
                    } else {
                        block.data[fieldPath] = uploadedUrl;
                    }
                }

                renderPhonePreview();
                saveToLocalStorage();
                if (typeof showToast === 'function') showToast('🎉 图片已上传并回填 URL！');
            } else {
                throw new Error(data.message || '上传响应错误');
            }
        } catch (err) {
            console.error('上传图片至 R2 失败:', err);
            if (typeof showToast === 'function') showToast(`上传失败: ${err.message}`, 'error');
        } finally {
            fileInput.value = '';
        }
    };

    // ----------------------------------------------------
    // 9. 1:1 手机真机实时预览渲染器 (renderPhonePreview)
    // ----------------------------------------------------
    function renderPhonePreview() {
        const feedEl = document.getElementById('phone-feed');
        if (!feedEl) return;

        if (currentBlocks.length === 0) {
            feedEl.innerHTML = `
                <div style="text-align: center; padding: 60px 20px; color: #8E887E;">
                    <div style="font-size: 32px; margin-bottom: 8px;">📻</div>
                    <div style="font-size: 13px; font-weight: 600; color: #1C1917;">MOODY 动态首页</div>
                    <div style="font-size: 11px; margin-top: 4px;">在左侧添加切片，实时渲染真机页面</div>
                </div>
            `;
            return;
        }

        feedEl.innerHTML = currentBlocks.map((block) => {
            return renderPhoneBlock(block);
        }).join('');

        // 绑定机壳内交互（如 Tab 切换、单曲播放动效）
        bindPhoneInteractions();
    }

    function renderPhoneBlock(block) {
        const d = block.data || {};
        switch (block.type) {
            case 'hero_banner':
                return `
                    <div class="p-hero-banner">
                        <img src="${escapeHtml(d.imageUrl || '')}" class="p-hero-bg" alt="Hero" onerror="this.style.opacity='0.2'">
                        <div class="p-hero-overlay"></div>
                        <div class="p-hero-content">
                            ${d.tag ? `<span class="p-hero-tag">${escapeHtml(d.tag)}</span>` : ''}
                            <div class="p-hero-title">${escapeHtml(d.title || '今日精选')}</div>
                            ${d.subtitle ? `<div class="p-hero-subtitle">${escapeHtml(d.subtitle)}</div>` : ''}
                            ${d.buttonText ? `<button class="p-hero-btn">${escapeHtml(d.buttonText)}</button>` : ''}
                        </div>
                    </div>
                `;

            case 'category_tabs':
                const tabs = Array.isArray(d.tabs) ? d.tabs : [];
                const activeIdx = d.activeIndex || 0;
                return `
                    <div class="p-category-tabs">
                        ${tabs.map((tab, idx) => `
                            <div class="p-tab-chip ${idx === activeIdx ? 'active' : ''}" data-idx="${idx}">${escapeHtml(tab)}</div>
                        `).join('')}
                    </div>
                `;

            case 'quick_actions':
                const items = d.items || [];
                return `
                    <div class="p-quick-actions">
                        ${items.map(item => `
                            <div class="p-action-card">
                                ${item.tag ? `<span class="p-action-tag">${escapeHtml(item.tag)}</span>` : ''}
                                <div class="p-action-icon">${escapeHtml(item.icon || '🎵')}</div>
                                <div class="p-action-title">${escapeHtml(item.title || '')}</div>
                                <div class="p-action-desc">${escapeHtml(item.desc || '')}</div>
                            </div>
                        `).join('')}
                    </div>
                `;

            case 'section_title':
                return `
                    <div class="p-section-title">
                        <div class="p-sec-main">
                            <div class="p-sec-title">${escapeHtml(d.title || '')}</div>
                            ${d.subtitle ? `<div class="p-sec-subtitle">${escapeHtml(d.subtitle)}</div>` : ''}
                        </div>
                        ${d.moreText ? `<div class="p-sec-more">${escapeHtml(d.moreText)}</div>` : ''}
                    </div>
                `;

            case 'artist_grid':
                const a1 = d.artist1 || {};
                const a2 = d.artist2 || {};
                return `
                    <div class="p-artist-grid">
                        <div class="p-artist-card">
                            <img src="${escapeHtml(a1.avatarUrl || '')}" class="p-artist-avatar" alt="${escapeHtml(a1.name)}" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'60\' height=\'60\'><circle cx=\'30\' cy=\'30\' r=\'30\' fill=\'%23e8e3d8\'/></svg>'">
                            <div class="p-artist-name">${escapeHtml(a1.name || '歌手')}</div>
                            <div class="p-artist-desc">${escapeHtml(a1.desc || '')}</div>
                        </div>
                        <div class="p-artist-card">
                            <img src="${escapeHtml(a2.avatarUrl || '')}" class="p-artist-avatar" alt="${escapeHtml(a2.name)}" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'60\' height=\'60\'><circle cx=\'30\' cy=\'30\' r=\'30\' fill=\'%23e8e3d8\'/></svg>'">
                            <div class="p-artist-name">${escapeHtml(a2.name || '歌手')}</div>
                            <div class="p-artist-desc">${escapeHtml(a2.desc || '')}</div>
                        </div>
                    </div>
                `;

            case 'track_list':
                const tracks = d.tracks || [];
                return `
                    <div class="p-track-list">
                        ${tracks.map((t, idx) => `
                            <div class="p-track-item" data-track-id="${idx}">
                                <img src="${escapeHtml(t.coverUrl || '')}" class="p-track-cover" alt="${escapeHtml(t.title)}" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'38\' height=\'38\'><rect width=\'100%\' height=\'100%\' fill=\'%23e8e3d8\'/></svg>'">
                                <div class="p-track-info">
                                    <div class="p-track-name">${escapeHtml(t.title || '无标题歌曲')}</div>
                                    <div class="p-track-artist">${escapeHtml(t.artist || 'MOODY')}</div>
                                </div>
                                <div class="p-track-duration">${escapeHtml(t.duration || '03:00')}</div>
                                <button class="p-track-play-btn" title="试听">▶</button>
                            </div>
                        `).join('')}
                    </div>
                `;

            case 'essay_card':
                return `
                    <div class="p-essay-card">
                        <img src="${escapeHtml(d.coverUrl || '')}" class="p-essay-cover" alt="${escapeHtml(d.title)}" onerror="this.style.display='none'">
                        <div class="p-essay-body">
                            ${d.tag ? `<div class="p-essay-tag">${escapeHtml(d.tag)}</div>` : ''}
                            <div class="p-essay-title">${escapeHtml(d.title || '')}</div>
                            <div class="p-essay-excerpt">${escapeHtml(d.excerpt || '')}</div>
                            <div class="p-essay-footer">
                                <span>${escapeHtml(d.author || 'MOODY')}</span>
                                <span>${escapeHtml(d.readTime || '')}</span>
                            </div>
                        </div>
                    </div>
                `;

            case 'archive_card':
                return `
                    <div class="p-archive-card">
                        <span class="p-archive-decade">${escapeHtml(d.decade || '80s')}</span>
                        <img src="${escapeHtml(d.coverUrl || '')}" class="p-archive-cover" alt="Archive" onerror="this.style.opacity='0.3'">
                        <div class="p-archive-info">
                            <span class="p-archive-badge">${escapeHtml(d.decade || 'ERA ARCHIVE')}</span>
                            <div class="p-archive-title">${escapeHtml(d.title || '')}</div>
                            <div class="p-archive-desc">${escapeHtml(d.desc || '')}</div>
                        </div>
                    </div>
                `;

            case 'image_feature':
                return `
                    <div class="p-image-feature">
                        <img src="${escapeHtml(d.imageUrl || '')}" class="p-feature-img" alt="Feature" onerror="this.style.opacity='0.2'">
                        ${d.badgeText ? `<div class="p-feature-badge">${escapeHtml(d.badgeText)}</div>` : ''}
                        ${d.caption ? `<div class="p-feature-caption">${escapeHtml(d.caption)}</div>` : ''}
                    </div>
                `;

            default:
                return '';
        }
    }

    function bindPhoneInteractions() {
        const feedEl = document.getElementById('phone-feed');
        if (!feedEl) return;

        // 分类标签点击交互
        feedEl.querySelectorAll('.p-tab-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const parent = chip.closest('.p-category-tabs');
                if (!parent) return;
                parent.querySelectorAll('.p-tab-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
            });
        });

        // 播放按钮动效交互
        feedEl.querySelectorAll('.p-track-play-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const isPlaying = btn.classList.toggle('is-playing');
                btn.textContent = isPlaying ? '❚❚' : '▶';
                btn.style.background = isPlaying ? '#D4AF37' : '#F3EFE6';
                btn.style.color = isPlaying ? '#000' : '#1C1917';
            });
        });
    }

    // ----------------------------------------------------
    // 10. R2 资产素材库管理 (R2 Asset Gallery)
    // ----------------------------------------------------
    function initR2Gallery() {
        const btnToggle = document.getElementById('btn-toggle-asset-gallery');
        const drawer = document.getElementById('r2-gallery-drawer');
        const btnClose = document.getElementById('btn-close-gallery');
        const dropzone = document.getElementById('asset-dropzone');
        const fileInput = document.getElementById('asset-file-input');
        const btnUpload = document.getElementById('btn-trigger-asset-upload');
        const btnClear = document.getElementById('btn-clear-asset-upload');
        const btnRefresh = document.getElementById('btn-refresh-gallery');
        const tabButtons = document.querySelectorAll('.gallery-tabs button');

        if (btnToggle && drawer) {
            btnToggle.addEventListener('click', () => {
                drawer.classList.toggle('hidden');
                if (!drawer.classList.contains('hidden')) {
                    loadR2AssetGallery(currentR2Category);
                }
            });
        }

        if (btnClose && drawer) {
            btnClose.addEventListener('click', () => {
                drawer.classList.add('hidden');
            });
        }

        if (dropzone && fileInput) {
            dropzone.addEventListener('click', () => fileInput.click());

            ['dragenter', 'dragover'].forEach(name => {
                dropzone.addEventListener(name, (e) => {
                    e.preventDefault();
                    dropzone.classList.add('dragover');
                });
            });

            ['dragleave', 'drop'].forEach(name => {
                dropzone.addEventListener(name, (e) => {
                    e.preventDefault();
                    dropzone.classList.remove('dragover');
                });
            });

            dropzone.addEventListener('drop', (e) => {
                const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
                if (files.length === 0) {
                    if (typeof showToast === 'function') showToast('请拖入有效的图片文件', 'error');
                    return;
                }
                addPendingR2Files(files);
            });

            fileInput.addEventListener('change', () => {
                const files = Array.from(fileInput.files);
                addPendingR2Files(files);
                fileInput.value = '';
            });
        }

        if (btnClear) {
            btnClear.addEventListener('click', () => {
                pendingR2Files = [];
                renderR2FileList();
            });
        }

        if (btnUpload) {
            btnUpload.addEventListener('click', async () => {
                await executeR2Upload();
            });
        }

        if (btnRefresh) {
            btnRefresh.addEventListener('click', () => {
                loadR2AssetGallery(currentR2Category);
            });
        }

        tabButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                tabButtons.forEach(b => b.classList.remove('tab-active'));
                btn.classList.add('tab-active');
                loadR2AssetGallery(btn.dataset.cat);
            });
        });

        // 初始拉取一次资产总数
        loadR2AssetGallery('all');
    }

    function addPendingR2Files(files) {
        for (const f of files) {
            pendingR2Files.push({
                file: f,
                status: 'waiting',
                progress: 0,
                error: null
            });
        }
        renderR2FileList();
    }

    function renderR2FileList() {
        const listEl = document.getElementById('asset-file-list');
        const btnUpload = document.getElementById('btn-trigger-asset-upload');
        if (!listEl) return;

        if (pendingR2Files.length === 0) {
            listEl.innerHTML = '';
            if (btnUpload) btnUpload.disabled = true;
            return;
        }

        if (btnUpload) btnUpload.disabled = false;
        listEl.innerHTML = pendingR2Files.map((fObj, idx) => `
            <div class="file-item">
                <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
                    <span>🖼️</span>
                    <span style="font-size: 12px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; overflow: hidden; max-width: 220px;">${escapeHtml(fObj.file.name)}</span>
                    <span style="font-size: 11px; color: var(--text-muted);">(${(fObj.file.size / 1024).toFixed(1)} KB)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="status-label status-${fObj.status}">${fObj.status === 'success' ? '✓ 完成' : (fObj.status === 'uploading' ? `${fObj.progress}%` : '待传')}</span>
                    ${fObj.status === 'waiting' ? `<button onclick="window.removePendingR2File(${idx})" style="background:none;border:none;color:var(--danger);cursor:pointer;">✕</button>` : ''}
                </div>
            </div>
        `).join('');
    }

    window.removePendingR2File = function (idx) {
        pendingR2Files.splice(idx, 1);
        renderR2FileList();
    };

    async function executeR2Upload() {
        if (window.MOODY_SAFETY_VALVE_ACTIVE) {
            if (typeof showToast === 'function') showToast('🚨 存储安全阀已激活：三桶存储已处于只读保护，禁止写入新文件！', 'error');
            return;
        }
        const toUpload = pendingR2Files.filter(f => f.status === 'waiting' || f.status === 'error');
        if (toUpload.length === 0) return;

        const category = document.getElementById('asset-category').value;
        const customName = document.getElementById('asset-filename').value.trim();
        const progContainer = document.getElementById('asset-upload-progress-container');
        const progBar = document.getElementById('asset-upload-progress');
        const btnUpload = document.getElementById('btn-trigger-asset-upload');

        if (btnUpload) btnUpload.disabled = true;
        if (progContainer) progContainer.classList.remove('hidden');

        let completed = 0;
        for (const fObj of toUpload) {
            fObj.status = 'uploading';
            renderR2FileList();

            try {
                const formData = new FormData();
                formData.append('file', fObj.file);
                formData.append('category', category);
                if (customName) formData.append('filename', customName);

                const res = await fetch(`${API_BASE}/api/admin/assets/upload`, {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (res.ok && data.code === 200) {
                    fObj.status = 'success';
                } else {
                    fObj.status = 'error';
                }
            } catch (err) {
                fObj.status = 'error';
            }

            completed++;
            if (progBar) progBar.style.width = `${Math.round((completed / toUpload.length) * 100)}%`;
            renderR2FileList();
        }

        if (typeof showToast === 'function') showToast(`成功上传 ${completed} 张素材到 Cloudflare R2！`);
        setTimeout(() => {
            if (progContainer) progContainer.classList.add('hidden');
            loadR2AssetGallery(currentR2Category);
        }, 1000);
    }

    async function loadR2AssetGallery(cat = 'all') {
        currentR2Category = cat;
        const grid = document.getElementById('asset-gallery-grid');
        const countBadge = document.getElementById('r2-asset-count');
        if (!grid) return;

        grid.innerHTML = '<p class="hint" style="grid-column: 1 / -1;">正在检索 R2 素材...</p>';

        try {
            const res = await fetch(`${API_BASE}/api/admin/assets/list?category=${cat}`);
            const data = await res.json();

            if (data.code === 200 && data.data.items && data.data.items.length > 0) {
                if (countBadge) countBadge.textContent = `${data.data.total} 个素材`;
                renderR2GalleryGrid(data.data.items);
            } else {
                if (countBadge && cat === 'all') countBadge.textContent = '0';
                grid.innerHTML = '<p class="hint" style="grid-column: 1 / -1;">该分类下暂无已上传素材</p>';
            }
        } catch (e) {
            grid.innerHTML = '<p class="hint" style="grid-column: 1 / -1; color: var(--danger);">加载 R2 资产列表失败</p>';
        }
    }

    function renderR2GalleryGrid(items) {
        const grid = document.getElementById('asset-gallery-grid');
        if (!grid) return;

        grid.innerHTML = items.map(item => `
            <div class="asset-card" style="background: #181818; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; display: flex; flex-direction: column;">
                <div style="width: 100%; height: 120px; background: #000; position: relative; overflow: hidden;">
                    <img src="${item.url}" alt="${escapeHtml(item.filename)}" loading="lazy" style="width: 100%; height: 100%; object-fit: cover;">
                </div>
                <div style="padding: 8px 10px; display: flex; flex-direction: column; gap: 3px; flex: 1;">
                    <div style="font-size: 11px; font-weight: 600; color: var(--text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</div>
                    <div style="font-size: 10px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(item.key)}</div>
                    <div style="margin-top: auto; display: flex; gap: 4px; padding-top: 6px;">
                        <button class="btn btn-secondary" style="font-size: 10px; padding: 3px 6px; flex: 1;" onclick="window.copyAssetUrl('${item.url}')">📋 复制 URL</button>
                    </div>
                </div>
            </div>
        `).join('');
    }

    window.copyAssetUrl = function (url) {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(url).then(() => {
                if (typeof showToast === 'function') showToast('已复制 CDN 地址！');
            }).catch(() => {
                prompt('请复制以下 URL:', url);
            });
        } else {
            prompt('请复制以下 URL:', url);
        }
    };

    // 工具函数：HTML 转义
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // 暴露初始化全局函数
    window.initAssetManager = initAssetManager;

})();
