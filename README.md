# gommi_download_manager (GDM)

FlaskFarm 범용 다운로더 큐 플러그인 (v0.2.0)

## 🆕 0.2.0 업데이트 (2026-01-06)

### 새 기능
- **플러그인 콜백 시스템**: 다운로드 완료 시 호출 플러그인에 상태 알림
- **외부 플러그인 통합 강화**: `caller_plugin`, `callback_id` 파라미터로 호출자 추적
- **HLS ffmpeg 헤더 수정**: None 값 필터링으로 에러 방지

### 버그 수정
- PluginManager API 호환성 수정 (`F.plugin_instance_list` → `F.PluginManager.all_package_list`)
- 완료된 다운로드 진행률 100% 표시 수정
- 큐 목록 URL 표시 제거 (깔끔한 UI)

### UI 개선
- 다크 메탈릭 디자인 유지
- 완료 상태 표시 개선

---

## 주요 기능

- **YouTube/일반 사이트**: yt-dlp + aria2c 지원 (고속 분할 다운로드)
- **스트리밍 사이트**: 애니24, 링크애니, Anilife (ffmpeg HLS / Camoufox) 지원
- **중앙 집중식 관리**: 여러 플러그인의 다운로드 요청을 한곳에서 통합 관리
- **전역 속도 제한 (Smart Limiter)**: 모든 다운로드에 공통 적용되는 속도 제한 기능

## 외부 플러그인에서 사용하기

```python
from gommi_download_manager.mod_queue import ModuleQueue

# 다운로드 추가 (콜백 지원)
task = ModuleQueue.add_download(
    url='https://www.youtube.com/watch?v=...',
    save_path='/path/to/save',
    filename='video.mp4',
    source_type='auto',
    caller_plugin='my_plugin_name',  # 콜백 호출 시 식별자
    callback_id='unique_item_id',    # 콜백 데이터에 포함
)
```

## 콜백 수신하기

호출 플러그인에서 `plugin_callback` 메서드를 정의하면 다운로드 완료 시 자동 호출됩니다:

```python
class MyModule:
    def plugin_callback(self, data):
        # data = {'callback_id': ..., 'status': 'completed', 'filepath': ..., 'error': ...}
        if data['status'] == 'completed':
            print(f"다운로드 완료: {data['filepath']}")
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
