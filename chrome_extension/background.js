// GDM YouTube Downloader - Background Service Worker
// Handles extension lifecycle and context menu integration

// Context menu setup
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'gdm-download',
    title: 'GDM으로 다운로드',
    contexts: ['page', 'link'],
    documentUrlPatterns: ['https://www.youtube.com/*', 'https://youtu.be/*']
  });
});

// Context menu click handler
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'gdm-download') {
    const url = info.linkUrl || tab.url;
    
    // Open popup or send directly
    const stored = await chrome.storage.local.get(['serverUrl']);
    const serverUrl = (stored.serverUrl || 'http://localhost:9099').replace(/\/$/, '');
    
    try {
      const response = await fetch(
        `${serverUrl}/gommi_downloader_manager/ajax/queue/youtube_add`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url: url,
            format: 'bestvideo+bestaudio/best'
          })
        }
      );
      
      const data = await response.json();
      
      if (data.ret === 'success') {
        // Show notification
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icons/icon128.png',
          title: 'GDM 다운로드',
          message: '다운로드가 추가되었습니다!'
        });
      }
    } catch (error) {
      console.error('GDM download error:', error);
      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon128.png',
        title: 'GDM 오류',
        message: '서버 연결 실패: ' + error.message
      });
    }
  }
});

// Message handler for content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'download') {
    handleDownload(request.url, request.format).then(sendResponse);
    return true; // Async response
  }
});

async function handleDownload(url, format = 'bestvideo+bestaudio/best') {
  const stored = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = (stored.serverUrl || 'http://localhost:9099').replace(/\/$/, '');
  
  try {
    const response = await fetch(
      `${serverUrl}/gommi_downloader_manager/ajax/queue/youtube_add`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, format })
      }
    );
    
    return await response.json();
  } catch (error) {
    return { ret: 'error', msg: error.message };
  }
}
