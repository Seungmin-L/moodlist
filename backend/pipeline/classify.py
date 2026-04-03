"""
가사 분류 모듈

파이프라인:
1. Spotify 검색 → spotify_id + 영어 제목/아티스트 확보
2. DB 중복 확인 (spotify_id 기준)
3. Genius에서 영어 제목으로 가사 크롤링
4. GPT-4o-mini로 category/mood/emotions 분류
5. text-embedding-3-small로 mood 임베딩 생성
6. Oracle DB에 저장
"""

import json
import os
import re
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
REPO_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(REPO_ROOT / ".env")

from db.database import (
    get_pending_songs,
    get_song,
    insert_song,
    update_classification,
    update_lyrics
)
from pipeline.crawl import search_song_with_diagnostics, filter_original_korean, get_lyrics
from pipeline.spotify import search_track

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

SYSTEM_PROMPT = """당신은 한국 노래 가사의 상황과 감정을 분석하는 전문가입니다.

## 분류 체계

### category (대주제) - 반드시 아래 10개 중 하나

category는 "관계의 현재 상태"를 기준으로 판단한다.
감정의 종류(분노, 자신감, 그리움 등)가 아니라 관계가 어떤 단계에 있는지가 category를 결정한다.

- 관심: 풋풋하게 눈에 띄는 단계, 아직 감정인지도 모르는 설레는 상태
- 짝사랑: 일방적인 감정, 고백 못 한 마음, 혼자 품는 사랑
- 썸: 밀당, 서로 의식하지만 아직 확실하지 않은 애매한 관계
- 사랑: 확실한 연애, 두 사람이 함께하는 상태에서의 감정
- 권태기: 관계가 유지되지만 무감각해지거나 식어가는 상태
- 갈등: 관계가 아직 유지되는 상태에서의 싸움, 오해, 충돌 (아직 헤어지지 않음)
- 이별: 관계가 끝났거나 끝나는 과정의 모든 감정 (분노, 후련, 그리움, 미련, 자존감 회복 등 감정 종류 무관)
  → 이별 후 분노/원망 → 이별 (갈등 아님)
  → 이별 후 자존감 회복/성장 → 이별 (자기자신 아님)
  → 이별 직전, 보내주기 → 이별
  → 이별 후 재회 소망 → 이별
- 자기자신: 연애와 완전히 무관한 자기 이야기 (자존감, 성장, 다짐, 위로)
- 일상: 친구, 가족, 일상의 감정
- 기타: 위에 해당 안 됨

### 분류 판단 순서 (반드시 따를 것)
1. 먼저 관계 상태를 파악: 만남 전 / 진행 중 / 끝났거나 끝나는 중?
2. 그 상태에 해당하는 category를 선택
3. 감정(분노, 자신감, 그리움 등)은 emotions와 mood로 표현

### mood (분위기/무드) - 자유롭게 생성
이 곡을 어떤 기분일 때 들을지를 짧은 한국어 구문으로 표현.
예: "후련한 이별", "슬픈 미련", "분노 폭발", "쿨하게 놓아줌", "달달한 설렘", "혼자만의 위로"
정해진 목록 없이 곡의 분위기에 맞게 자유롭게 만들어라.
단, 같은 category 안에서도 곡마다 다른 뉘앙스를 반드시 구분하여 다른 mood를 부여하라.

### emotions (감정 점수)
0.0~1.0 사이 점수, 0.3 이상만 포함.
반드시 아래 20개 표준 감정 중에서만 선택하라:

그리움, 슬픔, 미련, 체념, 분노, 후련함, 자신감, 결단,
설렘, 사랑, 불안, 혼란, 상실감, 행복, 기대, 상처, 외로움, 실망, 갈망, 안타까움

primary_emotion도 반드시 위 20개 중 하나여야 한다.

## 분석 규칙
1. 가사 전체 흐름을 읽어라 (시작 -> 끝)
2. 반전이 있으면 마지막 감정이 primary_emotion
3. 곡의 **관계 상태**가 category를 결정: 이별한 상태에서 어떤 감정을 느끼든 category는 이별
4. emotions 점수는 독립적 (합이 1.0 안 넘어도 됨)
5. narrative는 곡의 구체적인 상황과 화자의 심경을 2~3문장으로 자세히 서술하라. 다른 곡과 구별되는 고유한 맥락을 반드시 포함하라.
6. 반드시 JSON만 출력하고, 다른 텍스트는 절대 포함하지 마"""


# ======================
# 가사 정제
# ======================

