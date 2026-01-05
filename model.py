"""
다운로드 큐 모델 정의
"""
from plugin import ModelBase, db

package_name = 'gommi_download_manager'


from datetime import datetime

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

