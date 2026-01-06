"""
FFmpeg HLS 다운로더
- ani24, 링크애니 등 HLS 스트림용
- 기존 SupportFfmpeg 로직 재사용
"""
import os
import subprocess
import re
import traceback
from typing import Dict, Any, Optional, Callable

from .base import BaseDownloader

try:
    from ..setup import P
    logger = P.logger
except:
    import logging
    logger = logging.getLogger(__name__)


class FfmpegHlsDownloader(BaseDownloader):
    """FFmpeg HLS 다운로더"""
    
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
        """ffmpeg로 HLS 스트림 다운로드"""
        try:
            os.makedirs(save_path, exist_ok=True)
            
            # 파일명 결정
            if not filename:
                filename = f"download_{int(__import__('time').time())}.mp4"
            
            filepath = os.path.join(save_path, filename)
            
            # ffmpeg 명령어 구성
            ffmpeg_path = options.get('ffmpeg_path', 'ffmpeg')
            
            cmd = [ffmpeg_path, '-y']
            
            # 헤더 추가
            headers = options.get('headers', {})
            cookies_file = options.get('cookies_file')
            
            if headers:
                header_str = '\r\n'.join([f'{k}: {v}' for k, v in headers.items() if v is not None])
                if header_str:
                    cmd.extend(['-headers', header_str])
            
            if cookies_file and os.path.exists(cookies_file):
                # FFmpeg basically uses custom headers for cookies if not using a library that supports it
                # or we can pass it as a header
                if 'Cookie' not in headers:
                    try:
                        with open(cookies_file, 'r') as f:
                            cookie_lines = []
                            for line in f:
                                if line.startswith('#') or not line.strip(): continue
                                parts = line.strip().split('\t')
                                if len(parts) >= 7:
                                    cookie_lines.append(f"{parts[5]}={parts[6]}")
                            if cookie_lines:
                                cookie_str = '; '.join(cookie_lines)
                                if headers:
                                    header_str += f'\r\nCookie: {cookie_str}'
                                    cmd[-1] = header_str # Update headers
                                else:
                                    cmd.extend(['-headers', f'Cookie: {cookie_str}'])
                    except Exception as ce:
                        logger.error(f"Failed to read cookies_file: {ce}")

            # 입력 URL
            cmd.extend(['-i', url])
            
            # 코덱 복사 (트랜스코딩 없이 빠르게)
            cmd.extend(['-c', 'copy'])
            
            # 출력 파일
            cmd.append(filepath)
            
            logger.debug(f'ffmpeg 명령어: {" ".join(cmd[:15])}...')
            
            # 먼저 duration 얻기 위해 ffprobe 실행
            duration = self._get_duration(url, options.get('ffprobe_path', 'ffprobe'), headers)
            
            # 프로세스 실행
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # 출력 파싱 및 에러 메시지 캡처를 위한 변수
            last_lines = []
            for line in self._process.stdout:
                if self._cancelled:
                    self._process.terminate()
                    return {'success': False, 'error': 'Cancelled'}
                
                line = line.strip()
                if line:
                    last_lines.append(line)
                    if len(last_lines) > 20: last_lines.pop(0)
                
                # 진행률 계산 (time= 파싱)
                if duration > 0 and progress_callback:
                    time_match = re.search(r'time=(\d+):(\d+):(\d+)', line)
                    if time_match:
                        h, m, s = map(int, time_match.groups())
                        current_time = h * 3600 + m * 60 + s
                        progress = min(int(current_time / duration * 100), 99)
                        
                        # 속도 파싱
                        speed = ''
                        speed_match = re.search(r'speed=\s*([\d.]+)x', line)
                        if speed_match:
                            speed = f'{speed_match.group(1)}x'
                        
                        progress_callback(progress, speed, '')
            
            self._process.wait()
            
            if self._process.returncode == 0 and os.path.exists(filepath):
                if progress_callback:
                    progress_callback(100, '', '')
                return {'success': True, 'filepath': filepath}
            else:
                error_log = "\n".join(last_lines)
                logger.error(f"FFmpeg failed with return code {self._process.returncode}. Last output:\n{error_log}")
                return {'success': False, 'error': f'FFmpeg Error({self._process.returncode}): {last_lines[-1] if last_lines else "Unknown"}'}
                
        except Exception as e:
            logger.error(f'FfmpegHls download error: {e}')
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
    
    def get_info(self, url: str) -> Dict[str, Any]:
        """스트림 정보 추출"""
        try:
            duration = self._get_duration(url, 'ffprobe', {})
            return {
                'duration': duration,
                'type': 'hls',
            }
        except:
            return {}
    
    def cancel(self):
        """다운로드 취소"""
        super().cancel()
        if self._process:
            self._process.terminate()
    
    def _get_duration(self, url: str, ffprobe_path: str, headers: Dict) -> float:
        """ffprobe로 영상 길이 획득"""
        try:
            cmd = [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration',
                   '-of', 'default=noprint_wrappers=1:nokey=1']
            
            if headers:
                header_str = '\r\n'.join([f'{k}: {v}' for k, v in headers.items()])
                cmd.extend(['-headers', header_str])
            
            cmd.append(url)
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except:
            pass
        return 0
