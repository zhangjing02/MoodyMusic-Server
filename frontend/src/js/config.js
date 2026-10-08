/**
 * MOODY 全局前端配置中心 (Single Source of Truth)
 * 由 scripts/switch-domain.js 自动生成与维护
 */
(function() {
    // 优先直连高可用边缘网关 (https://moody-music-gateway.netlify.app)
    // 若需要调试本地 8787 端口的 Worker，可在 URL 后添加 ?env=local 或直接在 localhost 运行
    const urlParams = typeof window !== 'undefined' && window.location ? new URLSearchParams(window.location.search) : null;
    const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
    const isExplicitLocal = urlParams && urlParams.get('env') === 'local';

    const defaultApiBase = (isLocal || isExplicitLocal)
        ? 'http://127.0.0.1:8787'
        : 'https://moody-music-gateway.netlify.app';

    window.MOODY_CONFIG = {
        API_BASE: defaultApiBase,
        R2_BASE: 'https://pub-ade3407baf1041b49b5949a2539067f7.r2.dev'
    };
    window.API_BASE = window.MOODY_CONFIG.API_BASE;
})();
