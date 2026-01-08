// GDM YouTube Downloader - Content Script
// Optional: Inject download button on YouTube page

(function() {
  'use strict';
  
  // Check if we're on a YouTube video page
  if (!window.location.href.includes('youtube.com/watch')) {
    return;
  }
  
  // Wait for YouTube player to load
  const observer = new MutationObserver((mutations, obs) => {
    const actionBar = document.querySelector('#top-level-buttons-computed');
    if (actionBar && !document.getElementById('gdm-download-btn')) {
      injectButton(actionBar);
    }
  });
  
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
  
  function injectButton(container) {
    const btn = document.createElement('button');
    btn.id = 'gdm-download-btn';
    btn.className = 'gdm-yt-btn';
    btn.innerHTML = `
      <span class="gdm-icon">⬇️</span>
      <span class="gdm-text">GDM</span>
    `;
    btn.title = 'GDM으로 다운로드';
    
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      
      btn.disabled = true;
      btn.innerHTML = '<span class="gdm-icon">⏳</span><span class="gdm-text">전송중</span>';
      
      try {
        const response = await chrome.runtime.sendMessage({
          action: 'download',
          url: window.location.href
        });
        
        if (response && response.ret === 'success') {
          btn.innerHTML = '<span class="gdm-icon">✅</span><span class="gdm-text">완료</span>';
          setTimeout(() => {
            btn.innerHTML = '<span class="gdm-icon">⬇️</span><span class="gdm-text">GDM</span>';
            btn.disabled = false;
          }, 2000);
        } else {
          throw new Error(response?.msg || 'Unknown error');
        }
      } catch (error) {
        btn.innerHTML = '<span class="gdm-icon">❌</span><span class="gdm-text">실패</span>';
        console.error('GDM Error:', error);
        setTimeout(() => {
          btn.innerHTML = '<span class="gdm-icon">⬇️</span><span class="gdm-text">GDM</span>';
          btn.disabled = false;
        }, 2000);
      }
    });
    
    container.appendChild(btn);
  }
})();
