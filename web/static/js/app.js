let currentFilter = 'all';
let tasksCache = [];
let ws = null;
let currentPreviewPath = '';
let currentPreviewTaskId = null;

// ==================== QUẢN LÝ PHIÊN THIẾT BỊ / NGƯỜI DÙNG (SESSION ISOLATION) ====================
function getSessionId() {
    let sid = localStorage.getItem('pth_session_id');
    if (!sid) {
        sid = 'usr_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now().toString(36);
        localStorage.setItem('pth_session_id', sid);
    }
    return sid;
}

// ==================== KHỞI TẠO HỆ THỐNG ====================
document.addEventListener('DOMContentLoaded', () => {
    const sid = getSessionId();
    const sessionBadge = document.getElementById('sessionBadge');
    if (sessionBadge) {
        sessionBadge.textContent = sid.substring(0, 10) + '...';
        sessionBadge.title = `Mã phiên của bạn: ${sid}`;
    }

    initWebSocket();
    loadTasks();
    loadStats();
    loadSettings();

    // Lắng nghe toggle clipboard
    const cbToggle = document.getElementById('clipboardToggle');
    if (cbToggle) {
        cbToggle.addEventListener('change', async (e) => {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ auto_clipboard: e.target.checked })
            });
            showToast(e.target.checked ? 'Đã bật tự động bắt link Clipboard' : 'Đã tắt bắt link Clipboard', 'info');
        });
    }

    // Tự động làm mới định kỳ mỗi 5s
    setInterval(() => {
        loadStats();
    }, 5000);
});

// ==================== WEBSOCKET ====================
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const sid = getSessionId();
    const wsUrl = `${protocol}//${window.location.host}/ws?session_id=${encodeURIComponent(sid)}`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('[WebSocket] Đã kết nối với phiên riêng tư:', sid);
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWsMessage(data);
        } catch (e) {
            console.error('Lỗi phân tích WebSocket message:', e);
        }
    };

    ws.onclose = () => {
        console.warn('[WebSocket] Mất kết nối, đang thử kết nối lại sau 2s...');
        setTimeout(initWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error('[WebSocket] Lỗi kết nối:', err);
        ws.close();
    };
}

function handleWsMessage(payload) {
    const { event, data, session_id } = payload;
    const mySid = getSessionId();

    // Kiểm tra tính độc lập phiên: Nếu thông điệp chỉ dành cho phiên khác thì bỏ qua
    const targetSid = session_id || (data && data.session_id);
    if (targetSid && targetSid !== mySid && targetSid !== 'default') {
        return;
    }

    switch (event) {
        case 'clipboard_detected':
            showToast(`🔥 Đã bắt link: ${data.url}`, 'success');
            loadTasks();
            loadStats();
            break;

        case 'task_added':
        case 'batch_added':
        case 'task_retry':
            loadTasks();
            loadStats();
            break;

        case 'task_progress':
            updateTaskProgressInDom(data.id, data.progress, data.speed, data.status);
            break;

        case 'task_done':
            showToast(`✅ Đã tải xong video!`, 'success');
            loadTasks();
            loadStats();
            break;

        case 'task_error':
            showToast(`❌ Lỗi ID #${data.id}: ${data.error}`, 'error');
            loadTasks();
            loadStats();
            break;

        case 'settings_updated':
            // Cài đặt chung
            break;

        default:
            loadTasks();
            break;
    }
}

// Cập nhật mượt mà thanh tiến trình trực tiếp trong DOM
function updateTaskProgressInDom(taskId, progress, speed, status) {
    const bar = document.getElementById(`bar-${taskId}`);
    const pct = document.getElementById(`pct-${taskId}`);
    const spd = document.getElementById(`spd-${taskId}`);
    const badge = document.getElementById(`badge-${taskId}`);

    if (bar) bar.style.width = `${progress}%`;
    if (pct) pct.textContent = `${progress}%`;
    if (spd && speed) spd.textContent = speed;
    if (badge && status) {
        if (status === 'PROCESSING') {
            badge.className = 'px-2 py-0.5 rounded text-[11px] font-bold bg-purple-500/20 text-purple-400 border border-purple-500/30';
            badge.textContent = 'ĐANG RENDER';
        } else if (status === 'DOWNLOADING') {
            badge.className = 'px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30';
            badge.textContent = 'ĐANG TẢI';
        }
    }
}

// ==================== TẢI DỮ LIỆU TÁC VỤ ====================
async function loadTasks() {
    try {
        const sid = getSessionId();
        const res = await fetch(`/api/tasks?limit=100&session_id=${encodeURIComponent(sid)}`);
        const data = await res.json();
        tasksCache = data.tasks || [];
        renderTasks();
    } catch (err) {
        console.error('Lỗi nạp tác vụ:', err);
    }
}

async function loadStats() {
    try {
        const sid = getSessionId();
        const res = await fetch(`/api/stats?session_id=${encodeURIComponent(sid)}`);
        const stats = await res.json();
        document.getElementById('statTotal').textContent = stats.total || 0;
        document.getElementById('statCompleted').textContent = stats.completed || 0;
        document.getElementById('statPending').textContent = stats.pending || 0;
        document.getElementById('statSize').textContent = formatBytes(stats.total_size || 0);
        document.getElementById('taskCountBadge').textContent = stats.total || 0;
    } catch (err) {
        console.error('Lỗi nạp thống kê:', err);
    }
}

