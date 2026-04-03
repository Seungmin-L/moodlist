"""
Phase 2 Before vs After 비교 리포트 생성
- Phase 2 before (snapshot_phase2_before.md) vs 현재 DB 상태
- emotion_vector 품질 측정
- 2축 하이브리드 유사도 테스트
"""
import json
import math
import sys
import random
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import ssl as _ssl
from dotenv import load_dotenv
import oracledb

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

DSN = os.getenv("ORACLE_DSN", "").replace("ssl_server_dn_match=yes", "ssl_server_dn_match=no")

STANDARD_EMOTIONS = [
    "그리움", "슬픔", "미련", "체념", "분노", "후련함", "자신감", "결단",
    "설렘", "사랑", "불안", "혼란", "상실감", "행복", "기대", "상처",
    "외로움", "실망", "갈망", "안타까움"
]


def get_connection():
    ssl_ctx = _ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = _ssl.CERT_NONE
    conn = oracledb.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASSWORD"),
        dsn=DSN, tcp_connect_timeout=15, ssl_context=ssl_ctx,
    )
    def _clob_handler(cursor, metadata):
        if metadata.type_code is oracledb.DB_TYPE_CLOB:
            return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
    conn.outputtypehandler = _clob_handler
    return conn


def cosine_dist(a, b):
    if not a or not b:
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - dot / (na * nb)


def hybrid_dist(emb_a, emb_b, emo_a, emo_b):
    """2축 하이브리드: text embedding (0.6) + emotion vector (0.4)"""
    emb_d = cosine_dist(emb_a, emb_b)
    if emo_a and emo_b:
        emo_d = cosine_dist(emo_a, emo_b)
        return 0.6 * emb_d + 0.4 * emo_d
    return emb_d


def load_before_data():
    """Phase 2 before 스냅샷에서 곡별 데이터 파싱"""
    path = REPO_ROOT / "docs" / "pipeline-improvement" / "snapshot_phase2_before.md"
    text = path.read_text(encoding="utf-8")
    songs = {}
    current_song = None

    for line in text.split("\n"):
        if line.startswith("#### ") and " - " in line:
            current_song = {"_raw_header": line[5:].strip()}
        elif current_song and line.startswith("| spotify_id |"):
            current_song["spotify_id"] = line.split("|")[2].strip().strip("`")
        elif current_song and line.startswith("| category |"):
            current_song["category"] = line.split("|")[2].strip().strip("*")
        elif current_song and line.startswith("| mood |"):
            current_song["mood"] = line.split("|")[2].strip()
        elif current_song and line.startswith("| primary_emotion |"):
            current_song["primary_emotion"] = line.split("|")[2].strip()
        elif current_song and line.startswith("| emotional_arc |"):
            current_song["emotional_arc"] = line.split("|")[2].strip()
        elif current_song and line.startswith("| narrative |"):
            current_song["narrative"] = line.split("|")[2].strip()
            if "spotify_id" in current_song:
                songs[current_song["spotify_id"]] = current_song
            current_song = None

    return songs


