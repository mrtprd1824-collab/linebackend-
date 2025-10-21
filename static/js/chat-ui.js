// Function to create a single message element (but not append it)
function createMessageElement(msgData) {
    let imageLoadPromise = null;

    const wrapper = document.createElement('div');
    if (msgData.id) {
        wrapper.id = `msg-${msgData.id}`;
    }

    const content = document.createElement('div');
    content.classList.add('message-content');

    const meta = document.createElement('div');
    meta.classList.add('message-meta');

    // จัดการเนื้อหาและ Meta ก่อน (ใช้ Logic เดิมของคุณ)
    switch (msgData.message_type) {
        case 'image':
            const img = document.createElement('img');
            img.classList.add('chat-image');
            img.dataset.src = msgData.content;
            imageLoadPromise = new Promise(resolve => {
                img.onload = img.onerror = () => resolve();
                img.src = msgData.content;
            });
            content.appendChild(img);
            break;
        case 'sticker':
            const stickerImg = document.createElement('img');
            stickerImg.classList.add('chat-sticker');
            imageLoadPromise = new Promise(resolve => {
                stickerImg.onload = stickerImg.onerror = () => resolve();
                stickerImg.src = msgData.content;
            });
            content.appendChild(stickerImg);
            break;
        default: // Text และ Event
            content.innerHTML = msgData.content.replace(/\n/g, '<br>');
            break;
    }

    if (msgData.sender_type === 'admin') {
        meta.textContent = `@${msgData.oa_name || 'System'} : ${msgData.admin_email || ''} - ${msgData.full_datetime || ''}`;
    } else {
        meta.textContent = msgData.full_datetime || '';
    }

    // ★★★ ส่วนสำคัญ: ประกอบร่างตามประเภท ★★★
    if (msgData.message_type === 'event') {
        // --- ถ้าเป็น Event ---
        wrapper.classList.add('event-message');
        if (msgData.is_close_event) {
            wrapper.classList.add('event-closed');
        }
        wrapper.appendChild(content);
        wrapper.appendChild(meta);

    } else if (msgData.sender_type === 'customer') {
        // --- ถ้าเป็นลูกค้า ---
        wrapper.classList.add('message', 'customer-message');

        const avatar = document.createElement('img');
        avatar.className = 'chat-avatar';
        avatar.src = window.currentUserPictureUrl || '/static/images/default-avatar.png';

        const bubbleWrapper = document.createElement('div');
        bubbleWrapper.appendChild(content);
        bubbleWrapper.appendChild(meta);

        wrapper.appendChild(avatar);
        wrapper.appendChild(bubbleWrapper);

    } else { // sender_type === 'admin'
        // --- ถ้าเป็นแอดมิน (ใช้โครงสร้างแบบดั้งเดิมของคุณ) ---
        wrapper.classList.add('message', 'admin-message');
        wrapper.appendChild(content);
        wrapper.appendChild(meta);
    }

    return { element: wrapper, promise: imageLoadPromise };
}

// Function to add a message to the chat container
function appendMessage(container, msgData, isPrepending = false) {
    // ตรวจสอบว่ามีข้อความ ID นี้อยู่แล้วหรือยัง
    if (msgData.id && document.getElementById(`msg-${msgData.id}`)) {
        return null;
    }

    const { element, promise } = createMessageElement(msgData);

    if (isPrepending) {
        container.prepend(element);
    } else {
        container.appendChild(element);
    }

    if (msgData.line_sent_successfully === false) {
        // ถ้าส่งไม่สำเร็จ ให้เรียกฟังก์ชันแปะป้าย Error ทันที
        markMessageAsFailed(msgData.id, msgData.line_error_message);
    }

    // จัดการข้อความที่ส่งไม่สำเร็จ
    if (window.failedMessageQueue && window.failedMessageQueue[msgData.id]) {
        markMessageAsFailed(msgData.id, window.failedMessageQueue[msgData.id]);
        delete window.failedMessageQueue[msgData.id];
    }

    // ★★★ เพิ่มส่วน Auto-scroll ที่สมบูรณ์ ★★★
    if (!isPrepending) {
        // ใช้ setTimeout เล็กน้อยเพื่อให้แน่ใจว่า DOM ถูกวาดเสร็จแล้ว
        setTimeout(() => {
            container.scrollTop = container.scrollHeight;
        }, 50);
    }

    return promise;
}