async function loadSettings() {
    try {
        const res = await fetch('/api/settings');
        const settings = await res.json();
        const cbToggle = document.getElementById('clipboardToggle');
        if (cbToggle && settings.auto_clipboard !== undefined) {
            cbToggle.checked = settings.auto_clipboard;
        }
        const settingAntiDup = document.getElementById('settingAntiDup');
        if (settingAntiDup && settings.anti_duplicate !== undefined) {
            settingAntiDup.checked = settings.anti_duplicate;
        }
        const settingBlurBg = document.getElementById('settingBlurBg');
        if (settingBlurBg && settings.blur_background !== undefined) {
            settingBlurBg.checked = settings.blur_background;
        }
        const settingHashtags = document.getElementById('settingHashtags');
        if (settingHashtags && settings.custom_hashtags) {
            settingHashtags.value = settings.custom_hashtags;
        }
        const settingMaxWorkers = document.getElementById('settingMaxWorkers');
        if (settingMaxWorkers && settings.max_concurrent_downloads !== undefined) {
            settingMaxWorkers.value = settings.max_concurrent_downloads;
        }
    } catch (err) {
        console.error('Lỗi nạp cài đặt:', err);
    }
}

async function saveSettings() {
    const payload = {
        anti_duplicate: document.getElementById('settingAntiDup').checked,
        blur_background: document.getElementById('settingBlurBg').checked,
        custom_hashtags: document.getElementById('settingHashtags').value.trim(),
        max_concurrent_downloads: parseInt(document.getElementById('settingMaxWorkers').value) || 4
    };
    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        showToast('Đã lưu cấu hình thành công!', 'success');
        closeModal('settingsModal');
    } catch (e) {
        showToast('Lỗi khi lưu cài đặt', 'error');
    }
}

