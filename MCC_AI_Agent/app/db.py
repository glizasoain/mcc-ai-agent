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
			try:
				cur.execute(stmt)
				# Consume any result sets to avoid "Unread result found" between statements
				try:
					if getattr(cur, "with_rows", False):
						cur.fetchall()
				except Exception:
					pass
			except mysql.connector.Error as e:
				msg = str(e)
				# Ignore safe, idempotent errors (e.g., duplicate column/table when re-running)
				if e.errno in (1060, 1050) or "Duplicate column name" in msg or "already exists" in msg:
					continue
				raise
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
	# Seed brand_registry from CSV if empty
	try:
		conn = get_connection()
		cur = conn.cursor()
		cur.execute("SELECT COUNT(*) FROM brand_registry")
		count = int((cur.fetchone() or [0])[0])
		if count == 0:
			csv_path = Path(__file__).resolve().parents[1] / "data" / "brand_registry.csv"
			if csv_path.exists():
				with csv_path.open("r", encoding="utf-8") as f:
					import csv as _csv
					reader = _csv.DictReader(f)
					rows = []
					for r in reader:
						rows.append((
							(r.get("brand_key") or "").strip(),
							json.dumps([(n or "").strip() for n in (r.get("official_names") or "").split(";") if n.strip()]),
							json.dumps([(a or "").strip() for a in (r.get("aliases") or "").split(";") if a.strip()]),
							json.dumps([(d or "").strip() for d in (r.get("official_domains") or "").split(";") if d.strip()]),
							json.dumps([(i or "").strip() for i in (r.get("iata_codes") or "").split(";") if i.strip()]),
							(r.get("brand_mcc") or "").strip(),
							(r.get("country") or None),
							(r.get("network") or None),
							(r.get("source_url") or None),
						))
					if rows:
						cur.executemany(
							"INSERT INTO brand_registry (brand_key, official_names, aliases, official_domains, iata_codes, brand_mcc, country, network, source_url) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
							" ON DUPLICATE KEY UPDATE official_names=VALUES(official_names), aliases=VALUES(aliases), official_domains=VALUES(official_domains), iata_codes=VALUES(iata_codes), brand_mcc=VALUES(brand_mcc), country=VALUES(country), network=VALUES(network), source_url=VALUES(source_url)",
							rows,
						)
						conn.commit()
		cur.close(); conn.close()
	except Exception:
		pass


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


def get_portfolio_row(mcc_code: str) -> dict | None:
	"""Fetch portfolio IC/decline benchmarks for an MCC code."""
	try:
		conn = get_connection()
		cur = conn.cursor()
		cur.execute("SELECT mcc_code, mcc_description, weighted_avg_ic_rate, decline_rate_pct, example_merchant_name, example_merchant_url FROM mcc_portfolio WHERE mcc_code=%s LIMIT 1", (mcc_code,))
		row = cur.fetchone()
		cur.close(); conn.close()
		if not row:
			return None
		return {
			"mcc_code": row[0],
			"mcc_description": row[1],
			"weighted_avg_ic_rate": float(row[2]) if row[2] is not None else None,
			"decline_rate_pct": float(row[3]) if row[3] is not None else None,
			"example_merchant_name": (row[4] or None),
			"example_merchant_url": (row[5] or None),
		}
	except Exception:
		return None


def get_ic_optimization_metrics(mcc_code: str) -> dict | None:
	"""Fetch average effective IC rate and approximate decline rate from ic_optimization schema.

	Returns dict with keys: avg_ic_rate (float|None), decline_rate_pct (float|None)
	"""
	try:
		conn = get_connection(include_database=False)
		cur = conn.cursor()
		# Use CAST on varchar fields; treat 'declin' in Status/Auth as decline indicator
		cur.execute(
			"""
			SELECT 
			  AVG(CASE WHEN NULLIF(txt_effective_ic_rate,'') IS NOT NULL THEN CAST(txt_effective_ic_rate AS DECIMAL(10,6)) END) AS avg_ic_rate,
			  AVG(CASE WHEN LOWER(COALESCE(txt_Status,'')) LIKE '%declin%' OR LOWER(COALESCE(txt_Auth,'')) LIKE '%declin%' THEN 1 ELSE 0 END) AS decline_rate
			FROM ic_optimization.backup_transactions_full_profile
			WHERE txt_mccCode = %s
			""",
			(mcc_code,),
		)
		row = cur.fetchone()
		cur.close(); conn.close()
		if not row:
			return None
		avg_ic = float(row[0]) if row and row[0] is not None else None
		decl_rate_pct = float(row[1]) * 100.0 if row and row[1] is not None else None
		return {"avg_ic_rate": avg_ic, "decline_rate_pct": decl_rate_pct}
	except Exception:
		return None


