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
package_name = os.path.split(os.path.dirname(__file__))[-1]

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
