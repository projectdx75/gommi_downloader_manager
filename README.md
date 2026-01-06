# Gommi Downloader Manager (GDM)

FlaskFarm용 범용 다운로드 매니저 플러그인입니다.
여러 다운로더 플러그인(YouTube, Anime 등)의 다운로드 요청을 통합 관리하고 큐(Queue)를 제공합니다.

## v0.2.0 변경사항
- **패키지명 수정**: `gommi_download_manager` -> `gommi_downloader_manager`로 폴더명과 일치시켜 Bind Key 오류 해결.
- **안정성 개선**: DB 테이블 생성 로직 강화 (`setup.py` 명시적 모델 import).
- **YouTube 제목 지원**: `yt-dlp` 다운로드 시작 시 영상의 진짜 제목과 썸네일을 실시간으로 DB에 업데이트합니다.
- **UI 개선**: 큐 리스트 템플릿 오류 수정.

## 설치 및 업데이트
1. `git pull`
2. FlaskFarm 재시작 (DB 마이그레이션 적용을 위해 필수)

## 지원 플러그인
- youtube-dl
- anime_downloader (Ohli24, Linkkf 등)
