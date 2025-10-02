from __future__ import annotations

import json
from typing import List, Tuple
from pathlib import Path

import mysql.connector
from openai import OpenAI
from dotenv import load_dotenv

from app.db import get_connection


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)


EMBED_MODEL = "text-embedding-3-large"


def _embed_texts(texts: List[str]) -> List[List[float]]:
    client = OpenAI()
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in resp.data]


def ensure_mcc_embeddings_built() -> None:
    conn = get_connection()
    cur = conn.cursor()
    # Check if table has any rows
    cur.execute("SELECT COUNT(*) FROM mcc_embeddings")
    count = int((cur.fetchone() or [0])[0])
    if count > 0:
        cur.close(); conn.close()
        return

    # Load MCC catalog from mcc_codes table
    cur.execute("SELECT mcc_code, description FROM mcc_codes")
    rows = cur.fetchall() or []
    if not rows:
        cur.close(); conn.close()
        return

    texts: List[str] = []
    codes: List[str] = []
    for code, desc in rows:
        code_s = (code or "").strip()
        desc_s = (desc or "").strip()
        if not code_s:
            continue
        text = f"MCC {code_s}: {desc_s}"
        texts.append(text)
        codes.append(code_s)

    vectors = _embed_texts(texts)
    data = [(codes[i], EMBED_MODEL, 1536, json.dumps(vectors[i]), texts[i]) for i in range(len(codes))]
    cur.executemany(
        "INSERT INTO mcc_embeddings (mcc_code, model, dim, vector_json, text) VALUES (%s,%s,%s,%s,%s)"
        " ON DUPLICATE KEY UPDATE model=VALUES(model), dim=VALUES(dim), vector_json=VALUES(vector_json), text=VALUES(text)",
        data,
    )
    conn.commit(); cur.close(); conn.close()


def _cosine_sim(v1: List[float], v2: List[float]) -> float:
    import math
    if not v1 or not v2:
        return 0.0
    s = sum(a*b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a*a for a in v1))
    n2 = math.sqrt(sum(b*b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return s / (n1 * n2)


def retrieve_mcc_candidates(query_text: str, top_k: int = 7) -> List[Tuple[str, float]]:
    """Return top_k MCC codes with similarity scores using local vectors.

    Dev/local implementation: embeds query and brute-force compares with mcc_embeddings table.
    """
    qvec = _embed_texts([query_text])[0]
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT mcc_code, vector_json FROM mcc_embeddings")
    rows = cur.fetchall() or []
    scored = []
    for code, vjson in rows:
        try:
            vec = json.loads(vjson)
        except Exception:
            vec = []
        scored.append((code, _cosine_sim(qvec, vec)))
    scored.sort(key=lambda x: x[1], reverse=True)
    cur.close(); conn.close()
    return scored[:top_k]