// ==================== RENDER DANH SÁCH ====================
function renderTasks() {
    const listEl = document.getElementById('taskList');
    if (!listEl) return;

    let filtered = tasksCache;
    if (currentFilter === 'processing') {
        filtered = tasksCache.filter(t => ['PENDING', 'DOWNLOADING', 'PROCESSING'].includes(t.status));
    } else if (currentFilter === 'done') {
        filtered = tasksCache.filter(t => ['DONE', 'READY'].includes(t.status));
    } else if (currentFilter === 'failed') {
        filtered = tasksCache.filter(t => t.status === 'FAILED');
    }

    if (filtered.length === 0) {
        listEl.innerHTML = `
            <div class="text-center py-12 text-slate-500 space-y-2">
                <i class="fa-solid fa-cloud-arrow-down text-4xl text-slate-600"></i>
                <p class="text-sm">Chưa có video nào trong mục này của bạn.</p>
            </div>
        `;
        return;
    }

    listEl.innerHTML = filtered.map(task => {
        const isDone = ['DONE', 'READY'].includes(task.status);
        const isProcessing = ['DOWNLOADING', 'PROCESSING'].includes(task.status);
        const isFailed = task.status === 'FAILED';

        // Icon nền tảng
        let platformIcon = '<i class="fa-solid fa-globe text-slate-400"></i>';
        if (task.platform === 'tiktok') platformIcon = '<i class="fa-brands fa-tiktok text-pink-400"></i>';
        else if (task.platform === 'youtube') platformIcon = '<i class="fa-brands fa-youtube text-red-500"></i>';
        else if (task.platform === 'facebook') platformIcon = '<i class="fa-brands fa-facebook text-blue-500"></i>';
        else if (task.platform === 'instagram') platformIcon = '<i class="fa-brands fa-instagram text-fuchsia-400"></i>';
        else if (task.platform === 'threads') platformIcon = '<i class="fa-brands fa-threads text-white"></i>';
        else if (task.platform === 'twitter') platformIcon = '<i class="fa-brands fa-x-twitter text-slate-200"></i>';
        else if (task.platform === 'douyin') platformIcon = '<i class="fa-solid fa-play text-orange-400"></i>';

        // Badge trạng thái
        let statusBadge = '';
        if (task.status === 'DONE') {
            statusBadge = `<span id="badge-${task.id}" class="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">HOÀN TẤT</span>`;
        } else if (task.status === 'READY') {
            statusBadge = `<span id="badge-${task.id}" class="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-500/20 text-purple-400 border border-purple-500/30">ĐÃ LÁCH BẢN QUYỀN</span>`;
        } else if (task.status === 'DOWNLOADING') {
            statusBadge = `<span id="badge-${task.id}" class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30 animate-pulse">ĐANG TẢI</span>`;
        } else if (task.status === 'PROCESSING') {
            statusBadge = `<span id="badge-${task.id}" class="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-500/20 text-purple-400 border border-purple-500/30 animate-pulse">ĐANG RENDER</span>`;
        } else if (task.status === 'PENDING') {
            statusBadge = `<span id="badge-${task.id}" class="px-2 py-0.5 rounded text-[11px] font-bold bg-slate-700 text-slate-300">CHỜ TẢI</span>`;
        } else if (isFailed) {
            statusBadge = `<span id="badge-${task.id}" class="px-2 py-0.5 rounded text-[11px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">THẤT BẠI</span>`;
        }

        const thumb = task.thumbnail || 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=200&auto=format&fit=crop&q=60';
        const finalFile = task.final_path || task.raw_path || '';
        const titleText = task.title || task.url;

        return `
            <div class="bg-slate-900/90 hover:bg-slate-900 border border-slate-700/80 rounded-2xl p-3.5 sm:p-4 transition flex flex-col gap-3 group shadow-md">
                <!-- Top Row: Thumbnail + Info -->
                <div class="flex items-center space-x-3.5 w-full min-w-0">
                    <div class="relative w-16 h-16 sm:w-20 sm:h-20 rounded-xl overflow-hidden bg-slate-950 flex-shrink-0 border border-slate-800">
                        <img src="${thumb}" alt="thumb" class="w-full h-full object-cover" onerror="this.src='https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=200&auto=format&fit=crop&q=60'">
                        ${isDone && finalFile ? `
                            <button onclick="playVideo(${task.id}, '${encodeURIComponent(finalFile)}', '${encodeURIComponent(titleText)}')" class="absolute inset-0 bg-black/40 hover:bg-black/60 flex items-center justify-center text-white text-lg transition opacity-90 sm:opacity-0 sm:group-hover:opacity-100">
                                <i class="fa-solid fa-play"></i>
                            </button>
                        ` : ''}
                    </div>

                    <div class="flex-1 min-w-0 space-y-1">
                        <div class="flex items-center space-x-2">
                            ${platformIcon}
                            <span class="text-xs text-slate-400 truncate max-w-[120px] sm:max-w-none">${task.author || task.platform}</span>
                            ${statusBadge}
                        </div>
                        <h4 class="text-sm font-semibold text-white truncate max-w-xl" title="${titleText}">${titleText}</h4>
                        
                        <!-- Progress bar or File info -->
                        ${isProcessing || task.status === 'PENDING' ? `
                            <div class="space-y-1 pt-1">
                                <div class="w-full bg-slate-800 rounded-full h-2 overflow-hidden border border-slate-700">
                                    <div id="bar-${task.id}" class="bg-gradient-to-r from-emerald-500 to-teal-400 h-2 rounded-full transition-all duration-300" style="width: ${task.progress || 0}%"></div>
                                </div>
                                <div class="flex justify-between text-[11px] text-slate-400">
                                    <span id="spd-${task.id}">${task.speed || 'Đang chuẩn bị...'}</span>
                                    <span id="pct-${task.id}" class="font-bold text-emerald-400">${task.progress || 0}%</span>
                                </div>
                            </div>
                        ` : `
                            <div class="flex flex-wrap items-center gap-3 text-xs text-slate-400 pt-0.5">
                                ${task.file_size ? `<span><i class="fa-regular fa-file text-slate-500 mr-1"></i>${formatBytes(task.file_size)}</span>` : ''}
                                ${task.duration ? `<span><i class="fa-regular fa-clock text-slate-500 mr-1"></i>${Math.round(task.duration)}s</span>` : ''}
                                <span class="text-slate-500">${task.created_at || ''}</span>
                            </div>
                        `}

                        ${isFailed && task.error_log ? `
                            <p class="text-xs text-red-400 truncate max-w-lg"><i class="fa-solid fa-triangle-exclamation mr-1"></i>${task.error_log}</p>
                        ` : ''}
                    </div>
                </div>

                <!-- Bottom Row: 4 Nút Tải Rõ Ràng Cho Điện Thoại & Máy Tính -->
                ${isDone && finalFile ? `
                    <div class="pt-2.5 border-t border-slate-800/80 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2">
                        <!-- 4 Nút Tải Trực Tiếp Chuẩn Mobile -->
                        <div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 flex-1">
                            <a href="/api/download/${task.id}?type=clean" download class="py-2 px-2 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 hover:text-emerald-300 text-[11px] sm:text-xs font-bold transition flex items-center justify-center space-x-1 border border-emerald-500/30 text-center active:scale-95" title="Tải video sạch gốc không logo">
                                <i class="fa-solid fa-video"></i>
                                <span>Video Sạch</span>
                            </a>

                            <a href="/api/download/${task.id}?type=processed" download class="py-2 px-2 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 hover:text-purple-300 text-[11px] sm:text-xs font-bold transition flex items-center justify-center space-x-1 border border-purple-500/30 text-center active:scale-95" title="Tải video 9:16 đã lách bản quyền">
                                <i class="fa-solid fa-wand-magic-sparkles"></i>
                                <span>Lách 9:16</span>
                            </a>

                            <a href="/api/download/${task.id}?type=compressed" download class="py-2 px-2 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 hover:text-amber-300 text-[11px] sm:text-xs font-bold transition flex items-center justify-center space-x-1 border border-amber-500/30 text-center active:scale-95" title="Nén siêu nhẹ giảm 60-70% dung lượng gửi Zalo/Telegram">
                                <i class="fa-solid fa-file-zipper"></i>
                                <span>Nén Gọn</span>
                            </a>

                            <a href="/api/download/${task.id}?type=audio" download class="py-2 px-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 hover:text-cyan-300 text-[11px] sm:text-xs font-bold transition flex items-center justify-center space-x-1 border border-cyan-500/30 text-center active:scale-95" title="Tách và tải âm thanh MP3 320k">
                                <i class="fa-solid fa-music"></i>
                                <span>Tải MP3</span>
                            </a>
                        </div>

                        <!-- Các công cụ: AI Studio, Highlights, Xem thử, mở thư mục, xóa -->
                        <div class="flex items-center justify-end space-x-1.5 pt-1 sm:pt-0">
                            <button onclick="openAiStudio(${task.id})" class="px-2.5 py-1.5 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 hover:text-purple-300 text-[11px] sm:text-xs font-bold transition flex items-center space-x-1 border border-purple-500/30 active:scale-95" title="Tạo phụ đề CapCut & Lồng tiếng AI">
                                <i class="fa-solid fa-wand-magic-sparkles"></i>
                                <span class="hidden sm:inline">AI Studio</span>
                            </button>
                            <button onclick="openHighlightsModal(${task.id})" class="px-2.5 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 hover:text-cyan-300 text-[11px] sm:text-xs font-bold transition flex items-center space-x-1 border border-cyan-500/30 active:scale-95" title="AI Cắt 3-5 clip ngắn 9:16 Shorts/TikTok">
                                <i class="fa-solid fa-scissors"></i>
                                <span class="hidden sm:inline">Highlights</span>
                            </button>
                            <button onclick="playVideo(${task.id}, '${encodeURIComponent(finalFile)}', '${encodeURIComponent(titleText)}')" class="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-teal-400 hover:text-teal-300 text-xs font-semibold transition" title="Xem trước video">
                                <i class="fa-solid fa-play"></i>
                            </button>
                            <button onclick="openFolder('${encodeURIComponent(finalFile)}')" class="hidden sm:inline-flex p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-400 hover:text-amber-300 text-xs font-semibold transition" title="Mở trong Thư mục Windows">
                                <i class="fa-regular fa-folder-open"></i>
                            </button>
                            <button onclick="deleteTask(${task.id}, true)" class="p-2 rounded-lg bg-slate-800 hover:bg-red-500/20 text-slate-400 hover:text-red-400 text-xs font-semibold transition" title="Xóa">
                                <i class="fa-regular fa-trash-can"></i>
                            </button>
                        </div>
                    </div>
                ` : `
                    <div class="flex items-center justify-end space-x-1.5">
                        ${isFailed ? `
                            <button onclick="retryTask(${task.id})" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-400 hover:text-amber-300 text-xs font-semibold transition flex items-center space-x-1" title="Thử lại">
                                <i class="fa-solid fa-rotate-right"></i>
                                <span>Thử lại</span>
                            </button>
                        ` : ''}
                        <button onclick="deleteTask(${task.id}, true)" class="p-2 rounded-lg bg-slate-800 hover:bg-red-500/20 text-slate-400 hover:text-red-400 text-xs font-semibold transition" title="Xóa">
                            <i class="fa-regular fa-trash-can"></i>
                        </button>
                    </div>
                `}
            </div>
        `;
    }).join('');
}

