-- Optional example merchant fields for benchmarks
-- Add example columns only if they don't already exist (MySQL-compatible)
SET @stmt := (
  SELECT IF(
    EXISTS(
      SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mcc_portfolio' AND COLUMN_NAME = 'example_merchant_name'
    ),
    'SELECT 1',
    'ALTER TABLE mcc_portfolio ADD COLUMN example_merchant_name VARCHAR(255) NULL'
  )
);
PREPARE s1 FROM @stmt; EXECUTE s1; DEALLOCATE PREPARE s1;

SET @stmt := (
  SELECT IF(
    EXISTS(
      SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mcc_portfolio' AND COLUMN_NAME = 'example_merchant_url'
    ),
    'SELECT 1',
    'ALTER TABLE mcc_portfolio ADD COLUMN example_merchant_url VARCHAR(512) NULL'
  )
);
PREPARE s2 FROM @stmt; EXECUTE s2; DEALLOCATE PREPARE s2;

