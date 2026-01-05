"""
다운로더 베이스 클래스
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable


class BaseDownloader(ABC):
    """모든 다운로더의 추상 베이스 클래스"""
    
    def __init__(self):
        self._cancelled = False
        self._paused = False
    
    @abstractmethod
    def download(
        self,
        url: str,
        save_path: str,
        filename: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        **options
    ) -> Dict[str, Any]:
        """
        다운로드 실행
        
        Args:
            url: 다운로드 URL
            save_path: 저장 경로
            filename: 파일명 (None이면 자동 감지)
            progress_callback: 진행률 콜백 (progress, speed, eta)
            **options: 추가 옵션
        
        Returns:
            {
                'success': bool,
                'filepath': str,  # 완료된 파일 경로
                'error': str,  # 에러 메시지 (실패 시)
            }
        """
        pass
    
    @abstractmethod
    def get_info(self, url: str) -> Dict[str, Any]:
        """
        URL 정보 추출 (메타데이터)
        
        Returns:
            {
                'title': str,
                'thumbnail': str,
                'duration': int,
                'formats': list,
                ...
            }
        """
        pass
    
    def cancel(self):
        """다운로드 취소"""
        self._cancelled = True
    
    def pause(self):
        """다운로드 일시정지"""
        self._paused = True
    
    def resume(self):
        """다운로드 재개"""
        self._paused = False
    
    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
    
    @property
    def is_paused(self) -> bool:
        return self._paused
