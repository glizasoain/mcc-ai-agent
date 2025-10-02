-- PRD 6a core tables (dev/local demo only)
CREATE TABLE IF NOT EXISTS merchants (
  merchant_id VARCHAR(32) PRIMARY KEY,
  legal_name VARCHAR(255),
  dba_name VARCHAR(255),
  website VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS merchant_kpis_monthly (
  merchant_id VARCHAR(32) NOT NULL,
  period_month DATE NOT NULL,
  decline_rate_pct DECIMAL(5,2),
  ic_bps INT,
  volume_usd DECIMAL(18,2),
  avg_ticket_usd DECIMAL(12,2),
  PRIMARY KEY (merchant_id, period_month)
);

CREATE TABLE IF NOT EXISTS mcc_codes (
  mcc_code VARCHAR(10) PRIMARY KEY,
  description VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS runs (
  run_id CHAR(36) PRIMARY KEY,
  merchant_id VARCHAR(32),
  status ENUM('queued','running','completed','failed'),
  started_at TIMESTAMP NULL,
  finished_at TIMESTAMP NULL,
  provenance_id CHAR(36)
);

CREATE TABLE IF NOT EXISTS recommendations (
  run_id CHAR(36) NOT NULL,
  `rank` INT NOT NULL,
  mcc VARCHAR(4),
  confidence DECIMAL(4,3),
  decline_pp DECIMAL(5,2),
  ic_bps INT,
  reasons_json JSON,
  PRIMARY KEY (run_id, `rank`)
);

CREATE TABLE IF NOT EXISTS artifacts (
  run_id CHAR(36) NOT NULL,
  kind VARCHAR(32) NOT NULL,
  s3_uri VARCHAR(512),
  meta_json JSON,
  PRIMARY KEY (run_id, kind)
);

-- Web intelligence (Phase 6)
CREATE TABLE IF NOT EXISTS web_pages (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  merchant_id VARCHAR(32) NOT NULL,
  url VARCHAR(1024) NOT NULL,
  title VARCHAR(512),
  summary TEXT,
  content MEDIUMTEXT,
  content_hash CHAR(64),
  crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  -- Use a prefix length on url to keep composite index under 3072-byte InnoDB limit
  UNIQUE KEY uniq_merchant_url (merchant_id, url(255))
);

CREATE TABLE IF NOT EXISTS embeddings (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  merchant_id VARCHAR(32) NOT NULL,
  page_id BIGINT NOT NULL,
  chunk_index INT NOT NULL,
  model VARCHAR(64) NOT NULL,
  dim INT NOT NULL,
  vector_json JSON NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_page_chunk (page_id, chunk_index),
  INDEX idx_merchant (merchant_id)
);

-- MCC catalog embeddings (dev/local for RAG)
CREATE TABLE IF NOT EXISTS mcc_embeddings (
  mcc_code VARCHAR(10) PRIMARY KEY,
  model VARCHAR(64) NOT NULL,
  dim INT NOT NULL,
  vector_json JSON NOT NULL,
  text LONGTEXT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_model (model)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  idempotency_key VARCHAR(64) PRIMARY KEY,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  request_hash BINARY(32),
  response_json JSON,
  ttl_at TIMESTAMP,
  INDEX (ttl_at)
);

-- Brand overrides for deterministic MCC mapping
CREATE TABLE IF NOT EXISTS brand_mcc_overrides (
  brand_key VARCHAR(64) PRIMARY KEY, -- e.g., 'united', 'delta'
  domain_pattern VARCHAR(255) NOT NULL, -- e.g., 'united.com'
  mcc_code VARCHAR(10) NOT NULL,
  notes VARCHAR(255),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
