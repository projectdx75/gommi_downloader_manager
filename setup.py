"""
gommi_download_manager - FlaskFarm 범용 다운로더 큐 플러그인

지원 소스:
- YouTube (yt-dlp + aria2c)
- 애니24/링크애니 (ffmpeg HLS)
- Anilife (Camoufox + ffmpeg)
- 기타 HTTP 직접 다운로드

성능 최적화:
- aria2c 멀티커넥션 (16개 동시 연결)
- 직접 import 방식 (API 오버헤드 제거)
- asyncio 큐 처리
"""
import traceback

import os
package_name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))

setting = {
    'filepath': __file__,
    'use_db': True,
    'use_default_setting': True,
    'home_module': 'queue',
    'package_name': package_name,
    'menu': {
        'uri': package_name,
        'name': 'GDM',
        'list': [
            {
                'uri': 'queue',
                'name': '다운로드 큐',
                'list': [
                    {'uri': 'setting', 'name': '설정'},
                    {'uri': 'list', 'name': '다운로드 목록'},
                ]
            },
            {
                'uri': 'manual',
                'name': '매뉴얼',
                'list': [
                    {'uri': 'README.md', 'name': 'README'},
                ]
            },
            {'uri': 'log', 'name': '로그'},
        ]
    },
    'default_route': 'normal',
}

from plugin import *

P = create_plugin_instance(setting)

try:
    import flask
    from flask import Blueprint
    from .model import ModelSetting, ModelDownloadItem
except ImportError:
    pass

try:
    from .mod_queue import ModuleQueue
    P.set_module_list([ModuleQueue])
except Exception as e:
    P.logger.error(f'Exception:{str(e)}')
    P.logger.error(traceback.format_exc())


# ===== Public API for Chrome Extension (No Login Required) =====
try:
    from flask import Blueprint, request, jsonify
    
    public_api = Blueprint(f'{package_name}_public_api', package_name, url_prefix=f'/{package_name}/public')
    
    @public_api.route('/youtube/formats', methods=['GET', 'POST'])
    def youtube_formats():
        """YouTube 품질 목록 조회 (인증 불필요)"""
        url = request.args.get('url') or request.form.get('url', '')
        if not url:
            return jsonify({'ret': 'error', 'msg': 'URL이 필요합니다.'})
        
        try:
            import yt_dlp
            ydl_opts = {'quiet': True, 'no_warnings': True}
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                formats = [{'id': 'bestvideo+bestaudio/best', 'label': '최고 품질', 'note': ''}]
                heights = set()
                for f in info.get('formats', []):
                    h = f.get('height')
                    if h and f.get('vcodec') != 'none':
                        heights.add(h)
                
                for h in sorted(heights, reverse=True):
                    if h >= 2160: formats.append({'id': 'bestvideo[height<=2160]+bestaudio/best', 'label': '4K', 'note': ''})
                    elif h >= 1080: formats.append({'id': 'bestvideo[height<=1080]+bestaudio/best', 'label': '1080p', 'note': '권장'})
                    elif h >= 720: formats.append({'id': 'bestvideo[height<=720]+bestaudio/best', 'label': '720p', 'note': ''})
                
                formats.append({'id': 'bestaudio/best', 'label': '오디오만', 'note': ''})
                
                # 중복 제거
                seen, unique = set(), []
                for f in formats:
                    if f['id'] not in seen:
                        seen.add(f['id'])
                        unique.append(f)
                
                return jsonify({
                    'ret': 'success',
                    'title': info.get('title', ''),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration': info.get('duration', 0),
                    'formats': unique
                })
        except Exception as e:
            return jsonify({'ret': 'error', 'msg': str(e)})
    
    @public_api.route('/youtube/add', methods=['POST'])
    def youtube_add():
        """YouTube 다운로드 추가 (인증 불필요)"""
        try:
            if request.is_json:
                data = request.get_json()
            else:
                data = request.form.to_dict()
            
            url = data.get('url', '')
            if not url or ('youtube.com' not in url and 'youtu.be' not in url):
                return jsonify({'ret': 'error', 'msg': '유효한 YouTube URL이 필요합니다.'})
            
            format_id = data.get('format', 'bestvideo+bestaudio/best')
            
            from framework import F
            from tool import ToolUtil
            save_path = ToolUtil.make_path(P.ModelSetting.get('save_path'))
            
            item = ModuleQueue.add_download(
                url=url,
                save_path=save_path,
                source_type='youtube',
                caller_plugin='chrome_extension',
                format=format_id
            )
            
            if item:
                return jsonify({'ret': 'success', 'id': item.id, 'msg': '다운로드가 추가되었습니다.'})
            else:
                return jsonify({'ret': 'error', 'msg': '다운로드 추가 실패'})
        except Exception as e:
            P.logger.error(f'Public API youtube_add error: {e}')
            return jsonify({'ret': 'error', 'msg': str(e)})
    
    # Blueprint 등록
    from framework import F
    F.app.register_blueprint(public_api)
    P.logger.info(f'Public API registered: /{package_name}/public/')
    
except Exception as e:
    P.logger.warning(f'Public API registration failed: {e}')
