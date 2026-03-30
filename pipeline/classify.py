"""
가사 분류 모듈

- 가사 정제 (clean.py 로직 흡수)
- GPT-4o-mini로 category/mood/emotions 분류
- OpenAI text-embedding-3-small로 mood 임베딩 생성
- Oracle DB에 결과 저장
"""

import json
import os
import re
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from db.database import (
    get_pending_songs,
    get_song,
    insert_song,
    update_classification,
    update_lyrics
)
from pipeline.crawl import search_song_with_diagnostics, filter_original_korean, get_lyrics

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

SYSTEM_PROMPT = """당신은 한국 노래 가사의 상황과 감정을 분석하는 전문가입니다.

## 분류 체계

### category (대주제) - 반드시 아래 5개 중 하나
- 사랑: 연애, 호감, 관계에 대한 노래
- 이별: 헤어짐, 관계의 끝
- 자기자신: 자존감, 성장, 다짐, 위로
- 일상: 친구, 가족, 일상의 감정
- 기타: 위에 해당 안 됨

### mood (분위기/무드) - 자유롭게 생성
이 곡을 어떤 기분일 때 들을지를 짧은 한국어 구문으로 표현.
예: "후련한 이별", "슬픈 미련", "분노 폭발", "쿨하게 놓아줌", "달달한 설렘", "혼자만의 위로"
정해진 목록 없이 곡의 분위기에 맞게 자유롭게 만들어라.

### emotions (감정 점수)
0.0~1.0 사이 점수, 0.3 이상만 포함. 감정명도 자유롭게 사용 가능.

## 분석 규칙
1. 가사 전체 흐름을 읽어라 (시작 → 끝)
2. 반전이 있으면 마지막 감정이 primary_emotion
3. emotions 점수는 독립적 (합이 1.0 안 넘어도 됨)
4. 반드시 JSON만 출력하고, 다른 텍스트는 절대 포함하지 마"""


# ======================
# 가사 정제 (clean.py 흡수)
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
  "category": "대주제 (사랑/이별/자기자신/일상/기타)",
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


def get_mood_embedding(mood: str) -> list:
    """mood 텍스트 → 임베딩 벡터"""
    if not mood:
        return []
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=mood
    )
    return response.data[0].embedding


# ======================
# 파이프라인
# ======================

def classify_song(song_id: int) -> dict:
    """
    단일 곡 분류.
    가사 정제 → GPT 분류 → 임베딩 생성 → Oracle 저장
    """
    song = get_song(song_id)
    if not song:
        raise ValueError(f"Song ID {song_id} 없음")

    # 가사 정제
    lyrics = clean_lyrics(song.get("lyrics") or "")
    if not lyrics:
        update_classification(song_id, error="가사 없음")
        raise ValueError("정제 후 가사 없음")

    # 정제된 가사 저장
    update_lyrics(song_id, lyrics)

    # GPT 분류
    result = classify_lyrics(lyrics, song["title"], song["artist"])

    # 임베딩 생성
    result["mood_embedding"] = get_mood_embedding(result.get("mood", ""))

    # Oracle 저장
    update_classification(song_id, result=result)

    return result


def add_and_classify(title: str, artist: str) -> dict:
    """
    곡 추가 + 분류 전체 흐름.
    이미 분류된 곡이면 기존 결과 반환.

    1. DB 조회 → 이미 classified면 바로 반환
    2. Genius 크롤링
    3. insert_song → classify_song
    """
    # 1. DB 조회
    result = insert_song(title, artist)
    if result["already_exists"] and result["status"] == "classified":
        print(f"이미 분류된 곡: {title} - {artist}")
        return result

    song_id = result["song_id"]

    # 2. Genius 크롤링
    results, diagnostics = search_song_with_diagnostics(title=title, artist=artist, limit=20)
    filtered = filter_original_korean(results) or results

    if not filtered:
        error_msg = f"Genius에서 곡을 찾을 수 없음: {title} - {artist}"
        update_classification(song_id, error=error_msg)
        raise ValueError(error_msg)

    lyrics = get_lyrics(song_url=filtered[0]["url"])
    if not lyrics:
        error_msg = "가사를 가져올 수 없음"
        update_classification(song_id, error=error_msg)
        raise ValueError(error_msg)

    # 3. 가사 저장 후 분류
    update_lyrics(song_id, lyrics)
    classification = classify_song(song_id)

    return {
        "song_id": song_id,
        "title": title,
        "artist": artist,
        "already_exists": result["already_exists"],
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
        song_id = song["id"]
        title = song["title"]
        artist = song["artist"]

        print(f"분류 중: {title} - {artist}")

        try:
            result = classify_song(song_id)
            classified.append({
                "song_id": song_id,
                "title": title,
                "artist": artist,
                **result
            })
            print(f"  ✓ [{result['category']}] {result['mood']} ({result['primary_emotion']}, {result['confidence']:.0%})")
            print(f"    📝 {result['narrative']}")
            print(f"    🎵 \"{result.get('key_lyrics', '')}\"")
            print(f"    💡 {result.get('reasoning', '')}")

        except Exception as e:
            update_classification(song_id, error=str(e))
            print(f"  ✗ 실패: {e}")

    print(f"\n총 {len(classified)}곡 분류 완료")
    return classified


# ======================
# 내부 유틸
# ======================

def _try_repair_json(content: str) -> dict | None:
    """잘린 JSON 복구 시도"""
    idx = content.find('{')
    if idx == -1:
        return None
    content = content[idx:]

    for suffix in ['"}', ']}', '}', '"]}', '"}]}']:
        try:
            return json.loads(content + suffix)
        except json.JSONDecodeError:
            continue

    last_comma = content.rfind(',')
    if last_comma > 0:
        try:
            return json.loads(content[:last_comma] + '}')
        except json.JSONDecodeError:
            pass

    return None


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

    if result["category"] not in {"사랑", "이별", "자기자신", "일상", "기타"}:
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
