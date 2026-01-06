"""
다운로드 큐 모델 정의
"""
from plugin import ModelBase, db
from framework import F
import os
from datetime import datetime

# 패키지 이름 동적 처리 (폴더명 기준)
package_name = os.path.split(os.path.dirname(__file__))[-1]

class ModelDownloadItem(ModelBase):
    """다운로드 아이템 DB 모델"""
    __tablename__ = f'{package_name}_download_item'
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id: int = db.Column(db.Integer, primary_key=True)
    created_time: datetime = db.Column(db.DateTime)
    
    # 다운로드 정보
    url: str = db.Column(db.String)
    filename: str = db.Column(db.String)
    save_path: str = db.Column(db.String)
    source_type: str = db.Column(db.String)  # youtube, ani24, linkkf, anilife, http
    
    # 상태
    status: str = db.Column(db.String)  # pending, downloading, paused, completed, error
    progress: int = db.Column(db.Integer, default=0)
    speed: str = db.Column(db.String)
    eta: str = db.Column(db.String)
    
    # 메타데이터
    title: str = db.Column(db.String)
    thumbnail: str = db.Column(db.String)
    duration: int = db.Column(db.Integer)
    filesize: int = db.Column(db.Integer)
    
    # 호출자 정보
    caller_plugin: str = db.Column(db.String)
    callback_id: str = db.Column(db.String)
    
    # 에러 정보
    error_message: str = db.Column(db.Text)
    retry_count: int = db.Column(db.Integer, default=0)
    
    # 추가 메타데이터 (JSON 형태의 텍스트 저장)
    meta: str = db.Column(db.Text)

    def as_dict(self):
        ret = super(ModelDownloadItem, self).as_dict()
        import json
        if self.meta:
            try:
                ret['meta'] = json.loads(self.meta)
            except:
                ret['meta'] = {}
        else:
            ret['meta'] = {}
        return ret

    @classmethod
    def check_migration(cls):
        """DB 컬럼 누락 체크 및 추가"""
        try:
            from .setup import P
            import sqlite3
            db_file = F.app.config['SQLALCHEMY_BINDS'][package_name].replace('sqlite:///', '').split('?')[0]
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # meta 컬럼 확인
            cursor.execute(f"PRAGMA table_info({cls.__tablename__})")
            columns = [info[1] for info in cursor.fetchall()]
            
            if 'meta' not in columns:
                P.logger.info(f"Adding 'meta' column to {cls.__tablename__}")
                cursor.execute(f"ALTER TABLE {cls.__tablename__} ADD COLUMN meta TEXT")
                conn.commit()
            
            conn.close()
        except Exception as e:
            from .setup import P
            P.logger.error(f"Migration Error: {e}")
            import traceback
            P.logger.error(traceback.format_exc())

