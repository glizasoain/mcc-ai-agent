-- Brand registry for generic, data-driven brand matching
CREATE TABLE IF NOT EXISTS brand_registry (
  brand_key VARCHAR(64) PRIMARY KEY,
  official_names JSON NOT NULL,         -- ["United Airlines", "United"]
  aliases JSON NULL,                    -- ["United Air", "UA"]
  official_domains JSON NOT NULL,       -- ["united.com", "unitedairlines.com"]
  iata_codes JSON NULL,                 -- ["UA"] when applicable
  brand_mcc VARCHAR(10) NOT NULL,       -- e.g., 3000
  country VARCHAR(2) NULL,
  network VARCHAR(32) NULL,             -- optional scope if needed later
  source_url VARCHAR(512) NULL,
  last_verified_at TIMESTAMP NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

