/**
 * MOODY CMS - 留言与资源对齐管理模块 (Community & Resource Alignment)
 * 为开发者提供格式化专辑补齐申请与待办事项查询、一键状态流转与资产对齐管理
 */
(function() {
    const API_BASE = window.MOODY_CONFIG?.API_BASE || window.API_BASE || 'https://m-api.changgepd.ccwu.cc';
    let allPosts = [];
    let currentCategory = 'all';

    document.addEventListener('DOMContentLoaded', () => {
        initCommunityManager();
    });

    window.initCommunityManager = function() {
        const btnRefresh = document.getElementById('btn-cm-refresh');
        if (btnRefresh) {
            btnRefresh.addEventListener('click', async () => {
                btnRefresh.classList.add('loading');
                await loadCommunityPosts();
                setTimeout(() => btnRefresh.classList.remove('loading'), 500);
                if (typeof showToast === 'function') showToast('读者清单已刷新');
            });
        }

        // 分类筛选按钮点击事件
        const filterBtns = document.querySelectorAll('.cm-filter-btn');
        filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentCategory = btn.getAttribute('data-category') || 'all';
                renderCommunityList();
            });
        });

        // 监听侧边栏切换
        const navItem = document.querySelector('.nav-item[data-target="community-manager"]');
        if (navItem) {
            navItem.addEventListener('click', () => {
                loadCommunityPosts();
            });
        }

        // 初始加载一次
        loadCommunityPosts();
    };

    /**
     * 从后端加载全部帖子列表
     */
    async function loadCommunityPosts() {
        try {
            let res = await fetch(`${API_BASE}/api/admin/community/posts?t=${Date.now()}`);
            if (!res.ok) {
                res = await fetch(`${API_BASE}/api/community/posts?t=${Date.now()}`);
            }
            const data = await res.json();
            allPosts = data.data || [];
            updateCategoryCounts();
            renderCommunityList();
        } catch (e) {
            console.error('loadCommunityPosts error:', e);
            if (typeof showToast === 'function') showToast('获取读者留言列表失败', 'error');
        }
    }

    /**
     * 更新各分类计数
     */
    function updateCategoryCounts() {
        const counts = { all: allPosts.length, resource: 0, bug: 0, ui: 0, feature: 0, chat: 0 };
        allPosts.forEach(p => {
            if (counts[p.category] !== undefined) {
                counts[p.category]++;
            }
        });

        Object.keys(counts).forEach(k => {
            const el = document.getElementById(`cm-count-${k}`);
            if (el) el.textContent = counts[k];
        });
    }

    /**
     * 解析资源补齐内容 (尝试 JSON 或 文本键值对)
     */
    function parseResourceContent(content) {
        if (!content) return null;
        const trimmed = content.trim();
        if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
            try {
                const obj = JSON.parse(trimmed);
                if (obj.artist || obj.album) return obj;
            } catch (e) {}
        }

        // 文本解析兼容
        let artist = '', album = '', songs = '', year = '', desc = '';
        const lines = trimmed.split('\n');
        lines.forEach(l => {
            const line = l.trim();
            if (line.startsWith('歌手') || line.startsWith('艺人')) artist = line.replace(/^[^:：]+[:：]/, '').trim();
            else if (line.startsWith('专辑')) album = line.replace(/^[^:：]+[:：]/, '').trim();
            else if (line.startsWith('代表歌曲') || line.startsWith('歌曲') || line.startsWith('曲目')) songs = line.replace(/^[^:：]+[:：]/, '').trim();
            else if (line.startsWith('年份') || line.startsWith('发行年份')) year = line.replace(/^[^:：]+[:：]/, '').trim();
            else if (line.startsWith('介绍') || line.startsWith('专辑介绍') || line.startsWith('备注')) desc = line.replace(/^[^:：]+[:：]/, '').trim();
        });

        if (artist && album) {
            return { artist, album, songs, year, desc };
        }
        return null;
    }

    /**
     * 渲染主列表/表格
     */
    function renderCommunityList() {
        const container = document.getElementById('cm-list-container');
        const countSpan = document.getElementById('cm-current-count');
        if (!container) return;

        const filtered = currentCategory === 'all' 
            ? allPosts 
            : allPosts.filter(p => p.category === currentCategory);

        if (countSpan) countSpan.textContent = filtered.length;

        if (filtered.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 48px 16px; color: var(--text-muted);">
                    <div style="font-size: 32px; margin-bottom: 12px;">📭</div>
                    <div style="font-size: 15px; font-weight: 500; color: var(--text-primary);">暂无对应提报内容</div>
                    <div style="font-size: 13px; margin-top: 6px;">当读者在 App 留言板提交补齐需求或反馈时，将在此处实时归集</div>
                </div>
            `;
            return;
        }

        // 判断是否为纯资源补齐筛选，或是混排
        const isPureResource = currentCategory === 'resource';

        if (isPureResource) {
            renderResourceTable(container, filtered);
        } else {
            renderGenericTable(container, filtered);
        }
    }

    /**
     * 渲染专用的格式化专辑对齐数据表格
     */
    function renderResourceTable(container, list) {
        let html = `
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                    <thead>
                        <tr style="border-bottom: 1.5px solid var(--border-color); color: var(--text-muted); background: rgba(0,0,0,0.02);">
                            <th style="padding: 10px 12px; width: 105px;">待办状态</th>
                            <th style="padding: 10px 12px; width: 130px;">歌手 (Artist)</th>
                            <th style="padding: 10px 12px; width: 160px;">专辑名 (Album)</th>
                            <th style="padding: 10px 12px;">代表曲目</th>
                            <th style="padding: 10px 12px; width: 80px;">发行年份</th>
                            <th style="padding: 10px 12px; min-width: 180px;">说明 / 诉求</th>
                            <th style="padding: 10px 12px; width: 120px;">提报读者</th>
                            <th style="padding: 10px 12px; width: 110px; text-align: right;">操作</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        list.forEach(item => {
            const resData = parseResourceContent(item.content) || {
                artist: item.title.replace(/【专辑补齐】/, '').split('-')[0]?.trim() || '未知',
                album: item.title.split('-')[1]?.trim() || item.title,
                songs: '-',
                year: '-',
                desc: item.content
            };

            const isDone = item.status === 'completed';
            const statusBadge = getStatusBadge(item.status);

            html += `
                <tr style="border-bottom: 1px solid var(--border-color); ${isDone ? 'opacity: 0.65; background: rgba(46, 125, 50, 0.03);' : ''}" data-id="${item.id}">
                    <td style="padding: 12px;">
                        <button class="status-toggle-btn" data-id="${item.id}" data-status="${item.status}" style="background: none; border: none; cursor: pointer; padding: 0;" title="点击切换待办状态">
                            ${statusBadge}
                        </button>
                    </td>
                    <td style="padding: 12px; font-weight: 600; color: var(--text-primary);">
                        <span>${escapeHtml(resData.artist)}</span>
                        <a href="javascript:void(0)" class="btn-copy" data-text="${escapeHtml(resData.artist)}" title="点击复制歌手名" style="margin-left: 4px; font-size: 11px; text-decoration: none; opacity: 0.6;">📋</a>
                    </td>
                    <td style="padding: 12px; font-weight: 600; color: var(--accent);">
                        <span>《${escapeHtml(resData.album.replace(/[《》]/g, ''))}》</span>
                        <a href="javascript:void(0)" class="btn-copy" data-text="${escapeHtml(resData.album.replace(/[《》]/g, ''))}" title="点击复制专辑名" style="margin-left: 4px; font-size: 11px; text-decoration: none; opacity: 0.6;">📋</a>
                    </td>
                    <td style="padding: 12px; color: var(--text-secondary); max-width: 220px; word-break: break-all;">
                        ${escapeHtml(resData.songs || '-')}
                    </td>
                    <td style="padding: 12px; color: var(--text-muted);">
                        ${escapeHtml(resData.year || '-')}
                    </td>
                    <td style="padding: 12px; color: var(--text-secondary); max-width: 260px; line-height: 1.4;">
                        ${escapeHtml(resData.desc || '-')}
                    </td>
                    <td style="padding: 12px; color: var(--text-muted); font-size: 12px;">
                        <div>${escapeHtml(item.author_name)}</div>
                        <div style="font-size: 11px; opacity: 0.7;">${(item.created_at || '').slice(0, 10)}</div>
                    </td>
                    <td style="padding: 12px; text-align: right;">
                        <button class="btn btn-danger btn-delete-post" data-id="${item.id}" style="padding: 3px 8px; font-size: 11px;">删除</button>
                    </td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;
        container.innerHTML = html;
        bindTableEvents(container);
    }

    /**
     * 渲染全板块综合列表
     */
    function renderGenericTable(container, list) {
        let html = `
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                    <thead>
                        <tr style="border-bottom: 1.5px solid var(--border-color); color: var(--text-muted); background: rgba(0,0,0,0.02);">
                            <th style="padding: 10px 12px; width: 100px;">板块</th>
                            <th style="padding: 10px 12px; width: 105px;">待办状态</th>
                            <th style="padding: 10px 12px; width: 220px;">主题 / 标题</th>
                            <th style="padding: 10px 12px;">反馈详情 / 结构化内容</th>
                            <th style="padding: 10px 12px; width: 130px;">读者</th>
                            <th style="padding: 10px 12px; width: 90px; text-align: right;">操作</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        list.forEach(item => {
            const isDone = item.status === 'completed';
            const catBadge = getCategoryBadge(item.category);
            const statusBadge = getStatusBadge(item.status);
            const resData = item.category === 'resource' ? parseResourceContent(item.content) : null;

            let contentDisplay = '';
            if (resData) {
                contentDisplay = `
                    <div style="display: flex; gap: 8px; flex-wrap: wrap; font-size: 12px;">
                        <span style="background: rgba(108, 47, 0, 0.08); padding: 2px 6px; border-radius: 4px; color: var(--accent);">🎤 ${escapeHtml(resData.artist)}</span>
                        <span style="background: rgba(108, 47, 0, 0.08); padding: 2px 6px; border-radius: 4px; color: var(--accent);">💿 《${escapeHtml(resData.album)}》</span>
                        ${resData.songs ? `<span style="color: var(--text-muted);">🎵 ${escapeHtml(resData.songs)}</span>` : ''}
                        ${resData.year ? `<span style="color: var(--text-muted);">📅 ${escapeHtml(resData.year)}</span>` : ''}
                    </div>
                    ${resData.desc ? `<div style="margin-top: 4px; color: var(--text-secondary);">${escapeHtml(resData.desc)}</div>` : ''}
                `;
            } else {
                contentDisplay = `<div style="color: var(--text-secondary); line-height: 1.4; max-height: 4.2em; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(item.content)}</div>`;
            }

            html += `
                <tr style="border-bottom: 1px solid var(--border-color); ${isDone ? 'opacity: 0.65;' : ''}" data-id="${item.id}">
                    <td style="padding: 12px;">${catBadge}</td>
                    <td style="padding: 12px;">
                        <button class="status-toggle-btn" data-id="${item.id}" data-status="${item.status}" style="background: none; border: none; cursor: pointer; padding: 0;" title="点击切换待办状态">
                            ${statusBadge}
                        </button>
                    </td>
                    <td style="padding: 12px; font-weight: 600; color: var(--text-primary);">
                        ${escapeHtml(item.title)}
                    </td>
                    <td style="padding: 12px;">
                        ${contentDisplay}
                    </td>
                    <td style="padding: 12px; color: var(--text-muted); font-size: 12px;">
                        <div>${escapeHtml(item.author_name)}</div>
                        <div style="font-size: 11px; opacity: 0.7;">${(item.created_at || '').slice(0, 16)}</div>
                    </td>
                    <td style="padding: 12px; text-align: right;">
                        <button class="btn btn-danger btn-delete-post" data-id="${item.id}" style="padding: 3px 8px; font-size: 11px;">删除</button>
                    </td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;
        container.innerHTML = html;
        bindTableEvents(container);
    }

    /**
     * 绑定表格行内交互 (状态流转、一键复制、删除)
     */
    function bindTableEvents(container) {
        // 1. 状态一键流转
        container.querySelectorAll('.status-toggle-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.getAttribute('data-id');
                const currStatus = btn.getAttribute('data-status');
                // 循环切换: pending -> in_progress -> completed -> pending
                const nextStatus = currStatus === 'pending' ? 'in_progress' : (currStatus === 'in_progress' ? 'completed' : 'pending');
                await updatePostStatus(id, nextStatus);
            });
        });

        // 2. 复制文本
        container.querySelectorAll('.btn-copy').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const text = btn.getAttribute('data-text');
                if (text && navigator.clipboard) {
                    navigator.clipboard.writeText(text);
                    if (typeof showToast === 'function') showToast(`已复制: ${text}`);
                }
            });
        });

        // 3. 删除操作
        container.querySelectorAll('.btn-delete-post').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.getAttribute('data-id');
                if (!confirm(`确定要彻底删除此条留言/申请 (ID: ${id}) 吗？`)) return;
                await deletePost(id);
            });
        });
    }

    /**
     * 更新状态 API
     */
    async function updatePostStatus(id, status) {
        try {
            const res = await fetch(`${API_BASE}/api/admin/community/posts/${id}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status })
            });
            const data = await res.json();
            if (res.ok && data.code === 200) {
                const target = allPosts.find(p => p.id == id);
                if (target) target.status = status;
                renderCommunityList();
                const statusName = status === 'completed' ? '已完成' : (status === 'in_progress' ? '进行中' : '待处理');
                if (typeof showToast === 'function') showToast(`状态已切换为: ${statusName}`);
            } else {
                if (typeof showToast === 'function') showToast(data.message || '更新状态失败', 'error');
            }
        } catch (e) {
            if (typeof showToast === 'function') showToast('网络请求失败', 'error');
        }
    }

    /**
     * 删除帖子 API
     */
    async function deletePost(id) {
        try {
            const res = await fetch(`${API_BASE}/api/admin/community/posts/${id}`, {
                method: 'DELETE'
            });
            const data = await res.json();
            if (res.ok && data.code === 200) {
                allPosts = allPosts.filter(p => p.id != id);
                updateCategoryCounts();
                renderCommunityList();
                if (typeof showToast === 'function') showToast('已成功删除该条目');
            } else {
                if (typeof showToast === 'function') showToast(data.message || '删除失败', 'error');
            }
        } catch (e) {
            if (typeof showToast === 'function') showToast('网络请求失败', 'error');
        }
    }

    function getStatusBadge(status) {
        switch (status) {
            case 'completed':
                return '<span style="display: inline-flex; align-items: center; gap: 4px; background: #e8f5e9; color: #2e7d32; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">✓ 已完成</span>';
            case 'in_progress':
                return '<span style="display: inline-flex; align-items: center; gap: 4px; background: #fff3e0; color: #ef6c00; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">🔄 进行中</span>';
            default:
                return '<span style="display: inline-flex; align-items: center; gap: 4px; background: #eceff1; color: #546e7a; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">⏳ 待处理</span>';
        }
    }

    function getCategoryBadge(cat) {
        const map = {
            resource: { label: '💿 资源补齐', color: '#6C2F00', bg: 'rgba(108, 47, 0, 0.1)' },
            bug: { label: '🐛 Bug提示', color: '#c62828', bg: '#ffebee' },
            ui: { label: '🎨 页面优化', color: '#1565c0', bg: '#e3f2fd' },
            feature: { label: '💡 功能缺失', color: '#6a1b9a', bg: '#f3e5f5' },
            chat: { label: '💬 吐槽闲聊', color: '#37474f', bg: '#eceff1' }
        };
        const cfg = map[cat] || { label: cat, color: '#37474f', bg: '#eceff1' };
        return `<span style="background: ${cfg.bg}; color: ${cfg.color}; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600;">${cfg.label}</span>`;
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
})();
