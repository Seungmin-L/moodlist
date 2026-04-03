"""
DB 전체 곡 스냅샷 생성 스크립트
usage: python3 scripts/snapshot_db.py [before|after]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import ssl as _ssl
from dotenv import load_dotenv
import oracledb

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

DSN = os.getenv("ORACLE_DSN", "").replace("ssl_server_dn_match=yes", "ssl_server_dn_match=no")


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


def snapshot(label: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT spotify_id, title, artist, category, mood, primary_emotion,
               emotional_arc, emotions, tags, narrative, confidence, status
        FROM songs
        ORDER BY category, title
    """)
    cols = [c[0].lower() for c in cursor.description]
    rows = []
    for row in cursor.fetchall():
        d = dict(zip(cols, row))
        for field in ["emotions", "tags"]:
            val = d.get(field)
            if isinstance(val, str):
                try:
                    d[field] = json.loads(val)
                except Exception:
                    pass
        rows.append(d)
    conn.close()

    # Generate markdown
    lines = []
    lines.append(f"# DB 전체 곡 스냅샷 ({label.upper()})\n")
    lines.append(f"총 {len(rows)}곡\n")

    # 통계
    from collections import Counter
    cat_counter = Counter(r["category"] for r in rows if r["status"] == "classified")
    lines.append("## 카테고리 분포\n")
    lines.append("| 카테고리 | 곡 수 |")
    lines.append("|----------|-------|")
    for cat, cnt in cat_counter.most_common():
        lines.append(f"| {cat} | {cnt} |")
    lines.append("")

    # 곡별 상세
    lines.append("## 곡별 분류 데이터\n")

    current_cat = None
    for r in rows:
        if r["status"] != "classified":
            continue

        if r["category"] != current_cat:
            current_cat = r["category"]
            cat_songs = [s for s in rows if s["category"] == current_cat and s["status"] == "classified"]
            lines.append(f"### {current_cat} ({len(cat_songs)}곡)\n")

        emo_dict = r.get("emotions", {})
        if isinstance(emo_dict, dict):
            emo_str = ", ".join(f"{k}: {v}" for k, v in emo_dict.items())
        else:
            emo_str = str(emo_dict)

        tags_list = r.get("tags", [])
        if isinstance(tags_list, list):
            tags_str = ", ".join(tags_list)
        else:
            tags_str = str(tags_list)

        lines.append(f"#### {r['title']} - {r['artist']}\n")
        lines.append("| 필드 | 값 |")
        lines.append("|------|-----|")
        lines.append(f"| spotify_id | `{r['spotify_id']}` |")
        lines.append(f"| category | **{r['category']}** |")
        lines.append(f"| mood | {r['mood']} |")
        lines.append(f"| primary_emotion | {r['primary_emotion']} |")
        lines.append(f"| emotional_arc | {r.get('emotional_arc', '')} |")
        lines.append(f"| emotions | {emo_str} |")
        lines.append(f"| tags | {tags_str} |")
        lines.append(f"| narrative | {r.get('narrative', '')} |")
        lines.append(f"| confidence | {r.get('confidence', '')} |")
        lines.append("")

    # 에러 곡 목록
    error_songs = [r for r in rows if r["status"] == "error"]
    if error_songs:
        lines.append(f"## 에러 상태 곡 ({len(error_songs)}곡)\n")
        lines.append("| 제목 | 아티스트 |")
        lines.append("|------|---------|")
        for r in error_songs:
            lines.append(f"| {r['title']} | {r['artist']} |")
        lines.append("")

    output_path = REPO_ROOT / "docs" / "pipeline-improvement" / f"snapshot_{label}.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {output_path}")
    return rows


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "before"
    snapshot(label)
