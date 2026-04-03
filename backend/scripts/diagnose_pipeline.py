"""
파이프라인 알고리즘 진단 스크립트
- DB에서 실제 데이터를 조회하여 유사곡 추천/그룹핑 품질을 분석
"""
import json
import math
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from dotenv import load_dotenv
import oracledb

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

import ssl as _ssl

DSN_NO_DN_MATCH = os.getenv("ORACLE_DSN", "").replace("ssl_server_dn_match=yes", "ssl_server_dn_match=no")

def get_connection():
    # Python 3.10 on macOS may lack root CA certs - use certifi or disable verify
    try:
        import certifi
        ssl_ctx = _ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE

    conn = oracledb.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASSWORD"),
        dsn=DSN_NO_DN_MATCH,
        tcp_connect_timeout=15,
        ssl_context=ssl_ctx,
    )
    # CLOB -> string handler
    def _clob_handler(cursor, metadata):
        if metadata.type_code is oracledb.DB_TYPE_CLOB:
            return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
    conn.outputtypehandler = _clob_handler
    return conn

def run_diagnostic():
    conn = get_connection()
    cursor = conn.cursor()

    report = []
    report.append("# Moodlist 파이프라인 알고리즘 진단 리포트\n")

    # ============================================================
    # 1. 기본 통계
    # ============================================================
    report.append("## 1. DB 기본 통계\n")

    cursor.execute("SELECT COUNT(*) FROM songs")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM songs WHERE status = 'classified'")
    classified = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM songs WHERE status = 'error'")
    errors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM songs WHERE status = 'pending'")
    pending = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM songs WHERE mood_embedding IS NOT NULL")
    with_embedding = cursor.fetchone()[0]

    report.append(f"| 항목 | 수 |")
    report.append(f"|------|-----|")
    report.append(f"| 전체 곡 | {total} |")
    report.append(f"| 분류 완료 | {classified} |")
    report.append(f"| 에러 | {errors} |")
    report.append(f"| 대기 | {pending} |")
    report.append(f"| 임베딩 있음 | {with_embedding} |")
    report.append("")

    # ============================================================
    # 2. 카테고리 분포
    # ============================================================
    report.append("## 2. 카테고리 분포\n")

    cursor.execute("""
        SELECT category, COUNT(*) as cnt
        FROM songs WHERE status = 'classified'
        GROUP BY category ORDER BY cnt DESC
    """)
    cat_rows = cursor.fetchall()

    report.append("| 카테고리 | 곡 수 | 비율 |")
    report.append("|----------|-------|------|")
    for cat, cnt in cat_rows:
        pct = cnt / classified * 100 if classified > 0 else 0
        report.append(f"| {cat} | {cnt} | {pct:.1f}% |")
    report.append("")

    # ============================================================
    # 3. Mood 텍스트 분석
    # ============================================================
    report.append("## 3. Mood 텍스트 분석\n")

    cursor.execute("SELECT mood FROM songs WHERE status = 'classified' AND mood IS NOT NULL")
    moods = [r[0] for r in cursor.fetchall()]

    mood_counter = Counter(moods)
    unique_moods = len(mood_counter)
    report.append(f"- 총 mood 구문 수: {len(moods)}")
    report.append(f"- 고유 mood 구문 수: {unique_moods}")
    report.append(f"- 중복 비율: {(1 - unique_moods / len(moods)) * 100:.1f}%" if moods else "- N/A")
    report.append("")

    # 가장 많이 반복된 mood
    report.append("### 반복된 mood TOP 10\n")
    report.append("| mood | 횟수 |")
    report.append("|------|------|")
    for mood_text, count in mood_counter.most_common(10):
        report.append(f"| {mood_text} | {count} |")
    report.append("")

    # mood 길이 분포
    lengths = [len(m) for m in moods]
    if lengths:
        report.append("### Mood 텍스트 길이 분포\n")
        report.append(f"- 최소: {min(lengths)}자")
        report.append(f"- 최대: {max(lengths)}자")
        report.append(f"- 평균: {sum(lengths)/len(lengths):.1f}자")
        report.append("")

    # ============================================================
    # 4. Tags 분석
    # ============================================================
    report.append("## 4. Tags 분석\n")

    cursor.execute("SELECT tags FROM songs WHERE status = 'classified' AND tags IS NOT NULL")
    all_tags = []
    for (tags_raw,) in cursor.fetchall():
        try:
            val = tags_raw
            if hasattr(val, 'read'):
                val = val.read()
            tags_list = json.loads(val) if isinstance(val, str) else val
            if isinstance(tags_list, list):
                all_tags.extend(tags_list)
        except Exception:
            pass

    tag_counter = Counter(all_tags)
    report.append(f"- 전체 태그 인스턴스: {len(all_tags)}")
    report.append(f"- 고유 태그 수: {len(tag_counter)}")
    report.append("")

    report.append("### 가장 빈번한 태그 TOP 20\n")
    report.append("| 태그 | 횟수 |")
    report.append("|------|------|")
    for tag, cnt in tag_counter.most_common(20):
        report.append(f"| {tag} | {cnt} |")
    report.append("")

    # 의미 중복 태그 탐지
    report.append("### 의미 중복 의심 태그 그룹\n")
    tag_names = list(tag_counter.keys())
    similar_groups = []
    visited = set()
    for i, t1 in enumerate(tag_names):
        if t1 in visited:
            continue
        group = [t1]
        for j, t2 in enumerate(tag_names):
            if i != j and t2 not in visited:
                # 부분 문자열 포함 관계
                if t1 in t2 or t2 in t1:
                    group.append(t2)
                    visited.add(t2)
        if len(group) > 1:
            similar_groups.append(group)
            visited.add(t1)

    if similar_groups:
        for g in similar_groups[:15]:
            counts = [f"{t}({tag_counter[t]})" for t in g]
            report.append(f"- {' / '.join(counts)}")
    else:
        report.append("- 부분 문자열 기반 중복 없음")
    report.append("")

    # ============================================================
    # 5. Emotions 분석
    # ============================================================
    report.append("## 5. Emotions 분석\n")

    cursor.execute("SELECT emotions FROM songs WHERE status = 'classified' AND emotions IS NOT NULL")
    emotion_counter = Counter()
    emotion_scores = {}
    for (emo_raw,) in cursor.fetchall():
        try:
            val = emo_raw
            if hasattr(val, 'read'):
                val = val.read()
            emo_dict = json.loads(val) if isinstance(val, str) else val
            if isinstance(emo_dict, dict):
                for emo_name, score in emo_dict.items():
                    emotion_counter[emo_name] += 1
                    if emo_name not in emotion_scores:
                        emotion_scores[emo_name] = []
                    emotion_scores[emo_name].append(float(score))
        except Exception:
            pass

    report.append(f"- 고유 감정명 수: {len(emotion_counter)}")
    report.append("")

    report.append("### 가장 빈번한 감정 TOP 20\n")
    report.append("| 감정 | 출현 횟수 | 평균 점수 |")
    report.append("|------|----------|----------|")
    for emo, cnt in emotion_counter.most_common(20):
        avg = sum(emotion_scores[emo]) / len(emotion_scores[emo])
        report.append(f"| {emo} | {cnt} | {avg:.2f} |")
    report.append("")

    # ============================================================
    # 6. 유사곡 추천 품질 분석
    # ============================================================
    report.append("## 6. 유사곡 추천 품질 분석\n")
    report.append("무작위 5곡에 대해 유사곡 TOP 5를 조회하고, 카테고리 일치율을 확인.\n")

    cursor.execute("""
        SELECT spotify_id, title, artist, mood, category, primary_emotion, tags
        FROM songs
        WHERE status = 'classified' AND mood_embedding IS NOT NULL
        ORDER BY DBMS_RANDOM.VALUE
        FETCH FIRST 5 ROWS ONLY
    """)
    sample_songs = []
    sample_cols = [col[0].lower() for col in cursor.description]
    for row in cursor.fetchall():
        d = dict(zip(sample_cols, row))
        sample_songs.append(d)

    category_match_total = 0
    category_match_count = 0

    for song in sample_songs:
        sid = song["spotify_id"]

        cursor.execute("""
            SELECT s.spotify_id, s.title, s.artist, s.mood, s.category, s.primary_emotion, s.tags,
                   VECTOR_DISTANCE(s.mood_embedding, q.mood_embedding, COSINE) AS dist
            FROM songs s, songs q
            WHERE q.spotify_id = :1
              AND s.status = 'classified'
              AND s.mood_embedding IS NOT NULL
              AND s.spotify_id != :2
            ORDER BY dist
            FETCH FIRST 5 ROWS ONLY
        """, [sid, sid])

        sim_rows = cursor.fetchall()
        sim_cols = [col[0].lower() for col in cursor.description]

        report.append(f"### 기준곡: {song['title']} - {song['artist']}")
        report.append(f"- category: **{song['category']}** | mood: {song['mood']} | primary_emotion: {song['primary_emotion']}")
        tags_val = song.get('tags', '')
        if tags_val and isinstance(tags_val, str):
            try:
                tags_val = ', '.join(json.loads(tags_val))
            except Exception:
                pass
        report.append(f"- tags: {tags_val}")
        report.append("")

        report.append("| # | 유사곡 | 아티스트 | category | mood | 거리 |")
        report.append("|---|--------|----------|----------|------|------|")

        for i, row in enumerate(sim_rows):
            sim = dict(zip(sim_cols, row))
            cat_match = "O" if sim["category"] == song["category"] else "X"
            dist_val = sim["dist"]
            category_match_total += 1
            if sim["category"] == song["category"]:
                category_match_count += 1
            report.append(f"| {i+1} | {sim['title']} | {sim['artist']} | {sim['category']} ({cat_match}) | {sim['mood']} | {dist_val:.4f} |")
        report.append("")

    if category_match_total > 0:
        match_rate = category_match_count / category_match_total * 100
        report.append(f"### 카테고리 일치율: {category_match_count}/{category_match_total} = **{match_rate:.1f}%**\n")

    # ============================================================
    # 7. 그룹핑 품질 분석
    # ============================================================
    report.append("## 7. 그룹핑 시뮬레이션 분석\n")

    cursor.execute("""
        SELECT spotify_id, title, artist, mood, category, mood_embedding
        FROM songs
        WHERE status = 'classified' AND mood_embedding IS NOT NULL
        ORDER BY classified_at
    """)
    all_songs_rows = cursor.fetchall()
    grp_cols = [col[0].lower() for col in cursor.description]

    all_songs = []
    for row in all_songs_rows:
        d = dict(zip(grp_cols, row))
        emb = d["mood_embedding"]
        if emb is not None:
            try:
                d["_vec"] = list(emb)
            except Exception:
                d["_vec"] = []
        else:
            d["_vec"] = []
        all_songs.append(d)

    def cosine_dist(a, b):
        if not a or not b:
            return 1.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 1.0
        return 1.0 - dot / (na * nb)

    # 그룹핑 시뮬레이션
    grouped_ids = set()
    groups = []
    for seed in all_songs:
        if seed["spotify_id"] in grouped_ids:
            continue
        seed_vec = seed["_vec"]
        if not seed_vec:
            continue
        scored = [(cosine_dist(seed_vec, s["_vec"]), s) for s in all_songs]
        scored.sort(key=lambda x: x[0])
        group_songs = [s for dist, s in scored if dist <= 0.45][:20]
        for s in group_songs:
            grouped_ids.add(s["spotify_id"])
        groups.append({
            "mood": seed["mood"],
            "category": seed["category"],
            "songs": group_songs
        })

    report.append(f"- 전체 곡 수: {len(all_songs)}")
    report.append(f"- 생성된 그룹 수: {len(groups)}")

    sizes = [len(g["songs"]) for g in groups]
    if sizes:
        report.append(f"- 그룹 크기: 최소 {min(sizes)}, 최대 {max(sizes)}, 평균 {sum(sizes)/len(sizes):.1f}")
        single_groups = sum(1 for s in sizes if s == 1)
        report.append(f"- 1곡짜리 그룹: {single_groups}개 ({single_groups/len(groups)*100:.1f}%)")
    report.append("")

    # 그룹 내 카테고리 순도 분석
    report.append("### 그룹 내 카테고리 순도\n")
    report.append("각 그룹에서 가장 많은 카테고리가 차지하는 비율 (높을수록 좋음)\n")

    purities = []
    for g in groups:
        cats = [s["category"] for s in g["songs"]]
        if cats:
            most_common_count = Counter(cats).most_common(1)[0][1]
            purity = most_common_count / len(cats)
            purities.append(purity)

    if purities:
        avg_purity = sum(purities) / len(purities)
        report.append(f"- 평균 순도: **{avg_purity:.1%}**")
        report.append(f"- 순도 100% 그룹: {sum(1 for p in purities if p == 1.0)}개")
        report.append(f"- 순도 50% 미만 그룹: {sum(1 for p in purities if p < 0.5)}개")
    report.append("")

    # 그룹 샘플 출력 (혼합 카테고리 그룹 우선)
    report.append("### 카테고리 혼합이 심한 그룹 샘플 (최대 3개)\n")

    mixed_groups = []
    for i, g in enumerate(groups):
        cats = [s["category"] for s in g["songs"]]
        if len(cats) >= 2:
            most_common_count = Counter(cats).most_common(1)[0][1]
            purity = most_common_count / len(cats)
            if purity < 1.0:
                mixed_groups.append((purity, i, g))

    mixed_groups.sort(key=lambda x: x[0])

    for purity, idx, g in mixed_groups[:3]:
        report.append(f"#### 그룹 #{idx+1} (seed mood: {g['mood']}, seed category: {g['category']}, 순도: {purity:.0%})")
        report.append("| 곡 | 아티스트 | category | mood |")
        report.append("|-----|---------|----------|------|")
        for s in g["songs"]:
            report.append(f"| {s['title']} | {s['artist']} | {s['category']} | {s['mood']} |")
        report.append("")

    # ============================================================
    # 8. 임베딩 거리 분포 분석
    # ============================================================
    report.append("## 8. 임베딩 거리 분포\n")
    report.append("무작위 곡 쌍 200개의 코사인 거리 분포를 확인.\n")

    import random
    if len(all_songs) >= 2:
        sample_dists = []
        same_cat_dists = []
        diff_cat_dists = []
        pairs = min(200, len(all_songs) * (len(all_songs) - 1) // 2)
        seen_pairs = set()
        attempts = 0
        while len(sample_dists) < pairs and attempts < pairs * 3:
            attempts += 1
            i, j = random.sample(range(len(all_songs)), 2)
            if (i, j) in seen_pairs:
                continue
            seen_pairs.add((i, j))
            d = cosine_dist(all_songs[i]["_vec"], all_songs[j]["_vec"])
            sample_dists.append(d)
            if all_songs[i]["category"] == all_songs[j]["category"]:
                same_cat_dists.append(d)
            else:
                diff_cat_dists.append(d)

        report.append(f"- 전체 쌍: {len(sample_dists)}개")
        report.append(f"- 평균 거리: {sum(sample_dists)/len(sample_dists):.4f}")
        report.append(f"- 최소 거리: {min(sample_dists):.4f}")
        report.append(f"- 최대 거리: {max(sample_dists):.4f}")
        report.append("")

        if same_cat_dists:
            report.append(f"- **같은 카테고리** 쌍 평균 거리: {sum(same_cat_dists)/len(same_cat_dists):.4f} ({len(same_cat_dists)}쌍)")
        if diff_cat_dists:
            report.append(f"- **다른 카테고리** 쌍 평균 거리: {sum(diff_cat_dists)/len(diff_cat_dists):.4f} ({len(diff_cat_dists)}쌍)")
        report.append("")

        if same_cat_dists and diff_cat_dists:
            same_avg = sum(same_cat_dists) / len(same_cat_dists)
            diff_avg = sum(diff_cat_dists) / len(diff_cat_dists)
            separation = diff_avg - same_avg
            report.append(f"- **분리도** (다른 카테고리 평균 - 같은 카테고리 평균): **{separation:.4f}**")
            report.append(f"  - 0에 가까우면: 임베딩이 카테고리를 잘 구분하지 못함")
            report.append(f"  - 클수록: 임베딩이 카테고리별로 잘 분리됨")
        report.append("")

        # 거리 구간별 분포
        report.append("### 거리 구간별 분포\n")
        report.append("| 구간 | 전체 | 같은 카테고리 | 다른 카테고리 |")
        report.append("|------|------|-------------|-------------|")
        bins = [(0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.8), (0.8, 1.0)]
        for lo, hi in bins:
            all_cnt = sum(1 for d in sample_dists if lo <= d < hi)
            same_cnt = sum(1 for d in same_cat_dists if lo <= d < hi)
            diff_cnt = sum(1 for d in diff_cat_dists if lo <= d < hi)
            report.append(f"| {lo:.1f}-{hi:.1f} | {all_cnt} | {same_cnt} | {diff_cnt} |")
        report.append("")

    conn.close()

    # ============================================================
    # 9. 종합 진단
    # ============================================================
    report.append("## 9. 종합 진단\n")
    report.append("### 발견된 문제점\n")
    report.append("1. **Mood 텍스트 임베딩의 낮은 해상도**: 2-5단어 구문으로 1536차원 벡터를 생성하면 정보 밀도가 낮고 noise 비율이 높음")
    report.append("2. **구조화 데이터 미활용**: GPT가 생성한 tags, emotions, category, emotional_arc가 유사곡 매칭에 전혀 반영되지 않음")
    report.append("3. **태그 비표준화**: 자유형 태그로 인해 의미 중복 발생, 검색/필터링 불가")
    report.append("4. **감정명 비표준화**: 자유형 감정명으로 동일 감정이 여러 표현으로 분산")
    report.append("5. **그룹핑 O(N^2) 복잡도**: Python 순수 연산으로 곡 수 증가 시 성능 저하")
    report.append("6. **그룹핑 비결정성**: seed 순서에 따라 결과가 달라짐")
    report.append("")

    return "\n".join(report)


if __name__ == "__main__":
    result = run_diagnostic()
    output_path = Path(__file__).parent.parent.parent / "docs" / "PIPELINE_DIAGNOSIS.md"
    output_path.write_text(result, encoding="utf-8")
    print(f"진단 리포트 저장: {output_path}")
    print(result)