// ==================== HÀNH ĐỘNG NGƯỜI DÙNG ====================
async function handleDownloadSubmit(e) {
    e.preventDefault();
    const urlInput = document.getElementById('urlInput');
    const url = urlInput.value.trim();
    if (!url) return;

    const mode = document.querySelector('input[name="downloadMode"]:checked')?.value || 'video';
    const quality = document.getElementById('qualitySelect')?.value || '1080p';
    const btn = document.getElementById('btnSubmit');

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i><span>ĐANG NẠP...</span>`;

    try {
        const res = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url, format_type: mode, quality: quality, session_id: getSessionId() })
        });
        const data = await res.json();
        if (res.ok) {
            if (data.count && data.count > 1) {
                showToast(`⚡ Đã nhận diện và nạp ${data.count} link để tải song song!`, 'success');
            } else {
                showToast('Đã nạp link vào hàng đợi tải!', 'success');
            }
            urlInput.value = '';
            loadTasks();
            loadStats();
        } else {
            showToast(data.detail || 'Lỗi khi nạp link', 'error');
        }
    } catch (err) {
        showToast('Không thể kết nối đến máy chủ', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-bolt"></i><span>TẢI NGAY</span>`;
    }
}

async function handlePasteFromClipboard() {
    try {
        const text = await navigator.clipboard.readText();
        if (text) {
            document.getElementById('urlInput').value = text.trim();
            showToast('Đã dán từ bộ nhớ tạm!', 'info');
        }
    } catch (e) {
        showToast('Vui lòng cấp quyền truy cập Clipboard cho trình duyệt', 'warning');
    }
}

function updateBatchCounter() {
    const text = document.getElementById('batchUrls')?.value || '';
    const urls = text.match(/https?:\/\/[^\s,;"'<>]+/g) || [];
    const badge = document.getElementById('batchCountBadge');
    if (badge) {
        badge.textContent = `${urls.length} link hợp lệ`;
    }
}

async function pasteAllFromClipboardToBatch() {
    try {
        const text = await navigator.clipboard.readText();
        if (text) {
            const ta = document.getElementById('batchUrls');
            if (ta) {
                ta.value = (ta.value ? ta.value + '\n' : '') + text.trim();
                updateBatchCounter();
                showToast('Đã dán các link từ Clipboard!', 'success');
            }
        }
    } catch (e) {
        showToast('Vui lòng cho phép truy cập Clipboard trên trình duyệt', 'warning');
    }
}

async function submitBatchDownload() {
    const text = document.getElementById('batchUrls').value.trim();
    if (!text) return;

    // Tách thông minh mọi link bằng Regex (chấp nhận cả xuống dòng, dấu phẩy, khoảng trắng)
    const urls = text.match(/https?:\/\/[^\s,;"'<>]+/g) || [];
    if (urls.length === 0) {
        showToast('Không tìm thấy link hợp lệ nào!', 'warning');
        return;
    }

    const mode = document.getElementById('batchFormat').value;
    const quality = document.getElementById('batchQuality')?.value || '1080p';

    try {
        const res = await fetch('/api/tasks/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls: urls, format_type: mode, quality: quality, session_id: getSessionId() })
        });
        const data = await res.json();
        showToast(`⚡ Đã nạp ${data.count} link vào hệ thống tải song song!`, 'success');
        closeModal('batchModal');
        document.getElementById('batchUrls').value = '';
        updateBatchCounter();
        loadTasks();
        loadStats();
    } catch (e) {
        showToast('Lỗi khi nạp danh sách link', 'error');
    }
}

// Chuyển đổi tab trong Modal Tải Hàng Loạt & Playlist
function switchBatchTab(tab) {
    const linksDiv = document.getElementById('batchTabLinks');
    const playlistDiv = document.getElementById('batchTabPlaylist');
    const linksBtn = document.getElementById('tabBatchLinksBtn');
    const playlistBtn = document.getElementById('tabBatchPlaylistBtn');

    if (tab === 'playlist') {
        if (linksDiv) linksDiv.classList.add('hidden');
        if (playlistDiv) playlistDiv.classList.remove('hidden');
        if (linksBtn) {
            linksBtn.className = 'flex-1 py-2 rounded-lg text-slate-400 hover:text-white transition flex items-center justify-center space-x-1.5';
        }
        if (playlistBtn) {
            playlistBtn.className = 'flex-1 py-2 rounded-lg bg-slate-800 text-cyan-400 shadow transition flex items-center justify-center space-x-1.5';
        }
    } else {
        if (playlistDiv) playlistDiv.classList.add('hidden');
        if (linksDiv) linksDiv.classList.remove('hidden');
        if (playlistBtn) {
            playlistBtn.className = 'flex-1 py-2 rounded-lg text-slate-400 hover:text-white transition flex items-center justify-center space-x-1.5';
        }
        if (linksBtn) {
            linksBtn.className = 'flex-1 py-2 rounded-lg bg-slate-800 text-emerald-400 shadow transition flex items-center justify-center space-x-1.5';
        }
    }
}

// Bóc tách và nạp toàn bộ video của Kênh hoặc Playlist
async function submitPlaylistDownload() {
    const urlInput = document.getElementById('playlistUrlInput');
    const url = urlInput ? urlInput.value.trim() : '';
    if (!url) {
        showToast('Vui lòng nhập đường dẫn Kênh hoặc Playlist!', 'warning');
        return;
    }

    const maxItems = parseInt(document.getElementById('playlistMaxItems')?.value || '20');
    const format = document.getElementById('playlistFormat')?.value || 'video';
    const quality = document.getElementById('playlistQuality')?.value || '1080p';
    const btn = document.getElementById('btnPlaylistExtract');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Đang bóc tách kênh...`;
    }

    showToast('Đang kết nối và phân tích toàn bộ video của Kênh/Playlist...', 'info');

    try {
        const res = await fetch('/api/playlist/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                max_items: maxItems,
                format_type: format,
                quality: quality,
                session_id: getSessionId()
            })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`🎉 Bóc tách thành công: "${data.title || 'Kênh'}" - Đã nạp ${data.added_count} video vào hàng đợi!`, 'success');
            closeModal('batchModal');
            if (urlInput) urlInput.value = '';
            loadTasks();
            loadStats();
        } else {
            showToast(data.detail || 'Không thể bóc tách kênh/playlist này', 'error');
        }
    } catch (e) {
        showToast('Lỗi kết nối khi bóc tách kênh/playlist', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-cloud-arrow-down mr-1"></i> Bóc Tách & Tải Toàn Bộ Kênh`;
        }
    }
}

async function deleteTask(taskId, deleteFile = true) {
    if (!confirm('Bạn có chắc muốn xóa tác vụ này?')) return;
    try {
        await fetch(`/api/tasks/${taskId}?delete_file=${deleteFile}`, { method: 'DELETE' });
        showToast('Đã xóa tác vụ', 'info');
        loadTasks();
        loadStats();
    } catch (e) {
        showToast('Lỗi khi xóa', 'error');
    }
}

async function retryTask(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}/retry`, { method: 'POST' });
        showToast('Đang thử lại tác vụ...', 'info');
        loadTasks();
    } catch (e) {
        showToast('Lỗi khi thử lại', 'error');
    }
}

async function processAntiDuplicate(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}/process`, { method: 'POST' });
        showToast('Bắt đầu xử lý lách bản quyền FFmpeg 9:16...', 'info');
        loadTasks();
    } catch (e) {
        showToast('Lỗi khi kích hoạt render', 'error');
    }
}

