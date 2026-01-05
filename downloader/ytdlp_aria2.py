"""
yt-dlp + aria2c 다운로더 (최고속)
- aria2c 16개 연결로 3-5배 속도 향상
- YouTube 및 yt-dlp 지원 사이트 전용
"""
import os
import re
import subprocess
import traceback
from typing import Dict, Any, Optional, Callable

from .base import BaseDownloader

# 상위 모듈에서 로거 가져오기
try:
    from ..setup import P
    logger = P.logger
except:
    import logging
    logger = logging.getLogger(__name__)


class YtdlpAria2Downloader(BaseDownloader):
    """yt-dlp + aria2c 다운로더"""
    
    def __init__(self):
        super().__init__()
        self._process: Optional[subprocess.Popen] = None
    
    def download(
        self,
        url: str,
        save_path: str,
        filename: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        **options
    ) -> Dict[str, Any]:
        """yt-dlp + aria2c로 다운로드"""
        try:
            os.makedirs(save_path, exist_ok=True)
            
            # 출력 템플릿
            if filename:
                output_template = os.path.join(save_path, filename)
            else:
                output_template = os.path.join(save_path, '%(title)s.%(ext)s')
            
            # yt-dlp 명령어 구성
            cmd = [
                'yt-dlp',
                '--newline',  # 진행률 파싱용
                '-o', output_template,
            ]
            
            # aria2c 사용 (설치되어 있으면)
            aria2c_path = options.get('aria2c_path', 'aria2c')
            # TODO: 나중에 설정에서 쓰레드 수 지정 (기본값 4로 변경)
            connections = options.get('connections', 4)
            
            # 속도 제한 설정
            max_rate = P.ModelSetting.get('max_download_rate')
            if max_rate == '0':
                max_rate_arg = ''
                log_rate_msg = '무제한'
            else:
                max_rate_arg = f'--max-download-limit={max_rate}'
                log_rate_msg = max_rate
                cmd.extend(['--limit-rate', max_rate]) # Native downloader limit

            # aria2c 사용 (일시 중지: 진행률 파싱 문제 해결 전까지 Native 사용)
            if False and self._check_aria2c(aria2c_path):
                cmd.extend([
                    '--downloader', 'aria2c',
                    '--downloader-args', f'aria2c:-x {connections} -s {connections} -k 1M {max_rate_arg}',
                ])
                logger.debug(f'aria2c 사용: {connections}개 연결 (속도제한 {log_rate_msg})')
            
            # 포맷 선택
            format_spec = options.get('format', 'bestvideo+bestaudio/best')
            cmd.extend(['-f', format_spec])
            
            # 병합 포맷
            merge_format = options.get('merge_output_format', 'mp4')
            cmd.extend(['--merge-output-format', merge_format])
            
            # 쿠키 파일
            if options.get('cookiefile'):
                cmd.extend(['--cookies', options['cookiefile']])
            
            # 프록시
            if options.get('proxy'):
                cmd.extend(['--proxy', options['proxy']])
            
            # URL 추가
            cmd.append(url)
            
            logger.debug(f'yt-dlp 명령어: {" ".join(cmd)}')
            
            # 프로세스 실행
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            final_filepath = ''
            
            # 출력 파싱
            for line in self._process.stdout:
                if self._cancelled:
                    self._process.terminate()
                    return {'success': False, 'error': 'Cancelled'}
                
                line = line.strip()
                # logger.debug(line)
                
                # 진행률 파싱 (yt-dlp default)
                progress_match = re.search(r'\[download\]\s+(\d+\.?\d*)%', line)
                
                # 진행률 파싱 (aria2c)
                if not progress_match:
                    # logger.error(f'DEBUG LINE: {line}') # Log raw line to debug
                    aria2_match = re.search(r'\(\s*([\d.]+)%\)', line) # Allow spaces ( 7%)
                    if aria2_match and (('DL:' in line) or ('CN:' in line)): # DL or CN must be present
                        try:
                            progress = int(float(aria2_match.group(1)))
                            # logger.error(f'MATCHED PROGRESS: {progress}%')
                            
                            speed_match = re.search(r'DL:(\S+)', line)
                            speed = speed_match.group(1) if speed_match else ''
                            # Strip color codes from speed if needed? output is usually clean text if no TTY
                            
                            eta_match = re.search(r'ETA:(\S+)', line)
                            eta = eta_match.group(1) if eta_match else ''
                            
                            if progress_callback:
                                 progress_callback(progress, speed, eta)
                            continue
                        except Exception as e:
                            logger.error(f'Parsing Error: {e}')

                if progress_match and progress_callback:
                    progress = int(float(progress_match.group(1)))
                    
                    # 속도 파싱
                    speed = ''
                    speed_match = re.search(r'at\s+([\d.]+\s*[KMG]?i?B/s)', line)
                    if speed_match:
                        speed = speed_match.group(1)
                    
                    # ETA 파싱
                    eta = ''
                    eta_match = re.search(r'ETA\s+([\d:]+)', line)
                    if eta_match:
                        eta = eta_match.group(1)
                    
                    progress_callback(progress, speed, eta)
                
                # 최종 파일 경로 추출
                if '[Merger]' in line or 'Destination:' in line:
                    path_match = re.search(r'(?:Destination:|into\s+["\'])(.+?)(?:["\']|$)', line)
                    if path_match:
                        final_filepath = path_match.group(1).strip('"\'')
            
            self._process.wait()
            
            if self._process.returncode == 0:
                if progress_callback:
                    progress_callback(100, '', '')
                return {'success': True, 'filepath': final_filepath}
            else:
                return {'success': False, 'error': f'Exit code: {self._process.returncode}'}
                
        except Exception as e:
            logger.error(f'YtdlpAria2 download error: {e}')
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
    
    def get_info(self, url: str) -> Dict[str, Any]:
        """URL 정보 추출"""
        try:
            import yt_dlp
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', ''),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration': info.get('duration', 0),
                    'formats': info.get('formats', []),
                    'uploader': info.get('uploader', ''),
                    'view_count': info.get('view_count', 0),
                }
        except Exception as e:
            logger.error(f'get_info error: {e}')
            return {}
    
    def cancel(self):
        """다운로드 취소"""
        super().cancel()
        if self._process:
            self._process.terminate()
    
    def _check_aria2c(self, aria2c_path: str) -> bool:
        """aria2c 설치 확인"""
        try:
            result = subprocess.run(
                [aria2c_path, '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
