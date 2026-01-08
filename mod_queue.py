"""
gommi_download_manager - 다운로드 큐 관리 모듈
"""
import os
import time
import threading
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from enum import Enum

from flask import render_template, jsonify
from framework import F, socketio




class DownloadStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"  # 메타데이터 추출 중
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


from plugin import PluginModuleBase

class ModuleQueue(PluginModuleBase):
    """다운로드 큐 관리 모듈"""
    
    db_default = {
        'aria2c_path': 'aria2c',
        'aria2c_connections': '16',  # 동시 연결 수
        'ffmpeg_path': 'ffmpeg',
        'yt_dlp_path': '',  # 비어있으면 python module 사용
        'save_path': '{PATH_DATA}/download',
        'temp_path': '{PATH_DATA}/download_tmp',
        'max_concurrent': '3',  # 동시 다운로드 수
        'max_download_rate': '0',  # 최대 다운로드 속도 (0: 무제한, 5M, 10M...)
        'auto_retry': 'true',
        'max_retry': '3',
    }
    
    # 진행 중인 다운로드 인스턴스들
    _downloads: Dict[str, 'DownloadTask'] = {}
    _queue_lock = threading.Lock()
    
    def __init__(self, P: Any) -> None:
        from .setup import default_route_socketio_module
        super(ModuleQueue, self).__init__(P, name='queue', first_menu='list')
        default_route_socketio_module(self, attach='/queue')

    
    def process_menu(self, page_name: str, req: Any) -> Any:
        """메뉴 페이지 렌더링"""
        self.P.logger.debug(f'Page Request: {page_name}')
        arg = self.P.ModelSetting.to_dict()
        try:
            arg['module_name'] = self.name
            arg['package_name'] = self.P.package_name  # 명시적 추가
            arg['path_data'] = F.config['path_data']
            return render_template(f'{self.P.package_name}_{self.name}_{page_name}.html', arg=arg)
        except Exception as e:
            self.P.logger.error(f'Exception:{str(e)}')
            self.P.logger.error(traceback.format_exc())
            return render_template('sample.html', title=f"{self.P.package_name}/{self.name}/{page_name}")
    
    def process_ajax(self, command: str, req: Any) -> Any:
        """AJAX 명령 처리"""
        # P.logger.debug(f'Command: {command}')
        ret = {'ret': 'success'}
        try:
            if command == 'add':
                # 큐에 다운로드 추가
                from .setup import P, ToolUtil
                url = req.form['url']
                save_path = req.form.get('save_path') or ToolUtil.make_path(self.P.ModelSetting.get('save_path'))
                filename = req.form.get('filename')
                
                item = self.add_download(url, save_path, filename)
                ret['data'] = item.as_dict() if item else None
                
            elif command == 'list':
                # 진행 중인 다운로드 목록 + 최근 DB 내역 (영속성 강화)
                active_items = [d.get_status() for d in self._downloads.values()]
                active_ids = [i['id'] for i in active_items if 'id' in i]
                
                # DB에서 최근 50개 가져와서 합치기
                from .model import ModelDownloadItem
                with F.app.app_context():
                    db_items = F.db.session.query(ModelDownloadItem).order_by(ModelDownloadItem.id.desc()).limit(50).all()
                    for db_item in db_items:
                        # 이미 active에 있으면 스킵
                        is_active = False
                        for ai in active_items:
                            if ai.get('db_id') == db_item.id:
                                is_active = True
                                break
                        if not is_active:
                            item_dict = db_item.as_dict()
                            item_dict['id'] = f"db_{db_item.id}"
                            # completed 상태면 진행률 100%로 표시
                            if item_dict.get('status') == 'completed':
                                item_dict['progress'] = 100
                            active_items.append(item_dict)
                
                ret['data'] = active_items
                
            elif command == 'cancel':
                # 다운로드 취소
                download_id = req.form['id']
                if download_id in self._downloads:
                    self._downloads[download_id].cancel()
                    ret['msg'] = '다운로드가 취소되었습니다.'
                    
            elif command == 'pause':
                download_id = req.form['id']
                if download_id in self._downloads:
                    self._downloads[download_id].pause()
                    
            elif command == 'resume':
                download_id = req.form['id']
                if download_id in self._downloads:
                    self._downloads[download_id].resume()

            elif command == 'reset':
                # 전체 목록 초기화 (진행중인건 취소)
                for task in list(self._downloads.values()):
                    task.cancel()
                self._downloads.clear()
                
                # DB에서도 삭제
                try:
                    with F.app.app_context():
                        from .model import ModelDownloadItem
                        F.db.session.query(ModelDownloadItem).delete()
                        F.db.session.commit()
                except Exception as e:
                    P.logger.error(f'DB Clear Error: {e}')
                    
                ret['msg'] = '목록을 초기화했습니다.'
            
            elif command == 'delete':
                # 특정 항목 완전 삭제 (메모리 + DB)
                download_id = req.form.get('id', '')
                db_id_to_delete = None
                
                # 1. DB ID 추출 및 메모리 정리
                if download_id in self._downloads:
                    task = self._downloads[download_id]
                    if hasattr(task, 'db_id'):
                        db_id_to_delete = task.db_id
                    task.cancel()
                    del self._downloads[download_id]
                
                # 2. DB에서 삭제 처리
                if download_id.startswith('db_'):
                    db_id_to_delete = int(download_id.replace('db_', ''))
                
                if db_id_to_delete:
                    try:
                        from .model import ModelDownloadItem
                        with F.app.app_context():
                            F.db.session.query(ModelDownloadItem).filter_by(id=db_id_to_delete).delete()
                            F.db.session.commit()
                            self.P.logger.info(f"Deleted DB item: {db_id_to_delete}")
                    except Exception as e:
                        self.P.logger.error(f'DB Delete Error: {e}')
                
                ret['msg'] = '항목이 삭제되었습니다.'
            
            # ===== YouTube API for Chrome Extension =====
            
            elif command == 'youtube_add':
                # Chrome 확장에서 YouTube 다운로드 요청
                import json
                from .setup import P, ToolUtil
                
                # JSON 또는 Form 데이터 처리
                if req.is_json:
                    data = req.get_json()
                else:
                    data = req.form.to_dict()
                
                url = data.get('url', '')
                if not url:
                    ret['ret'] = 'error'
                    ret['msg'] = 'URL이 필요합니다.'
                    return jsonify(ret)
                
                # YouTube URL 검증
                if 'youtube.com' not in url and 'youtu.be' not in url:
                    ret['ret'] = 'error'
                    ret['msg'] = '유효한 YouTube URL이 아닙니다.'
                    return jsonify(ret)
                
                format_id = data.get('format', 'bestvideo+bestaudio/best')
                save_path = data.get('path') or ToolUtil.make_path(self.P.ModelSetting.get('save_path'))
                
                # 다운로드 추가
                item = self.add_download(
                    url=url,
                    save_path=save_path,
                    source_type='youtube',
                    caller_plugin='chrome_extension',
                    format=format_id
                )
                
                if item:
                    ret['id'] = item.id
                    ret['msg'] = '다운로드가 추가되었습니다.'
                else:
                    ret['ret'] = 'error'
                    ret['msg'] = '다운로드 추가 실패'
            
            elif command == 'youtube_formats':
                # YouTube 영상 품질 목록 조회
                url = req.args.get('url') or req.form.get('url', '')
                
                if not url:
                    ret['ret'] = 'error'
                    ret['msg'] = 'URL이 필요합니다.'
                    return jsonify(ret)
                
                try:
                    import yt_dlp
                    
                    ydl_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': False,
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        
                        ret['title'] = info.get('title', '')
                        ret['thumbnail'] = info.get('thumbnail', '')
                        ret['duration'] = info.get('duration', 0)
                        
                        # 품질 목록 생성
                        formats = []
                        
                        # 미리 정의된 품질 옵션들
                        formats.append({'id': 'bestvideo+bestaudio/best', 'label': '최고 품질', 'note': '자동 선택'})
                        
                        # 실제 포맷에서 해상도 추출
                        available_heights = set()
                        for f in info.get('formats', []):
                            height = f.get('height')
                            if height and f.get('vcodec') != 'none':
                                available_heights.add(height)
                        
                        # 해상도별 옵션 추가
                        for height in sorted(available_heights, reverse=True):
                            if height >= 2160:
                                formats.append({'id': f'bestvideo[height<=2160]+bestaudio/best', 'label': '4K (2160p)', 'note': '고용량'})
                            elif height >= 1440:
                                formats.append({'id': f'bestvideo[height<=1440]+bestaudio/best', 'label': '2K (1440p)', 'note': ''})
                            elif height >= 1080:
                                formats.append({'id': f'bestvideo[height<=1080]+bestaudio/best', 'label': 'FHD (1080p)', 'note': '권장'})
                            elif height >= 720:
                                formats.append({'id': f'bestvideo[height<=720]+bestaudio/best', 'label': 'HD (720p)', 'note': ''})
                            elif height >= 480:
                                formats.append({'id': f'bestvideo[height<=480]+bestaudio/best', 'label': 'SD (480p)', 'note': '저용량'})
                        
                        # 오디오 전용 옵션
                        formats.append({'id': 'bestaudio/best', 'label': '오디오만', 'note': 'MP3 변환'})
                        
                        # 중복 제거
                        seen = set()
                        unique_formats = []
                        for f in formats:
                            if f['id'] not in seen:
                                seen.add(f['id'])
                                unique_formats.append(f)
                        
                        ret['formats'] = unique_formats
                        
                except Exception as e:
                    self.P.logger.error(f'YouTube format extraction error: {e}')
                    ret['ret'] = 'error'
                    ret['msg'] = str(e)
                    
        except Exception as e:
            self.P.logger.error(f'Exception:{str(e)}')
            self.P.logger.error(traceback.format_exc())
            ret['ret'] = 'error'
            ret['msg'] = str(e)
            
        return jsonify(ret)
    
    # ===== 외부 플러그인용 API =====
    
    @classmethod
    def add_download(
        cls,
        url: str,
        save_path: str,
        filename: Optional[str] = None,
        source_type: Optional[str] = None,
        caller_plugin: Optional[str] = None,
        callback_id: Optional[str] = None,
        on_progress: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        title: Optional[str] = None,
        thumbnail: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        **options
    ) -> Optional['DownloadTask']:
        """다운로드를 큐에 추가 (외부 플러그인에서 호출)"""
        try:
            # 옵션 평탄화 (Nesting 방지)
            if 'options' in options and isinstance(options['options'], dict):
                inner_options = options.pop('options')
                options.update(inner_options)
            
            # 소스 타입 자동 감지
            if not source_type or source_type == 'auto':
                source_type = cls._detect_source_type(url, caller_plugin, meta)
            
            # DownloadTask 생성
            task = DownloadTask(
                url=url,
                save_path=save_path,
                filename=filename,
                source_type=source_type,
                caller_plugin=caller_plugin,
                callback_id=callback_id,
                on_progress=on_progress,
                on_complete=on_complete,
                on_error=on_error,
                title=title,
                thumbnail=thumbnail,
                meta=meta,
                **options
            )
            
            with cls._queue_lock:
                cls._downloads[task.id] = task
            
            
            # 비동기 시작
            task.start()
            
            # DB 저장
            import json
            from .model import ModelDownloadItem
            db_item = ModelDownloadItem()
            db_item.created_time = datetime.now()
            db_item.url = url
            db_item.save_path = save_path
            db_item.filename = filename
            db_item.source_type = source_type
            db_item.status = DownloadStatus.PENDING
            db_item.caller_plugin = caller_plugin
            db_item.callback_id = callback_id
            db_item.title = title or task.title
            db_item.thumbnail = thumbnail or task.thumbnail
            if meta:
                db_item.meta = json.dumps(meta, ensure_ascii=False)
            db_item.save()
            
            task.db_id = db_item.id

            
            return task
            
        except Exception as e:
            from .setup import P
            P.logger.error(f'add_download error: {e}')
            P.logger.error(traceback.format_exc())
            return None
    
    @classmethod
    def get_download(cls, download_id: str) -> Optional['DownloadTask']:
        """다운로드 태스크 조회"""
        return cls._downloads.get(download_id)
    
    @classmethod
    def get_all_downloads(cls) -> List['DownloadTask']:
        """모든 다운로드 태스크 조회"""
        return list(cls._downloads.values())
    
    @classmethod
    def _detect_source_type(cls, url: str, caller_plugin: Optional[str] = None, meta: Optional[Dict] = None) -> str:
        """URL 및 호출자 정보를 기반으로 지능적 소스 타입 감지"""
        url_lower = url.lower()
        
        # 1. 호출자(Plugin) 기반 우선 판단
        if caller_plugin:
            cp_lower = caller_plugin.lower()
            if 'anilife' in cp_lower: return 'anilife'
            if 'ohli24' in cp_lower or 'ani24' in cp_lower: return 'ohli24'
            if 'linkkf' in cp_lower: return 'linkkf'
            if 'youtube' in cp_lower: return 'youtube'
        
        # 2. 메타데이터 기반 판단
        if meta and meta.get('source'):
            ms_lower = meta.get('source').lower()
            if ms_lower in ['ani24', 'ohli24']: return 'ohli24'
            if ms_lower == 'anilife': return 'anilife'
            if ms_lower == 'linkkf': return 'linkkf'

        # 3. URL 기반 판단
        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'youtube'
        elif 'ani24' in url_lower or 'ohli24' in url_lower:
            return 'ohli24'
        elif 'linkkf' in url_lower:
            return 'linkkf'
        elif 'anilife' in url_lower:
            return 'anilife'
        elif url_lower.endswith('.m3u8') or 'manifest' in url_lower:
            return 'hls'
        else:
            return 'http'
    
    def plugin_load(self) -> None:
        """플러그인 로드 시 초기화"""
        self.P.logger.info('gommi_downloader 플러그인 로드')
        try:
            # DB에서 진행 중인 작업 로드
            with F.app.app_context():
                from .model import ModelDownloadItem
                from datetime import datetime
                ModelDownloadItem.P = self.P
                ModelDownloadItem.check_migration()
                
                # 간단하게 status != completed, cancelled, error
                items = F.db.session.query(ModelDownloadItem).filter(
                    ModelDownloadItem.status.in_([
                        DownloadStatus.PENDING, 
                        DownloadStatus.DOWNLOADING, 
                        DownloadStatus.EXTRACTING
                    ])
                ).all()
                
                for item in items:
                    # DownloadTask 복원
                    task = DownloadTask(
                        url=item.url,
                        save_path=item.save_path,
                        filename=item.filename,
                        source_type=item.source_type,
                        caller_plugin=item.caller_plugin,
                        callback_id=item.callback_id,
                        title=item.title,
                        thumbnail=item.thumbnail,
                        meta=item.as_dict().get('meta')
                    )
                    task.status = DownloadStatus(item.status)
                    task.db_id = item.id
                    task.title = item.title or ''
                    
                    # 상태가 downloading/extracting이었다면 pending으로 되돌려서 재시작하거나,
                    # 바로 시작
                    # 여기서는 pending으로 변경 후 다시 start 호출
                    task.status = DownloadStatus.PENDING
                    
                    self._downloads[task.id] = task
                    task.start()
                    
                self.P.logger.info(f'{len(items)}개의 중단된 다운로드 작업 복원됨')
            
        except Exception as e:
            self.P.logger.error(f'plugin_load error: {e}')
            self.P.logger.error(traceback.format_exc())
    
    def plugin_unload(self) -> None:
        """플러그인 언로드 시 정리"""
        # 모든 다운로드 중지
        for task in self._downloads.values():
            task.cancel()


