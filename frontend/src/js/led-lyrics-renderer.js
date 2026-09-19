/**
 * MoodyMusic - 动态 LED 点阵歌词渲染引擎 (LedLyricsRenderer)
 * 
 * 核心原理：
 * 1. 采用离屏 Canvas 对歌词文本进行单线 16×16 中文字模光栅化；
 * 2. 提取像素有效点位建立高速坐标缓存（LRU）；
 * 3. 在目标 Canvas 上以独立圆形发光灯珠（LED Beads）绘制；
 * 4. 优化机制：高亮行实时渲染流光 (Karaoke 逐点流光点亮)，非激活行使用微暗灯珠颗粒感，仅在行切换时重绘。
 */

(function (window) {
    'use strict';

    const STORAGE_KEY = 'moodymusic_lyrics_led_mode';

    class LedLyricsRendererEngine {
        constructor() {
            // 状态开关 (默认关闭，用户可一键开启)
            this.enabled = localStorage.getItem(STORAGE_KEY) === 'true';

            // 样式与灯珠配置
            this.config = {
                fontFamily: '"SimHei", "Microsoft YaHei", "PingFang SC", sans-serif',
                fontSize: 16,             // 基础单线字模高度 (px)
                dotRadius: 1.0,           // 灯珠半径（缩小以适应歌词列表行高）
                dotStep: 2.8,             // 点阵网格步长（缩小至 2.8 px，字高约 16×2.8≈45px）
                activeColor: '#ffffff',   // 点亮灯珠颜色（纯正冷白）
                unlitColor: 'rgba(255, 255, 255, 0.20)', // 激活行未唱灯珠颜色
                inactiveLineColor: 'rgba(255, 255, 255, 0.28)', // 邻近/未播放行灯珠颜色
                glowColor: 'rgba(255, 255, 255, 0.85)',  // 辉光颜色
                glowBlur: 3.0,            // 辉光模糊半径（缩小配合小 step）
                minAlphaThreshold: 85     // 像素提取阈值 (0-255)
            };

            // 点阵坐标缓存: Map<text, { dots: Array<{x, y, alpha}>, width: number, height: number }>
            this.dotCache = new Map();
            this.maxCacheSize = 250;

            // 离屏光栅化画布
            this.offscreenCanvas = document.createElement('canvas');
            this.offscreenCtx = this.offscreenCanvas.getContext('2d', { willReadFrequently: true });

            // 跟踪记录当前高亮状态
            this.lastActiveIndex = -1;
            this.lastProgress = -1;

            console.log(`[LedLyricsRenderer] 引擎已构建，当前 LED 模式: ${this.enabled ? '已开启' : '关闭'}`);
        }

        /**
         * 切换 LED 模式开关
         */
        toggle() {
            this.enabled = !this.enabled;
            localStorage.setItem(STORAGE_KEY, this.enabled ? 'true' : 'false');
            this.updateContainersClass();
            this.updateButtonUI();

            // 刷新所有当前显示的歌词
            this.lastActiveIndex = -1;
            if (typeof window.highlightLyricLine === 'function' && window.LyricsSync) {
                window.highlightLyricLine(window.LyricsSync.currentIndex, 1.0);
            }
            return this.enabled;
        }

        /**
         * 获取当前是否开启
         */
        isEnabled() {
            return this.enabled;
        }

        /**
         * 更新页面容器的 class 标志
         */
        updateContainersClass() {
            const containers = [
                document.getElementById('albumLyrics'),
                document.getElementById('lyricsContent'),
                document.querySelector('.zen-lyrics-container')
            ];
            containers.forEach(el => {
                if (!el) return;
                if (this.enabled) {
                    el.classList.add('led-lyrics-active');
                } else {
                    el.classList.remove('led-lyrics-active');
                    // 隐藏其中的所有 canvas，恢复普通文字
                    el.querySelectorAll('.led-lyrics-canvas').forEach(c => c.style.display = 'none');
                    el.querySelectorAll('.lyric-text-normal').forEach(t => t.style.display = '');
                }
            });
        }

        /**
         * 更新切换按钮的高亮状态
         */
        updateButtonUI() {
            const buttons = document.querySelectorAll('.lyric-style-toggle-btn');
            buttons.forEach(btn => {
                if (this.enabled) {
                    btn.classList.add('active');
                    btn.setAttribute('title', '当前：复古 LED 点阵屏模式（点击切回常规字体）');
                } else {
                    btn.classList.remove('active');
                    btn.setAttribute('title', '当前：常规字体模式（点击开启复古 LED 点阵屏）');
                }
            });
        }

        /**
         * 获取或计算单行文本的点阵坐标阵列
         */
        getDotMatrix(text) {
            if (!text || typeof text !== 'string') return null;
            const cleanText = text.trim();
            if (!cleanText) return null;

            if (this.dotCache.has(cleanText)) {
                return this.dotCache.get(cleanText);
            }

            // 1. 设置离屏文字测量
            const fontSize = this.config.fontSize;
            this.offscreenCtx.font = `${fontSize}px ${this.config.fontFamily}`;
            const metrics = this.offscreenCtx.measureText(cleanText);
            const textWidth = Math.ceil(metrics.width);
            const textHeight = 22; // 16px 汉字垂直边界高度

            this.offscreenCanvas.width = textWidth + 8;
            this.offscreenCanvas.height = textHeight;

            // 2. 绘制纯白单线字模
            this.offscreenCtx.clearRect(0, 0, this.offscreenCanvas.width, textHeight);
            this.offscreenCtx.fillStyle = '#ffffff';
            this.offscreenCtx.font = `${fontSize}px ${this.config.fontFamily}`;
            this.offscreenCtx.textBaseline = 'middle';
            this.offscreenCtx.fillText(cleanText, 4, textHeight / 2);

            // 3. 提取有效像素点
            const imgData = this.offscreenCtx.getImageData(0, 0, this.offscreenCanvas.width, textHeight);
            const pixels = imgData.data;
            const dots = [];

            for (let y = 0; y < textHeight; y++) {
                for (let x = 0; x < this.offscreenCanvas.width; x++) {
                    const idx = (y * this.offscreenCanvas.width + x) * 4;
                    const alpha = pixels[idx + 3];
                    if (alpha > this.config.minAlphaThreshold) {
                        dots.push({
                            x: x,
                            y: y,
                            alpha: alpha / 255
                        });
                    }
                }
            }

            const matrixData = {
                dots: dots,
                width: this.offscreenCanvas.width,
                height: textHeight,
                charLength: cleanText.length
            };

            // LRU 缓存保护
            if (this.dotCache.size >= this.maxCacheSize) {
                const firstKey = this.dotCache.keys().next().value;
                this.dotCache.delete(firstKey);
            }
            this.dotCache.set(cleanText, matrixData);

            return matrixData;
        }

        /**
         * 渲染单行歌词至指定的 Canvas
         */
        renderLineCanvas(canvas, text, progress = 1.0, isCurrent = true) {
            if (!canvas) return;
            const matrix = this.getDotMatrix(text);
            if (!matrix || matrix.dots.length === 0) return;

            const ctx = canvas.getContext('2d');
            const dpr = window.devicePixelRatio || 1;

            // --- 自适应 step：根据父容器可用宽度缩小 step，确保文字不被截断 ---
            let step = this.config.dotStep;
            const rawCssW = matrix.width * step;

            const parentEl = canvas.parentElement;
            if (parentEl) {
                const availW = parentEl.clientWidth || parentEl.offsetWidth;
                if (availW > 20 && rawCssW > availW) {
                    // 按比例缩小 step，使整行文字恰好放进容器
                    step = step * (availW / rawCssW);
                }
            }

            // 用自适应 step 重新计算最终 CSS 尺寸
            const cssW = matrix.width * step;
            const cssH = matrix.height * step;
            // 灯珠半径也随 step 等比缩小（保持灯珠间隙感）
            const r = Math.min(this.config.dotRadius, step * 0.38);

            canvas.style.width  = `${cssW}px`;
            canvas.style.height = `${cssH}px`;

            // 保持高清屏点对点清晰度
            const targetW = Math.round(cssW * dpr);
            const targetH = Math.round(cssH * dpr);
            if (canvas.width !== targetW || canvas.height !== targetH) {
                canvas.width  = targetW;
                canvas.height = targetH;
            }

            ctx.save();
            ctx.scale(dpr, dpr);
            ctx.clearRect(0, 0, cssW, cssH);

            const activeThresholdX = matrix.width * Math.max(0, Math.min(1, progress));

            // 批量绘制点阵灯珠（使用自适应 step 计算坐标）
            for (let i = 0; i < matrix.dots.length; i++) {
                const dot = matrix.dots[i];
                const cx = dot.x * step + step / 2;
                const cy = dot.y * step + step / 2;

                const isLit = isCurrent ? (dot.x <= activeThresholdX) : false;

                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);

                if (isLit) {
                    // 当前行点亮状态 (带 LED 漫反射辉光)
                    if (this.config.glowBlur > 0) {
                        ctx.shadowColor = this.config.glowColor;
                        ctx.shadowBlur  = this.config.glowBlur;
                    }
                    ctx.fillStyle = this.config.activeColor;
                    ctx.fill();
                } else {
                    ctx.shadowColor = 'transparent';
                    ctx.shadowBlur  = 0;
                    ctx.fillStyle   = isCurrent ? this.config.unlitColor : this.config.inactiveLineColor;
                    ctx.fill();
                }
            }

            ctx.restore();
        }

        /**
         * 针对宿主元素（如 .ms-lyrics-item 或 .lyrics-line）挂载或更新其 LED Canvas
         */
        applyToElement(el, text, isCurrent, progress = 1.0) {
            if (!el) return;

            let canvas = el.querySelector('.led-lyrics-canvas');

            if (!this.enabled) {
                // 如果关闭了 LED 模式，隐藏 Canvas，恢复普通文本
                if (canvas) canvas.style.display = 'none';
                const textWrap = el.querySelector('.lyric-text-normal');
                if (textWrap) textWrap.style.display = '';
                return;
            }

            // 开启了 LED 模式：
            let textWrap = el.querySelector('.lyric-text-normal');
            if (!textWrap) {
                // 首次封装原有 DOM 子节点（如各 span.lyric-char）
                textWrap = document.createElement('span');
                textWrap.className = 'lyric-text-normal';
                while (el.firstChild) {
                    textWrap.appendChild(el.firstChild);
                }
                el.appendChild(textWrap);
            }
            textWrap.style.display = 'none';

            if (!canvas) {
                canvas = document.createElement('canvas');
                canvas.className = 'led-lyrics-canvas';
                el.appendChild(canvas);
            }
            canvas.style.display = 'inline-block';

            // 渲染点阵
            this.renderLineCanvas(canvas, text, progress, isCurrent);
        }

        /**
         * 同步容器所有行的高亮与点阵渲染
         * @param {HTMLElement} container 歌词列表容器
         * @param {number} currentIndex 当前高亮行索引
         * @param {number} progress 唱到第几个字或比例 (0.0 - 1.0)
         */
        syncContainer(container, currentIndex, progress = 1.0) {
            if (!container) return;
            if (!this.enabled) {
                // 如果未开启，清理并还原
                const canvases = container.querySelectorAll('.led-lyrics-canvas');
                canvases.forEach(c => c.style.display = 'none');
                const normals = container.querySelectorAll('.lyric-text-normal');
                normals.forEach(n => n.style.display = '');
                return;
            }

            const items = container.querySelectorAll('.ms-lyrics-item, .lyrics-line, .zen-lyric-line');
            if (items.length === 0) return;

            const isIndexChanged = (this.lastActiveIndex !== currentIndex);
            this.lastActiveIndex = currentIndex;
            this.lastProgress = progress;

            items.forEach((el, i) => {
                const text = el.dataset.text || el.textContent.trim();
                const isCurrent = (i === currentIndex);

                // 性能优化：只有在索引发生变动时才重绘全部非高亮行；如果只是 progress 变化，仅高亮行更新
                if (isCurrent) {
                    this.applyToElement(el, text, true, progress);
                } else if (isIndexChanged || !el.querySelector('.led-lyrics-canvas')) {
                    this.applyToElement(el, text, false, 0);
                }
            });
        }

        /**
         * 初始化挂载到页面各按钮及事件
         */
        init() {
            this.updateContainersClass();
            this.updateButtonUI();

            // 全局事件代理：支持任何时期动态渲染的 .lyric-style-toggle-btn 按钮
            document.addEventListener('click', (e) => {
                const btn = e.target.closest('.lyric-style-toggle-btn');
                if (btn) {
                    e.stopPropagation();
                    e.preventDefault();
                    this.toggle();
                }
            });

            console.log('[LedLyricsRenderer] 挂载就绪');
        }
    }

    // 单例导出
    window.LedLyricsRenderer = new LedLyricsRendererEngine();

})(window);
