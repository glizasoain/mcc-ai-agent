import os
import csv
from pathlib import Path
from typing import Iterable

import mysql.connector
from dotenv import load_dotenv
import uuid
import json
import hashlib

# Ensure environment variables are loaded when this module is imported,
# so standalone calls to init_database() pick up MySQL credentials.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)


def get_db_cfg() -> dict:
	return {
		"host": os.getenv("MYSQL_HOST", "127.0.0.1"),
		"port": int(os.getenv("MYSQL_PORT", "3306")),
		"user": os.getenv("MYSQL_USER", "root"),
		"password": os.getenv("MYSQL_PASSWORD", ""),
		"database": os.getenv("MYSQL_DB", "data_engineering"),
	}


def ensure_database_exists():
	cfg = get_db_cfg()
	db = cfg.pop("database")
	conn = mysql.connector.connect(**{k: v for k, v in cfg.items() if k != "database"})
	cur = conn.cursor()
	cur.execute(f"CREATE DATABASE IF NOT EXISTS {db} CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")
	conn.commit()
	cur.close()
	conn.close()


def run_migrations():
	cfg = get_db_cfg()
	conn = mysql.connector.connect(**cfg)
	cur = conn.cursor()
	migrations_dir = Path(__file__).resolve().parents[1] / "db" / "migrations"
	for sql_file in sorted(migrations_dir.glob("*.sql")):
		with sql_file.open("r", encoding="utf-8") as f:
			sql = f.read()
		for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
			cur.execute(stmt)
	conn.commit()
	cur.close()
	conn.close()


def seed_mcc_codes_from_requirements_csv():
	cfg = get_db_cfg()
	conn = mysql.connector.connect(**cfg)
	cur = conn.cursor()
	req_root = Path(__file__).resolve().parents[2] / "requirements"
	csv_path = req_root / "data" / "catalogs" / "mcc_codes_full.csv"
	if not csv_path.exists():
		cur.close(); conn.close(); return
	with csv_path.open("r", encoding="utf-8") as f:
		reader = csv.DictReader(f)
		rows: list[tuple[str, str]] = []
		for row in reader:
			code = (row.get("mcc_code") or row.get("mcc") or "").strip()
			# Prefer richer descriptions from provided catalog headers
			desc = (
				row.get("description")
				or row.get("mcc_description")
				or row.get("combined_description")
				or row.get("edited_description")
				or row.get("usda_description")
				or row.get("irs_description")
				or ""
			).strip()
			if code:
				rows.append((code, desc))
	if rows:
		cur.executemany(
			"INSERT INTO mcc_codes (mcc_code, description) VALUES (%s,%s) ON DUPLICATE KEY UPDATE description=VALUES(description)",
			rows,
		)
		conn.commit()
	cur.close()
	conn.close()


def init_database():
	ensure_database_exists()
	run_migrations()
	seed_mcc_codes_from_requirements_csv()


def get_connection(include_database: bool = True) -> mysql.connector.MySQLConnection:
	cfg = get_db_cfg()
	if not include_database:
		cfg.pop("database", None)
	return mysql.connector.connect(**cfg)


def get_mcc_description(mcc_code: str) -> str:
	"""Return description for a given MCC code or empty string if not found."""
	try:
		conn = get_connection()
		cur = conn.cursor()
		cur.execute("SELECT description FROM mcc_codes WHERE mcc_code = %s LIMIT 1", (mcc_code,))
		row = cur.fetchone()
		cur.close(); conn.close()
		desc = (row[0] if row and row[0] else "").strip()
		return desc
	except Exception:
		return ""


# ------------------ Persistence helpers ------------------

def create_run(merchant_id: str) -> str:
	"""Insert a new run with status 'running' and return run_id (uuid4)."""
	run_id = str(uuid.uuid4())
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"INSERT INTO runs (run_id, merchant_id, status, started_at) VALUES (%s,%s,'running', NOW())",
		(run_id, merchant_id),
	)
	conn.commit(); cur.close(); conn.close()
	return run_id


def complete_run(run_id: str, status: str = "completed") -> None:
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"UPDATE runs SET status=%s, finished_at=NOW() WHERE run_id=%s",
		(status, run_id),
	)
	conn.commit(); cur.close(); conn.close()


def insert_recommendation(
	run_id: str,
	rank: int,
	mcc: str,
	confidence_pct: int,
	reasons: dict,
) -> None:
	"""Store a single ranked recommendation for a run.

	confidence is stored as 0.000-1.000 (DECIMAL(4,3))
	"""
	confidence_frac = max(0.0, min(1.0, (confidence_pct or 0) / 100.0))
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"INSERT INTO recommendations (run_id, `rank`, mcc, confidence, reasons_json) VALUES (%s,%s,%s,%s,%s)",
		(run_id, rank, mcc or None, confidence_frac, json.dumps(reasons)),
	)
	conn.commit(); cur.close(); conn.close()


