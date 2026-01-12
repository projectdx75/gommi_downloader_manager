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
        info_callback: Optional[Callable] = None,
        **options
    ) -> Dict[str, Any]:
        """yt-dlp + aria2c로 다운로드"""
        try:
            os.makedirs(save_path, exist_ok=True)
            
            # 출력 템플릿
            if filename:
                output_template = os.path.normpath(os.path.join(save_path, filename))
            else:
                output_template = os.path.normpath(os.path.join(save_path, '%(title)s.%(ext)s'))
            
            # yt-dlp 명령어 구성
            cmd = [
                'yt-dlp',
                '--newline',  # 진행률 파싱용
                '--no-check-certificate',
                '-o', output_template,
            ]
            
            # 제목/썸네일 업데이트용 출력 추가 (GDM_FIX)
            cmd.extend(['--print', 'before_dl:GDM_FIX:title:%(title)s'])
            cmd.extend(['--print', 'before_dl:GDM_FIX:thumb:%(thumbnail)s'])
            
            # aria2c 사용 (설치되어 있으면)
            aria2c_path = options.get('aria2c_path', 'aria2c')
            connections = options.get('connections', 4)
            
            if self._check_aria2c(aria2c_path):
                cmd.extend(['--external-downloader', aria2c_path])
                # aria2c 설정: -x=연결수, -s=분할수, -j=병렬, -k=조각크기, --console-log-level=notice로 진행률 출력
                cmd.extend(['--external-downloader-args', f'aria2c:-x{connections} -s{connections} -j{connections} -k1M --summary-interval=1 --console-log-level=notice'])
                logger.info(f'[GDM] Using aria2c for multi-threaded download (connections: {connections})')
            
            # 진행률 템플릿 추가 (yt-dlp native downloader)
            cmd.extend(['--progress-template', 'download:GDM_PROGRESS:%(progress._percent_str)s:%(progress._speed_str)s:%(progress._eta_str)s'])
            
            # 속도 제한 설정
            max_rate = P.ModelSetting.get('max_download_rate')
            if max_rate == '0':
                max_rate_arg = ''
                log_rate_msg = '무제한'
            else:
                max_rate_arg = f'--max-download-limit={max_rate}'
                log_rate_msg = max_rate
                cmd.extend(['--limit-rate', max_rate]) # Native downloader limit

            # 포맷 선택
            format_spec = options.get('format')
            if not format_spec:
                if options.get('extract_audio'):
                    format_spec = 'bestaudio/best'
                else:
                    format_spec = 'bestvideo+bestaudio/best'
            cmd.extend(['-f', format_spec])
            
            # 병합 포맷 (비디오인 경우에만)
            if not options.get('extract_audio'):
                merge_format = options.get('merge_output_format', 'mp4')
                cmd.extend(['--merge-output-format', merge_format])
            
            # 쿠키 파일
            if options.get('cookiefile'):
                cmd.extend(['--cookies', options['cookiefile']])
            
            # 프록시
            if options.get('proxy'):
                cmd.extend(['--proxy', options['proxy']])
            
            # HTTP 헤더 추가 (Referer 등 - Linkkf 등 리다이렉트 방지용)
            if options.get('headers'):
                for key, value in options['headers'].items():
                    cmd.extend(['--add-header', f'{key}:{value}'])

            # FFmpeg 경로 자동 감지 및 설정
            ffmpeg_path = options.get('ffmpeg_path') or P.ModelSetting.get('ffmpeg_path')
            
            if not ffmpeg_path or ffmpeg_path == 'ffmpeg':
                import shutil
                detected_path = shutil.which('ffmpeg')
                if detected_path:
                    ffmpeg_path = detected_path
                else:
                    common_paths = [
                        '/opt/homebrew/bin/ffmpeg',
                        '/usr/local/bin/ffmpeg',
                        '/usr/bin/ffmpeg'
                    ]
                    for p in common_paths:
                        if os.path.exists(p):
                            ffmpeg_path = p
                            break
            
            if ffmpeg_path:
                cmd.extend(['--ffmpeg-location', ffmpeg_path])
                logger.debug(f'[GDM] 감지된 FFmpeg 경로: {ffmpeg_path}')

            # 추가 인자 (extra_args: list)
            extra_args = options.get('extra_args', [])
            if isinstance(extra_args, list):
                cmd.extend(extra_args)
            
            if options.get('extract_audio'):
                cmd.append('--extract-audio')
                if options.get('audio_format'):
                    cmd.extend(['--audio-format', options['audio_format']])
            
            if options.get('embed_thumbnail'):
                cmd.append('--embed-thumbnail')
            
            if options.get('add_metadata'):
                cmd.append('--add-metadata')
            
            if options.get('outtmpl'):
                 # outtmpl 옵션이 별도로 전달된 경우 덮어쓰기 (output_template는 -o가 이미 차지함)
                 # 하지만 yt-dlp -o 옵션이 곧 outtmpl임.
                 # 파일명 템플릿 문제 해결을 위해 filename 인자 대신 outtmpl 옵션을 우선시
                 # 위에서 -o output_template를 이미 넣었으므로, 여기서 다시 넣으면 중복될 수 있음.
                 # 따라서 로직 수정: filename 없이 outtmpl만 온 경우
                 pass

            # URL 추가
            cmd.append(url)
            
            logger.info(f'[GDM] yt-dlp command: {" ".join(cmd)}')
            
            # 프로세스 실행
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            final_filepath = ''
            last_logged_pct = -1
            
            # 출력 파싱
            for line in self._process.stdout:
                if self._cancelled:
                    self._process.terminate()
                    return {'success': False, 'error': 'Cancelled'}
                
                line = line.strip()
                if not line:
                    continue

                # 메타데이터 파싱 (GDM_FIX)
                if 'GDM_FIX:' in line:
                    try:
                        if 'GDM_FIX:title:' in line:
                            title = line.split('GDM_FIX:title:', 1)[1].strip()
                            if info_callback:
                                info_callback({'title': title})
                        elif 'GDM_FIX:thumb:' in line:
                            thumb = line.split('GDM_FIX:thumb:', 1)[1].strip()
                            if info_callback:
                                info_callback({'thumbnail': thumb})
                    except:
                        pass
                
                # 진행률 파싱 - GDM_PROGRESS 템플릿 (우선)
                # 형식: GDM_PROGRESS:XX.X%:SPEED:ETA
                if 'GDM_PROGRESS:' in line:
                    try:
                        parts = line.split('GDM_PROGRESS:', 1)[1].split(':')
                        if len(parts) >= 1:
                            pct_str = parts[0].strip().replace('%', '').strip()
                            progress = int(float(pct_str)) if pct_str and pct_str != 'N/A' else 0
                            speed = parts[1].strip() if len(parts) > 1 else ''
                            eta = parts[2].strip() if len(parts) > 2 else ''
                            if speed == 'N/A': speed = ''
                            if eta == 'N/A': eta = ''
                            if progress_callback and progress > 0:
                                progress_callback(progress, speed, eta)
                            continue
                    except:
                        pass
                
                # 진행률 파싱 (yt-dlp default)
                progress_match = re.search(r'\[download\]\s+(\d+\.?\d*)%', line)
                
                should_log = True
                if progress_match:
                    pct = float(progress_match.group(1))
                    if int(pct) >= last_logged_pct + 5 or pct >= 99.9:
                        last_logged_pct = int(pct)
                    else:
                        should_log = False
                
                if should_log:
                    logger.info(f'[GDM][yt-dlp] {line}')
                
                if not progress_match:
                    aria2_match = re.search(r'\(\s*([\d.]+)%\)', line)
                    if aria2_match and (('DL:' in line) or ('CN:' in line)):
                        try:
                            progress = int(float(aria2_match.group(1)))
                            speed_match = re.search(r'DL:(\S+)', line)
                            speed = speed_match.group(1) if speed_match else ''
                            eta_match = re.search(r'ETA:(\S+)', line)
                            eta = eta_match.group(1) if eta_match else ''
                            if progress_callback:
                                 progress_callback(progress, speed, eta)
                            continue
                        except Exception as e:
                            logger.error(f'Parsing Error: {e}')

                if progress_match and progress_callback:
                    progress = int(float(progress_match.group(1)))
                    speed = ''
                    speed_match = re.search(r'at\s+([\d.]+\s*[KMG]?i?B/s)', line)
                    if speed_match:
                        speed = speed_match.group(1)
                    eta = ''
                    eta_match = re.search(r'ETA\s+([\d:]+)', line)
                    if eta_match:
                        eta = eta_match.group(1)
                    progress_callback(progress, speed, eta)
                
                if any(x in line for x in ['[Merger]', '[VideoConvertor]', 'Destination:']):
                    path_match = re.search(r'(?:Destination:|into|to)\s+["\']?(.+?)(?:["\']|$)', line)
                    if path_match:
                        potential_path = path_match.group(1).strip('"\'')
                        if '.' in os.path.basename(potential_path):
                            final_filepath = potential_path
            
            self._process.wait()
            
            if self._process.returncode == 0:
                if progress_callback:
                    progress_callback(100, '', '')
                
                # 자막 다운로드 처리
                vtt_url = options.get('subtitles')
                if vtt_url and final_filepath:
                    try:
                        self._download_subtitle(vtt_url, final_filepath, headers=options.get('headers'))
                    except Exception as e:
                        logger.error(f'[GDM] Subtitle download error: {e}')
                
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

    def _download_subtitle(self, vtt_url: str, output_path: str, headers: Optional[dict] = None):
        """자막 다운로드 및 SRT 변환"""
        try:
            import requests
            # 자막 파일 경로 생성 (비디오 파일명.srt)
            video_basename = os.path.splitext(output_path)[0]
            srt_path = video_basename + ".srt"
            
            logger.info(f"[GDM] Downloading subtitle from: {vtt_url}")
            response = requests.get(vtt_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                vtt_content = response.text
                srt_content = self._vtt_to_srt(vtt_content)
                with open(srt_path, "w", encoding="utf-8") as f:
                    f.write(srt_content)
                logger.info(f"[GDM] Subtitle saved to: {srt_path}")
                return True
        except Exception as e:
            logger.error(f"[GDM] Failed to download subtitle: {e}")
        return False

    def _vtt_to_srt(self, vtt_content: str) -> str:
        """VTT 형식을 SRT 형식으로 간단히 변환"""
        if not vtt_content.startswith("WEBVTT"):
            return vtt_content
            
        lines = vtt_content.split("\n")
        srt_lines = []
        cue_index = 1
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("WEBVTT") or line.startswith("NOTE") or line.startswith("STYLE"):
                i += 1
                continue
            if not line:
                i += 1
                continue
            if "-->" in line:
                # VTT 타임코드를 SRT 형식으로 변환 (. -> ,)
                srt_timecode = line.replace(".", ",")
                srt_lines.append(str(cue_index))
                srt_lines.append(srt_timecode)
                cue_index += 1
                i += 1
                while i < len(lines) and lines[i].strip():
                    srt_lines.append(lines[i].rstrip())
                    i += 1
                srt_lines.append("")
            else:
                i += 1
        return "\n".join(srt_lines)