def run():
    before = load_before_data()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT spotify_id, title, artist, category, mood, primary_emotion,
               emotional_arc, emotions, tags, narrative, confidence,
               mood_embedding, emotion_vector
        FROM songs
        WHERE status = 'classified'
        ORDER BY category, title
    """)
    cols = [c[0].lower() for c in cursor.description]
    after_rows = []
    for row in cursor.fetchall():
        d = dict(zip(cols, row))
        emb = d.get("mood_embedding")
        d["_vec"] = list(emb) if emb is not None else []
        emo = d.get("emotion_vector")
        d["_emo"] = list(emo) if emo is not None else []
        for field in ["emotions", "tags"]:
            val = d.get(field)
            if isinstance(val, str):
                try:
                    d[field] = json.loads(val)
                except Exception:
                    pass
        after_rows.append(d)

    after = {r["spotify_id"]: r for r in after_rows}
    conn.close()

    lines = []
    lines.append("# Phase 2 Before vs After 비교 리포트\n")
    lines.append("> Phase 2: 표준 감정 사전(20개) + emotion_vector(20차원) + 2축 하이브리드 유사도\n")
    lines.append("> Spotify audio features는 API 제한(403)으로 수집 불가, 2축(embedding+emotion) 적용\n")

    # 1. 카테고리 분포 비교
    lines.append("## 1. 카테고리 분포 비교\n")
    before_cats = Counter(s.get("category", "") for s in before.values())
    after_cats = Counter(s.get("category", "") for s in after.values())
    all_cats = sorted(set(list(before_cats.keys()) + list(after_cats.keys())))
    lines.append("| 카테고리 | Before | After | 변화 |")
    lines.append("|----------|--------|-------|------|")
    for cat in all_cats:
        b = before_cats.get(cat, 0)
        a = after_cats.get(cat, 0)
        diff = a - b
        diff_str = f"+{diff}" if diff > 0 else str(diff) if diff != 0 else "-"
        lines.append(f"| {cat} | {b} | {a} | {diff_str} |")
    lines.append("")

    # 2. 카테고리 변경 곡
    lines.append("## 2. 카테고리가 변경된 곡\n")
    changed = []
    for sid, a_song in after.items():
        b_song = before.get(sid)
        if b_song and b_song.get("category") != a_song.get("category"):
            changed.append((a_song["title"], a_song["artist"],
                          b_song.get("category", ""), a_song.get("category", ""),
                          b_song.get("mood", ""), a_song.get("mood", "")))

    if changed:
        lines.append(f"**{len(changed)}곡의 카테고리가 변경됨**\n")
        lines.append("| 곡 | 아티스트 | Before | After | Before mood | After mood |")
        lines.append("|-----|---------|--------|-------|-------------|------------|")
        for title, artist, b_cat, a_cat, b_mood, a_mood in changed:
            lines.append(f"| {title} | {artist} | {b_cat} | **{a_cat}** | {b_mood} | {a_mood} |")
    else:
        lines.append("변경 없음")
    lines.append("")

    # 3. Mood 변경
    lines.append("## 3. Mood 텍스트가 변경된 곡\n")
    mood_changed = []
    for sid, a_song in after.items():
        b_song = before.get(sid)
        if b_song and b_song.get("mood") != a_song.get("mood"):
            mood_changed.append((a_song["title"], a_song["artist"],
                               b_song.get("mood", ""), a_song.get("mood", "")))
    if mood_changed:
        lines.append(f"**{len(mood_changed)}곡의 mood가 변경됨**\n")
        lines.append("| 곡 | 아티스트 | Before mood | After mood |")
        lines.append("|-----|---------|-------------|------------|")
        for title, artist, b_mood, a_mood in mood_changed:
            lines.append(f"| {title} | {artist} | {b_mood} | {a_mood} |")
    else:
        lines.append("변경 없음")
    lines.append("")

    # 4. Emotion Vector 품질 측정
    lines.append("## 4. Emotion Vector 품질 측정\n")
    lines.append("### 표준 감정 사전 적용 현황\n")

    all_emotions = Counter()
    songs_with_emo = 0
    for s in after_rows:
        emo = s.get("emotions")
        if isinstance(emo, dict) and emo:
            songs_with_emo += 1
            for k in emo:
                all_emotions[k] += 1

    lines.append(f"- emotions 보유 곡: {songs_with_emo}/{len(after_rows)}")
    lines.append(f"- 사용된 감정 종류: {len(all_emotions)}개\n")

    non_standard = [e for e in all_emotions if e not in STANDARD_EMOTIONS]
    if non_standard:
        lines.append(f"- **비표준 감정 발견**: {', '.join(non_standard)}")
    else:
        lines.append("- 비표준 감정: 없음 (100% 표준 사전 준수)")
    lines.append("")

    lines.append("### 감정별 사용 빈도\n")
    lines.append("| 감정 | 사용 곡 수 |")
    lines.append("|------|----------|")
    for emo, cnt in all_emotions.most_common():
        lines.append(f"| {emo} | {cnt} |")
    lines.append("")

    # 5. Emotion Vector로 카테고리 내부 분리도
    lines.append("## 5. Emotion Vector 카테고리 내부 분리도\n")
    lines.append("emotion_vector(20차원) 코사인 거리 기준\n")

    by_cat = {}
    for s in after_rows:
        by_cat.setdefault(s["category"], []).append(s)

    lines.append("| 카테고리 | 곡 수 | 평균 emo 거리 | 최소 | 최대 |")
    lines.append("|----------|-------|-------------|------|------|")
    for cat in sorted(by_cat.keys(), key=lambda c: -len(by_cat[c])):
        songs_list = by_cat[cat]
        if len(songs_list) < 2:
            continue
        dists = []
        for i in range(len(songs_list)):
            for j in range(i + 1, len(songs_list)):
                d = cosine_dist(songs_list[i]["_emo"], songs_list[j]["_emo"])
                dists.append(d)
        if dists:
            avg_d = sum(dists) / len(dists)
            lines.append(f"| {cat} | {len(songs_list)} | {avg_d:.4f} | {min(dists):.4f} | {max(dists):.4f} |")
    lines.append("")

    # 6. 2축 하이브리드 vs 단축(embedding만) 비교
    lines.append("## 6. 2축 하이브리드 유사도 vs 단축(embedding만) 비교\n")
    lines.append("### 임베딩 분리도 비교\n")

    random.seed(42)
    emb_same, emb_diff = [], []
    hyb_same, hyb_diff = [], []
    for _ in range(300):
        i, j = random.sample(range(len(after_rows)), 2)
        a, b = after_rows[i], after_rows[j]
        ed = cosine_dist(a["_vec"], b["_vec"])
        hd = hybrid_dist(a["_vec"], b["_vec"], a["_emo"], b["_emo"])
        if a["category"] == b["category"]:
            emb_same.append(ed)
            hyb_same.append(hd)
        else:
            emb_diff.append(ed)
            hyb_diff.append(hd)

    if emb_same and emb_diff:
        emb_same_avg = sum(emb_same) / len(emb_same)
        emb_diff_avg = sum(emb_diff) / len(emb_diff)
        hyb_same_avg = sum(hyb_same) / len(hyb_same)
        hyb_diff_avg = sum(hyb_diff) / len(hyb_diff)
        lines.append("| 지표 | Embedding만 | 2축 하이브리드 |")
        lines.append("|------|------------|--------------|")
        lines.append(f"| 같은 카테고리 평균 거리 | {emb_same_avg:.4f} | {hyb_same_avg:.4f} |")
        lines.append(f"| 다른 카테고리 평균 거리 | {emb_diff_avg:.4f} | {hyb_diff_avg:.4f} |")
        lines.append(f"| **분리도** (차이) | **{emb_diff_avg - emb_same_avg:.4f}** | **{hyb_diff_avg - hyb_same_avg:.4f}** |")
    lines.append("")

    # 7. 크로스 카테고리 침범율 비교
    lines.append("## 7. 크로스 카테고리 침범율 (2축 하이브리드)\n")
    lines.append("각 곡의 유사곡 TOP5 중 다른 카테고리 비율\n")

    invasion_emb = {}
    invasion_hyb = {}
    for s in after_rows:
        emb_dists = []
        hyb_dists = []
        for other in after_rows:
            if other["spotify_id"] == s["spotify_id"]:
                continue
            ed = cosine_dist(s["_vec"], other["_vec"])
            hd = hybrid_dist(s["_vec"], other["_vec"], s["_emo"], other["_emo"])
            emb_dists.append((ed, other))
            hyb_dists.append((hd, other))

        cat = s["category"]

        emb_dists.sort(key=lambda x: x[0])
        top5_emb = emb_dists[:5]
        diff_emb = sum(1 for _, o in top5_emb if o["category"] != cat)
        invasion_emb.setdefault(cat, {"total": 0, "invaded": 0})
        invasion_emb[cat]["total"] += 1
        invasion_emb[cat]["invaded"] += diff_emb

        hyb_dists.sort(key=lambda x: x[0])
        top5_hyb = hyb_dists[:5]
        diff_hyb = sum(1 for _, o in top5_hyb if o["category"] != cat)
        invasion_hyb.setdefault(cat, {"total": 0, "invaded": 0})
        invasion_hyb[cat]["total"] += 1
        invasion_hyb[cat]["invaded"] += diff_hyb

    lines.append("| 카테고리 | Embedding만 | 2축 하이브리드 |")
    lines.append("|----------|------------|--------------|")
    for cat in sorted(invasion_hyb.keys(), key=lambda c: -invasion_hyb[c]["total"]):
        e_stats = invasion_emb.get(cat, {"total": 1, "invaded": 0})
        h_stats = invasion_hyb[cat]
        e_rate = e_stats["invaded"] / (e_stats["total"] * 5) * 100
        h_rate = h_stats["invaded"] / (h_stats["total"] * 5) * 100
        lines.append(f"| {cat} | {e_rate:.0f}% | {h_rate:.0f}% |")
    lines.append("")

    # 8. 유사곡 추천 샘플 (2축 하이브리드)
    lines.append("## 8. 유사곡 추천 샘플 (2축 하이브리드)\n")
    check_songs = ["Lxxk 2 U", "Good bye-bye", "So Cool", "Kick It", "Crazy", "Hurt", "BANG BANG"]
    for check_title in check_songs:
        song = next((s for s in after_rows if s["title"] == check_title), None)
        if not song:
            continue

        hyb_list = []
        for other in after_rows:
            if other["spotify_id"] == song["spotify_id"]:
                continue
            hd = hybrid_dist(song["_vec"], other["_vec"], song["_emo"], other["_emo"])
            hyb_list.append((hd, other))
        hyb_list.sort(key=lambda x: x[0])

        emo_str = ""
        if isinstance(song.get("emotions"), dict):
            emo_str = ", ".join(f"{k}:{v}" for k, v in song["emotions"].items())

        lines.append(f"### {song['title']} ({song['artist']}) - [{song['category']}] {song['mood']}")
        lines.append(f"emotions: {emo_str}\n")
        lines.append("| # | 유사곡 | 아티스트 | category | mood | 거리 |")
        lines.append("|---|--------|----------|----------|------|------|")
        for k, (d, o) in enumerate(hyb_list[:5]):
            match = "O" if o["category"] == song["category"] else "X"
            lines.append(f"| {k+1} | {o['title']} | {o['artist']} | {o['category']} ({match}) | {o['mood']} | {d:.4f} |")
        lines.append("")

    # 9. 전체 곡 Before/After 비교 테이블
    lines.append("## 9. 전체 곡 Before/After 비교\n")
    lines.append("| 곡 | 아티스트 | Before cat | After cat | Before mood | After mood | 변경 |")
    lines.append("|-----|---------|-----------|----------|-------------|------------|------|")

    for sid, a in sorted(after.items(), key=lambda x: x[1]["title"]):
        b = before.get(sid, {})
        b_cat = b.get("category", "N/A")
        a_cat = a.get("category", "")
        b_mood = b.get("mood", "N/A")
        a_mood = a.get("mood", "")
        cat_changed = b_cat != a_cat
        mood_changed_flag = b_mood != a_mood
        change = ""
        if cat_changed:
            change += "CAT "
        if mood_changed_flag:
            change += "MOOD"
        if not change:
            change = "-"
        lines.append(f"| {a['title']} | {a['artist']} | {b_cat} | {a_cat} | {b_mood} | {a_mood} | {change} |")
    lines.append("")

    output_path = REPO_ROOT / "docs" / "pipeline-improvement" / "phase2_comparison.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {output_path}")


if __name__ == "__main__":
    run()