async function extractAudio(taskId) {
    try {
        await fetch(`/api/tasks/${taskId}/extract-audio`, { method: 'POST' });
        showToast('Đang trích xuất tệp âm thanh MP3...', 'info');
        loadTasks();
    } catch (e) {
        showToast('Lỗi khi tách âm thanh', 'error');
    }
}

async function openFolder(typeOrPath) {
    try {
        let payload = {};
        if (['all', 'videos', 'audios', 'processed'].includes(typeOrPath)) {
            payload.type = typeOrPath;
        } else {
            payload.path = decodeURIComponent(typeOrPath);
        }
        await fetch('/api/open-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    } catch (e) {
        console.error('Lỗi mở thư mục:', e);
    }
}

async function triggerLoginSession() {
    try {
        showToast('Đang mở trình duyệt đăng nhập...', 'info');
        const res = await fetch('/api/login-session', { method: 'POST' });
        const data = await res.json();
        showToast('Trình duyệt đã mở. Hãy đăng nhập và tắt cửa sổ khi xong!', 'success');
    } catch (e) {
        showToast('Không thể mở trình duyệt đăng nhập', 'error');
    }
}

function openCurrentVideoFolder() {
    if (currentPreviewPath) {
        openFolder(currentPreviewPath);
    }
}

// ==================== VIDEO PLAYER PREVIEW ====================
function playVideo(taskId, encodedPath, encodedTitle) {
    const rawPath = decodeURIComponent(encodedPath);
    const title = decodeURIComponent(encodedTitle);
    currentPreviewPath = rawPath;
    currentPreviewTaskId = taskId;

    const modal = document.getElementById('playerModal');
    const video = document.getElementById('videoElement');
    const titleEl = document.getElementById('playerTitle');
    const dlClean = document.getElementById('playerDlClean');
    const dlProcessed = document.getElementById('playerDlProcessed');
    const dlCompressed = document.getElementById('playerDlCompressed');
    const dlAudio = document.getElementById('playerDlAudio');

    titleEl.textContent = title;

    // Stream trực tiếp theo taskId hỗ trợ Range HTTP 206 cho iPhone / Android
    if (taskId) {
        video.src = `/media/stream/${taskId}`;
    } else {
        video.src = `/media/preview?path=${encodeURIComponent(rawPath)}`;
    }
    video.load();

    if (taskId) {
        if (dlClean) dlClean.href = `/api/download/${taskId}?type=clean`;
        if (dlProcessed) dlProcessed.href = `/api/download/${taskId}?type=processed`;
        if (dlCompressed) dlCompressed.href = `/api/download/${taskId}?type=compressed`;
        if (dlAudio) dlAudio.href = `/api/download/${taskId}?type=audio`;
    }

    modal.classList.remove('hidden');

    const playPromise = video.play();
    if (playPromise !== undefined) {
        playPromise.catch(() => {
            console.log('iOS chặn tự động phát có âm thanh, người dùng bấm Play thủ công');
        });
    }
}

function closePlayerModal() {
    const modal = document.getElementById('playerModal');
    const video = document.getElementById('videoElement');
    if (video) {
        video.pause();
        video.removeAttribute('src');
        video.load();
    }
    modal.classList.add('hidden');
}

// ==================== TIỆN ÍCH GIAO DIỆN ====================
function setFilter(filter) {
    currentFilter = filter;
    ['all', 'processing', 'done', 'failed'].forEach(f => {
        const btn = document.getElementById('tab' + f.charAt(0).toUpperCase() + f.slice(1));
        if (btn) {
            if (f === filter) {
                btn.className = 'px-3 py-1.5 rounded-lg text-white bg-slate-800 shadow';
            } else {
                btn.className = 'px-3 py-1.5 rounded-lg text-slate-400 hover:text-white';
            }
        }
    });
    renderTasks();
}

function openModal(id) {
    document.getElementById(id)?.classList.remove('hidden');
}

function closeModal(id) {
    document.getElementById(id)?.classList.add('hidden');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    let bg = 'bg-slate-800 border-slate-700 text-white';
    let icon = '<i class="fa-solid fa-circle-info text-blue-400"></i>';

    if (type === 'success') {
        bg = 'bg-slate-800/95 border-emerald-500/50 text-white shadow-emerald-500/10';
        icon = '<i class="fa-solid fa-circle-check text-emerald-400"></i>';
    } else if (type === 'error') {
        bg = 'bg-slate-800/95 border-red-500/50 text-white shadow-red-500/10';
        icon = '<i class="fa-solid fa-circle-xmark text-red-400"></i>';
    } else if (type === 'warning') {
        bg = 'bg-slate-800/95 border-amber-500/50 text-white shadow-amber-500/10';
        icon = '<i class="fa-solid fa-triangle-exclamation text-amber-400"></i>';
    }

    toast.className = `flex items-center space-x-2.5 px-4 py-3 rounded-xl border shadow-xl text-xs font-semibold pointer-events-auto transition-all duration-300 transform translate-y-2 opacity-0 ${bg}`;
    toast.innerHTML = `${icon}<span>${message}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.remove('translate-y-2', 'opacity-0');
    }, 10);

    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function formatBytes(bytes, decimals = 1) {
    if (!+bytes) return '0 B';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

// ==================== MỞ LIÊN KẾT ĐIỆN THOẠI ====================
async function openMobileModal() {
    let finalUrl = `http://192.168.1.10:5000`;
    try {
        const res = await fetch('/api/tunnel');
        const data = await res.json();
        if (data.public_url) {
            finalUrl = data.public_url;
        }
    } catch (e) {}

    const txt = document.getElementById('mobileUrlText');
    const qr = document.getElementById('mobileQrImg');
    if (txt) txt.textContent = finalUrl;
    if (qr) qr.src = `https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(finalUrl)}`;
    openModal('mobileModal');
}

function copyMobileUrl() {
    const txt = document.getElementById('mobileUrlText')?.textContent;
    if (txt) {
        navigator.clipboard.writeText(txt);
        showToast('Đã sao chép liên kết cho điện thoại!', 'success');
    }
}

// ==================== PTH AI STUDIO PRO ====================
let currentAiTaskId = null;
let currentHighlightsTaskId = null;
let currentAntiCopyDownloadUrl = '';

function openAiStudio(taskId, defaultTab = 'captions') {
    currentAiTaskId = taskId;
    // Ẩn kết quả cũ khi mở modal
    const sepRes = document.getElementById('separationResultContainer');
    if (sepRes) sepRes.classList.add('hidden');
    const acRes = document.getElementById('antiCopyResultContainer');
    if (acRes) acRes.classList.add('hidden');

    switchAiTab(defaultTab);
    openModal('aiStudioModal');
}

function switchAiTab(tab) {
    const tabs = ['Captions', 'Dubbing', 'Separation', 'AntiCopy'];
    tabs.forEach(t => {
        const div = document.getElementById(`aiTab${t}`);
        const btn = document.getElementById(`tabAi${t}Btn`);
        if (t.toLowerCase() === tab.toLowerCase()) {
            if (div) div.classList.remove('hidden');
            if (btn) {
                let colorClass = 'text-yellow-400';
                if (tab === 'dubbing') colorClass = 'text-purple-400';
                else if (tab === 'separation') colorClass = 'text-teal-400';
                else if (tab === 'anticopy') colorClass = 'text-rose-400';
                btn.className = `py-2 px-1 rounded-lg bg-slate-800 ${colorClass} shadow transition flex items-center justify-center space-x-1 text-center`;
            }
        } else {
            if (div) div.classList.add('hidden');
            if (btn) btn.className = 'py-2 px-1 rounded-lg text-slate-400 hover:text-white transition flex items-center justify-center space-x-1 text-center';
        }
    });
}

async function triggerAiCaptions() {
    if (!currentAiTaskId) return;
    const style = document.getElementById('captionStylePreset')?.value || 'capcut_yellow';
    const pos = document.getElementById('captionPosition')?.value || 'bottom';
    const skip = document.getElementById('captionSkipIfExists')?.checked ?? true;
    const btn = document.getElementById('btnRunCaptions');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Đang nhận diện & tạo chữ...`;
    }

    try {
        const res = await fetch('/api/ai/autocaptions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: currentAiTaskId,
                style_preset: style,
                position: pos,
                skip_if_exists: skip
            })
        });
        const data = await res.json();
        if (res.ok) {
            showToast('🚀 Đang chạy tạo phụ đề CapCut trong nền...', 'info');
            closeModal('aiStudioModal');
            loadTasks();
        } else {
            showToast(data.detail || 'Lỗi khi kích hoạt tạo phụ đề', 'error');
        }
    } catch (e) {
        showToast('Lỗi kết nối máy chủ', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles mr-1"></i> Tạo Phụ Đề CapCut Ngay`;
        }
    }
}

