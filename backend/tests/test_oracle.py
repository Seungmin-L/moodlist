"""Oracle Cloud ATP 연결 테스트"""
import os
from dotenv import load_dotenv
import oracledb

load_dotenv()

DSN_NO_DN_MATCH = "(description=(retry_count=3)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host=adb.ap-osaka-1.oraclecloud.com))(connect_data=(service_name=g5570ac1c96da48_moodlistdb_tp.adb.oraclecloud.com))(security=(ssl_server_dn_match=no)))"

try:
    conn = oracledb.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASSWORD"),
        dsn=DSN_NO_DN_MATCH,
        tcp_connect_timeout=15,
    )
    print(f"연결 성공! Oracle {conn.version}")
    conn.close()
except Exception as e:
    print(f"연결 실패: {e}")
