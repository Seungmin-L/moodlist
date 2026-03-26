# Moodlist (Music Classification)

Korean mood-based music playlist tool using lyric crawling, text cleaning, and LLM classification.

This project enables:
- Search lyrics from Genius
- Clean and enrich lyric data
- Classify songs into emotion-themed categories via Ollama
- Manage categories and create Spotify playlists from results

---

## 1) 프로젝트 개요

`music-classification`은 스트리밍형 파이프라인이 아니라,  
사용자 요청(버튼 클릭/탭 실행) 기반으로 처리되는 `Medallion` 구조의 음악 분류 시스템이다.

- UI: Streamlit (`app/streamlit_app.py`)
- DB: SQLite (`data/songs.db`)
- Orchestration: Streamlit이 탭별 동작을 오케스트레이션
- Processing: `crawl` → `clean` → `classify`

---

## 2) 폴더/파일 구조

```text
.
├─ app/
│  └─ streamlit_app.py          # Streamlit UI + 전체 오케스트레이션
├─ db/
│  └─ database.py               # SQLite 스키마/조회/저장 함수
├─ pipeline/
│  ├─ crawl.py                  # Genius 검색/가사 크롤링
│  ├─ clean.py                  # 가사 정제(Bronze->Silver)
│  ├─ classify.py               # LLM 분류(Silver->Gold)
│  ├─ spotify.py                # Spotify API 래퍼
│  ├─ naver_search.py           # 영어 제목 -> 한국어 제목 보정
│  ├─ test_spotify_kr.py        # Spotify API 보조 테스트
│  └─ test_naver_search.py      # Naver 검색 보조 테스트
├─ data/
│  └─ songs.db                  # SQLite DB 파일(실행 시 생성)
├─ requirements.txt
└─ README.md
```

---

## 3) 아키텍처 요약

### Medallion Pipeline
- Bronze: `songs_bronze` (원본 가사)
- Silver: `songs_silver` (정제 가사)
- Gold: `songs_gold` (분류 결과)

### App Flow
1. 사용자가 Streamlit에서 요청
2. 모듈 호출 (`crawl` / `clean` / `classify` / `spotify.py`)
3. 결과를 SQLite에 저장
4. UI에서 통계/분류 결과/플레이리스트 생성 버튼으로 결과 확인

---

## 4) DB 스키마

핵심 테이블은 `db/database.py`의 `init_db()`에서 생성된다.

```sql
CREATE TABLE songs_bronze (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    raw_lyrics TEXT,
    source_url TEXT,
    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(title, artist)
);

CREATE TABLE songs_silver (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bronze_id INTEGER NOT NULL,
    clean_lyrics TEXT NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bronze_id) REFERENCES songs_bronze(id)
);

CREATE TABLE songs_gold (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    silver_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    confidence REAL,
    classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (silver_id) REFERENCES songs_silver(id)
);

CREATE TABLE playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE playlist_songs (
    playlist_id INTEGER,
    gold_id INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (playlist_id, gold_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id),
    FOREIGN KEY (gold_id) REFERENCES songs_gold(id)
);
```

---

## 5) 실행 전 준비

### 필수 외부 서비스
- Genius API 키
  - https://genius.com/api-clients
- Spotify API 키
  - Client ID / Client Secret
- Naver 검색 API 키 (선택, 일부 경로에서 사용)
- Ollama (로컬 LLM)

### 의존성 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> 참고: `requirements.txt`에는 일부 런타임 패키지가 빠져 있을 수 있어 아래 패키지를 추가 설치해야 할 수 있다.

```bash
pip install lyricsgenius spotipy python-dotenv
```

### 환경 변수(.env)

```bash
GENIUS_ACCESS_TOKEN=your_genius_token
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret
```

`.env`는 프로젝트 루트(`/Users/iseungmin/Documents/GitHub/music-classification/.env`)에 둔다.

### Ollama 설정

```bash
brew install ollama
ollama serve
ollama pull ministral-3:8b   # 또는 모델명 변경 가능
```

---

## 6) 실행 방법

### DB 초기화

```bash
python -c "from db.database import init_db; init_db()"
```

### Streamlit 실행

```bash
streamlit run app/streamlit_app.py
```

### 주요 사용 흐름

- 곡 추가 탭: 곡 검색 → 가사 가져오기 → 정제 → 분류
- Spotify 탭: 플레이리스트 불러오기 → 선택 곡 처리 → 분류 → 카테고리별 플레이리스트 생성
- 파이프라인 탭: 정제 실행 / 분류 실행 / 전체 실행
- 분류 결과 탭: 카테고리별 목록 조회

---

## 7) 트러블슈팅

- Ollama가 안 뜰 때: `ollama serve` 실행 여부 확인
- Spotify 로그인 실패: `SPOTIFY_CLIENT_*` 값과 OAuth 캐시 초기화 후 재시도
- Naver 키 오류: `NAVER_CLIENT_*` 값 확인
- 중복 수집 방지: `songs_bronze`는 `(title, artist)` 유니크 제약 적용

---

## 8) 현재 상태

- 핵심 기능은 구현됨(검색/크롤링/정제/분류/플레이리스트 생성)
- 운영 수준 안정성은 미흡한 편
  - 예외/재시도 정책 강화 필요
  - 의존성 정합성 점검 필요 (`requirements.txt` 보완 권장)
  - DB 외래키 활성화/스키마 마이그레이션 전략 정립 필요

---

## 9) 라이선스

개인/학습용 프로젝트.  
필요 시 재배포 전 의존성 및 API 이용 약관을 다시 확인한다.

