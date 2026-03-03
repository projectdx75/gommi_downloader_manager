"""
HTTP 직접 다운로더
- 단순 HTTP 파일 다운로드
- aiohttp 비동기 사용 (고성능)
"""
import os
import traceback
import re
import time
from typing import Dict, Any, Optional, Callable

from .base import BaseDownloader

try:
    from ..setup import P
    logger = P.logger
except:
    import logging
    logger = logging.getLogger(__name__)


class HttpDirectDownloader(BaseDownloader):
    """HTTP 직접 다운로더"""

    @staticmethod
    def _rate_to_bps(rate_value: Any) -> float:
        if rate_value is None:
            return 0.0
        value = str(rate_value).strip().upper()
        if not value or value in ('0', 'UNLIMITED'):
            return 0.0
        m = re.match(r'^(\d+(?:\.\d+)?)\s*([KMG])(?:I?B)?$', value)
        if not m:
            return 0.0
        num = float(m.group(1))
        unit = m.group(2)
        mul = {'K': 1024, 'M': 1024 ** 2, 'G': 1024 ** 3}[unit]
        return num * mul
    
    def download(
        self,
        url: str,
        save_path: str,
        filename: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        **options
    ) -> Dict[str, Any]:
        """HTTP로 직접 다운로드"""
        try:
            import requests
            
            os.makedirs(save_path, exist_ok=True)
            
            # 파일명 결정
            if not filename:
                filename = url.split('/')[-1].split('?')[0] or f"download_{int(__import__('time').time())}"
            
            filepath = os.path.abspath(os.path.join(save_path, filename))
            filepath = os.path.normpath(filepath)
            
            # 헤더 설정
            headers = options.get('headers', {})
            if 'User-Agent' not in headers:
                headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            
            # 스트리밍 다운로드
            response = requests.get(url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB 청크
            max_rate = options.get('effective_max_download_rate') or options.get('max_download_rate')
            rate_bps = self._rate_to_bps(max_rate)
            start_time = time.monotonic()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self._cancelled:
                        return {'success': False, 'error': 'Cancelled'}
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 평균 다운로드 속도를 제한(총량 제한 분배값 포함)
                        if rate_bps > 0:
                            elapsed = max(0.001, time.monotonic() - start_time)
                            expected_elapsed = downloaded / rate_bps
                            if expected_elapsed > elapsed:
                                time.sleep(expected_elapsed - elapsed)
                        
                        if total_size > 0 and progress_callback:
                            progress = int(downloaded / total_size * 100)
                            speed = ''  # TODO: 속도 계산
                            progress_callback(progress, speed, '')
            
            if progress_callback:
                progress_callback(100, '', '')
            
            return {'success': True, 'filepath': filepath}
            
        except Exception as e:
            logger.error(f'HTTP download error: {e}')
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
    
    def get_info(self, url: str) -> Dict[str, Any]:
        """URL 정보 추출"""
        try:
            import requests
            
            response = requests.head(url, timeout=10)
            return {
                'content_length': response.headers.get('content-length'),
                'content_type': response.headers.get('content-type'),
            }
        except:
            return {}