async function triggerAiDubbing() {
    if (!currentAiTaskId) return;
    const isEnabled = document.getElementById('dubbingEnabledToggle')?.checked ?? true;
    if (!isEnabled) {
        showToast('Chế độ lồng tiếng đang tắt. Vui lòng gạt công tắc BẬT để dùng!', 'warning');
        return;
    }

    const voice = document.getElementById('dubbingVoiceType')?.value || 'male_north';
    const btn = document.getElementById('btnRunDubbing');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Đang dịch & lồng tiếng...`;
    }

    try {
        const res = await fetch('/api/ai/dubbing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: currentAiTaskId,
                voice_type: voice
            })
        });
        const data = await res.json();
        if (res.ok) {
            showToast('🎙️ Đang dịch và lồng tiếng AI trong nền...', 'info');
            closeModal('aiStudioModal');
            loadTasks();
        } else {
            showToast(data.detail || 'Lỗi khi kích hoạt lồng tiếng', 'error');
        }
    } catch (e) {
        showToast('Lỗi kết nối máy chủ', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-microphone-lines mr-1"></i> Bắt Đầu Lồng Tiếng`;
        }
    }
}

async function triggerAiAudioSeparation() {
    if (!currentAiTaskId) return;
    const btn = document.getElementById('btnRunSeparation');
    const resContainer = document.getElementById('separationResultContainer');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Đang tách Beat & Vocal...`;
    }

    try {
        const res = await fetch('/api/ai/audio-separation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: currentAiTaskId })
        });
        const data = await res.json();
        if (res.ok && data.data) {
            showToast('🎵 Đã tách thành công Beat Karaoke & Vocal Acapella!', 'success');
            const d = data.data;
            const btnBeat = document.getElementById('btnDlBeat');
            const btnVocal = document.getElementById('btnDlVocal');
            const btnZip = document.getElementById('btnDlAudioZip');

            if (btnBeat) btnBeat.href = d.beat.download_url;
            if (btnVocal) btnVocal.href = d.vocal.download_url;
            if (btnZip) btnZip.href = d.zip.download_url;

            if (resContainer) resContainer.classList.remove('hidden');
        } else {
            showToast(data.detail || 'Không thể tách âm thanh', 'error');
        }
    } catch (e) {
        showToast('Lỗi kết nối máy chủ', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles mr-1"></i> Bắt Đầu Tách Beat & Vocal`;
        }
    }
}