def get_merchant_kpis_aggregates(merchant_id: str) -> dict | None:
	"""Return average volume_usd and avg_ticket_usd for the merchant (if available)."""
	try:
		conn = get_connection()
		cur = conn.cursor()
		cur.execute(
			"SELECT AVG(volume_usd), AVG(avg_ticket_usd) FROM merchant_kpis_monthly WHERE merchant_id=%s",
			(merchant_id,),
		)
		row = cur.fetchone()
		cur.close(); conn.close()
		if not row:
			return None
		avg_vol = float(row[0]) if row and row[0] is not None else None
		avg_ticket = float(row[1]) if row and row[1] is not None else None
		return {"avg_volume_usd": avg_vol, "avg_ticket_usd": avg_ticket}
	except Exception:
		return None


def compute_bands(avg_volume_usd: float | None, avg_ticket_usd: float | None) -> dict:
	"""Compute coarse bands for volume and average ticket.

	volume_band: small(<50k), mid(50k-500k), large(>500k)
	ticket_band: low(<20), mid(20-200), high(>200)
	"""
	vol_band = None
	if avg_volume_usd is not None:
		if avg_volume_usd < 50_000:
			vol_band = "small"
		elif avg_volume_usd <= 500_000:
			vol_band = "mid"
		else:
			vol_band = "large"

	tkt_band = None
	if avg_ticket_usd is not None:
		if avg_ticket_usd < 20:
			tkt_band = "low"
		elif avg_ticket_usd <= 200:
			tkt_band = "mid"
		else:
			tkt_band = "high"

	return {"volume_band": vol_band, "ticket_band": tkt_band}


def get_ic_optimization_metrics_band(mcc_code: str, volume_band: str | None, ticket_band: str | None) -> dict | None:
	"""Fetch metrics from ic_optimization with optional band filters (approximate via varchar casts)."""
	try:
		conn = get_connection(include_database=False)
		cur = conn.cursor()
		conds = ["txt_mccCode = %s"]
		params: list = [mcc_code]
		# derive numeric ranges for bands based on txt_Monthly_Volume and txt_Average_Ticket
		if volume_band:
			if volume_band == "small":
				conds.append("CAST(NULLIF(txt_Monthly_Volume,'') AS DECIMAL(18,2)) < 50000")
			elif volume_band == "mid":
				conds.append("CAST(NULLIF(txt_Monthly_Volume,'') AS DECIMAL(18,2)) BETWEEN 50000 AND 500000")
			elif volume_band == "large":
				conds.append("CAST(NULLIF(txt_Monthly_Volume,'') AS DECIMAL(18,2)) > 500000")
		if ticket_band:
			if ticket_band == "low":
				conds.append("CAST(NULLIF(txt_Average_Ticket,'') AS DECIMAL(18,2)) < 20")
			elif ticket_band == "mid":
				conds.append("CAST(NULLIF(txt_Average_Ticket,'') AS DECIMAL(18,2)) BETWEEN 20 AND 200")
			elif ticket_band == "high":
				conds.append("CAST(NULLIF(txt_Average_Ticket,'') AS DECIMAL(18,2)) > 200")
		where = " AND ".join(conds)
		cur.execute(
			f"""
			SELECT 
			  AVG(CASE WHEN NULLIF(txt_effective_ic_rate,'') IS NOT NULL THEN CAST(txt_effective_ic_rate AS DECIMAL(10,6)) END) AS avg_ic_rate,
			  AVG(CASE WHEN LOWER(COALESCE(txt_Status,'')) LIKE '%declin%' OR LOWER(COALESCE(txt_Auth,'')) LIKE '%declin%' THEN 1 ELSE 0 END) AS decline_rate
			FROM ic_optimization.backup_transactions_full_profile
			WHERE {where}
			""",
			params,
		)
		row = cur.fetchone()
		cur.close(); conn.close()
		if not row:
			return None
		avg_ic = float(row[0]) if row and row[0] is not None else None
		decl_rate_pct = float(row[1]) * 100.0 if row and row[1] is not None else None
		return {"avg_ic_rate": avg_ic, "decline_rate_pct": decl_rate_pct}
	except Exception:
		return None


