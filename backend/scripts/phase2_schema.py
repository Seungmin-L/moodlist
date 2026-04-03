"""Phase 2 DB 스키마 변경 - emotion_vector + audio features 컬럼 추가"""
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
    return oracledb.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASSWORD"),
        dsn=DSN, tcp_connect_timeout=15, ssl_context=ssl_ctx,
    )


def run():
    conn = get_connection()
    cursor = conn.cursor()

    columns = [
        ("emotion_vector", "VECTOR(20, FLOAT64)"),
        ("valence", "NUMBER(4,3)"),
        ("energy", "NUMBER(4,3)"),
        ("danceability", "NUMBER(4,3)"),
        ("tempo", "NUMBER(6,2)"),
        ("acousticness", "NUMBER(4,3)"),
    ]

    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE songs ADD ({col_name} {col_type})")
            conn.commit()
            print(f"  + {col_name} ({col_type}) 추가 완료")
        except oracledb.DatabaseError as e:
            if "ORA-01430" in str(e):
                print(f"  = {col_name} 이미 존재")
            else:
                print(f"  ! {col_name} 실패: {e}")

    conn.close()
    print("\n스키마 변경 완료")


if __name__ == "__main__":
    run()
