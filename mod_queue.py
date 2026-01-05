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

from .setup import P, PluginModuleBase, default_route_socketio_module, ToolUtil


class DownloadStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"  # 메타데이터 추출 중
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


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
        super(ModuleQueue, self).__init__(P, name='queue', first_menu='list')
        default_route_socketio_module(self, attach='/queue')

    
    def process_menu(self, page_name: str, req: Any) -> Any:
        """메뉴 페이지 렌더링"""
        P.logger.debug(f'Page Request: {page_name}')
        arg = P.ModelSetting.to_dict()
        try:
            arg['module_name'] = self.name
            arg['package_name'] = P.package_name  # 명시적 추가
            arg['path_data'] = F.config['path_data']
            return render_template(f'{P.package_name}_{self.name}_{page_name}.html', arg=arg)
        except Exception as e:
            P.logger.error(f'Exception:{str(e)}')
            P.logger.error(traceback.format_exc())
            return render_template('sample.html', title=f"{P.package_name}/{self.name}/{page_name}")
    
    def process_ajax(self, command: str, req: Any) -> Any:
        """AJAX 명령 처리"""
        # P.logger.debug(f'Command: {command}')
        ret = {'ret': 'success'}
        try:
            if command == 'add':
                # 큐에 다운로드 추가
                url = req.form['url']
                save_path = req.form.get('save_path') or ToolUtil.make_path(P.ModelSetting.get('save_path'))
                filename = req.form.get('filename')
                
                item = self.add_download(url, save_path, filename)
                ret['data'] = item.as_dict() if item else None
                
            elif command == 'list':
                # 진행 중인 다운로드 목록
                items = [d.get_status() for d in self._downloads.values()]
                P.logger.debug(f'List Command: {len(items)} items')
                ret['data'] = items
                
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
                    
        except Exception as e:
            P.logger.error(f'Exception:{str(e)}')
            P.logger.error(traceback.format_exc())
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
        **options
    ) -> Optional['DownloadTask']:
        """
        다운로드를 큐에 추가 (외부 플러그인에서 호출)
        
        Args:
            url: 다운로드 URL
            save_path: 저장 경로
            filename: 파일명 (자동 감지 가능)
            source_type: 소스 타입 (auto, youtube, ani24, linkkf, anilife, http)
            caller_plugin: 호출 플러그인 이름
            callback_id: 콜백 식별자
            on_progress: 진행률 콜백 (progress, speed, eta)
            on_complete: 완료 콜백 (filepath)
            on_error: 에러 콜백 (error_message)
            **options: 추가 옵션 (headers, cookies 등)
        
        Returns:
            DownloadTask 인스턴스
        """
        try:
            # 소스 타입 자동 감지
            if not source_type or source_type == 'auto':
                source_type = cls._detect_source_type(url)
            
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
                **options
            )
            
            with cls._queue_lock:
                cls._downloads[task.id] = task
            
            
            # 비동기 시작
            task.start()
            
            # DB 저장
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
            db_item.save()
            
            task.db_id = db_item.id

            
            return task
            
        except Exception as e:
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
    def _detect_source_type(cls, url: str) -> str:
        """URL에서 소스 타입 자동 감지"""
        url_lower = url.lower()
        
        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'youtube'
        elif 'ani24' in url_lower or 'ohli24' in url_lower:
            return 'ani24'
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
        P.logger.info('gommi_downloader 플러그인 로드')
        try:
            # DB에서 진행 중인 작업 로드
            with F.app.app_context():
                from .model import ModelDownloadItem
                
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
                        callback_id=item.callback_id
                        # options? DB에 저장 안함. 필요하면 추가해야 함.
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
                    
                P.logger.info(f'{len(items)}개의 중단된 다운로드 작업 복원됨')
            
        except Exception as e:
            P.logger.error(f'plugin_load error: {e}')
            P.logger.error(traceback.format_exc())
    
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
        self.filepath = ''
        
        # 메타데이터
        self.title = ''
        self.thumbnail = ''
        self.duration = 0
        self.filesize = 0
        
        # 내부
        self._thread: Optional[threading.Thread] = None
        self._downloader = None
        self._cancelled = False
        self.db_id: Optional[int] = None
    
    def start(self):
        """다운로드 시작 (비동기)"""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def _run(self):
        """다운로드 실행"""
        try:
            self.status = DownloadStatus.EXTRACTING
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
                **self.options
            )
            
            if self._cancelled:
                self.status = DownloadStatus.CANCELLED
            elif result.get('success'):
                self.status = DownloadStatus.COMPLETED
                self.filepath = result.get('filepath', '')
                self.progress = 100
                if self._on_complete:
                    self._on_complete(self.filepath)
            else:
                self.status = DownloadStatus.ERROR
                self.error_message = result.get('error', 'Unknown error')
                if self._on_error:
                    self._on_error(self.error_message)
                    
        except Exception as e:
            P.logger.error(f'Download error: {e}')
            P.logger.error(traceback.format_exc())
            self.status = DownloadStatus.ERROR
            self.error_message = str(e)
            if self._on_error:
                self._on_error(self.error_message)
        
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
                namespace=f'/{P.package_name}'
            )
        except:
            pass
    
    def cancel(self):
        """다운로드 취소"""
        self._cancelled = True
        if self._downloader:
            self._downloader.cancel()
        self.status = DownloadStatus.CANCELLED
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
            'error_message': self.error_message,
            'filepath': self.filepath,
            'caller_plugin': self.caller_plugin,
            'callback_id': self.callback_id,
        }