def insert_artifact(merchant_id: str, kind: str, content: str, metadata: dict | None = None) -> str:
	artifact_id = str(uuid.uuid4())
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"INSERT INTO artifacts (artifact_id, merchant_id, kind, content, metadata_json, created_at) VALUES (%s,%s,%s,%s,%s, NOW())",
		(artifact_id, merchant_id, kind, content, json.dumps(metadata or {})),
	)
	conn.commit(); cur.close(); conn.close()
	return artifact_id


def get_idempotent_response(idempotency_key: str) -> dict | None:
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"SELECT response_json FROM idempotency_keys WHERE idempotency_key=%s LIMIT 1",
		(idempotency_key,),
	)
	row = cur.fetchone()
	cur.close(); conn.close()
	if row and row[0]:
		try:
			return json.loads(row[0])
		except Exception:
			return None
	return None


def save_idempotent_response(idempotency_key: str, request_obj: dict, response_obj: dict) -> None:
	req_json = json.dumps(request_obj, sort_keys=True)
	req_hash = hashlib.sha256(req_json.encode("utf-8")).digest()
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"REPLACE INTO idempotency_keys (idempotency_key, request_hash, response_json, ttl_at) VALUES (%s,%s,%s, DATE_ADD(NOW(), INTERVAL 1 DAY))",
		(idempotency_key, req_hash, json.dumps(response_obj)),
	)
	conn.commit(); cur.close(); conn.close()


def upsert_merchant(merchant_id: str, legal_name: str | None, website: str | None) -> None:
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"INSERT INTO merchants (merchant_id, legal_name, website) VALUES (%s,%s,%s)"
		" ON DUPLICATE KEY UPDATE legal_name=VALUES(legal_name), website=VALUES(website), updated_at=NOW()",
		(merchant_id, legal_name, website),
	)
	conn.commit(); cur.close(); conn.close()


def get_merchant(merchant_id: str) -> dict | None:
	"""Fetch merchant record by id."""
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"SELECT merchant_id, legal_name, website FROM merchants WHERE merchant_id=%s LIMIT 1",
		(merchant_id,),
	)
	row = cur.fetchone()
	cur.close(); conn.close()
	if not row:
		return None
	return {"merchant_id": row[0], "legal_name": row[1], "website": row[2]}

def list_runs_db(limit: int = 50, merchant_id: str | None = None) -> list[dict]:
	conn = get_connection()
	cur = conn.cursor()
	if merchant_id:
		cur.execute(
			"SELECT run_id, merchant_id, status, started_at, finished_at FROM runs WHERE merchant_id=%s ORDER BY started_at DESC LIMIT %s",
			(merchant_id, int(limit)),
		)
	else:
		cur.execute(
			"SELECT run_id, merchant_id, status, started_at, finished_at FROM runs ORDER BY started_at DESC LIMIT %s",
			(int(limit),),
		)
	rows = cur.fetchall()
	cur.close(); conn.close()
	result: list[dict] = []
	for r in rows or []:
		result.append({
			"run_id": r[0],
			"merchant_id": r[1],
			"status": r[2],
			"started_at": r[3].isoformat() if r[3] else None,
			"finished_at": r[4].isoformat() if r[4] else None,
		})
	return result


def get_run_db(run_id: str) -> dict | None:
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"SELECT run_id, merchant_id, status, started_at, finished_at FROM runs WHERE run_id=%s LIMIT 1",
		(run_id,),
	)
	row = cur.fetchone()
	cur.close(); conn.close()
	if not row:
		return None
	return {
		"run_id": row[0],
		"merchant_id": row[1],
		"status": row[2],
		"started_at": row[3].isoformat() if row[3] else None,
		"finished_at": row[4].isoformat() if row[4] else None,
	}


def get_latest_recommendation_for_merchant(merchant_id: str) -> dict | None:
	"""Return the latest run's top recommendation for a merchant, if any."""
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"SELECT r.run_id, rec.mcc, rec.confidence, rec.reasons_json FROM runs r"
		" JOIN recommendations rec ON rec.run_id=r.run_id AND rec.`rank`=1"
		" WHERE r.merchant_id=%s ORDER BY r.started_at DESC LIMIT 1",
		(merchant_id,),
	)
	row = cur.fetchone()
	cur.close(); conn.close()
	if not row:
		return None
	return {
		"run_id": row[0],
		"mcc": row[1] or "",
		"confidence": int(round(float(row[2] or 0) * 100)),
		"reasons": json.loads(row[3]) if row[3] else {},
	}
