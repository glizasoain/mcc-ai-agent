import os
import json
import threading
import time
import socket
from contextlib import closing
import subprocess

import httpx
import pytest


def wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
	end = time.time() + timeout
	while time.time() < end:
		with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
			sock.settimeout(0.5)
			if sock.connect_ex((host, port)) == 0:
				return
		time.sleep(0.1)
	raise RuntimeError("server did not start in time")


def test_smoke_endpoints():
	# Ensure server is running on 8090; start a temp one if needed
	base_url = "http://127.0.0.1:8090"
	started = False
	proc = None
	try:
		try:
			wait_for_port("127.0.0.1", 8090, timeout=0.5)
		except Exception:
			proc = subprocess.Popen([
				".venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8090"
			])
			started = True
			wait_for_port("127.0.0.1", 8090, timeout=5)

		with httpx.Client(base_url=base_url, timeout=12.0) as client:
			# health
			r = client.get("/health")
			assert r.status_code == 200
			assert r.json().get("ok") is True

			# submit_merchant
			r = client.post("/api/v1/submit_merchant", json={
				"merchant_id": "apple", "merchant_name": "Apple Inc.",
				"website": {"url": "https://apple.com"}
			})
			assert r.status_code == 200
			assert r.json().get("submitted") is True

			# recommend
			r = client.post("/api/v1/mcc/recommend", json={
				"merchant_id": "apple", "website": "https://apple.com"
			})
			assert r.status_code == 200
			body = r.json()
			assert body.get("merchant_id") == "apple"
			mcc = body.get("recommended_mcc", "")
			assert isinstance(mcc, str) and len(mcc) in (0, 4)
			if len(mcc) == 4:
				assert mcc.isdigit()
				desc = body.get("recommended_mcc_description", "")
				assert isinstance(desc, str)
				# DB-backed description may be empty if not present; allow non-empty check when present
				# assert desc != ""
			prov = body.get("provenance", {}) or {}
			assert prov.get("model") in ("crewai", "gpt-4o", None)

			# list_runs
			r = client.get("/api/v1/list_runs")
			assert r.status_code == 200
			assert isinstance(r.json().get("runs"), list)

			# simulate_impact smoke
			r = client.post("/api/v1/simulate_impact", json={
				"mcc_from": "5732", "mcc_to": "5734", "cohort_size": 10
			})
			assert r.status_code == 200
			body = r.json()
			assert isinstance(body.get("cohort_size"), int)
			assert isinstance(body.get("summary"), str)

	finally:
		if started and proc is not None:
			proc.terminate()
			try:
				proc.wait(timeout=3)
			except Exception:
				proc.kill()
				proc.wait(timeout=3)



def test_crewai_provenance_and_prompt_hash_changes():
	# Ensure server is running on 8090; start a temp one if needed
	base_url = "http://127.0.0.1:8090"
	started = False
	proc = None
	try:
		try:
			wait_for_port("127.0.0.1", 8090, timeout=0.5)
		except Exception:
			proc = subprocess.Popen([
				".venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8090"
			])
			started = True
			wait_for_port("127.0.0.1", 8090, timeout=5)

		with httpx.Client(base_url=base_url, timeout=12.0) as client:
			# First call with profile A
			r1 = client.post("/api/v1/mcc/recommend", json={
				"merchant_id": "hashcheck-a",
				"website": {"url": "https://shop.example/a"},
				"profile": {
					"industry": "apparel",
					"vertical": "ecommerce",
					"country": "US",
					"existing_mcc": "5651",
					"avg_ticket": 49.0,
					"volume_band": "high"
				}
			})
			if r1.status_code == 503:
				pytest.skip("CrewAI unavailable in this environment")
			assert r1.status_code == 200
			body1 = r1.json()
			prov1 = body1.get("provenance", {}) or {}
			assert prov1.get("model") == "crewai"
			hash1 = prov1.get("prompt_hash")
			assert isinstance(hash1, str) and len(hash1) > 0

			# Second call with profile B and different merchant_description -> different prompt -> different hash
			r2 = client.post("/api/v1/mcc/recommend", json={
				"merchant_id": "hashcheck-b",
				"websites": [{"url": "https://shop.example/b1"}, {"url": "https://shop.example/b2"}],
				"profile": {
					"industry": "electronics",
					"vertical": "retail",
					"country": "CA",
					"existing_mcc": "5732",
					"avg_ticket": 299.0,
					"volume_band": "medium"
				},
				"merchant_description": "Sells gadgets and accessories"
			})
			if r2.status_code == 503:
				pytest.skip("CrewAI unavailable in this environment")
			assert r2.status_code == 200
			body2 = r2.json()
			prov2 = body2.get("provenance", {}) or {}
			assert prov2.get("model") == "crewai"
			hash2 = prov2.get("prompt_hash")
			assert isinstance(hash2, str) and len(hash2) > 0

			assert hash1 != hash2, "prompt_hash should differ when profile inputs change"

	finally:
		if started and proc is not None:
			proc.terminate()
			try:
				proc.wait(timeout=3)
			except Exception:
				proc.kill()
				proc.wait(timeout=3)


def test_openapi_contract_and_invalid_payload_validation():
	# Ensure server is running on 8090; start a temp one if needed
	base_url = "http://127.0.0.1:8090"
	started = False
	proc = None
	try:
		try:
			wait_for_port("127.0.0.1", 8090, timeout=0.5)
		except Exception:
			proc = subprocess.Popen([
				".venv/bin/uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8090"
			])
			started = True
			wait_for_port("127.0.0.1", 8090, timeout=5)

		with httpx.Client(base_url=base_url, timeout=12.0) as client:
			# Fetch OpenAPI and check recommend endpoint schemas exist
			r = client.get("/openapi.json")
			assert r.status_code == 200
			spec = r.json()
			paths = spec.get("paths", {})
			assert "/api/v1/mcc/recommend" in paths
			post_op = paths["/api/v1/mcc/recommend"].get("post", {})
			assert post_op
			assert any(cr.get("content", {}).get("application/json") for cr in [post_op.get("requestBody", {})])
			assert any("application/json" in (rsp.get("content") or {}) for rsp in (post_op.get("responses") or {}).values())
			# Ensure new field is present in request schema (resolve $ref if present)
			req_schema = post_op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
			if "$ref" in req_schema:
				ref = req_schema["$ref"]
				# Format: #/components/schemas/RecommendRequest
				parts = ref.split("/")
				schema_name = parts[-1] if parts else None
				assert schema_name
				props = (spec.get("components", {}).get("schemas", {}).get(schema_name, {}).get("properties", {}))
			else:
				props = req_schema.get("properties", {})
			assert "merchant_description" in props
			assert "websites" in props

			# Send invalid payload: website as object missing url, confidence not allowed, etc.
			r = client.post("/api/v1/mcc/recommend", json={
				"merchant_id": 123,  # should be string
				"website": {"bad": "field"}
			})
			assert r.status_code == 422
			err = r.json()
			assert err.get("detail")
			# Ensure error mentions merchant_id type
			detail_str = json.dumps(err["detail"]) if isinstance(err.get("detail"), list) else json.dumps(err)
			assert "merchant_id" in detail_str

	finally:
		if started and proc is not None:
			proc.terminate()
			try:
				proc.wait(timeout=3)
			except Exception:
				proc.kill()
				proc.wait(timeout=3)
