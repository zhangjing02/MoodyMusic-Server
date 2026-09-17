/**
 * MOODY CMS - 官方系统公告管理模块 (Notice Manager)
 * 支持在线发布、编辑、置顶与删除系统公告，数据实时同步至 Cloudflare D1 与 Supabase，并即时推送到 Android 客户端。
 */
(function() {
    const API_BASE = window.MOODY_CONFIG?.API_BASE || window.API_BASE || 'https://m-api.changgepd.ccwu.cc';
    let currentNotices = [];
    let editingNoticeId = null;

    document.addEventListener('DOMContentLoaded', () => {
        initNoticeManager();
    });

    function initNoticeManager() {
        const btnSubmit = document.getElementById('btn-nm-submit');
        const btnReset = document.getElementById('btn-nm-reset');
        const btnRefresh = document.getElementById('btn-nm-refresh');

        const btnSubmitBottom = document.getElementById('btn-nm-submit-bottom');
        const btnResetBottom = document.getElementById('btn-nm-reset-bottom');

        if (btnSubmit) {
            btnSubmit.addEventListener('click', handleSubmitNotice);
        }
        if (btnSubmitBottom) {
            btnSubmitBottom.addEventListener('click', handleSubmitNotice);
        }

        if (btnReset) {
            btnReset.addEventListener('click', resetNoticeForm);
        }
        if (btnResetBottom) {
            btnResetBottom.addEventListener('click', resetNoticeForm);
        }

        // 实时字数统计
        const contentArea = document.getElementById('nm-content');
        const charCount = document.getElementById('nm-char-count');
        if (contentArea && charCount) {
            const updateCount = () => {
                charCount.textContent = (contentArea.value || '').length;
            };
            contentArea.addEventListener('input', updateCount);
            updateCount();
        }

        // 快捷插入工具条
        document.querySelectorAll('.nm-tool-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const insertText = btn.getAttribute('data-insert');
                if (!contentArea || !insertText) return;
                const start = contentArea.selectionStart || 0;
                const end = contentArea.selectionEnd || 0;
                const val = contentArea.value || '';
                contentArea.value = val.substring(0, start) + insertText + val.substring(end);
                contentArea.focus();
                const nextPos = start + insertText.length;
                contentArea.selectionStart = contentArea.selectionEnd = nextPos;
                if (charCount) charCount.textContent = contentArea.value.length;
            });
        });

        if (btnRefresh) {
            btnRefresh.addEventListener('click', async () => {
                btnRefresh.classList.add('loading');
                await loadNotices();
                setTimeout(() => btnRefresh.classList.remove('loading'), 500);
                if (typeof showToast === 'function') showToast('公告列表已刷新');
            });
        }

        const btnClearAll = document.getElementById('btn-nm-clear-all');
        if (btnClearAll) {
            btnClearAll.addEventListener('click', async () => {
                const confirmed = confirm('⚠️ 确定要一键清空所有系统公告、留言帖子与评论吗？\n清空后将完全变为空白状态，以便您测试自行添加新内容。');
                if (!confirmed) return;
                try {
                    const res = await fetch(`${API_BASE}/api/admin/community/clear-all`, { method: 'POST' });
                    const data = await res.json();
                    if (res.ok && data.code === 200) {
                        if (typeof showToast === 'function') showToast('🗑️ 所有公告与留言内容已全部清空！');
                        resetNoticeForm();
                        await loadNotices();
                    } else {
                        if (typeof showToast === 'function') showToast(data.message || '清空失败', 'error');
                    }
                } catch (e) {
                    if (typeof showToast === 'function') showToast('请求失败，请检查网络', 'error');
                }
            });
        }

        // 监听侧边栏切换到公告管理时的自动加载
        const navItem = document.querySelector('.nav-item[data-target="notice-manager"]');
        if (navItem) {
            navItem.addEventListener('click', () => {
                loadNotices();
            });
        }

        // 初始加载一次
        loadNotices();
    }

    /**
     * 从后端获取全部公告
     */
    async function loadNotices() {
        const listContainer = document.getElementById('nm-list');
        const countSpan = document.getElementById('nm-count');
        if (!listContainer) return;

        try {
            let res = await fetch(`${API_BASE}/api/admin/notices?t=${Date.now()}`);
            if (!res.ok) {
                // 兜底尝试公开只读接口
                res = await fetch(`${API_BASE}/api/notices?t=${Date.now()}`);
            }

            const data = await res.json();
            const notices = data.data || [];
            currentNotices = notices;

            if (countSpan) {
                countSpan.textContent = notices.length;
            }

            renderNoticeList(notices);
        } catch (err) {
            console.error('加载公告列表异常:', err);
            listContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--danger);">加载公告失败，请检查网络或后端接口状态</div>';
        }
    }

    /**
     * 渲染公告卡片列表
     */
    function renderNoticeList(notices) {
        const listContainer = document.getElementById('nm-list');
        if (!listContainer) return;

        if (!notices || notices.length === 0) {
            listContainer.innerHTML = `
                <div style="text-align:center; padding:40px 20px; color:var(--text-muted); background:rgba(255,255,255,0.02); border-radius:var(--radius); border:1px dashed var(--border);">
                    <div style="font-size:32px; margin-bottom:10px;">📢</div>
                    <div>暂无线上公告，可在上方表单中编写并发布第一条公告</div>
                </div>
            `;
            return;
        }

        listContainer.innerHTML = notices.map(item => {
            const isPinned = Boolean(item.is_pinned);
            const formattedTime = item.created_at ? item.created_at.replace('T', ' ').slice(0, 19) : '--';
            const isBeingEdited = editingNoticeId === item.id;

            return `
                <div class="notice-item-card ${isPinned ? 'pinned-card' : ''} ${isBeingEdited ? 'editing-highlight' : ''}" data-id="${item.id}" style="
                    background: ${isPinned ? 'linear-gradient(180deg, rgba(212, 175, 55, 0.08) 0%, rgba(38, 38, 38, 0.95) 100%)' : 'var(--bg-panel)'};
                    border: 1px solid ${isPinned ? 'rgba(212, 175, 55, 0.4)' : 'var(--border)'};
                    border-radius: var(--radius);
                    padding: 20px;
                    margin-bottom: 16px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
                    transition: all 0.2s ease;
                ">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px; gap:12px; flex-wrap:wrap;">
                        <div style="display:flex; align-items:center; gap:10px; flex:1; min-width:260px;">
                            ${isPinned ? '<span style="background:var(--accent); color:#000; font-size:11px; font-weight:700; padding:2px 8px; border-radius:4px;">📌 置顶推荐</span>' : '<span style="background:rgba(255,255,255,0.1); color:var(--text-muted); font-size:11px; padding:2px 8px; border-radius:4px;">普通公告</span>'}
                            <h4 style="font-size:16px; font-weight:600; color:var(--text-main); line-height:1.4;">${escapeHtml(item.title)}</h4>
                        </div>
                        <div style="font-size:12px; color:var(--text-muted); display:flex; align-items:center; gap:12px;">
                            <span>✍️ ${escapeHtml(item.author_name || '音信官方')}</span>
                            <span>🕒 ${formattedTime}</span>
                            <span style="opacity:0.6;">#${item.id}</span>
                        </div>
                    </div>

                    <div style="
                        font-size:14px;
                        color:#d1d1d6;
                        line-height:1.7;
                        white-space:pre-wrap;
                        background:rgba(0,0,0,0.2);
                        padding:14px 16px;
                        border-radius:6px;
                        margin-bottom:16px;
                        border-left:3px solid ${isPinned ? 'var(--accent)' : 'rgba(255,255,255,0.15)'};
                    ">${escapeHtml(item.content)}</div>

                    <div style="display:flex; justify-content:flex-end; align-items:center; gap:10px; border-top:1px solid rgba(255,255,255,0.06); padding-top:14px;">
                        <button class="btn btn-secondary btn-action-pin" data-id="${item.id}" data-pinned="${isPinned ? '1' : '0'}" style="font-size:12px; padding:6px 12px;">
                            ${isPinned ? '📍 取消置顶' : '📌 设为置顶'}
                        </button>
                        <button class="btn btn-warning btn-action-edit" data-id="${item.id}" style="font-size:12px; padding:6px 12px;">
                            ✏️ 编辑修改
                        </button>
                        <button class="btn btn-danger btn-action-del" data-id="${item.id}" data-title="${escapeHtml(item.title)}" style="font-size:12px; padding:6px 12px;">
                            🗑️ 删除
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        // 绑定按钮事件
        listContainer.querySelectorAll('.btn-action-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id, 10);
                startEditNotice(id);
            });
        });

        listContainer.querySelectorAll('.btn-action-pin').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id, 10);
                const isCurrentPinned = btn.dataset.pinned === '1';
                toggleNoticePin(id, !isCurrentPinned);
            });
        });

        listContainer.querySelectorAll('.btn-action-del').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id, 10);
                const title = btn.dataset.title || '';
                deleteNotice(id, title);
            });
        });
    }

    /**
     * 进入编辑模式
     */
    function startEditNotice(id) {
        const notice = currentNotices.find(n => n.id === id);
        if (!notice) return;

        editingNoticeId = id;
        document.getElementById('nm-notice-id').value = notice.id;
        document.getElementById('nm-title').value = notice.title;
        document.getElementById('nm-author').value = notice.author_name || '音信官方';
        document.getElementById('nm-pinned').checked = Boolean(notice.is_pinned);
        document.getElementById('nm-content').value = notice.content;

        const modeBadge = document.getElementById('nm-form-mode');
        if (modeBadge) {
            modeBadge.textContent = `编辑中 (#${notice.id})`;
            modeBadge.style.background = 'var(--warning)';
            modeBadge.style.color = '#000';
        }

        const btnSubmit = document.getElementById('btn-nm-submit');
        const btnSubmitBottom = document.getElementById('btn-nm-submit-bottom');
        if (btnSubmit) {
            btnSubmit.textContent = '💾 保存修改并同步';
            btnSubmit.className = 'btn btn-warning';
        }
        if (btnSubmitBottom) {
            btnSubmitBottom.textContent = '💾 保存修改并同步';
            btnSubmitBottom.className = 'btn btn-warning';
        }

        const charCount = document.getElementById('nm-char-count');
        if (charCount) {
            charCount.textContent = (notice.content || '').length;
        }

        const formCard = document.getElementById('nm-form-card');
        if (formCard) {
            formCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        renderNoticeList(currentNotices);
        if (typeof showToast === 'function') showToast(`已加载公告 #${id} 到编辑框`);
    }

    /**
     * 重置表单
     */
    function resetNoticeForm() {
        editingNoticeId = null;
        const idInput = document.getElementById('nm-notice-id');
        if (idInput) idInput.value = '';

        document.getElementById('nm-title').value = '';
        document.getElementById('nm-author').value = '音信官方';
        document.getElementById('nm-pinned').checked = false;
        document.getElementById('nm-content').value = '';

        const modeBadge = document.getElementById('nm-form-mode');
        if (modeBadge) {
            modeBadge.textContent = '新增模式';
            modeBadge.style.background = 'var(--accent)';
            modeBadge.style.color = '#000';
        }

        const btnSubmit = document.getElementById('btn-nm-submit');
        const btnSubmitBottom = document.getElementById('btn-nm-submit-bottom');
        if (btnSubmit) {
            btnSubmit.textContent = '🚀 立即发布到 App';
            btnSubmit.className = 'btn btn-primary';
        }
        if (btnSubmitBottom) {
            btnSubmitBottom.textContent = '🚀 立即发布到 App';
            btnSubmitBottom.className = 'btn btn-primary';
        }

        const charCount = document.getElementById('nm-char-count');
        if (charCount) {
            charCount.textContent = '0';
        }

        renderNoticeList(currentNotices);
    }

    /**
     * 提交表单 (新增或更新)
     */
    async function handleSubmitNotice() {
        const title = (document.getElementById('nm-title')?.value || '').trim();
        const author = (document.getElementById('nm-author')?.value || '').trim() || '音信官方';
        const isPinned = document.getElementById('nm-pinned')?.checked || false;
        const content = (document.getElementById('nm-content')?.value || '').trim();
        const noticeId = document.getElementById('nm-notice-id')?.value;

        if (!title) {
            if (typeof showToast === 'function') showToast('请填写公告标题', 'error');
            document.getElementById('nm-title')?.focus();
            return;
        }

        if (!content) {
            if (typeof showToast === 'function') showToast('请填写公告详细内容', 'error');
            document.getElementById('nm-content')?.focus();
            return;
        }

        const btnSubmit = document.getElementById('btn-nm-submit');
        const btnSubmitBottom = document.getElementById('btn-nm-submit-bottom');
        if (btnSubmit) {
            btnSubmit.disabled = true;
            btnSubmit.textContent = '⏳ 同步中...';
        }
        if (btnSubmitBottom) {
            btnSubmitBottom.disabled = true;
            btnSubmitBottom.textContent = '⏳ 同步中...';
        }

        const payload = {
            title,
            author_name: author,
            is_pinned: isPinned,
            content
        };

        try {
            const isEditing = Boolean(noticeId);
            const url = isEditing
                ? `${API_BASE}/api/admin/notices/${noticeId}`
                : `${API_BASE}/api/admin/notices`;
            const method = isEditing ? 'PUT' : 'POST';

            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (res.ok && data.code === 200) {
                if (typeof showToast === 'function') {
                    showToast(isEditing ? '✅ 公告修改已保存并同步！' : '🎉 公告发布成功，App 已实时生效！');
                }
                resetNoticeForm();
                await loadNotices();
            } else {
                if (typeof showToast === 'function') {
                    showToast(data.message || '操作失败', 'error');
                }
            }
        } catch (err) {
            console.error('提交公告失败:', err);
            if (typeof showToast === 'function') showToast('网络异常，请重试', 'error');
        } finally {
            if (btnSubmit) {
                btnSubmit.disabled = false;
                btnSubmit.textContent = noticeId ? '💾 保存修改并同步' : '🚀 立即发布到 App';
            }
            if (btnSubmitBottom) {
                btnSubmitBottom.disabled = false;
                btnSubmitBottom.textContent = noticeId ? '💾 保存修改并同步' : '🚀 立即发布到 App';
            }
        }
    }

    /**
     * 快速置顶/取消置顶
     */
    async function toggleNoticePin(id, newPinState) {
        try {
            const res = await fetch(`${API_BASE}/api/admin/notices/${id}/pin`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_pinned: newPinState ? 1 : 0 })
            });

            const data = await res.json();
            if (res.ok && data.code === 200) {
                if (typeof showToast === 'function') {
                    showToast(newPinState ? '📌 公告已置顶展示' : '📍 公告已取消置顶');
                }
                await loadNotices();
            } else {
                if (typeof showToast === 'function') showToast(data.message || '更新置顶状态失败', 'error');
            }
        } catch (e) {
            if (typeof showToast === 'function') showToast('请求失败', 'error');
        }
    }

    /**
     * 删除公告
     */
    async function deleteNotice(id, title) {
        const confirmed = confirm(`确定要彻底删除公告《${title}》吗？\n删除后 Android 客户端将同步下线此公告。`);
        if (!confirmed) return;

        try {
            const res = await fetch(`${API_BASE}/api/admin/notices/${id}`, {
                method: 'DELETE'
            });

            const data = await res.json();
            if (res.ok && data.code === 200) {
                if (typeof showToast === 'function') showToast('🗑️ 公告已删除并同步下线');
                if (editingNoticeId === id) {
                    resetNoticeForm();
                }
                await loadNotices();
            } else {
                if (typeof showToast === 'function') showToast(data.message || '删除失败', 'error');
            }
        } catch (e) {
            if (typeof showToast === 'function') showToast('网络异常', 'error');
        }
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
})();