async function triggerAiAntiCopyright() {
    if (!currentAiTaskId) return;
    const mirror = document.getElementById('antiCopyMirrorToggle')?.checked ?? true;
    const speedBoost = parseFloat(document.getElementById('antiCopySpeedBoost')?.value || '1.04');
    const btn = document.getElementById('btnRunAntiCopy');
    const resContainer = document.getElementById('antiCopyResultContainer');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Đang xử lý lách bản quyền...`;
    }

    try {
        const res = await fetch('/api/ai/anti-copyright', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: currentAiTaskId,
                mirror: mirror,
                speed_boost: speedBoost
            })
        });
        const data = await res.json();
        if (res.ok && data.data) {
            showToast('🛡️ Đã tạo video lách bản quyền thành công!', 'success');
            const d = data.data;
            currentAntiCopyDownloadUrl = d.download_url;
            const btnDl = document.getElementById('btnDlAntiCopy');
            if (btnDl) btnDl.href = d.download_url;
            if (resContainer) resContainer.classList.remove('hidden');
            loadTasks();
        } else {
            showToast(data.detail || 'Lỗi khi xử lý video', 'error');
        }
    } catch (e) {
        showToast('Lỗi kết nối máy chủ', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-shield-halved mr-1"></i> Áp Dụng Lách Bản Quyền`;
        }
    }
}

function previewAntiCopyVideo() {
    if (!currentAntiCopyDownloadUrl) return;
    const video = document.getElementById('videoElement');
    const titleEl = document.getElementById('playerTitle');
    if (titleEl) titleEl.textContent = 'Video Đã Lách Bản Quyền';
    if (video) {
        video.src = currentAntiCopyDownloadUrl;
        video.load();
        video.play().catch(e => console.log(e));
    }
    openModal('playerModal');
}

function openHighlightsModal(taskId) {
    currentHighlightsTaskId = taskId;
    const zipSec = document.getElementById('hlZipSection');
    if (zipSec) zipSec.classList.add('hidden');
    closeHlPreviewPlayer();

    const container = document.getElementById('hlClipsContainer');
    if (container) {
        container.innerHTML = `
            <div class="text-center py-10 text-slate-500 text-xs space-y-1">
                <i class="fa-solid fa-spinner fa-spin text-2xl text-cyan-400 mb-2"></i>
                <p>Đang kiểm tra các clip highlights đã cắt...</p>
            </div>
        `;
    }
    openModal('highlightsModal');

    // Tự động kiểm tra và tải lại các clip đã cắt trước đó để tải về bất kỳ lúc nào
    fetch(`/api/highlights/${taskId}/info`)
        .then(res => res.json())
        .then(data => {
            if (data.has_clips && data.clips && data.clips.length > 0) {
                renderHighlightClipsList(data);
            } else {
                if (container) {
                    container.innerHTML = `
                        <div class="text-center py-10 text-slate-500 text-xs space-y-1">
                            <i class="fa-solid fa-clapperboard text-3xl text-slate-600 mb-2"></i>
                            <p>Bấm nút <b>"Quét & Cắt Highlights"</b> ở trên để AI tự động tìm đoạn hay nhất!</p>
                            <p class="text-slate-600 text-[11px]">Clip sau khi cắt được lưu trữ để bạn có thể xem lại và tải về sau bất cứ lúc nào!</p>
                        </div>
                    `;
                }
            }
        })
        .catch(() => {
            if (container) {
                container.innerHTML = `
                    <div class="text-center py-10 text-slate-500 text-xs space-y-1">
                        <i class="fa-solid fa-clapperboard text-3xl text-slate-600 mb-2"></i>
                        <p>Bấm nút <b>"Quét & Cắt Highlights"</b> ở trên để AI tự động tìm đoạn hay nhất!</p>
                    </div>
                `;
            }
        });
}

