// ==========================================
// 专辑管理模块
// ==========================================
function initAlbumManager() {
    const API_BASE = window.MOODY_CONFIG?.API_BASE || window.API_BASE || 'https://m-api.changgepd.ccwu.cc';
    let currentAlbumId = null;
    let currentSongs = [];

    // 搜索专辑
    document.getElementById('btn-am-search').addEventListener('click', async () => {
        const keyword = document.getElementById('am-search-keyword').value.trim();
        if (!keyword) {
            showToast('请输入搜索关键词', 'error');
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/api/admin/albums/search?keyword=${encodeURIComponent(keyword)}&limit=20`);
            const data = await res.json();

            if (data.code === 200 && data.data.albums.length > 0) {
                displaySearchResults(data.data.albums);
            } else {
                document.getElementById('am-search-results').innerHTML = '<p class="hint">未找到匹配的专辑</p>';
            }
        } catch (e) {
            console.error(e);
            showToast('搜索失败', 'error');
        }
    });

    // 显示搜索结果
    function displaySearchResults(albums) {
        const html = albums.map(album => `
            <div class="album-item" style="padding: 10px; border: 1px solid #ddd; margin: 5px 0; cursor: pointer; border-radius: 4px;" data-album-id="${album.id}">
                <strong>${album.artist_name}</strong> - ${album.title} (${album.song_count || 0} 首)
            </div>
        `).join('');

        document.getElementById('am-search-results').innerHTML = html;

        // 绑定点击事件
        document.querySelectorAll('.album-item').forEach(item => {
            item.addEventListener('click', () => {
                loadAlbumDetail(item.dataset.albumId);
            });
        });
    }

    // 加载专辑详情
    async function loadAlbumDetail(albumId) {
        currentAlbumId = albumId;

        try {
            const res = await fetch(`${API_BASE}/api/admin/albums/detail?album_id=${albumId}`);
            const data = await res.json();

            if (data.code === 200) {
                displayAlbumDetail(data.data);
                document.getElementById('am-detail-card').classList.remove('hidden');
            } else {
                showToast('加载专辑详情失败', 'error');
            }
        } catch (e) {
            console.error(e);
            showToast('加载失败', 'error');
        }
    }

    // 显示专辑详情
    function displayAlbumDetail(data) {
        const { album, artist, songs } = data;

        // 显示专辑信息（包含封面图）
        const coverUrl = album?.cover_url 
            ? (album.cover_url.startsWith('http') ? album.cover_url : `${API_BASE}/storage/${album.cover_url}`)
            : '/src/assets/images/vinyl_default.png';

        document.getElementById('am-album-info').innerHTML = `
            <div style="display: flex; gap: 20px; align-items: flex-start; margin-bottom: 15px;">
                <div style="width: 120px; height: 120px; border-radius: 8px; overflow: hidden; background: #000; flex-shrink: 0; border: 1px solid #444;">
                    <img src="${coverUrl}" alt="Album Cover" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.src='/src/assets/images/vinyl_default.png'">
                </div>
                <div style="flex: 1; display: flex; flex-direction: column; gap: 6px;">
                    <p><strong>艺人:</strong> ${artist?.name || '未知'}</p>
                    <p><strong>专辑:</strong> ${album?.title || '未知'}</p>
                    <p><strong>发行年份:</strong> ${album?.release_date || '未知'}</p>
                    <p><strong>专辑 ID:</strong> ${album?.id}</p>
                    <p style="font-size: 12px; color: #aaa;"><strong>封面路径:</strong> ${album?.cover_url || '（未设置）'}</p>
                </div>
            </div>
        `;

        // 保存当前歌曲列表
        currentSongs = songs;

        // 显示歌曲列表
        displaySongsList(songs);
    }

    // 绑定更换封面事件
    const coverInput = document.getElementById('am-cover-input');
    if (coverInput) {
        coverInput.addEventListener('change', async () => {
            if (!currentAlbumId || !coverInput.files || coverInput.files.length === 0) return;
            if (window.MOODY_SAFETY_VALVE_ACTIVE) {
                showToast('🚨 存储安全阀已激活：三桶存储已处于只读保护，禁止写入新文件！', 'error');
                coverInput.value = '';
                return;
            }
            const file = coverInput.files[0];
            showToast('正在上传新封面到 Cloudflare R2...');

            const formData = new FormData();
            formData.append('file', file);
            formData.append('category', 'albums');
            formData.append('album_id', currentAlbumId);

            try {
                const res = await fetch(`${API_BASE}/api/admin/assets/upload`, {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.code === 200) {
                    showToast('✅ 封面上传并更新成功！');
                    loadAlbumDetail(currentAlbumId); // 刷新详情
                } else {
                    showToast(`上传失败: ${data.message}`, 'error');
                }
            } catch (e) {
                console.error(e);
                showToast('网络错误，请稍后重试', 'error');
            } finally {
                coverInput.value = '';
            }
        });
    }

    // 显示歌曲列表
    function displaySongsList(songs) {
        document.getElementById('am-song-count').textContent = songs.length;

        const html = songs.map(song => `
            <div class="song-item" style="padding: 8px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between;">
                <div>
                    <span style="color: #666; margin-right: 10px;">#${song.track_index || '-'}</span>
                    <strong>${song.title || '(无标题)'}</strong>
                </div>
                <div style="font-size: 12px; color: #999;">
                    ID: ${song.id} | ${song.file_path ? '✓ 有文件' : '✗ 无文件'}
                </div>
            </div>
        `).join('');

        document.getElementById('am-songs-list').innerHTML = html || '<p class="hint">暂无歌曲</p>';
    }

    // 清空所有歌曲
    document.getElementById('btn-am-clear-songs').addEventListener('click', async () => {
        if (!currentAlbumId) return;
        if (!confirm(`确认清空专辑 ${currentAlbumId} 下的所有歌曲？此操作不可恢复！`)) return;

        try {
            const res = await fetch(`${API_BASE}/api/admin/songs/delete-all`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ album_id: parseInt(currentAlbumId) })
            });

            const data = await res.json();

            if (data.code === 200) {
                showToast(data.message);
                loadAlbumDetail(currentAlbumId); // 重新加载
            } else {
                showToast('操作失败', 'error');
            }
        } catch (e) {
            console.error(e);
            showToast('网络异常', 'error');
        }
    });

    // 删除专辑
    document.getElementById('btn-am-delete-album').addEventListener('click', async () => {
        if (!currentAlbumId) return;
        if (!confirm(`确认删除专辑 ${currentAlbumId} 及其所有歌曲？此操作不可恢复！`)) return;

        try {
            const res = await fetch(`${API_BASE}/api/admin/albums/delete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ album_id: parseInt(currentAlbumId) })
            });

            const data = await res.json();

            if (data.code === 200) {
                showToast(data.message);
                document.getElementById('am-detail-card').classList.add('hidden');
                document.getElementById('am-search-results').innerHTML = '';
            } else {
                showToast('删除失败', 'error');
            }
        } catch (e) {
            console.error(e);
            showToast('网络异常', 'error');
        }
    });

    // 批量编辑歌曲
    document.getElementById('btn-am-batch-edit').addEventListener('click', () => {
        if (!currentSongs || currentSongs.length === 0) {
            showToast('当前专辑没有歌曲', 'error');
            return;
        }

        // 填充当前歌曲列表到文本框
        const text = currentSongs.map(song =>
            `${song.title || ''},${song.track_index || 0}`
        ).join('\n');

        document.getElementById('am-batch-data').value = text;
        document.getElementById('am-batch-edit-card').classList.remove('hidden');
    });

    // 取消批量编辑
    document.getElementById('btn-am-cancel-batch').addEventListener('click', () => {
        document.getElementById('am-batch-edit-card').classList.add('hidden');
    });

    // 保存批量编辑
    document.getElementById('btn-am-save-batch').addEventListener('click', async () => {
        if (!currentAlbumId) return;

        const text = document.getElementById('am-batch-data').value.trim();
        if (!text) {
            showToast('请输入歌曲列表', 'error');
            return;
        }

        // 解析文本
        const lines = text.split('\n');
        const updates = [];

        lines.forEach((line, index) => {
            const parts = line.split(',');
            if (parts.length >= 2) {
                const title = parts[0].trim();
                const trackIndex = parseInt(parts[1].trim());

                if (currentSongs[index]) {
                    updates.push({
                        id: currentSongs[index].id,
                        title: title,
                        track_index: trackIndex
                    });
                }
            }
        });

        if (updates.length === 0) {
            showToast('没有有效的更新数据', 'error');
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/api/admin/songs/batch-update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json; charset=utf-8' },
                body: JSON.stringify({ updates })
            });

            const data = await res.json();

            if (data.code === 200) {
                showToast(data.message);
                document.getElementById('am-batch-edit-card').classList.add('hidden');
                loadAlbumDetail(currentAlbumId); // 重新加载
            } else {
                showToast('保存失败', 'error');
            }
        } catch (e) {
            console.error(e);
            showToast('网络异常', 'error');
        }
    });
}