// Function to populate the quick reply modal list
function populateQuickReplyList(listElement, replies) {
    listElement.innerHTML = '';
    if (replies.length === 0) {
        listElement.innerHTML = '<p class="text-center text-muted">No replies found.</p>';
        return;
    }
    replies.forEach(reply => {
        const replyEl = document.createElement('div');
        replyEl.classList.add('list-group-item', 'list-group-item-action', 'quick-reply-item');
        replyEl.style.cursor = 'pointer';
        replyEl.innerHTML = `<strong>${reply.shortcut}</strong><p class="mb-0 text-muted text-truncate">${reply.message}</p>`;
        replyEl.dataset.message = reply.message;
        listElement.appendChild(replyEl);
    });
}

// Function to populate the inline quick reply suggestions
function populateInlineQuickReply(resultsElement, replies) {
    resultsElement.innerHTML = '';
    // Use all replies directly without slicing
    replies.forEach(reply => {
        const itemEl = document.createElement('a');
        itemEl.href = '#';
        itemEl.classList.add('list-group-item', 'list-group-item-action', 'inline-qr-item');
        itemEl.innerHTML = `<strong>${reply.shortcut}</strong> - <span class="text-muted text-truncate">${reply.message}</span>`;
        itemEl.dataset.message = reply.message;
        resultsElement.appendChild(itemEl);
    });
}

function markMessageAsFailed(messageId, errorMessage) {
    const messageElement = document.getElementById(`msg-${messageId}`);
    if (!messageElement) return;

    // ถ้ามี error ซ้ำแล้ว ลบออกก่อน
    const oldBadge = messageElement.querySelector('.message-error-wrapper');
    if (oldBadge) oldBadge.remove();

    // wrapper แยกใหม่สำหรับ error
    const errorWrapper = document.createElement('div');
    errorWrapper.className = 'message-error-wrapper';

    const errorBadge = document.createElement('div');
    errorBadge.className = 'message-error-badge';
    errorBadge.textContent = errorMessage || '! ส่งไม่สำเร็จ';
    errorBadge.title = errorMessage || 'ไม่สามารถส่งข้อความนี้ไปยัง LINE ได้';

    errorWrapper.appendChild(errorBadge);
    messageElement.appendChild(errorWrapper);
}

/**
 * ฟังก์ชันสำหรับแสดง Tag ของผู้ใช้ใน chat header
 * @param {Array} tags - Array ของ tag objects ที่ได้จาก API
 */
function displayUserTags(tags) {
    const tagsContainer = document.getElementById('user-tags-container');
    if (!tagsContainer) return; // ออกถ้าหา container ไม่เจอ

    tagsContainer.innerHTML = ''; // ล้างแท็กเก่าออกก่อนเสมอ

    if (tags && tags.length > 0) {
        tags.forEach(tag => {
            const tagBadge = document.createElement('span');
            tagBadge.className = 'badge rounded-pill me-1'; // ใช้ badge ของ Bootstrap

            // กำหนดสีพื้นหลังและสีตัวอักษร
            tagBadge.style.backgroundColor = tag.color || '#6c757d';
            tagBadge.style.color = '#fff';

            tagBadge.textContent = tag.name;
            tagBadge.dataset.tagId = tag.id; // เก็บ ID ของแท็กไว้เผื่อใช้ในอนาคต

            tagsContainer.appendChild(tagBadge);
        });
    }
}