function renderHighlightClipsList(hData) {
    const container = document.getElementById('hlClipsContainer');
    const zipSec = document.getElementById('hlZipSection');
    const zipBtn = document.getElementById('hlZipDownloadBtn');
    const zipTitle = document.getElementById('hlZipTitle');

    if (zipSec && zipBtn) {
        zipSec.classList.remove('hidden');
        zipBtn.href = hData.zip_url || `/api/highlights/${hData.task_id}/zip`;
        if (zipTitle) zipTitle.textContent = `Đã cắt thành công ${hData.total_clips} clip (${formatBytes(hData.zip_size)})`;
    }

    if (container) {
        container.innerHTML = hData.clips.map(clip => `
            <div class="bg-slate-950 border border-slate-800 rounded-xl p-3 flex items-center justify-between gap-3 hover:border-cyan-500/40 transition">
                <div class="flex items-center space-x-3 min-w-0">
                    <div class="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center font-bold text-sm flex-shrink-0">
                        #${clip.clip_number}
                    </div>
                    <div class="min-w-0">
                        <div class="text-white font-bold text-xs truncate">Clip Viral #${clip.clip_number} (Dọc 9:16)</div>
                        <div class="text-slate-400 text-[11px] flex items-center space-x-2 pt-0.5">
                            <span><i class="fa-regular fa-clock mr-1 text-slate-500"></i>${clip.time_range || clip.duration + 's'}</span>
                            <span>•</span>
                            <span>${formatBytes(clip.file_size)}</span>
                        </div>
                    </div>
                </div>

                <div class="flex items-center space-x-2 flex-shrink-0">
                    <button onclick="playHighlightClipInline('${clip.download_url}', 'Clip Viral #${clip.clip_number}')" class="py-1.5 px-3 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-xs font-bold transition flex items-center space-x-1.5 border border-cyan-500/30 active:scale-95 shadow-sm" title="Xem trước clip trực tiếp">
                        <i class="fa-solid fa-play text-cyan-400"></i>
                        <span>Xem Thử</span>
                    </button>
                    <a href="${clip.download_url}" download class="py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white text-xs font-bold transition flex items-center space-x-1 border border-slate-700 active:scale-95" title="Tải clip về máy">
                        <i class="fa-solid fa-cloud-arrow-down text-emerald-400"></i>
                        <span>Tải Về</span>
                    </a>
                </div>
            </div>
        `).join('');
    }
}

function playHighlightClipInline(clipUrl, title) {
    const sec = document.getElementById('hlPlayerSection');
    const video = document.getElementById('hlVideoElement');
    const titleEl = document.getElementById('hlPlayerTitle');

    if (titleEl) titleEl.textContent = `Đang xem: ${title}`;
    if (sec) sec.classList.remove('hidden');

    if (video) {
        video.src = clipUrl;
        video.load();
        video.play().catch(e => console.log('Autoplay:', e));
    }
    sec?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeHlPreviewPlayer() {
    const sec = document.getElementById('hlPlayerSection');
    const video = document.getElementById('hlVideoElement');
    if (video) {
        video.pause();
        video.src = '';
    }
    if (sec) sec.classList.add('hidden');
}

async function generateViralHighlights() {
    if (!currentHighlightsTaskId) return;
    const numClips = parseInt(document.getElementById('hlNumClips')?.value || '3');
    const duration = parseInt(document.getElementById('hlClipDuration')?.value || '45');
    const cropMode = document.getElementById('hlCropMode')?.value || 'blur';
    const btn = document.getElementById('btnGenerateHighlights');
    const container = document.getElementById('hlClipsContainer');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Đang quét cao trào...`;
    }

    if (container) {
        container.innerHTML = `
            <div class="text-center py-10 text-cyan-400 text-xs space-y-2">
                <i class="fa-solid fa-spinner fa-spin text-3xl"></i>
                <p class="font-bold">AI đang phân tích âm thanh, chuyển cảnh và render clip 9:16 (${cropMode === 'fill' ? 'Tràn viền' : (cropMode === 'fit' ? 'Viền đen' : 'Nền mờ')})...</p>
                <p class="text-slate-500 text-[11px]">Tốc độ siêu tốc tối ưu hoá chỉ mất 3-8 giây</p>
            </div>
        `;
    }

    try {
        const res = await fetch('/api/ai/highlights', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: currentHighlightsTaskId,
                num_clips: numClips,
                clip_duration: duration,
                crop_mode: cropMode
            })
        });
        const data = await res.json();
        if (res.ok && data.data) {
            const hData = data.data;
            showToast(`🎉 Đã tạo thành công ${hData.total_clips} clip ngắn viral!`, 'success');
            renderHighlightClipsList(hData);

            // Tự động phát clip đầu tiên để người dùng xem thử ngay lập tức!
            if (hData.clips && hData.clips.length > 0) {
                playHighlightClipInline(hData.clips[0].download_url, `Clip Viral #${hData.clips[0].clip_number}`);
            }
        } else {
            showToast(data.detail || 'Không thể tạo clip viral từ video này', 'error');
            if (container) {
                container.innerHTML = `<div class="text-center py-8 text-red-400 text-xs">${data.detail || 'Lỗi khi cắt video'}</div>`;
            }
        }
    } catch (e) {
        showToast('Lỗi kết nối máy chủ', 'error');
        if (container) {
            container.innerHTML = `<div class="text-center py-8 text-red-400 text-xs">Lỗi kết nối máy chủ</div>`;
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-bolt mr-1"></i> Quét & Cắt Highlights`;
        }
    }
}

function playHighlightClip(clipUrl, title) {
    playHighlightClipInline(clipUrl, title);
}

