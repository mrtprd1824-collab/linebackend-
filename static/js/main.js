// =======================================================
// START: Sound Notification Setup
// =======================================================
// 1. สร้าง Audio object เตรียมไว้แค่ครั้งเดียว
const notificationSound = new Audio('/static/sounds/newchats.mp3');
let canPlaySound = false; // เริ่มต้นโดยยังไม่อนุญาตให้เล่นเสียง

// 2. ฟังก์ชันสำหรับปลดล็อกเสียงเมื่อผู้ใช้คลิกครั้งแรก
function enableSound() {
    if (canPlaySound) return; // ทำงานแค่ครั้งเดียว

    // ทำให้การเล่นครั้งแรก "เงียบ" โดยการ Mute เสียงชั่วคราว
    notificationSound.muted = true;
    const promise = notificationSound.play();

    if (promise !== undefined) {
        promise.then(_ => {
            // เมื่อเล่นสำเร็จ ให้หยุดและยกเลิกการ Mute ทันที
            notificationSound.pause();
            notificationSound.currentTime = 0;
            notificationSound.muted = false;
            canPlaySound = true;
            console.log('🔊 Sound system activated silently by user interaction.');
            document.body.removeEventListener('click', enableSound, true);
        }).catch(error => {
            // ถ้ามีปัญหา ให้ยกเลิกการ Mute แล้วปล่อยให้ครั้งถัดไปลองใหม่
            notificationSound.muted = false;
            console.error("Silent sound activation failed:", error);
        });
    }
}

// 3. รอให้ผู้ใช้คลิกที่ไหนก็ได้ในหน้าเว็บเพื่อเปิดใช้งานเสียง
document.body.addEventListener('click', enableSound, true);
// =======================================================
// END: Sound Notification Setup
// =======================================================

/**
 * ★★★ [ย้ายมาไว้ตรงนี้] ★★★
 * แปลง ISO timestamp string ให้อยู่ในรูปแบบ "HH:mm" หรือ "DD Mon"
 * @param {string} isoString - เวลาในรูปแบบ ISO 8601 (เช่น "2025-10-15T12:30:00Z")
 * @returns {string} - เวลาที่จัดรูปแบบแล้ว
 */
function formatSidebarTimestamp(isoString) {
    if (!isoString) return '';

    const messageDate = new Date(isoString);
    const now = new Date();

    const isToday = messageDate.getDate() === now.getDate() &&
        messageDate.getMonth() === now.getMonth() &&
        messageDate.getFullYear() === now.getFullYear();

    if (isToday) {
        // ถ้าเป็นวันนี้: แสดงแค่ HH:mm
        return messageDate.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
    } else {
        // ถ้าเป็นวันอื่น: แสดงแค่ "15 Oct"
        return messageDate.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    }
}

function truncateDisplayName(name, maxLength = 20) {
    if (!name) return '';
    const normalized = String(name);
    if (normalized.length <= maxLength) {
        return normalized;
    }
    const sliceLength = Math.max(maxLength - 3, 0);
    return sliceLength > 0 ? normalized.slice(0, sliceLength) + '...' : normalized.slice(0, maxLength);
}