class DownloadTask:
    """개별 다운로드 태스크"""
    
    _counter = 0
    _counter_lock = threading.Lock()
    
    def __init__(
        self,
        url: str,
        save_path: str,
        filename: Optional[str] = None,
        source_type: str = 'auto',
        caller_plugin: Optional[str] = None,
        callback_id: Optional[str] = None,
        on_progress: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        title: Optional[str] = None,
        thumbnail: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        **options
    ):
        with self._counter_lock:
            DownloadTask._counter += 1
            self.id = f"dl_{int(time.time())}_{DownloadTask._counter}"
        
        self.url = url
        self.save_path = save_path
        self.filename = filename
        self.source_type = source_type
        self.caller_plugin = caller_plugin
        self.callback_id = callback_id
        self.title = title or ''
        self.thumbnail = thumbnail or ''
        self.meta = meta or {}
        self.options = options
        
        # 콜백
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        
        # 상태
        self.status = DownloadStatus.PENDING
        self.progress = 0
        self.speed = ''
        self.eta = ''
        self.error_message = ''
        self.filepath = os.path.join(save_path, filename) if filename else ''
        
        # 메타데이터 (이미 __init__ 상단에서 인자로 받은 title, thumbnail을 self.title, self.thumbnail에 할당함)
        self.duration = 0
        self.filesize = 0
        
        # 내부
        self._thread: Optional[threading.Thread] = None
        self._downloader = None
        self._cancelled = False
        self.db_id: Optional[int] = None
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.created_time: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def start(self):
        """다운로드 시작 (비동기)"""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def _run(self):
        """다운로드 실행"""
        try:
            self.status = DownloadStatus.EXTRACTING
            if not self.start_time:
                self.start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self._emit_status()
            
            # 다운로더 선택 및 실행
            from .downloader import get_downloader
            self._downloader = get_downloader(self.source_type)
            
            if not self._downloader:
                raise Exception(f"지원하지 않는 소스 타입: {self.source_type}")
            
            self.status = DownloadStatus.DOWNLOADING
            self._emit_status()
            
            # 다운로드 실행
            result = self._downloader.download(
                url=self.url,
                save_path=self.save_path,
                filename=self.filename,
                progress_callback=self._progress_callback,
                info_callback=self._info_update_callback,
                **self.options
            )
            
            if self._cancelled:
                self.status = DownloadStatus.CANCELLED
            elif result.get('success'):
                self.status = DownloadStatus.COMPLETED
                self.filepath = result.get('filepath', '')
                self.progress = 100
                self.end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if self.filepath and os.path.exists(self.filepath):
                    self.filesize = os.path.getsize(self.filepath)
                
                # DB 업데이트
                self._update_db_status()
                
                # 실시간 콜백 처리
                if self._on_complete:
                    try: self._on_complete(self.filepath)
                    except: pass
                
                # 플러그인 간 영구적 콜백 처리
                if self.caller_plugin and self.callback_id:
                    self._invoke_plugin_callback()
            else:
                self.status = DownloadStatus.ERROR
                self.error_message = result.get('error', 'Unknown error')
                self._update_db_status()
                if self._on_error:
                    self._on_error(self.error_message)
                    
        except Exception as e:
            from .setup import P
            P.logger.error(f'Download error: {e}')
            P.logger.error(traceback.format_exc())
            self.status = DownloadStatus.ERROR
            self.error_message = str(e)
            if self._on_error:
                self._on_error(self.error_message)
            
            # 0바이트 파일 정리 (실패 시)
            self._cleanup_if_empty()
        
        finally:
            self._emit_status()
    
    def _progress_callback(self, progress: int, speed: str = '', eta: str = ''):
        """진행률 콜백"""
        self.progress = progress
        self.speed = speed
        self.eta = eta
        
        if self._on_progress:
            self._on_progress(progress, speed, eta)
        
        self._emit_status()
    
    def _emit_status(self):
        """Socket.IO로 상태 전송"""
        try:
            socketio.emit(
                'download_status',
                self.get_status(),
                namespace=f'/gommi_downloader_manager'
            )
        except:
            pass
    

    def _info_update_callback(self, info_dict):
        """다운로더로부터 메타데이터 업데이트 수신"""
        try:
            if 'title' in info_dict and info_dict['title']:
                self.title = info_dict['title']
                if 'thumbnail' in info_dict and info_dict['thumbnail']:
                    self.thumbnail = info_dict['thumbnail']
                
                # DB 업데이트
                self._update_db_info()
                
                # 상태 전송
                self._emit_status()
        except:
            pass

    def _update_db_info(self):
        """DB의 제목/썸네일 정보 동기화"""
        try:
            if self.db_id:
                from .model import ModelDownloadItem
                with F.app.app_context():
                    item = F.db.session.query(ModelDownloadItem).filter_by(id=self.db_id).first()
                    if item:
                        item.title = self.title
                        item.thumbnail = self.thumbnail
                        F.db.session.commit()
        except:
            pass

    def cancel(self):
        """다운로드 취소"""
        self._cancelled = True
        if self._downloader:
            self._downloader.cancel()
        self.status = DownloadStatus.CANCELLED
        self._cleanup_if_empty()
        self._emit_status()
    
    def pause(self):
        """다운로드 일시정지"""
        if self._downloader and hasattr(self._downloader, 'pause'):
            self._downloader.pause()
        self.status = DownloadStatus.PAUSED
        self._emit_status()
    
    def resume(self):
        """다운로드 재개"""
        if self._downloader and hasattr(self._downloader, 'resume'):
            self._downloader.resume()
        self.status = DownloadStatus.DOWNLOADING
        self._emit_status()

    def _cleanup_if_empty(self):
        """출력 파일이 0바이트거나 존재하지 않으면 삭제 (정리)"""
        try:
            if self.filepath and os.path.exists(self.filepath):
                if os.path.getsize(self.filepath) == 0:
                    from .setup import P
                    P.logger.info(f"Cleaning up 0-byte file: {self.filepath}")
                    os.remove(self.filepath)
        except Exception as e:
            from .setup import P
            P.logger.error(f"Cleanup error: {e}")

    def _update_db_status(self):
        """DB의 상태 정보를 동기화"""
        try:
            if self.db_id:
                from .model import ModelDownloadItem
                with F.app.app_context():
                    item = F.db.session.query(ModelDownloadItem).filter_by(id=self.db_id).first()
                    if item:
                        item.status = self.status
                        if self.status == DownloadStatus.COMPLETED:
                            item.completed_time = datetime.now()
                            item.filesize = self.filesize
                        if self.error_message:
                            item.error_message = self.error_message
                        F.db.session.add(item)
                        F.db.session.commit()
        except Exception as e:
            from .setup import P
            P.logger.error(f"Failed to update DB status: {e}")

    def _invoke_plugin_callback(self):
        """호출한 플러그인의 콜백 메서드 호출"""
        try:
            from .setup import P
            P.logger.info(f"Invoking callback for plugin: {self.caller_plugin}, id: {self.callback_id}")
            
            # 플러그인 인스턴스 찾기 (PluginManager 사용)
            from framework import F
            target_P = None
            
            # caller_plugin은 "anime_downloader_ohli24" 형식이므로 패키지명 추출
            parts = self.caller_plugin.split('_')
            package_name = parts[0] if parts else self.caller_plugin
            
            # 패키지 이름으로 여러 조합 시도
            possible_names = [
                self.caller_plugin,  # anime_downloader_ohli24
                '_'.join(parts[:2]) if len(parts) > 1 else self.caller_plugin,  # anime_downloader
                package_name  # anime
            ]
            
            for name in possible_names:
                if name in F.PluginManager.all_package_list:
                    pkg_info = F.PluginManager.all_package_list[name]
                    if pkg_info.get('loading') and 'P' in pkg_info:
                        target_P = pkg_info['P']
                        break
            
            if target_P:
                # 모듈에서 콜백 메서드 찾기
                callback_invoked = False
                module_list = getattr(target_P, 'module_list', [])
                if isinstance(module_list, dict):
                    modules = module_list.items()
                elif isinstance(module_list, list):
                    modules = [(getattr(m, 'name', str(i)), m) for i, m in enumerate(module_list)]
                else:
                    modules = []

                for module_name, module_instance in modules:
                    if hasattr(module_instance, 'plugin_callback'):
                        callback_data = {
                            'callback_id': self.callback_id,
                            'status': self.status,
                            'filepath': self.filepath,
                            'filename': os.path.basename(self.filepath) if self.filepath else '',
                            'error': self.error_message
                        }
                        module_instance.plugin_callback(callback_data)
                        callback_invoked = True
                        P.logger.info(f"Callback invoked on module {module_name}")
                        break
                
                if not callback_invoked:
                    P.logger.debug(f"No plugin_callback method found in {self.caller_plugin}")
            else:
                P.logger.debug(f"Plugin {self.caller_plugin} not found in PluginManager")
        except Exception as e:
            P.logger.error(f"Error invoking plugin callback: {e}")
            P.logger.error(traceback.format_exc())
    
    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return {
            'id': self.id,
            'url': self.url,
            'filename': self.filename,
            'save_path': self.save_path,
            'source_type': self.source_type,
            'status': self.status,
            'progress': self.progress,
            'speed': self.speed,
            'eta': self.eta,
            'title': self.title,
            'thumbnail': self.thumbnail,
            'meta': self.meta,
            'error_message': self.error_message,
            'filepath': self.filepath,
            'caller_plugin': self.caller_plugin,
            'callback_id': self.callback_id,
            'db_id': self.db_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'created_time': self.created_time,
            'file_size': self.filesize,
        }
    
    def as_dict(self) -> Dict[str, Any]:
        """데이터 직렬화 (get_status 별칭)"""
        return self.get_status()
