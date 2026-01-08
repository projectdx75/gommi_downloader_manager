// GDM YouTube Downloader - Popup Script

const DEFAULT_SERVER = 'http://localhost:9099';
let currentUrl = '';
let selectedFormat = 'bestvideo+bestaudio/best';

// DOM Elements
const loadingEl = document.getElementById('loading');
const errorEl = document.getElementById('error');
const notYoutubeEl = document.getElementById('not-youtube');
const mainEl = document.getElementById('main');
const thumbnailEl = document.getElementById('thumbnail');
const titleEl = document.getElementById('video-title');
const durationEl = document.getElementById('video-duration');
const qualityOptionsEl = document.getElementById('quality-options');
const serverUrlEl = document.getElementById('server-url');
const downloadBtn = document.getElementById('download-btn');
const statusEl = document.getElementById('status');
const retryBtn = document.getElementById('retry-btn');
const errorMessageEl = document.getElementById('error-message');

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  // Load saved server URL
  const stored = await chrome.storage.local.get(['serverUrl']);
  serverUrlEl.value = stored.serverUrl || DEFAULT_SERVER;
  
  // Get current tab URL
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentUrl = tab.url;
  
  // Check if YouTube
  if (!isYouTubeUrl(currentUrl)) {
    showSection('not-youtube');
    return;
  }
  
  // Fetch video info
  fetchVideoInfo();
});

// Event Listeners
downloadBtn.addEventListener('click', startDownload);
retryBtn.addEventListener('click', fetchVideoInfo);
serverUrlEl.addEventListener('change', saveServerUrl);

function isYouTubeUrl(url) {
  return url && (url.includes('youtube.com/watch') || url.includes('youtu.be/'));
}

function showSection(section) {
  loadingEl.classList.add('hidden');
  errorEl.classList.add('hidden');
  notYoutubeEl.classList.add('hidden');
  mainEl.classList.add('hidden');
  
  switch (section) {
    case 'loading': loadingEl.classList.remove('hidden'); break;
    case 'error': errorEl.classList.remove('hidden'); break;
    case 'not-youtube': notYoutubeEl.classList.remove('hidden'); break;
    case 'main': mainEl.classList.remove('hidden'); break;
  }
}

function showStatus(message, type = 'info') {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
  statusEl.classList.remove('hidden');
  
  if (type === 'success') {
    setTimeout(() => statusEl.classList.add('hidden'), 3000);
  }
}

function hideStatus() {
  statusEl.classList.add('hidden');
}

function formatDuration(seconds) {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

async function fetchVideoInfo() {
  showSection('loading');
  hideStatus();
  
  const serverUrl = serverUrlEl.value.replace(/\/$/, '');
  
  try {
    const response = await fetch(
      `${serverUrl}/gommi_downloader_manager/ajax/queue/youtube_formats?url=${encodeURIComponent(currentUrl)}`,
      { method: 'GET' }
    );
    
    const data = await response.json();
    
    if (data.ret !== 'success') {
      throw new Error(data.msg || '영상 정보를 가져올 수 없습니다.');
    }
    
    // Display video info
    titleEl.textContent = data.title || '제목 없음';
    thumbnailEl.src = data.thumbnail || '';
    durationEl.textContent = formatDuration(data.duration);
    
    // Render quality options
    renderQualityOptions(data.formats || []);
    
    showSection('main');
    
  } catch (error) {
    console.error('Fetch error:', error);
    errorMessageEl.textContent = error.message || '서버 연결 실패';
    showSection('error');
  }
}

function renderQualityOptions(formats) {
  qualityOptionsEl.innerHTML = '';
  
  if (formats.length === 0) {
    // Default options
    formats = [
      { id: 'bestvideo+bestaudio/best', label: '최고 품질', note: '' },
      { id: 'bestvideo[height<=1080]+bestaudio/best', label: '1080p', note: '권장' },
      { id: 'bestvideo[height<=720]+bestaudio/best', label: '720p', note: '' },
      { id: 'bestaudio/best', label: '오디오만', note: '' }
    ];
  }
  
  formats.forEach((format, index) => {
    const option = document.createElement('div');
    option.className = 'quality-option' + (index === 0 ? ' selected' : '');
    option.dataset.format = format.id;
    option.innerHTML = `
      <div class="label">${format.label}</div>
      ${format.note ? `<div class="note">${format.note}</div>` : ''}
    `;
    option.addEventListener('click', () => selectQuality(option, format.id));
    qualityOptionsEl.appendChild(option);
  });
  
  // Select first by default
  if (formats.length > 0) {
    selectedFormat = formats[0].id;
  }
}

function selectQuality(element, formatId) {
  document.querySelectorAll('.quality-option').forEach(el => el.classList.remove('selected'));
  element.classList.add('selected');
  selectedFormat = formatId;
}

async function startDownload() {
  downloadBtn.disabled = true;
  downloadBtn.innerHTML = '<span class="btn-icon">⏳</span> 전송 중...';
  hideStatus();
  
  const serverUrl = serverUrlEl.value.replace(/\/$/, '');
  
  try {
    const response = await fetch(
      `${serverUrl}/gommi_downloader_manager/ajax/queue/youtube_add`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: currentUrl,
          format: selectedFormat
        })
      }
    );
    
    const data = await response.json();
    
    if (data.ret === 'success') {
      showStatus('✅ 다운로드가 추가되었습니다!', 'success');
    } else {
      throw new Error(data.msg || '다운로드 추가 실패');
    }
    
  } catch (error) {
    console.error('Download error:', error);
    showStatus('❌ ' + (error.message || '전송 실패'), 'error');
  } finally {
    downloadBtn.disabled = false;
    downloadBtn.innerHTML = '<span class="btn-icon">⬇️</span> 다운로드 시작';
  }
}

async function saveServerUrl() {
  await chrome.storage.local.set({ serverUrl: serverUrlEl.value });
}
