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
    let currentFullNote = '';



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
    const searchInput = document.getElementById('user-search-input');
    const noteEditorModal = new bootstrap.Modal(document.getElementById('noteEditorModal'));
    const fullNoteTextarea = document.getElementById('full-note-textarea');
    const newMessageAlert = document.getElementById('new-message-alert');


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

    // =======================================================
    // END: REAL-TIME UNREAD TIMER LOGIC
    // =======================================================

    // 3. EVENT HANDLERS (ฟังก์ชันจัดการ Event)

    // Event เมื่อมีการคลิกที่ปุ่ม Edit Note
    chatArea.addEventListener('click', function (event) {
        if (event.target.closest('#edit-note-btn')) {
            // ดึง Note ทั้งหมดมาใส่ใน Textarea ของ Modal แล้วเปิด Modal
            fullNoteTextarea.value = currentFullNote;
            noteEditorModal.show();
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

            currentUserId = userId;
            currentOaId = oaId;
            currentUserDbId = data.user.db_id;
            currentOffset = data.messages.length;
            totalMessages = data.total_messages;
            isLoadingMore = false;
            currentFullNote = data.user.note || '';

            // (โค้ดส่วน Render ทั้งหมดยาวๆ เหมือนเดิม)
            const chatHeader = document.getElementById('chat-header');
            chatHeader.innerHTML = `<form id="user-info-form" class="p-2 border-bottom"><div class="row gx-2 align-items-center mb-2"><div class="col"><input type="text" id="user-nickname" class="form-control form-control-sm" placeholder="Nickname" value="${data.user.nickname || ''}"></div><div class="col"><input type="text" id="user-phone" class="form-control form-control-sm" placeholder="Phone" value="${data.user.phone || ''}"></div><div class="col-auto"><button type="submit" class="btn btn-sm btn-success">Save</button> <a href="/chats/download/${userId}?oa=${oaId}" target="_blank" class="btn btn-sm btn-outline-secondary" title="Download Chat History"><i class="bi bi-download"></i></a></div></div><div class="row gx-2 align-items-center"><div class="col"><button type="button" id="edit-note-btn" class="btn btn-outline-secondary btn-sm w-100 text-start"><i class="bi bi-pencil-square"></i> <span id="note-preview" class="text-truncate d-inline-block" style="max-width: 80%;">${data.user.note ? data.user.note.replace(/\n/g, ' ') : 'Add a note...'}</span></button></div><div class="col-auto"><div class="btn-group btn-group-sm" role="group"><button type="button" class="btn btn-outline-success status-btn" data-status="deposit">ฝาก</button><button type="button" class="btn btn-outline-warning status-btn" data-status="withdraw">ถอน</button><button type="button" class="btn btn-outline-danger status-btn" data-status="issue">ติดปัญหา</button><button type="button" class="btn btn-outline-dark status-btn" data-status="closed">ปิดเคส</button></div></div></div>${data.account.manager_url ? `<a href="${data.account.manager_url}" target="_blank" rel="noopener noreferrer" class="text-muted d-block mt-2 text-decoration-none" title="Open in LINE Official Account Manager">@${data.account.name} <i class="bi bi-box-arrow-up-right small"></i></a>` : `<small class="text-muted d-block mt-2">@${data.account.name}</small>`}</form>`;
            messagesContainer.innerHTML = '';
            const imagePromises = [];
            data.messages.forEach(msg => { const promise = appendMessage(messagesContainer, msg); if (promise) { imagePromises.push(promise); } });
            Promise.all(imagePromises).then(() => { messagesContainer.scrollTop = messagesContainer.scrollHeight; });
            const qrResponse = await fetch(`/chats/api/quick_replies/${oaId}`);
            availableQuickReplies = await qrResponse.json();
            const newRoomName = `chat_${userId}_${oaId}`;
            if (currentRoom && currentRoom !== newRoomName) { socket.emit('leave', { room: currentRoom }); }
            socket.emit('join', { room: newRoomName });
            currentRoom = newRoomName;

        } catch (error) {
            console.error('Failed to load chat:', error);
            messagesContainer.innerHTML = '<p class="text-center text-danger">Failed to load conversation.</p>';
        }
    }

    function handleConversationUpdate(convData) {
        if (!convData || !convData.user_id) return;

        const existingUserLink = document.querySelector(`.list-group-item-action[data-userid="${convData.user_id}"][data-oaid="${convData.line_account_id}"]`);
        if (existingUserLink) {
            existingUserLink.remove();
        }

        const newLink = document.createElement('a');
        newLink.href = "#";
        newLink.className = `list-group-item list-group-item-action d-flex align-items-center status-${convData.status}`;
        newLink.dataset.userid = convData.user_id;
        newLink.dataset.oaid = convData.line_account_id;

        if (convData.status === 'unread' && convData.last_unread_timestamp) {
            newLink.dataset.unreadTimestamp = convData.last_unread_timestamp;
        }

        const defaultAvatar = "/static/images/default-avatar.png";
        const unreadBadge = (convData.unread_count && convData.unread_count > 0) ? `<span class="badge bg-danger rounded-pill">${convData.unread_count}</span>` : '';
        const timerHTML = `<small class="text-danger me-2 unread-timer" id="timer-${convData.user_id}-${convData.line_account_id}"></small>`;

        newLink.innerHTML = `<img src="${convData.picture_url || defaultAvatar}" alt="Profile" class="rounded-circle me-3" style="width: 50px; height: 50px;"><div class="flex-grow-1"><div class="d-flex w-100 justify-content-between"><strong class="mb-1">${convData.display_name}</strong><div>${timerHTML}${unreadBadge}</div></div><small class="text-muted">@${convData.oa_name}</small><p class="mb-0 text-muted text-truncate small"><span>${convData.last_message_prefix}</span> ${convData.last_message_content}</p></div>`;

        const timerElement = newLink.querySelector('.unread-timer');
        if (timerElement) {
            if (convData.status !== 'unread' && convData.frozen_time) {
                timerElement.textContent = convData.frozen_time;
                timerElement.classList.add('text-muted', 'timer-frozen');
                timerElement.classList.remove('text-danger');
            }
        }

        userList.prepend(newLink);

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


    socket.on('connect', () => {
        console.log('✅ Successfully connected to WebSocket server!');
    });

    socket.on('update_conversation_list', reloadSidebar);

    socket.on('resort_sidebar', () => {
        const params = new URLSearchParams(window.location.search);
        const page = parseInt(params.get('page')) || 1;

        if (page > 1) {
            // ถ้าไม่ได้อยู่หน้าแรก ให้แสดงป้ายเตือนแทนการ reload
            if (newMessageAlert) {
                newMessageAlert.style.display = 'block';
                newMessageAlert.textContent = 'List re-sorted. Click to view latest.'; // เปลี่ยนข้อความได้
            }
        } else {
            // ถ้าอยู่หน้าแรก ก็ให้ reload ตามปกติ
            reloadSidebar();
        }
    });

    socket.on('resort_sidebar', function (convData) {
        console.log('🔄 Received intelligent sidebar update:', convData);

        // ตรวจสอบว่ามีข้อมูลที่จำเป็นส่งมาหรือไม่
        if (!convData || !convData.user_id) {
            console.warn('Received resort signal without data, falling back to full reload.');
            reloadSidebar(); // ทำงานแบบเก่าเพื่อป้องกันข้อผิดพลาด
            return;
        }

        // เรียกใช้ฟังก์ชันอัปเดตแบบเจาะจงที่มีอยู่แล้ว
        // ฟังก์ชันนี้จะอัปเดตแค่รายการเดียว โดยไม่กระทบรายการอื่น
        handleConversationUpdate(convData);
    });

    socket.on('new_message', function (msgData) {
        console.groupCollapsed('--- Received New Message Event ---');
        console.log('Message Data Received:', msgData);

        // --- [FINAL FIX] ---
        // กรองข้อความที่ไม่ต้องการเสียงแจ้งเตือนออกไป
        // 1. ข้อความประเภท 'event' (เช่น การเปลี่ยนสถานะ)
        // 2. ข้อความจากแอดมิน (ตัวเอง)
        const isAdminMessage = msgData.sender_type === 'admin' && msgData.admin_email === currentUserEmail;
        if (msgData.message_type === 'event' || isAdminMessage) {
            console.log('ℹ️ Ignoring event or own admin message.');
            console.groupEnd();
            return; // ออกจากฟังก์ชันทันที ไม่ต้องทำอะไรต่อ
        }
        // --- [END FINAL FIX] ---

        // ถ้าผ่านมาถึงตรงนี้ได้ แปลว่าเป็นข้อความ "จากลูกค้าจริงๆ" เท่านั้น
        notificationSound.currentTime = 0;
        notificationSound.play().catch(error => {
            console.error("Could not play sound (this is normal until user clicks on the page):", error);
        });

        const isForCurrentChat = String(msgData.user_id) === String(currentUserId) && String(msgData.oa_id) === String(currentOaId);
        if (isForCurrentChat) {
            appendMessage(messagesContainer, msgData);
            // ... (โค้ดส่วน scroll เหมือนเดิม ไม่ต้องเปลี่ยน)
        }

        console.groupEnd();
    });





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
        if (file && file.type.startsWith('image/')) {
            selectedImageFile = file;
            const reader = new FileReader();
            reader.onload = (e) => { previewImage.src = e.target.result; imagePreviewModal.show(); }
            reader.readAsDataURL(file);
        }
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
        }
    }

    async function handleSaveUserInfo(event) {
        // [แก้ไข] ไม่ต้องหาปุ่มแล้ว เพราะเราดักฟัง submit event โดยตรง
        event.preventDefault(); // หยุดการโหลดหน้าเว็บใหม่

        if (!currentUserDbId) {
            console.error("Cannot save, currentUserDbId is not set.");
            return;
        }

        const nickname = document.getElementById('user-nickname').value;
        const phone = document.getElementById('user-phone').value;
        // เราดึง note จากตัวแปรที่เราเก็บไว้ เพื่อไม่ให้ข้อมูลหาย
        const note = currentFullNote;

        try {
            // เราใช้ Endpoint เดิม แต่ตอนนี้จะส่งแค่ nickname กับ phone ที่เปลี่ยนไป
            await saveUserInfo(currentUserDbId, nickname, phone, note);

            // โหลดแชทใหม่เพื่อให้เห็น Log การแก้ไข
            loadChatForUser(currentUserId, currentOaId);

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
            // --- แก้ไขโดยเพิ่ม || r.message.toUpperCase().includes(searchTerm) ---
            const filteredReplies = availableQuickReplies.filter(r =>
                r.shortcut.toUpperCase().includes(searchTerm) ||
                r.message.toUpperCase().includes(searchTerm)
            );

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
                    <strong class="mb-1">${user.display_name}</strong>
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

            loadChatForUser(currentUserId, currentOaId);

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

    chatArea.addEventListener('click', (event) => {
        handleStatusButtonClick(event);
    });
    // [เพิ่ม] Event Listener สำหรับฟอร์มข้อมูล User โดยเฉพาะ
    chatArea.addEventListener('submit', function (event) {
        if (event.target.id === 'user-info-form') {
            handleSaveUserInfo(event);
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

    // [เพิ่ม] Event Listener สำหรับช่องค้นหา
    let searchTimeout;
    searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            performSearch(e.target.value);
        }, 300);
    });
    replyMessageInput.addEventListener('paste', function (event) {
        const items = (event.clipboardData || event.originalEvent.clipboardData).items;

        for (let index in items) {
            const item = items[index];

            // ตรวจสอบว่าเป็น "ไฟล์" และเป็น "รูปภาพ" หรือไม่
            if (item.kind === 'file' && item.type.includes('image')) {
                // หยุดการทำงานปกติของการ paste (ไม่ให้แสดงข้อความแปลกๆ)
                event.preventDefault();

                // แปลงข้อมูลใน Clipboard ให้กลายเป็นไฟล์
                const file = item.getAsFile();

                // ใช้ฟังก์ชันเดียวกับตอนเลือกไฟล์มาแสดง Preview
                selectedImageFile = file;
                const reader = new FileReader();
                reader.onload = (e) => {
                    previewImage.src = e.target.result;
                    imagePreviewModal.show();
                }
                reader.readAsDataURL(file);
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

});