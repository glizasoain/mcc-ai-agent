#!/usr/bin/env python3
"""
Seed the agent schema from CSVs under MCC_AI_Agent/data/catalogs/ and data/samples/.

Env vars (target DB):
- TGT_MYSQL_HOST (default 127.0.0.1)
- TGT_MYSQL_USER (default root)
- TGT_MYSQL_PASSWORD (default root)
- TGT_MYSQL_DB (default data_engineering)
"""

import os
import sys
from pathlib import Path

import pandas as pd
import mysql.connector
from mysql.connector import Error


def upsert_dataframe(df: pd.DataFrame, conn, table: str) -> None:
    if df.empty:
        return
    columns = list(df.columns)
    cols = ",".join(columns)
    placeholders = ",".join(["%s"] * len(columns))
    ondup = ",".join([f"{c}=VALUES({c})" for c in columns])
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {ondup}"
    cur = conn.cursor()
    cur.executemany(sql, [tuple(x) for x in df.values])
    conn.commit()
    cur.close()


def main() -> int:
    base = Path(__file__).resolve().parents[1]
    catalogs = base / "data" / "catalogs"
    samples = base / "data" / "samples"

    cfg = {
        "host": os.getenv("TGT_MYSQL_HOST", "127.0.0.1"),
        "user": os.getenv("TGT_MYSQL_USER", "root"),
        "password": os.getenv("TGT_MYSQL_PASSWORD", "root"),
        "database": os.getenv("TGT_MYSQL_DB", "data_engineering"),
    }

    try:
        conn = mysql.connector.connect(**cfg)
        cur = conn.cursor()

        # Ensure core tables exist (no mcc_catalog in source; use mcc_codes + ranking)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mcc_ranking_portfolio (
                mcc_code VARCHAR(10) PRIMARY KEY,
                mcc_description VARCHAR(255) NULL,
                weighted_avg_ic_rate DECIMAL(8,6) NULL,
                simple_avg_ic_rate DECIMAL(8,6) NULL,
                total_transactions INT NULL,
                total_volume DECIMAL(15,2) NULL,
                avg_transaction_size DECIMAL(10,2) NULL,
                ic_rate_std_dev DECIMAL(8,6) NULL,
                coefficient_of_variation DECIMAL(6,4) NULL,
                min_ic_rate DECIMAL(8,6) NULL,
                max_ic_rate DECIMAL(8,6) NULL,
                median_ic_rate DECIMAL(8,6) NULL,
                unique_merchants INT NULL,
                date_range_days INT NULL,
                weighted_rate_rank INT NULL,
                simple_rate_rank INT NULL,
                volume_rank INT NULL,
                confidence_level VARCHAR(16) NULL,
                data_quality_score DECIMAL(4,2) NULL,
                analysis_date DATETIME NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        # Load mcc_codes full dump if present
        codes = catalogs / "mcc_codes_full.csv"
        if codes.exists():
            df = pd.read_csv(codes)
            # Create a simple table if not exists
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS mcc_codes (
                    mcc_code VARCHAR(10) PRIMARY KEY,
                    description VARCHAR(255) NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            # Normalize columns
            rename_map = {}
            if "mcc" in df.columns and "mcc_code" not in df.columns:
                rename_map["mcc"] = "mcc_code"
            if "mcc_description" in df.columns and "description" not in df.columns:
                rename_map["mcc_description"] = "description"
            if rename_map:
                df = df.rename(columns=rename_map)
            keep = [c for c in ["mcc_code", "description"] if c in df.columns]
            if keep:
                upsert_dataframe(df[keep], conn, "mcc_codes")
                print("✅ Loaded mcc_codes_full.csv")

        # Load ranking portfolio if present
        rank = catalogs / "mcc_ranking_portfolio.csv"
        if rank.exists():
            df = pd.read_csv(rank)
            if "mcc_code" not in df.columns and "mcc" in df.columns:
                df = df.rename(columns={"mcc": "mcc_code"})
            upsert_dataframe(df, conn, "mcc_ranking_portfolio")
            print("✅ Loaded mcc_ranking_portfolio.csv")

        # Load samples
        ms = samples / "merchants.sample.csv"
        if ms.exists():
            df = pd.read_csv(ms)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS merchants (
                    merchant_id VARCHAR(32) PRIMARY KEY,
                    legal_name VARCHAR(255),
                    dba_name VARCHAR(255),
                    website VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            upsert_dataframe(df, conn, "merchants")
            print("✅ Loaded merchants.sample.csv")

        kp = samples / "merchant_kpis_monthly.sample.csv"
        if kp.exists():
            df = pd.read_csv(kp)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS merchant_kpis_monthly (
                    merchant_id VARCHAR(32) NOT NULL,
                    period_month DATE NOT NULL,
                    decline_rate_pct DECIMAL(5,2),
                    ic_bps INT,
                    volume_usd DECIMAL(18,2),
                    avg_ticket_usd DECIMAL(12,2),
                    PRIMARY KEY (merchant_id, period_month)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            upsert_dataframe(df, conn, "merchant_kpis_monthly")
            print("✅ Loaded merchant_kpis_monthly.sample.csv")

        cur.close()
        conn.close()
        return 0
    except Error as e:
        print(f"❌ MySQL error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