def clean_lyrics(raw_lyrics: str) -> str:
    """Genius raw 가사 정제"""
    if not raw_lyrics:
        return ""

    text = raw_lyrics
    text = re.sub(r'\d*Embed$', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'You might also like', '', text, flags=re.IGNORECASE)
    text = re.sub(r'See .+ Live.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Get tickets as low as \$\d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines).strip()
    return text


# ======================
# LLM 분류
# ======================

def classify_lyrics(lyrics: str, title: str = "", artist: str = "") -> dict:
    """GPT-4o-mini로 가사 분류"""

    user_prompt = f"""아래 곡을 분석하고 JSON만 출력하세요.

- 제목: {title}
- 아티스트: {artist}

## 가사
{lyrics[:3000]}

## 응답 형식 (JSON만, 다른 텍스트 금지)
{{
  "category": "대주제 (관심/짝사랑/썸/사랑/권태기/갈등/이별/자기자신/일상/기타)",
  "mood": "이 곡의 분위기를 짧은 구문으로 자유롭게 표현",
  "emotions": {{"감정명": 점수}},
  "primary_emotion": "가장 강한 감정",
  "emotional_arc": "시작감정 → 끝감정",
  "tags": ["키워드1", "키워드2"],
  "narrative": "가사의 핵심 상황과 화자의 심정을 2~3문장으로",
  "key_lyrics": "분류 근거가 된 핵심 가사 1~2줄 인용",
  "reasoning": "이렇게 분류한 이유를 한 줄로",
  "confidence": 0.0~1.0
}}"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=800
    )

    content = response.choices[0].message.content.strip()

    if "```" in content:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if match:
            content = match.group(1).strip()

    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        content = json_match.group()

    result = json.loads(content)
    return _validate_result(result)


def get_mood_embedding(mood: str, result: dict = None) -> list:
    """mood + 분류 컨텍스트 → 임베딩 벡터
    Phase 1: mood 단독(~8자) 대신 category/emotion/arc/narrative를 결합(~120자)하여
    카테고리 내부 분화와 크로스 카테고리 침범을 개선한다.
    """
    if not mood:
        return []
    if result:
        text = (
            f"[{result.get('category', '')}] {mood}"
            f" | {result.get('primary_emotion', '')}"
            f" | {result.get('emotional_arc', '')}"
            f" | {result.get('narrative', '')}"
        )
    else:
        text = mood
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


# ======================
# 파이프라인
# ======================

def classify_song(spotify_id: str) -> dict:
    """
    단일 곡 분류.
    가사 정제 → GPT 분류 → 임베딩 생성 → Oracle 저장
    """
    song = get_song(spotify_id)
    if not song:
        raise ValueError(f"Spotify ID {spotify_id} 없음")

    lyrics = clean_lyrics(song.get("lyrics") or "")
    if not lyrics:
        update_classification(spotify_id, error="가사 없음")
        raise ValueError("정제 후 가사 없음")

    update_lyrics(spotify_id, lyrics)

    result = classify_lyrics(lyrics, song["title"], song["artist"])
    result["mood_embedding"] = get_mood_embedding(result.get("mood", ""), result)

    update_classification(spotify_id, result=result)

    return result


def add_and_classify(title: str, artist: str) -> dict:
    """
    곡 추가 + 분류 전체 흐름.

    1. Spotify 검색 → spotify_id + 영어 제목/아티스트
    2. DB 중복 확인 → 이미 classified면 즉시 반환
    3. Genius에서 영어 제목으로 가사 크롤링
    4. 분류 → 저장
    """
    # 1. Spotify 검색
    # 아티스트 포함해서 먼저 시도, 실패하면 제목만으로 재시도
    spotify_result = search_track(title, artist)
    if not spotify_result:
        spotify_result = search_track(title, "")
    if not spotify_result:
        raise ValueError(f"Spotify에서 곡을 찾을 수 없음: {title} - {artist}")

    spotify_id = spotify_result["id"]
    en_title = spotify_result["title"]
    en_artist = spotify_result["artist"]
    image_url = spotify_result.get("image_url")

    print(f"Spotify 매칭: '{title} - {artist}' → '{en_title} - {en_artist}'")

    # 2. DB 중복 확인
    db_result = insert_song(spotify_id, en_title, en_artist, album_art_url=image_url)
    if db_result["already_exists"] and db_result.get("status") == "classified":
        print(f"이미 분류된 곡: {en_title} - {en_artist}")
        return db_result

    # 3. Genius 가사 크롤링 (영어 제목/아티스트로)
    results, diagnostics = search_song_with_diagnostics(title=en_title, artist=en_artist, limit=20)
    filtered = filter_original_korean(results) or results

    if not filtered:
        error_msg = f"Genius에서 가사를 찾을 수 없음: {en_title} - {en_artist}"
        update_classification(spotify_id, error=error_msg)
        raise ValueError(error_msg)

    lyrics = get_lyrics(song_url=filtered[0]["url"])
    if not lyrics:
        error_msg = "가사를 가져올 수 없음"
        update_classification(spotify_id, error=error_msg)
        raise ValueError(error_msg)

    # 4. 가사 저장 후 분류
    update_lyrics(spotify_id, lyrics)
    classification = classify_song(spotify_id)

    return {
        "spotify_id": spotify_id,
        "title": en_title,
        "artist": en_artist,
        "album_art_url": image_url,
        "already_exists": db_result["already_exists"],
        **classification
    }


def add_and_classify_by_id(spotify_id: str, title: str, artist: str, image_url: str = None) -> dict:
    """
    Spotify ID가 확정된 곡 추가 + 분류 (Spotify 검색 스킵).
    유저가 suggestions에서 직접 선택한 경우 사용.
    """
    db_result = insert_song(spotify_id, title, artist, album_art_url=image_url)
    if db_result["already_exists"] and db_result.get("status") == "classified":
        print(f"이미 분류된 곡: {title} - {artist}")
        return db_result

    results, diagnostics = search_song_with_diagnostics(title=title, artist=artist, limit=20)
    filtered = filter_original_korean(results) or results

    if not filtered:
        error_msg = f"Genius에서 가사를 찾을 수 없음: {title} - {artist}"
        update_classification(spotify_id, error=error_msg)
        raise ValueError(error_msg)

    lyrics = get_lyrics(song_url=filtered[0]["url"])
    if not lyrics:
        error_msg = "가사를 가져올 수 없음"
        update_classification(spotify_id, error=error_msg)
        raise ValueError(error_msg)

    update_lyrics(spotify_id, lyrics)
    classification = classify_song(spotify_id)

    return {
        "spotify_id": spotify_id,
        "title": title,
        "artist": artist,
        "album_art_url": image_url,
        "already_exists": db_result["already_exists"],
        **classification
    }


def classify_pending_songs() -> list:
    """pending/error 상태 곡 일괄 분류"""
    pending = get_pending_songs()

    if not pending:
        print("분류할 곡이 없습니다.")
        return []

    classified = []

    for song in pending:
        spotify_id = song["spotify_id"]
        title = song["title"]
        artist = song["artist"]

        print(f"분류 중: {title} - {artist}")

        try:
            result = classify_song(spotify_id)
            classified.append({
                "spotify_id": spotify_id,
                "title": title,
                "artist": artist,
                **result
            })
            print(f"  ✓ [{result['category']}] {result['mood']} ({result['primary_emotion']}, {result['confidence']:.0%})")
            print(f"    {result['narrative']}")
            print(f"    \"{result.get('key_lyrics', '')}\"")

        except Exception as e:
            update_classification(spotify_id, error=str(e))
            print(f"  ✗ 실패: {e}")

    print(f"\n총 {len(classified)}곡 분류 완료")
    return classified


# ======================
# 내부 유틸
# ======================

def _validate_result(result: dict) -> dict:
    """분류 결과 검증 및 정규화"""
    defaults = {
        "category": "기타",
        "mood": "",
        "emotions": {},
        "primary_emotion": "미분류",
        "emotional_arc": "",
        "tags": [],
        "narrative": "",
        "key_lyrics": "",
        "reasoning": "",
        "confidence": 0.5
    }

    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    if result["category"] not in {"관심", "짝사랑", "썸", "사랑", "권태기", "갈등", "이별", "자기자신", "일상", "기타"}:
        result["category"] = "기타"

    if not isinstance(result["emotions"], dict):
        result["emotions"] = {}

    for emotion, score in list(result["emotions"].items()):
        if not isinstance(score, (int, float)):
            result["emotions"][emotion] = 0.0
        else:
            result["emotions"][emotion] = max(0.0, min(1.0, float(score)))

    if not result["primary_emotion"] and result["emotions"]:
        result["primary_emotion"] = max(result["emotions"], key=result["emotions"].get)

    if not isinstance(result["tags"], list):
        result["tags"] = []

    result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.5))))

    return result
