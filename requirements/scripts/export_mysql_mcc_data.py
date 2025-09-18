#!/usr/bin/env python3
"""
Export MCC reference data from an existing MySQL database into
MCC_AI_Agent/data/catalogs/ (non-PII) for local/CI usage.

Env vars (source DB):
- SRC_MYSQL_HOST (default: localhost)
- SRC_MYSQL_USER (default: root)
- SRC_MYSQL_PASSWORD (default: empty)
- SRC_MYSQL_DB (default: ic_optimization)

Tables attempted:
- mcc_ranking → mcc_ranking_portfolio.csv (optional)
- mcc_codes  → mcc_codes_full.csv (optional)
"""

import os
import sys
from pathlib import Path

import pandas as pd
import mysql.connector
from mysql.connector import Error


def table_exists(cur, name: str) -> bool:
    cur.execute("SHOW TABLES LIKE %s", (name,))
    return cur.fetchone() is not None


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "data" / "catalogs"
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "host": os.getenv("SRC_MYSQL_HOST", "localhost"),
        "user": os.getenv("SRC_MYSQL_USER", "root"),
        "password": os.getenv("SRC_MYSQL_PASSWORD", ""),
        "database": os.getenv("SRC_MYSQL_DB", "ic_optimization"),
    }

    try:
        conn = mysql.connector.connect(**cfg)
        cur = conn.cursor()

        # mcc_ranking → portfolio snapshot
        if table_exists(cur, "mcc_ranking"):
            df = pd.read_sql("SELECT * FROM mcc_ranking", conn)
            (out_dir / "mcc_ranking_portfolio.csv").parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_dir / "mcc_ranking_portfolio.csv", index=False)
            print("✅ Exported mcc_ranking → data/catalogs/mcc_ranking_portfolio.csv")
        else:
            print("ℹ️  Table mcc_ranking not found; skipping.")

        # mcc_codes → full dump (if available)
        if table_exists(cur, "mcc_codes"):
            df = pd.read_sql("SELECT * FROM mcc_codes", conn)
            df.to_csv(out_dir / "mcc_codes_full.csv", index=False)
            print("✅ Exported mcc_codes → data/catalogs/mcc_codes_full.csv")
        else:
            print("ℹ️  Table mcc_codes not found; skipping.")

        cur.close()
        conn.close()
        return 0
    except Error as e:
        print(f"❌ MySQL error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