def list_all_mcc_codes() -> list[tuple[str, str]]:
	"""Return list of (mcc_code, description)."""
	try:
		conn = get_connection()
		cur = conn.cursor()
		cur.execute("SELECT mcc_code, description FROM mcc_codes ORDER BY mcc_code")
		rows = cur.fetchall() or []
		cur.close(); conn.close()
		result: list[tuple[str, str]] = []
		for r in rows:
			code = (r[0] or "").strip()
			desc = (r[1] or "").strip()
			if code:
				result.append((code, desc))
		return result
	except Exception:
		return []


def load_brand_registry() -> list[dict]:
	"""Load brand registry rows as dicts."""
	try:
		conn = get_connection()
		cur = conn.cursor()
		cur.execute("SELECT brand_key, official_names, aliases, official_domains, iata_codes, brand_mcc, country, network, source_url, last_verified_at FROM brand_registry")
		rows = cur.fetchall() or []
		cur.close(); conn.close()
		result: list[dict] = []
		for r in rows:
			result.append({
				"brand_key": r[0],
				"official_names": json.loads(r[1] or "[]"),
				"aliases": json.loads(r[2] or "[]"),
				"official_domains": json.loads(r[3] or "[]"),
				"iata_codes": json.loads(r[4] or "[]"),
				"brand_mcc": (r[5] or "").strip(),
				"country": r[6],
				"network": r[7],
				"source_url": r[8],
				"last_verified_at": r[9].isoformat() if r[9] else None,
			})
		return result
	except Exception:
		return []


def get_brand_override(brand_key: str | None, host: str | None) -> str | None:
	"""Return MCC code override for a brand/domain if configured, else None.

	Looks up by brand_key first; if not found, matches exact domain_pattern or suffix against host.
	"""
	try:
		if not brand_key and not host:
			return None
		conn = get_connection()
		cur = conn.cursor()
		# Try brand_key
		if brand_key:
			cur.execute("SELECT mcc_code FROM brand_mcc_overrides WHERE brand_key=%s LIMIT 1", (brand_key,))
			row = cur.fetchone()
			if row and row[0]:
				cur.close(); conn.close(); return str(row[0])
		# Try domain_pattern exact or suffix match
		if host:
			cur.execute("SELECT mcc_code, domain_pattern FROM brand_mcc_overrides")
			for code, pattern in cur.fetchall() or []:
				p = (pattern or "").lower().strip()
				if not p:
					continue
				if host.lower() == p or host.lower().endswith("." + p):
					cur.close(); conn.close(); return str(code)
		cur.close(); conn.close()
		return None
	except Exception:
		return None


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


def upsert_merchant(merchant_id: str, legal_name: str | None, website: str | None, dba_name: str | None = None) -> None:
	conn = get_connection()
	cur = conn.cursor()
	cur.execute(
		"INSERT INTO merchants (merchant_id, legal_name, dba_name, website) VALUES (%s,%s,%s,%s)"
		" ON DUPLICATE KEY UPDATE legal_name=VALUES(legal_name), dba_name=VALUES(dba_name), website=VALUES(website), updated_at=NOW()",
		(merchant_id, legal_name, dba_name, website),
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
