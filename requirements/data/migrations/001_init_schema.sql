
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
  PRIMARY KEY (merchant_id, period_month),
  CONSTRAINT fk_kpis_merchant FOREIGN KEY (merchant_id) REFERENCES merchants(merchant_id)
);

CREATE TABLE IF NOT EXISTS mcc_catalog (
  network ENUM('VISA','MC','AMEX','DISC') NOT NULL,
  mcc VARCHAR(4) NOT NULL,
  title VARCHAR(255),
  description TEXT,
  rules_json JSON,
  PRIMARY KEY (network, mcc)
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
  rank INT NOT NULL,
  mcc VARCHAR(4),
  confidence DECIMAL(4,3),
  decline_pp DECIMAL(5,2),
  ic_bps INT,
  reasons_json JSON,
  PRIMARY KEY (run_id, rank)
);

CREATE TABLE IF NOT EXISTS artifacts (
  run_id CHAR(36) NOT NULL,
  kind VARCHAR(32) NOT NULL,
  s3_uri VARCHAR(512),
  meta_json JSON,
  PRIMARY KEY (run_id, kind)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  idempotency_key VARCHAR(64) PRIMARY KEY,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  request_hash BINARY(32),
  response_json JSON,
  ttl_at TIMESTAMP,
  INDEX (ttl_at)
);
