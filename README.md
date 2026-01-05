# gommi_download_manager (GDM)

FlaskFarm 범용 다운로더 큐 플러그인 (v0.1.0)

## 🆕 0.1.0 업데이트 (Latest)
- **다운로드 속도 제한**: 설정 페이지에서 대역폭 제한 설정 가능 (무제한, 1MB/s, 5MB/s...)
- **UI 리뉴얼**: 고급스러운 Dark Metallic 디자인 & 반응형 웹 지원
- **안정성 강화**: 서버 재시작 시 대기 중인 다운로드 상태 복원 (Queue Persistence)
- **목록 관리**: 전체 삭제 및 자동 목록 갱신 기능 (Flickr-free)

## 주요 기능

- **YouTube/일반 사이트**: yt-dlp + aria2c 지원 (고속 분할 다운로드)
- **스트리밍 사이트**: 애니24, 링크애니, Anilife (ffmpeg HLS / Camoufox) 지원
- **중앙 집중식 관리**: 여러 플러그인의 다운로드 요청을 한곳에서 통합 관리
- **전역 속도 제한 (Smart Limiter)**: 모든 다운로드에 공통 적용되는 속도 제한 기능

## 외부 플러그인에서 사용하기

```python
from gommi_download_manager.mod_queue import ModuleQueue

# 다운로드 추가 (속도 제한은 사용자가 설정한 값 자동 적용)
task = ModuleQueue.add_download(
    url='https://www.youtube.com/watch?v=...',
    save_path='/path/to/save', # 플러그인별 저장 경로 우선 적용
    filename='video.mp4',  # 선택
    source_type='auto',    # 자동 감지
    caller_plugin='youtube', # 호출자 식별
)
```

## 설정 가이드

웹 인터페이스 (`/gommi_download_manager/queue/setting`)에서 다음을 설정할 수 있습니다:
- **속도 제한**: 네트워크 상황에 맞춰 최대 다운로드 속도 조절
- **동시 다운로드 수**: 한 번에 몇 개를 받을지 설정
- **기본 저장 경로**: 경로 미지정 요청에 대한 백업 경로

## 성능 비교

| 다운로더 | 방식 | 특징 |
|---------|------|------|
| **yt-dlp (Native)** | 안정적 | 속도 제한 기능 완벽 지원 |
| **aria2c** | 고속 (분할) | 대용량 파일에 최적화 (현재 실험적 지원) |
| **ffmpeg** | 스트림 | HLS/M3U8 영상 저장에 사용 |
