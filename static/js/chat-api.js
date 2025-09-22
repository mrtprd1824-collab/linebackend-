// Function to fetch initial chat data for a user
async function fetchChatData(userId, oaId) {
    const response = await fetch(`/chats/api/messages/${userId}?oa=${oaId}`);
    if (!response.ok) throw new Error('Network response was not ok');
    return await response.json();
}

// Function to fetch more (older) messages
async function fetchMoreMessages(userId, oaId, offset) {
    const response = await fetch(`/chats/${userId}/more?oa=${oaId}&offset=${offset}`);
    if (!response.ok) throw new Error('Failed to load more messages');
    return await response.json();
}

// Function to send a text message
async function sendTextMessage(userId, oaId, message) {
    const response = await fetch('/chats/api/send_message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, oa_id: oaId, message: message })
    });
    if (!response.ok) throw new Error('Failed to send message');
    return await response.json();
}

// Function to send an image message
async function sendImageMessage(userId, oaId, imageFile) {
    const formData = new FormData();
    formData.append('image', imageFile);
    formData.append('user_id', userId);
    formData.append('oa_id', oaId);
    const response = await fetch('/chats/api/send_image', { method: 'POST', body: formData });
    if (!response.ok) throw new Error('Image upload failed');
    return await response.json();
}

// Function to send a sticker message
async function sendStickerMessage(userId, oaId, packageId, stickerId) {
    const response = await fetch('/chats/api/send_sticker', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, oa_id: oaId, package_id: packageId, sticker_id: stickerId })
    });
    if (!response.ok) throw new Error('Failed to send sticker');
    return await response.json();
}


// Function to save user info
async function saveUserInfo(userDbId, nickname, phone, note) {
    const response = await fetch(`/chats/api/user_info/${userDbId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname, phone, note })
    });
    if (!response.ok) throw new Error('Failed to save user info');
    return await response.json();
}

// Function to fetch stickers from the server
async function fetchStickers() {
    const response = await fetch('/chats/api/stickers');
    if (!response.ok) throw new Error('Failed to load stickers');
    return await response.json();
}