document.addEventListener('DOMContentLoaded', function () {
    // 1. STATE & VARIABLES
    window.failedMessageQueue = {};
    let currentUserId = null;
    let currentOaId = null;
    let currentUserDbId = null;
    let selectedImageFile = null;
    let availableQuickReplies = [];
    let currentOffset = 0;
    let totalMessages = 0;
    let isLoadingMore = false;
    let currentRoom = null;
    let isSearching = false;
    let currentFullNote = '';
    let currentUserTags = [];
    window.currentUserPictureUrl = null;



    const serverDataEl = document.getElementById('server-data');
    const SERVER_DATA = JSON.parse(serverDataEl.textContent);
    const currentUserEmail = SERVER_DATA.current_user_email;
    const socket = io();

    // 2. ELEMENT SELECTORS
    const userList = document.getElementById('user-list');
    const chatArea = document.getElementById('chat-area');
    const chatPlaceholder = document.querySelector('.chat-placeholder');
    const messagesContainer = document.getElementById('chat-messages');
    const replyForm = document.getElementById('reply-form');
    const replyMessageInput = document.getElementById('reply-message');
    const attachImageBtn = document.getElementById('attach-image-btn');
    const imageInput = document.getElementById('image-input');
    const imagePreviewModal = new bootstrap.Modal(document.getElementById('imagePreviewModal'));
    const previewImage = document.getElementById('preview-image');
    const confirmSendImageBtn = document.getElementById('confirm-send-image-btn');
    const imageViewModal = new bootstrap.Modal(document.getElementById('imageViewModal'));
    const fullImageView = document.getElementById('full-image-view');
    const stickerPickerModalEl = document.getElementById('stickerPickerModal');
    const stickerPickerModal = new bootstrap.Modal(stickerPickerModalEl);
    const quickReplyBtn = document.getElementById('quick-reply-btn');
    const quickReplyModal = new bootstrap.Modal(document.getElementById('quickReplyModal'));
    const quickReplyList = document.getElementById('quick-reply-list');
    const quickReplySearch = document.getElementById('quick-reply-search');
    const inlineQrResults = document.getElementById('inline-qr-results');
    const noteEditorModal = new bootstrap.Modal(document.getElementById('noteEditorModal'));
    const fullNoteTextarea = document.getElementById('full-note-textarea');
    const newMessageAlert = document.getElementById('new-message-alert');
    const tagsModal = new bootstrap.Modal(document.getElementById('tagsModal'));
    const saveTagsBtn = document.getElementById('save-tags-btn');
    const tagsChecklistContainer = document.getElementById('tags-checklist-container');
    const customerInfoPanel = document.getElementById('customer-info-panel');
    const infoPlaceholder = customerInfoPanel.querySelector('.info-placeholder');
    const infoArea = document.getElementById('info-area');

    // =======================================================
    // START: REAL-TIME UNREAD TIMER LOGIC
    // =======================================================

    /**
     * แปลงจำนวนวินาทีทั้งหมดให้เป็นรูปแบบ MM:SS
     * @param {number} totalSeconds - จำนวนวินาที
     * @returns {string} - สตริงในรูปแบบ MM:SS
     */
    function formatTime(totalSeconds) {
        if (totalSeconds < 0) totalSeconds = 0;

        // 1. คำนวณ ชั่วโมง, นาที, และวินาที ให้เป็นเลขจำนวนเต็ม
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = Math.floor(totalSeconds % 60);

        // 2. ทำให้เป็นเลข 2 หลักเสมอ (เช่น 01, 02)
        const paddedMinutes = String(minutes).padStart(2, '0');
        const paddedSeconds = String(seconds).padStart(2, '0');

        // 3. เลือกว่าจะแสดงผลแบบไหน
        if (hours > 0) {
            // ถ้าเกิน 1 ชั่วโมง ให้แสดง ชั่วโมง:นาที:วินาที
            const paddedHours = String(hours).padStart(2, '0');
            return `${paddedHours}:${paddedMinutes}:${paddedSeconds}`;
        } else {
            // ถ้าไม่ถึงชั่วโมง ให้แสดงแค่ นาที:วินาที
            return `${paddedMinutes}:${paddedSeconds}`;
        }
    }


    /**
     * อัปเดตตัวนับเวลาที่ยังไม่ได้อ่านทั้งหมดใน sidebar
     */
    function updateUnreadTimers() {
        // เลือกทุกรายการแชทที่มี data-unread-timestamp
        const conversationsWithUnread = document.querySelectorAll('[data-unread-timestamp]');

        conversationsWithUnread.forEach(convElement => {
            const timestamp = parseFloat(convElement.dataset.unreadTimestamp);
            const userId = convElement.dataset.userid;
            const oaId = convElement.dataset.oaid;
            const timerElement = document.getElementById(`timer-${userId}-${oaId}`);

            if (timerElement && timestamp) {
                const nowInSeconds = Math.floor(Date.now() / 1000);
                const secondsDiff = nowInSeconds - timestamp;
                timerElement.textContent = formatTime(secondsDiff);
            }
        });
    }

    // --- ★★★ ใช้ Listener ชุดใหม่นี้แทนของเก่า ★★★ ---
    infoArea.addEventListener('click', function (event) {
        // จัดการ 3 ปุ่มในที่เดียว: Status, Manage Tags, Edit Note
        handleStatusButtonClick(event);
        if (event.target.closest('#manage-tags-btn')) {
            openTagsModal();
        }
        if (event.target.closest('#edit-note-btn')) {
            fullNoteTextarea.value = currentFullNote;
            noteEditorModal.show();
        }
    });

    infoArea.addEventListener('submit', function (event) {
        // จัดการฟอร์ม Save Info
        if (event.target.id === 'user-info-form') {
            handleSaveUserInfo(event);
        }
    });

    // Event เมื่อกดปุ่ม Save Note ใน Modal
    document.getElementById('save-note-btn').addEventListener('click', async function () {
        const newNoteText = fullNoteTextarea.value;
        if (!currentUserDbId) return;

        try {
            const response = await fetch(`/chats/api/user_info/${currentUserDbId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                // เราใช้ Endpoint เดิม แต่ส่งแค่ note ไป
                body: JSON.stringify({
                    note: newNoteText,
                    // ส่งค่าเดิมไปด้วยเพื่อไม่ให้มันกลายเป็นค่าว่าง
                    nickname: document.getElementById('user-nickname').value,
                    phone: document.getElementById('user-phone').value,
                })
            });

            if (!response.ok) throw new Error('Failed to save note');

            // อัปเดต UI
            currentFullNote = newNoteText;
            const notePreview = document.getElementById('note-preview');
            notePreview.textContent = newNoteText ? newNoteText.replace(/\n/g, ' ') : 'Add a note...';

            noteEditorModal.hide();
            // โหลดแชทใหม่เพื่อให้เห็น Log การแก้ไข
            loadChatForUser(currentUserId, currentOaId);

        } catch (error) {
            console.error("Save note error:", error);
            alert("Failed to save note.");
        }
    });

    async function loadChatForUser(userId, oaId) {
        console.log(`--- Starting loadChatForUser for ${userId} ---`);
        let frozenTime = null;
        const userLink = document.querySelector(`.list-group-item-action[data-userid="${userId}"][data-oaid="${oaId}"]`);

        if (userLink) {
            // --- [แก้ไข] ย้าย Logic ทั้งหมดมาไว้ตรงนี้ ---
            // 1. คำนวณเวลาล่าสุด ณ วินาทีที่กด
            if (userLink.dataset.unreadTimestamp) {
                const timestamp = parseFloat(userLink.dataset.unreadTimestamp);
                const nowInSeconds = Math.floor(Date.now() / 1000);
                const secondsDiff = nowInSeconds - timestamp;
                frozenTime = formatTime(secondsDiff);
                console.log(`Timer calculated and frozen at: ${frozenTime}`);
            }

            // 2. อัปเดต UI ทันที
            userLink.classList.remove('status-unread');
            userLink.removeAttribute('data-unread-timestamp');
            const timerElement = userLink.querySelector('.unread-timer');
            if (timerElement) {
                if (frozenTime !== null) {
                    timerElement.textContent = frozenTime;
                }
                timerElement.classList.add('text-muted', 'timer-frozen');
                timerElement.classList.remove('text-danger');
            }

            // 3. จัดการ Active Class
            document.querySelectorAll('#user-list .list-group-item-action').forEach(link => link.classList.remove('active'));
            userLink.classList.add('active');
            // --- [จบส่วนแก้ไข] ---
        }

        chatPlaceholder.classList.add('d-none');
        chatArea.classList.remove('d-none');
        messagesContainer.innerHTML = '<p class="text-center text-muted">Loading messages...</p>';

        try {
            const data = await fetchChatData(userId, oaId, frozenTime);
            console.log("Data received from server for this user:", data.user);
            console.log("Tags for this user:", data.user.tags);

            currentUserId = userId;
            currentOaId = oaId;
            currentUserDbId = data.user.db_id;
            window.currentUserPictureUrl = data.user.picture_url;
            currentOffset = data.messages.length;
            totalMessages = data.total_messages;
            isLoadingMore = false;
            currentFullNote = data.user.note || '';


            // (โค้ดส่วน Render ทั้งหมดยาวๆ เหมือนเดิม)
            // 1. แสดง panel ข้อมูลลูกค้า และซ่อน placeholder
            infoPlaceholder.classList.add('d-none');
            infoArea.classList.remove('d-none');

            // 2. สร้าง HTML สำหรับคอลัมน์ข้อมูลลูกค้า
            infoArea.innerHTML = `
                <img src="${data.user.picture_url || '/static/images/No_profile.png'}" 
                    alt="Profile Picture" 
                    class="info-profile-pic">
                <form id="user-info-form">
                    <h5><i class="bi bi-person-badge"></i> User Info</h5>
                    <div class="mb-2">
                        <label for="user-nickname" class="form-label small">Nickname</label>
                        <input type="text" id="user-nickname" class="form-control form-control-sm" value="${data.user.nickname || ''}">
                    </div>
                    <div class="mb-3">
                        <label for="user-phone" class="form-label small">Phone</label>
                        <input type="text" id="user-phone" class="form-control form-control-sm" value="${data.user.phone || ''}">
                    </div>
                    <button type="submit" class="btn btn-sm btn-success w-100">Save Info</button>
                </form>

                <h5><i class="bi bi-tag"></i> Status & Tags</h5>
                <div class="btn-group btn-group-sm w-100 mb-2" role="group">
                    <button type="button" class="btn btn-outline-success status-btn" data-status="deposit">ฝาก</button>
                    <button type="button" class="btn btn-outline-warning status-btn" data-status="withdraw">ถอน</button>
                    <button type="button" class="btn btn-outline-danger status-btn" data-status="issue">ติดปัญหา</button>
                    <button type="button" class="btn btn-outline-dark status-btn" data-status="closed">ปิดเคส</button>
                </div>
                <div id="tag-management-area" class="mb-2">
                    <div id="user-tags-container"></div>
                    <button type="button" class="btn btn-outline-primary btn-sm" id="manage-tags-btn">
                        <i class="bi bi-tags-fill"></i> จัดการ Tag
                    </button>
                </div>
                <a href="/chats/download/${userId}?oa=${oaId}" target="_blank" class="btn btn-sm btn-outline-secondary w-100" title="Download Chat History">
                    <i class="bi bi-download"></i> Download History
                </a>

                <h5><i class="bi bi-pencil-square"></i> Note</h5>
                <textarea id="user-note" class="form-control" rows="5" placeholder="Add a note...">${data.user.note || ''}</textarea>
            `;

            // 3. สร้าง HTML สำหรับ Chat Header (ทำให้เรียบง่ายขึ้น)
            const chatHeader = document.getElementById('chat-header');
            chatHeader.innerHTML = `
                <a href="${data.account.manager_url || '#'}" target="_blank" rel="noopener noreferrer" class="text-muted d-block text-decoration-none" title="Open in LINE Official Account Manager">
                    <i class="bi bi-line"></i> Chatting on: <strong>@${data.account.name}</strong> <i class="bi bi-box-arrow-up-right small"></i>
                </a>
            `;

            currentUserTags = data.user.tags; // 1. เก็บ Tag ปัจจุบันไว้ในตัวแปร
            displayUserTags(data.user.tags);  // 2. เรียกใช้ฟังก์ชันวาด Tag

            messagesContainer.innerHTML = '';
            const imagePromises = [];
            data.messages.forEach(msg => { const promise = appendMessage(messagesContainer, msg); if (promise) { imagePromises.push(promise); } });
            Promise.all(imagePromises).then(() => {
                // หน่วงคำสั่ง scroll ไปท้ายสุดของ event queue
                setTimeout(() => {
                    messagesContainer.scrollTop = messagesContainer.scrollHeight;
                }, 0);
            });
            const qrResponse = await fetch(`/chats/api/quick_replies/${oaId}`);
            availableQuickReplies = await qrResponse.json();
            const newRoomName = `chat_${userId}_${oaId}`;
            if (currentRoom && currentRoom !== newRoomName) { socket.emit('leave', { room: currentRoom }); }
            socket.emit('join', { room: newRoomName });
            currentRoom = newRoomName;

            const blockedAlert = document.getElementById('blocked-user-alert');
            const replyForm = document.getElementById('reply-form'); // <--- เปลี่ยนมาใช้ ID ของฟอร์มโดยตรง

            if (data.user.is_blocked) {
                // ถ้าบล็อก: แสดงแถบแจ้งเตือน และซ่อนฟอร์มพิมพ์
                blockedAlert.classList.remove('d-none');
                replyForm.classList.add('d-none');
            } else {
                // ถ้าไม่บล็อก: ซ่อนแถบแจ้งเตือน และแสดงฟอร์มพิมพ์
                blockedAlert.classList.add('d-none');
                replyForm.classList.remove('d-none');
            }

        } catch (error) {
            console.error('Failed to load chat:', error);
            messagesContainer.innerHTML = '<p class="text-center text-danger">Failed to load conversation.</p>';
        }
    }

    function handleConversationUpdate(convData) {
        if (!convData || !convData.user_id) return;

        // --- ส่วนที่ 1: สร้าง Element ใหม่ (เหมือนเดิม) ---
        const existingUserLink = document.querySelector(`.list-group-item-action[data-userid="${convData.user_id}"][data-oaid="${convData.line_account_id}"]`);
        if (existingUserLink) {
            existingUserLink.remove();
        }

        const newLink = document.createElement('a');
        // ... (โค้ดส่วนสร้าง newLink ทั้งหมดเหมือนเดิม) ...
        newLink.href = "#";
        newLink.className = `list-group-item list-group-item-action d-flex align-items-center status-${convData.status}`;
        newLink.dataset.userid = convData.user_id;
        newLink.dataset.oaid = convData.line_account_id;
        if (convData.last_unread_timestamp) {
            newLink.dataset.unreadTimestamp = convData.last_unread_timestamp;
        } else {
            delete newLink.dataset.unreadTimestamp;
        }
        const defaultAvatar = "/static/images/No_profile.png";
        const unreadBadge = (convData.unread_count && convData.unread_count > 0) ? `<span class="badge bg-danger rounded-pill">${convData.unread_count}</span>` : '';
        const timerHTML = `<small class="text-danger me-2 unread-timer" id="timer-${convData.user_id}-${convData.line_account_id}"></small>`;
        const readByHTML = convData.read_by ? `<small class="text-muted read-by-badge">${convData.read_by}</small>` : '';
        const truncatedMessage = convData.last_message_content;
        let tagsHTML = '';
        if (convData.tags && convData.tags.length > 0) {
            tagsHTML = convData.tags.map(tag => `<span class="badge me-1" style="background-color: ${tag.color}; color: white; font-size: 0.65em;">${tag.name}</span>`).join('');
        }
        const displayTime = formatSidebarTimestamp(convData.last_message_iso_timestamp);

        newLink.innerHTML = `
        <img src="${convData.picture_url || defaultAvatar}" alt="Profile" class="rounded-circle me-3" style="width: 50px; height: 50px;">
        <div class="flex-grow-1">
            <div class="d-flex w-100 justify-content-between">
                <strong class="mb-1">${truncateDisplayName(convData.display_name)}</strong>
                <div>${timerHTML}${unreadBadge}</div>
            </div>
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <small class="text-muted me-2">@${convData.oa_name}</small>
                    ${tagsHTML}
                </div>
                <small class="text-muted">${displayTime}</small>
            </div>
            <p class="mb-0 text-muted small sidebar-last-message">
                <span class="message-preview">
                    <span>${convData.last_message_prefix}</span> ${truncatedMessage}
                </span>
                ${readByHTML}
            </p>
        </div>`;

        // --- ★★★ ส่วนที่ 2: Logic ใหม่สำหรับหาตำแหน่งที่จะแทรก ★★★ ---
        const userList = document.getElementById('user-list');

        if (convData.status === 'closed') {
            // --- ถ้าสถานะเป็น 'closed' ---
            // ให้หาแชท 'closed' อันแรกสุดที่มีอยู่
            const firstClosed = userList.querySelector('.status-closed');
            if (firstClosed) {
                // ถ้าเจอ ให้แทรก "ก่อนหน้า" แชท closed อันแรก
                userList.insertBefore(newLink, firstClosed);
            } else {
                // ถ้าไม่เจอแชท closed เลย ให้เอาไปต่อท้ายสุด
                userList.appendChild(newLink);
            }
        } else {
            // --- ถ้าเป็นสถานะอื่นๆ (unread, read, issue, etc.) ---
            // ให้นำไปวางไว้บนสุดเหมือนเดิม
            userList.prepend(newLink);
        }

        if (String(convData.user_id) === String(currentUserId) && String(convData.line_account_id) === String(currentOaId)) {
            newLink.classList.add('active');
        }
    }


    // 4. SOCKET.IO EVENT LISTENERS (ตัวดักฟังจาก Server)

    async function reloadSidebar() {
        console.log('🔄 Received resort signal. Reloading sidebar...');
        try {
            // 1. ยิง request ไปที่หน้าแชทหลัก เพื่อขอ HTML ล่าสุด
            const response = await fetch('/chats/');
            if (!response.ok) {
                throw new Error('Failed to fetch sidebar content');
            }
            const htmlText = await response.text();

            // 2. แปลงข้อความ HTML ให้กลายเป็น Document object ชั่วคราวใน memory
            const parser = new DOMParser();
            const doc = parser.parseFromString(htmlText, 'text/html');

            // 3. ดึงเนื้อหาใหม่จาก Document ชั่วคราวนั้น
            const newUserListContent = doc.getElementById('user-list').innerHTML;
            const newPaginationContent = doc.getElementById('sidebar-pagination-container').innerHTML;

            // 4. นำเนื้อหาใหม่ไป "สวมทับ" ของเก่าบนหน้าเว็บจริง
            document.getElementById('user-list').innerHTML = newUserListContent;
            document.getElementById('sidebar-pagination-container').innerHTML = newPaginationContent;


            console.log('✅ Sidebar reloaded successfully.');
        } catch (error) {
            console.error('Failed to reload sidebar:', error);
        }
    }

    // =======================================================
    // START: SOCKET.IO EVENT LISTENERS (FINAL DEBUG VERSION)
    // =======================================================

    console.log('Attempting to connect to Socket.IO server...');

    socket.on('connect', () => {
        console.log('✅✅✅ SUCCESS: Connected to WebSocket server! Session ID:', socket.id);

        // ดึง group_ids ที่ใช้งานอยู่จาก SERVER_DATA ที่ Flask ส่งมาให้
        const activeGroupIds = SERVER_DATA.selected_group_ids || [];
        socket.emit('update_active_groups', { group_ids: activeGroupIds });
    });

    socket.on('connect_error', (err) => {
        console.error('🔥🔥🔥 FAILED: Socket.IO Connection Error! 🔥🔥🔥');
        console.error('Error Type:', err.name);
        console.error('Error Message:', err.message);
        if (err.data) {
            console.error('Error Data:', err.data);
        }
    });

    socket.on('disconnect', (reason) => {
        console.warn('🔌 Socket.IO Disconnected. Reason:', reason);
    });

    socket.on('render_conversation_update', (freshData) => {
        if (isSearching) {
            console.log('Search is active. Ignoring real-time sidebar update.');

            // (ทางเลือก) แสดงป้ายเตือนว่ามีอัปเดตใหม่ แต่ไม่ไปรบกวนผลการค้นหา
            const newMessageAlert = document.getElementById('new-message-alert');
            if (newMessageAlert) {
                newMessageAlert.style.display = 'block';
                newMessageAlert.textContent = 'New updates available. Clear search to see them.';
            }
            return; // ออกจากฟังก์ชันทันที
        }

        if (!freshData || !freshData.user_id) return;

        const urlParams = new URLSearchParams(window.location.search);
        const currentFilter = urlParams.get('status_filter') || 'all';
        const existingElement = document.querySelector(`.list-group-item-action[data-userid="${freshData.user_id}"][data-oaid="${freshData.line_account_id}"]`);

        // --- ★★★ Logic ใหม่ทั้งหมด ★★★ ---

        // 1. ตรวจสอบว่าสถานะใหม่ของแชทตรงกับฟิลเตอร์ปัจจุบันหรือไม่ (หรือเราอยู่ที่หน้า 'ทั้งหมด')
        const shouldBeVisible = (currentFilter === 'all') || (freshData.status === currentFilter);

        if (shouldBeVisible) {
            // 2. ถ้าแชทควรจะแสดงผลในหน้านี้: ให้เรียกใช้ handleConversationUpdate
            // ฟังก์ชันนี้จะลบของเก่า (ถ้ามี) แล้วสร้างของใหม่ใส่เข้าไป ทำให้ข้อมูลเป็นปัจจุบันเสมอ
            handleConversationUpdate(freshData);
        } else {
            // 3. ถ้าแชท "ไม่ควร" แสดงผลในหน้านี้อีกต่อไป (เช่น สถานะเปลี่ยนไปแล้ว)
            // และถ้าแชทนั้นมีแสดงอยู่ใน Sidebar ของเรา
            if (existingElement) {
                // ให้ลบมันทิ้งไปจากหน้าจอทันที
                existingElement.remove();
            }
        }
    });

    socket.on('new_message', function (msgData) {
        // --- ส่วนที่ 1: จัดการการแจ้งเตือน (เสียง & Desktop) ---
        const isAdminMessage = msgData.sender_type === 'admin';
        if (msgData.message_type !== 'event' && !isAdminMessage) {
            // เล่นเสียง
            notificationSound.play().catch(e => console.warn("Sound notification failed.", e));

            // แสดง Desktop notification
            if (Notification.permission === "granted") {
                const userLink = document.querySelector(`.list-group-item-action[data-userid="${msgData.user_id}"][data-oaid="${msgData.oa_id}"]`);
                let title = "มีข้อความใหม่";
                let iconUrl = "/static/images/default-avatar.png";
                if (userLink) {
                    title = `ข้อความใหม่จาก ${userLink.querySelector('strong').textContent}`;
                    iconUrl = userLink.querySelector('img').src;
                }
                const notification = new Notification(title, { body: msgData.content, icon: iconUrl, tag: msgData.user_id });
                notification.onclick = () => {
                    window.focus();
                    if (userLink) userLink.click();
                };
            }
        }

        // --- ส่วนที่ 2: อัปเดตหน้าต่างแชทที่เปิดอยู่ ---
        const isForCurrentChat = String(msgData.user_id) === String(currentUserId) &&
            String(msgData.oa_id) === String(currentOaId);

        if (isForCurrentChat) {
            appendMessage(messagesContainer, msgData);
        }
    });

    // =======================================================
    // END: SOCKET.IO EVENT LISTENERS
    // =======================================================





    // handle

    async function handleSendTextMessage(e) {
        e.preventDefault();
        const messageText = replyMessageInput.value.trim();
        if (!messageText || !currentUserId) return;

        const originalMessage = replyMessageInput.value;
        replyMessageInput.value = '';
        inlineQrResults.style.display = 'none';

        const sendButton = document.getElementById('send-btn');
        if (sendButton) sendButton.disabled = true;

        try {
            // 1. เรียก API และรอจนกว่าจะได้ผลลัพธ์กลับมา
            const result = await sendTextMessage(currentUserId, currentOaId, messageText);

            // 2. ตรวจสอบว่า Server ทำงานสำเร็จหรือไม่
            if (result && result.db_saved_successfully) {
                // 3. ถ้าสำเร็จ, นำข้อมูลที่สมบูรณ์จาก Server มาวาด UI
                const promise = appendMessage(messagesContainer, result);

                Promise.resolve(promise).then(() => {
                    messagesContainer.scrollTop = messagesContainer.scrollHeight;
                });

                // --- ★★★ 4. ตรวจสอบสถานะและเรียก markMessageAsFailed ที่นี่ ★★★ ---
                if (!result.line_sent_successfully) {
                    markMessageAsFailed(result.id, result.line_api_error_message || 'ส่งข้อความไป LINE ไม่สำเร็จ');
                }
            } else {
                throw new Error(result.message || 'Server did not process the message.');
            }
        } catch (error) {
            console.error("Failed to send message:", error);
            alert('การส่งข้อความล้มเหลว: ' + error.message);
            replyMessageInput.value = originalMessage;
        } finally {
            if (sendButton) sendButton.disabled = false;
        }
    }





    function handleImageSelection(event) {
        const file = event.target.files[0];
        processAndPreviewImage(file);
    }

    async function handleSendImage() {
        if (!selectedImageFile || !currentUserId) return;
        imagePreviewModal.hide(); // ปิด Modal ก่อน

        try {
            // 1. ส่งรูปภาพไปที่ Server และรอจนกว่าจะได้ข้อมูลที่สมบูรณ์กลับมา
            const result = await sendImageMessage(currentUserId, currentOaId, selectedImageFile);

            // 2. ตรวจสอบว่า Server ตอบกลับมาว่าสำเร็จหรือไม่
            if (result && result.db_saved_successfully) {
                // 3. ถ้าสำเร็จ, ค่อยนำข้อมูลจาก Server มาแสดงผลเพียงครั้งเดียว
                const promise = appendMessage(messagesContainer, result);
                Promise.resolve(promise).then(() => {
                    messagesContainer.scrollTop = messagesContainer.scrollHeight;
                });
            } else {
                // ถ้า Server ตอบกลับมาว่าไม่สำเร็จ
                throw new Error(result.db_error || 'Failed to process image on server');
            }
        } catch (error) {
            console.error('Send image error:', error);
            alert('Failed to send image.');
        } finally {
            // เคลียร์ค่าหลังจากทำงานเสร็จเสมอ
            imageInput.value = '';
            selectedImageFile = null;
            replyMessageInput.focus();
        }
    }

    function processAndPreviewImage(file) {
        if (file && file.type.startsWith('image/')) {
            selectedImageFile = file;
            const reader = new FileReader();
            reader.onload = (e) => {
                previewImage.src = e.target.result;
                imagePreviewModal.show();
            }
            reader.readAsDataURL(file);
        }
    }

    async function handleSaveUserInfo(event) {
        event.preventDefault();

        if (!currentUserDbId) {
            console.error("Cannot save, currentUserDbId is not set.");
            return;
        }

        const nickname = document.getElementById('user-nickname').value;
        const phone = document.getElementById('user-phone').value;
        const note = document.getElementById('user-note').value;

        try {
            // เราจะเรียก API ให้บันทึกข้อมูลเหมือนเดิม
            await saveUserInfo(currentUserDbId, nickname, phone, note);

            const saveBtn = document.querySelector('#user-info-form button[type="submit"]');
            if (saveBtn) {
                saveBtn.textContent = 'Saved!';
                setTimeout(() => { saveBtn.textContent = 'Save Info'; }, 2000);
            }

        } catch (error) {
            console.error('Save user info error:', error);
            alert('Failed to save user info.');
        }
    }

    async function handleStickerSelection(event) {
        if (event.target && event.target.classList.contains('sticker-item')) {
            const { packageid, stickerid } = event.target.dataset;
            if (!packageid || !stickerid || !currentUserId) return;
            stickerPickerModal.hide();

            try {
                // 1. ส่งข้อมูลสติกเกอร์ไป Server และรอการตอบกลับ
                const result = await sendStickerMessage(currentUserId, currentOaId, packageid, stickerid);

                // 2. ตรวจสอบและแสดงผลจากข้อมูลที่ Server ส่งกลับมา
                if (result && result.db_saved_successfully) {
                    const promise = appendMessage(messagesContainer, result);
                    Promise.resolve(promise).then(() => {
                        messagesContainer.scrollTop = messagesContainer.scrollHeight;
                    });
                    replyMessageInput.focus();
                } else {
                    throw new Error('Failed to process sticker on server');
                }

            } catch (error) {
                console.error('Send sticker error:', error);
                alert('Failed to send sticker.');
            }
        }
    }


    async function handleScrollToLoadMore() {
        if (isLoadingMore || messagesContainer.scrollTop !== 0 || currentOffset >= totalMessages) {
            return;
        }
        isLoadingMore = true;
        const loadingIndicator = document.createElement('p');
        loadingIndicator.className = 'text-center text-muted small py-2';
        loadingIndicator.textContent = 'Loading older messages...';
        messagesContainer.prepend(loadingIndicator);

        try {
            const data = await fetchMoreMessages(currentUserId, currentOaId, currentOffset);
            const oldScrollHeight = messagesContainer.scrollHeight;
            loadingIndicator.remove();

            if (data.messages.length > 0) {
                data.messages.forEach(msg => appendMessage(messagesContainer, msg, true));
                messagesContainer.scrollTop = messagesContainer.scrollHeight - oldScrollHeight;
                currentOffset += data.messages.length;
            } else {
                const endOfHistory = document.createElement('p');
                endOfHistory.className = 'text-center text-muted small py-3';
                endOfHistory.textContent = 'End of conversation history';
                messagesContainer.prepend(endOfHistory);
                totalMessages = currentOffset;
            }
        } catch (error) {
            console.error("Load more error:", error);
            loadingIndicator.textContent = 'Failed to load messages.';
        } finally {
            isLoadingMore = false;
        }
    }

    async function loadStickers() {
        const stickerGrid = document.getElementById('sticker-grid');
        if (stickerGrid.dataset.loaded) return;
        try {
            const stickers = await fetchStickers();
            stickerGrid.innerHTML = '';
            stickers.forEach(sticker => {
                const stickerEl = document.createElement('img');
                stickerEl.src = `https://stickershop.line-scdn.net/stickershop/v1/sticker/${sticker.stickerId}/ANDROID/sticker.png`;
                stickerEl.classList.add('sticker-item');
                stickerEl.dataset.packageid = sticker.packageId;
                stickerEl.dataset.stickerid = sticker.stickerId;
                stickerGrid.appendChild(stickerEl);
            });
            stickerGrid.dataset.loaded = "true";
        } catch (error) {
            console.error('Sticker load error:', error);
            stickerGrid.innerHTML = '<p class="text-center text-danger">Failed to load stickers.</p>';
        }
    }

    function handleQuickReplySelection(e) {
        const item = e.target.closest('.quick-reply-item');
        if (item) {
            replyMessageInput.value = item.dataset.message;
            quickReplyModal.hide();
            replyMessageInput.focus();
        }
    }

    function handleQuickReplySearch() {
        const filter = quickReplySearch.value.toUpperCase();
        const filteredReplies = availableQuickReplies.filter(r =>
            r.shortcut.toUpperCase().includes(filter) || r.message.toUpperCase().includes(filter)
        );
        populateQuickReplyList(quickReplyList, filteredReplies);
    }

    function handleInlineQuickReply(e) {
        const text = e.target.value;
        if (text.length > 0) {
            const searchTerm = text.toUpperCase();
            // --- ปัญหาอยู่ตรงนี้ ---
            const filteredReplies = availableQuickReplies.filter(r =>
                r.shortcut.toUpperCase().includes(searchTerm));
            if (filteredReplies.length > 0) {
                populateInlineQuickReply(inlineQrResults, filteredReplies);
                inlineQrResults.style.display = 'block';
            } else {
                inlineQrResults.style.display = 'none';
            }
        } else {
            inlineQrResults.style.display = 'none';
        }
    }

    function handleInlineQrSelection(e) {
        e.preventDefault();
        const item = e.target.closest('.inline-qr-item');
        if (item) {
            replyMessageInput.value = item.dataset.message;
            inlineQrResults.style.display = 'none';
            replyMessageInput.focus();
        }
    }

    async function performSearch(query) {
        if (query.length < 2) { // เริ่มค้นหาเมื่อพิมพ์อย่างน้อย 2 ตัวอักษร
            // ถ้าคำค้นหาสั้นไป ให้โหลดรายการแชทล่าสุดกลับมา (ถ้าต้องการ)
            // หรือเคลียร์รายการให้ว่าง
            // userList.innerHTML = ''; // ตัวเลือก: เคลียร์รายการ
            return;
        }

        try {
            const response = await fetch(`/chats/api/search_conversations?q=${query}`);
            if (!response.ok) throw new Error('Search request failed');
            const users = await response.json();
            renderUserList(users);
        } catch (error) {
            console.error("Search error:", error);
        }
    }

    // [เพิ่ม] ฟังก์ชันใหม่สำหรับวาดรายการ User เพื่อใช้ซ้ำได้
    function renderUserList(users) {
        const userList = document.getElementById('user-list');
        userList.innerHTML = ''; // เคลียร์รายการเก่าทิ้ง

        if (users.length === 0) {
            userList.innerHTML = '<li class="list-group-item">No conversations found.</li>';
            return;
        }

        users.forEach(user => {
            const userLink = document.createElement('a');
            userLink.href = "#";
            userLink.className = "list-group-item list-group-item-action d-flex align-items-center";
            userLink.dataset.userid = user.user_id;
            userLink.dataset.oaid = user.line_account_id;

            const defaultAvatar = "{{ url_for('static', filename='images/default-avatar.png') }}";
            const unreadBadge = user.is_read ? '' : '<span class="badge bg-danger rounded-pill">[U]</span>';

            userLink.innerHTML = `
            <img src="${user.picture_url || defaultAvatar}"
                 alt="Profile" class="rounded-circle me-3" style="width: 50px; height: 50px;">
            <div class="flex-grow-1">
                <div class="d-flex w-100 justify-content-between">
                    <strong class="mb-1">${truncateDisplayName(user.display_name)}</strong>
                    ${unreadBadge}
                </div>
                <small class="text-muted">@${user.oa_name}</small>
                <p class="mb-0 text-muted text-truncate small">
                    <span class="${user.is_read ? 'text-primary' : ''}">${user.last_message_prefix}</span> 
                    ${user.last_message_content}
                </p>
            </div>
        `;
            userList.appendChild(userLink);
        });
    }

    async function handleStatusButtonClick(event) {
        const statusButton = event.target.closest('.status-btn');
        if (!statusButton) return;

        const newStatus = statusButton.dataset.status;
        if (!currentUserDbId || !newStatus) return;

        try {
            const response = await fetch(`/chats/api/conversation_status/${currentUserDbId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus })
            });
            if (!response.ok) throw new Error('Failed to update status');

            const result = await response.json();

            const userLink = document.querySelector(`.list-group-item-action[data-userid="${currentUserId}"][data-oaid="${currentOaId}"]`);
            if (userLink) {
                userLink.className = 'list-group-item list-group-item-action d-flex align-items-center'; // Reset classes
                userLink.classList.add(`status-${result.new_status}`);
            }

        } catch (error) {
            console.error("Status update error:", error);
            alert("Failed to update status.");
        }
    }

    function checkAndHideAlert() {
        const params = new URLSearchParams(window.location.search);
        const page = parseInt(params.get('page')) || 1;
        if (page === 1 && newMessageAlert) {
            newMessageAlert.style.display = 'none';
        }
    }

    // 4. INITIALIZATION (การตั้งค่าเริ่มต้น)

    //  เพิ่ม Event Listener ให้กับป้าย
    checkAndHideAlert();
    if (newMessageAlert) {
        newMessageAlert.addEventListener('click', () => {
            window.location.href = '/chats/'; // เมื่อคลิกให้ไปที่หน้าแรก
        });
    }

    //  ฟังก์ชันสำหรับเช็คและซ่อนป้ายตอนโหลดหน้า

    userList.addEventListener('click', (e) => {
        e.preventDefault();
        const userLink = e.target.closest('a.list-group-item-action');
        if (userLink) {
            currentUserId = userLink.dataset.userid;
            currentOaId = userLink.dataset.oaid;
            if (currentUserId && currentOaId) {
                loadChatForUser(currentUserId, currentOaId);
                document.querySelectorAll('#user-list .list-group-item-action').forEach(link => {
                    link.classList.remove('active');
                });
                // 2. เพิ่ม active class ให้กับรายการที่เพิ่งคลิก
                userLink.classList.add('active');
            }
        }
    });

    const enableNotificationsBtn = document.getElementById('enable-notifications-btn');
    if (enableNotificationsBtn) {
        enableNotificationsBtn.addEventListener('click', (event) => {
            event.preventDefault();

            // 1. ตรวจสอบว่า Browser รองรับ Notification API หรือไม่
            if (!("Notification" in window)) {
                alert("This browser does not support desktop notification");
            }
            // 2. ตรวจสอบสถานะการอนุญาตปัจจุบัน
            else if (Notification.permission === "granted") {
                alert("Desktop notifications are already enabled.");
                // สร้างการแจ้งเตือนตัวอย่าง
                new Notification("เปิดการแจ้งเตือนสำเร็จ!", { body: "คุณจะได้รับการแจ้งเตือนเมื่อมีข้อความใหม่" });
            }
            else if (Notification.permission !== "denied") {
                // 3. ถ้ายังไม่เคยถาม หรือยังไม่ได้ปฏิเสธ ให้ขออนุญาต
                Notification.requestPermission().then((permission) => {
                    // 4. หลังจากผู้ใช้เลือกแล้ว
                    if (permission === "granted") {
                        alert("Desktop notifications have been enabled successfully!");
                        new Notification("เปิดการแจ้งเตือนสำเร็จ!", { body: "คุณจะได้รับการแจ้งเตือนเมื่อมีข้อความใหม่" });
                    } else {
                        alert("You have denied notification permissions.");
                    }
                });
            } else {
                alert("You have previously denied notifications. Please enable them in your browser settings.");
            }
        });
    }

    // ฟังก์ชันสำหรับเปิด Modal (นำ Logic เดิมมาใส่ในนี้)
    async function openTagsModal() {
        if (!currentUserDbId) return;

        try {
            // 1. ดึง Tag ทั้งหมดในระบบจาก API
            const response = await fetch('/api/tags');
            if (!response.ok) throw new Error('Could not fetch tags');
            const allTags = await response.json();

            // 2. สร้าง Checkbox list
            const tagsChecklistContainer = document.getElementById('tags-checklist-container');
            tagsChecklistContainer.innerHTML = ''; // เคลียร์ของเก่า

            allTags.forEach(tag => {
                const isChecked = currentUserTags.some(userTag => userTag.id === tag.id);
                const div = document.createElement('div');
                div.classList.add('form-check');
                div.innerHTML = `
                <input class="form-check-input" type="checkbox" value="${tag.id}" id="tag-${tag.id}" ${isChecked ? 'checked' : ''}>
                <label class="form-check-label" for="tag-${tag.id}">
                    <span class="badge" style="background-color: ${tag.color}; color: #fff;">${tag.name}</span>
                </label>
            `;
                tagsChecklistContainer.appendChild(div);
            });

            // 3. เปิด Modal
            tagsModal.show();

        } catch (error) {
            console.error("Failed to open tags modal:", error);
            alert("Could not load tags.");
        }
    }


    // เมื่อกดปุ่ม "Save changes" ใน Modal
    saveTagsBtn.addEventListener('click', async () => {
        if (!currentUserDbId) return;

        const selectedTagIds = Array.from(tagsChecklistContainer.querySelectorAll('input:checked')).map(input => parseInt(input.value));
        const originalTagIds = currentUserTags.map(tag => tag.id);

        try {
            // หา Tag ที่ต้องเพิ่ม
            const tagsToAdd = selectedTagIds.filter(id => !originalTagIds.includes(id));
            // หา Tag ที่ต้องลบ
            const tagsToRemove = originalTagIds.filter(id => !selectedTagIds.includes(id));

            // ส่ง API request สำหรับการเพิ่มและลบ
            for (const tagId of tagsToAdd) {
                await fetch(`/api/tags/${currentUserDbId}/assign`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tag_id: tagId })
                });
            }
            for (const tagId of tagsToRemove) {
                await fetch(`/api/tags/${currentUserDbId}/remove/${tagId}`, {
                    method: 'DELETE'
                });
            }

            // โหลดข้อมูล chat ใหม่อีกครั้งเพื่ออัปเดตหน้าจอ
            await loadChatForUser(currentUserId, currentOaId);

        } catch (error) {
            console.error("Failed to save tags:", error);
            alert("An error occurred while saving tags.");
        } finally {
            tagsModal.hide(); // ปิด Modal
        }
    });


    // --- [เพิ่ม] Event Listener สำหรับ Keyboard Shortcut (F4) ---
    document.addEventListener('keydown', function (event) {
        // ตรวจสอบว่าปุ่มที่กดคือ F4 (keyCode คือ 115)
        // และต้องมีการเปิดแชทอยู่ (currentUserId ไม่ใช่ null)
        if (event.key === 'F4' || event.keyCode === 115) {

            // หยุดการทำงานปกติของปุ่ม F4 (เช่น การเปิดเมนูของเบราว์เซอร์)
            event.preventDefault();

            // ตรวจสอบว่ามีแชทเปิดอยู่จริงหรือไม่
            if (!currentUserId || !currentUserDbId) {
                console.log("No active chat to close.");
                return; // ถ้าไม่มีแชทเปิดอยู่ ก็ไม่ต้องทำอะไร
            }

            // หาปุ่ม "ปิดเคส" ในหน้าเว็บ
            const closeCaseButton = document.querySelector('.status-btn[data-status="closed"]');

            if (closeCaseButton) {
                console.log("F4 pressed, clicking 'Close Case' button...");
                // สั่งให้ JavaScript คลิกปุ่มนั้นแทนเรา
                closeCaseButton.click();
            } else {
                console.log("Could not find the 'Close Case' button.");
            }
        }
    });

    replyForm.addEventListener('submit', handleSendTextMessage);
    confirmSendImageBtn.addEventListener('click', handleSendImage);
    attachImageBtn.addEventListener('click', () => imageInput.click());
    imageInput.addEventListener('change', handleImageSelection);
    messagesContainer.addEventListener('scroll', handleScrollToLoadMore);
    messagesContainer.addEventListener('click', (event) => {
        if (event.target.classList.contains('chat-image')) {
            fullImageView.src = event.target.dataset.src;
            imageViewModal.show();
        }
    });





    messagesContainer.addEventListener('scroll', handleScrollToLoadMore);

    // --- สติ๊กเกอร์ ---
    stickerPickerModalEl.addEventListener('show.bs.modal', loadStickers);
    stickerPickerModalEl.addEventListener('click', handleStickerSelection);

    // --- Quick Reply ---
    quickReplyBtn.addEventListener('click', () => {
        populateQuickReplyList(quickReplyList, availableQuickReplies);
        quickReplyModal.show();
    });

    quickReplyList.addEventListener('click', handleQuickReplySelection);
    quickReplySearch.addEventListener('keyup', handleQuickReplySearch);
    replyMessageInput.addEventListener('keyup', handleInlineQuickReply);
    inlineQrResults.addEventListener('click', handleInlineQrSelection);
    messagesContainer.addEventListener('click', (event) => {
        if (event.target.classList.contains('chat-image')) {
            fullImageView.src = event.target.dataset.src;
            imageViewModal.show();
        }
    });

    const searchInput = document.getElementById('user-search-input');
    const searchBtn = document.getElementById('user-search-btn');

    // ฟังก์ชันสำหรับเริ่มการค้นหา
    function triggerSearch() {
        const query = searchInput.value.trim();
        if (query) {
            isSearching = true; // ★★★ ตั้งสถานะว่ากำลังค้นหา ★★★
            console.log(`Starting search for: "${query}"`);
            performSearch(query); // เรียกใช้ฟังก์ชัน performSearch เดิมของคุณ
        }
    }

    // Event Listener สำหรับช่องค้นหา
    if (searchInput) {
        // เมื่อกดปุ่ม Search
        searchBtn.addEventListener('click', triggerSearch);

        // เมื่อกด Enter
        searchInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                triggerSearch();
            }
        });

        // ★★★ ส่วนสำคัญ: เมื่อลบข้อความค้นหาจนหมด ★★★
        searchInput.addEventListener('input', function () {
            if (searchInput.value.trim() === '') {
                isSearching = false; // ★★★ ยกเลิกสถานะการค้นหา ★★★
                console.log('Search cleared. Reloading default chat list.');
                // กลับไปที่หน้าแรกเพื่อโหลดรายการแชทล่าสุด
                window.location.href = '/chats/';
            }
        });
    }

    replyMessageInput.addEventListener('paste', function (event) {
        const items = (event.clipboardData || event.originalEvent.clipboardData).items;
        for (let index in items) {
            const item = items[index];
            if (item.kind === 'file' && item.type.includes('image')) {
                event.preventDefault();
                const file = item.getAsFile();
                processAndPreviewImage(file);
                break; // เจอรูปแล้ว หยุดทำงานได้เลย
            }
        }
    });

    replyMessageInput.addEventListener('keydown', function (event) {
        // ตรวจสอบว่าปุ่มที่กดคือ 'Enter' และไม่ได้กด 'Shift' ค้างไว้
        if (event.key === 'Enter' && !event.shiftKey) {
            // 1. ป้องกันการขึ้นบรรทัดใหม่โดยอัตโนมัติ
            event.preventDefault();

            // 2. หาปุ่ม Send แล้วสั่งให้คลิกเพื่อส่งข้อความ
            const sendButton = document.getElementById('send-btn');
            if (sendButton) {
                sendButton.click();
            }
        }
        // ถ้ากด Shift + Enter, เราจะไม่ทำอะไรเลย ปล่อยให้เบราว์เซอร์ทำงานตามปกติ (คือขึ้นบรรทัดใหม่)
    });

    replyMessageInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    updateUnreadTimers();
    // ตั้งให้ทำงานทุกๆ 1 วินาที
    setInterval(updateUnreadTimers, 1000);

    // ★★★ 4. เพิ่มโค้ด Drag and Drop ทั้งหมดนี้เข้าไป ★★★

    const chatInputArea = document.querySelector('.chat-input');

    // Event 1: เมื่อลากไฟล์เข้ามาในพื้นที่เป้าหมาย
    chatInputArea.addEventListener('dragenter', (event) => {
        event.preventDefault();
        chatInputArea.classList.add('drag-over');
    });

    // Event 2: เมื่อลากไฟล์ค้างไว้เหนือพื้นที่เป้าหมาย (สำคัญมาก)
    chatInputArea.addEventListener('dragover', (event) => {
        event.preventDefault(); // ป้องกันไม่ให้เบราว์เซอร์เปิดไฟล์เอง
        chatInputArea.classList.add('drag-over');
    });

    // Event 3: เมื่อลากไฟล์ออกจากพื้นที่เป้าหมาย
    chatInputArea.addEventListener('dragleave', (event) => {
        chatInputArea.classList.remove('drag-over');
    });

    // Event 4: เมื่อปล่อยไฟล์ลงในพื้นที่เป้าหมาย (หัวใจหลัก)
    chatInputArea.addEventListener('drop', (event) => {
        event.preventDefault(); // ป้องกันไม่ให้เบราว์เซอร์เปิดไฟล์เอง
        chatInputArea.classList.remove('drag-over');

        const files = event.dataTransfer.files;
        if (files.length > 0) {
            // ดึงไฟล์แรกที่ลากมา
            const file = files[0];
            // ส่งไปให้ฟังก์ชันกลางที่เราสร้างไว้จัดการต่อ
            processAndPreviewImage(file);
        }
    });

    const applyFilterBtn = document.getElementById('apply-group-filter-btn'); // **คุณอาจจะต้องเปลี่ยน id นี้ให้ตรงกับปุ่มของคุณ**
    if (applyFilterBtn) {
        applyFilterBtn.addEventListener('click', function () {
            // เมื่อกด Apply Filter ให้อ่านค่า checkbox ที่เลือกใหม่
            const selectedIds = Array.from(document.querySelectorAll('.group-checkbox:checked')).map(cb => parseInt(cb.value));
            // แล้วส่งไปอัปเดตที่ server ทันที
            socket.emit('update_active_groups', { group_ids: selectedIds });

            // หมายเหตุ: ส่วนนี้เป็นการยิง socket event ควบคู่ไปกับการ submit form เดิมของคุณ
            // ไม่ต้องลบโค้ด submit form เดิมออก
        });
    }
});
