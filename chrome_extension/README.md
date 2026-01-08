# GDM YouTube Downloader Chrome Extension

YouTube 영상을 FlaskFarm GDM(gommi_downloader_manager)으로 전송하여 다운로드하는 Chrome 확장프로그램입니다.

## 설치 방법

1. Chrome에서 `chrome://extensions/` 접속
2. 우측 상단 **개발자 모드** 활성화
3. **압축해제된 확장 프로그램을 로드합니다** 클릭
4. 이 `chrome_extension` 폴더 선택

## 사용 방법

### 팝업 UI
1. YouTube 영상 페이지에서 확장 아이콘 클릭
2. **GDM 서버** 주소 입력 (예: `http://192.168.1.100:9099`)
3. 원하는 **품질** 선택
4. **다운로드 시작** 클릭

### 페이지 버튼 (선택)
- YouTube 동영상 페이지에서 자동으로 **GDM** 버튼이 추가됩니다
- 버튼 클릭 시 최고 품질로 바로 다운로드 전송

### 우클릭 메뉴
- YouTube 페이지에서 우클릭 → **GDM으로 다운로드**

## API 엔드포인트

확장에서 사용하는 GDM API:

| 엔드포인트 | 용도 |
|-----------|------|
| `GET /gommi_downloader_manager/ajax/queue/youtube_formats?url=...` | 품질 목록 조회 |
| `POST /gommi_downloader_manager/ajax/queue/youtube_add` | 다운로드 추가 |

## 요구사항

- Chrome 88+ (Manifest V3)
- FlaskFarm + gommi_downloader_manager 플러그인
- yt-dlp 설치됨
