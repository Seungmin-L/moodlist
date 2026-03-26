# Moodlist

가사 기반으로 곡을 분류해서 카테고리별 플레이리스트를 만드는 Streamlit 앱입니다.

## 빠른 시작

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install lyricsgenius spotipy python-dotenv
```

```bash
streamlit run app/streamlit_app.py
```

## 필요한 외부 서비스

- Genius API: `GENIUS_ACCESS_TOKEN`
- Spotify API: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`
- Naver 검색 API: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`(선택)
- Ollama: `ollama serve` 실행 후 모델 사용 가능

`.env` 예시:

```bash
GENIUS_ACCESS_TOKEN=...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
```

## 사용 방법

- `곡 추가` 탭: 곡 검색 → 가사 수집 → 정제 → 분류
- `Spotify` 탭: 플레이리스트 불러오기 → 트랙 선택 → 가사 + 분류
- `분류 결과` 탭: 카테고리별로 분류된 곡 조회
- `파이프라인` 탭: 미정제/미분류 데이터 일괄 정제·분류

## DB

- 파일: `data/songs.db`
- 설계: `songs_bronze`, `songs_silver`, `songs_gold`(Medallion)
- 초기화:

```bash
python -c "from db.database import init_db; init_db()"
```

## 참고

상세 아키텍처, DB 구조, 진행 상태는 아래 문서에서 확인하세요.  
`[PROJECT_PROGRESS.md](PROJECT_PROGRESS.md)`

## 트러블슈팅

- 화면/분류가 안 되면 `ollama serve`와 모델 상태를 먼저 확인
- Spotify 인증이 안 되면 `.spotify_cache`를 삭제하고 다시 로그인
- 중복 수집은 `songs_bronze`의 `(title, artist)` 유니크 조건으로 처리됨
