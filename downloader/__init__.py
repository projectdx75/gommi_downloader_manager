"""
다운로더 모듈 패키지
"""
from typing import Optional
from .base import BaseDownloader


def get_downloader(source_type: str) -> Optional[BaseDownloader]:
    """소스 타입에 맞는 다운로더 인스턴스 반환"""
    
    if source_type in ('youtube', 'general'):
        from .ytdlp_aria2 import YtdlpAria2Downloader
        return YtdlpAria2Downloader()
    
    elif source_type in ('ani24', 'linkkf', 'hls'):
        from .ffmpeg_hls import FfmpegHlsDownloader
        return FfmpegHlsDownloader()
    
    elif source_type == 'anilife':
        from .anilife import AnilifeDnloader
        return AnilifeDnloader()
    
    elif source_type == 'http':
        from .http_direct import HttpDirectDownloader
        return HttpDirectDownloader()
    
    return None


__all__ = ['get_downloader', 'BaseDownloader']
