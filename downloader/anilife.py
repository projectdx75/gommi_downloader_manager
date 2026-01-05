"""
Anilife 전용 다운로더
- Camoufox로 _aldata 추출 후 ffmpeg 다운로드
- 기존 anime_downloader의 camoufox_anilife.py 로직 활용
"""
import os
import traceback
from typing import Dict, Any, Optional, Callable

from .base import BaseDownloader
from .ffmpeg_hls import FfmpegHlsDownloader

try:
    from ..setup import P
    logger = P.logger
except:
    import logging
    logger = logging.getLogger(__name__)


class AnilifeDnloader(BaseDownloader):
    """Anilife 전용 다운로더 (Camoufox + FFmpeg)"""
    
    def __init__(self):
        super().__init__()
        self._ffmpeg_downloader = FfmpegHlsDownloader()
    
    def download(
        self,
        url: str,
        save_path: str,
        filename: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        **options
    ) -> Dict[str, Any]:
        """Anilife 다운로드 (추출 + 다운로드)"""
        try:
            # 1. 스트림 URL 추출
            if progress_callback:
                progress_callback(0, 'Extracting...', '')
            
            stream_url = self._extract_stream_url(url, options)
            
            if not stream_url:
                return {'success': False, 'error': 'Failed to extract stream URL'}
            
            logger.info(f'Anilife 스트림 URL 추출 완료: {stream_url[:50]}...')
            
            # 2. FFmpeg로 다운로드
            return self._ffmpeg_downloader.download(
                url=stream_url,
                save_path=save_path,
                filename=filename,
                progress_callback=progress_callback,
                **options
            )
            
        except Exception as e:
            logger.error(f'Anilife download error: {e}')
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
    
    def get_info(self, url: str) -> Dict[str, Any]:
        """URL 정보 추출"""
        return {'source': 'anilife'}
    
    def cancel(self):
        """다운로드 취소"""
        super().cancel()
        self._ffmpeg_downloader.cancel()
    
    def _extract_stream_url(self, url: str, options: Dict) -> Optional[str]:
        """Camoufox를 사용하여 스트림 URL 추출"""
        try:
            # anime_downloader의 기존 로직 활용 시도
            try:
                from anime_downloader.lib.camoufox_anilife import extract_aldata
                import asyncio
                
                # URL에서 detail_url과 episode_num 파싱
                detail_url = options.get('detail_url', url)
                episode_num = options.get('episode_num', '1')
                
                # 비동기 추출 실행
                result = asyncio.run(extract_aldata(detail_url, episode_num))
                
                if result.get('success') and result.get('aldata'):
                    # aldata 디코딩하여 실제 스트림 URL 획득
                    return self._decode_aldata(result['aldata'])
                    
            except ImportError:
                logger.warning('anime_downloader 모듈을 찾을 수 없습니다. 기본 추출 로직 사용')
            
            # 폴백: 직접 Camoufox 사용
            return self._extract_with_camoufox(url, options)
            
        except Exception as e:
            logger.error(f'Stream URL extraction error: {e}')
            return None
    
    def _decode_aldata(self, aldata: str) -> Optional[str]:
        """_aldata base64 디코딩"""
        try:
            import base64
            import json
            
            decoded = base64.b64decode(aldata).decode('utf-8')
            data = json.loads(decoded)
            
            # 스트림 URL 추출 (구조에 따라 다를 수 있음)
            if isinstance(data, dict):
                return data.get('url') or data.get('stream') or data.get('file')
            elif isinstance(data, str):
                return data
                
        except Exception as e:
            logger.error(f'_aldata decode error: {e}')
        return None
    
    def _extract_with_camoufox(self, url: str, options: Dict) -> Optional[str]:
        """직접 Camoufox 사용하여 추출"""
        try:
            from camoufox.async_api import AsyncCamoufox
            import asyncio
            
            async def extract():
                async with AsyncCamoufox(headless=True) as browser:
                    page = await browser.new_page()
                    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    
                    # _aldata 변수 추출 시도
                    aldata = await page.evaluate("typeof _aldata !== 'undefined' ? _aldata : null")
                    
                    await page.close()
                    return aldata
            
            aldata = asyncio.run(extract())
            if aldata:
                return self._decode_aldata(aldata)
                
        except Exception as e:
            logger.error(f'Camoufox extraction error: {e}')
        
        return None
