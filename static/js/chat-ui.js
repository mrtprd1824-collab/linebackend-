// Function to create a single message element (but not append it)
function createMessageElement(msgData) {
    let imageLoadPromise = null;

    const wrapper = document.createElement('div');
    // กำหนด ID ก่อนเสมอ ถ้ามี
    if (msgData.id) {
        wrapper.id = `msg-${msgData.id}`;
    }

    // กำหนด Class หลักตามประเภทข้อความ
    if (msgData.message_type === 'event') {
        wrapper.classList.add('event-message');
        if (msgData.is_close_event) {
            wrapper.classList.add('event-closed');
        }
    } else {
        // ใช้ sender_type ในการกำหนดว่าเป็น customer หรือ admin
        // ถ้าไม่มี sender_type ให้ถือว่าเป็น customer เพื่อความปลอดภัย
        const senderClass = `${msgData.sender_type || 'customer'}-message`;
        wrapper.classList.add('message', senderClass);
    }

    const content = document.createElement('div');
    content.classList.add('message-content');

    // จัดการเนื้อหาตามประเภท
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
            content.textContent = msgData.content;
            break;
    }

    wrapper.appendChild(content);

    if (msgData.sender_type === 'admin' && msgData.line_sent_successfully === false) {
        const errorBadge = document.createElement('div');
        errorBadge.className = 'message-error-badge';
        errorBadge.textContent = '! ส่งไม่สำเร็จ';
        errorBadge.title = msgData.line_error_message || 'ไม่สามารถส่งข้อความนี้ไปยัง LINE ได้';
        wrapper.appendChild(errorBadge);
    }


    // --- [แก้ไข] Logic การสร้าง Meta Data ใหม่ทั้งหมด ---
    const meta = document.createElement('div');
    meta.classList.add('message-meta');

    if (msgData.sender_type === 'admin') {
        // ถ้าเป็น Admin (รวมถึง Event Log) ให้แสดงชื่อและเวลา
        meta.textContent = `@${msgData.oa_name || 'System'} : ${msgData.admin_email || ''} - ${msgData.full_datetime || ''}`;
    } else {
        // ถ้าเป็น Customer ให้แสดงแค่เวลา
        meta.textContent = msgData.full_datetime || '';
    }

    wrapper.appendChild(meta);

    return { element: wrapper, promise: imageLoadPromise };
}

// Function to add a message to the chat container
function appendMessage(container, msgData, isPrepending = false) {

    if (msgData.id && document.getElementById(`msg-${msgData.id}`)) {
        console.log(`Message with ID ${msgData.id} already exists. Skipping.`);
        return null;
    }
    // [แก้ไข] เรียกใช้ createMessageElement และรับค่ากลับมา
    const { element, promise } = createMessageElement(msgData);

    if (isPrepending) {
        container.prepend(element);
    } else {
        container.appendChild(element);
        // [ลบ] เอาการ scroll ออกจากตรงนี้ เพราะมันเร็วเกินไป
        // container.scrollTop = container.scrollHeight; 
    }
    if (window.failedMessageQueue && window.failedMessageQueue[msgData.id]) {
        console.log(`ข้อความ ID ${msgData.id} อยู่ในคิวล้มเหลว! กำลังแปะป้าย Error...`);
        // ถ้าใช่ ให้เรียกฟังก์ชันแปะป้าย Error ทันที
        markMessageAsFailed(msgData.id, window.failedMessageQueue[msgData.id]);

        // ลบออกจากคิว เพื่อไม่ให้ทำงานซ้ำ
        delete window.failedMessageQueue[msgData.id];
    }

    // [แก้ไข] คืนค่า promise ออกไป เพื่อให้คนเรียกใช้รอได้
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
    if (!messageElement) {
        console.error(`Could not find message element with ID: msg-${messageId} to mark as failed.`);
        return;
    }

    const errorBadge = document.createElement('div');
    errorBadge.className = 'message-error-badge';
    errorBadge.textContent = '! ส่งไม่สำเร็จ';
    errorBadge.title = errorMessage || 'ไม่สามารถส่งข้อความนี้ไปยัง LINE ได้';

    messageElement.appendChild(errorBadge);
}
