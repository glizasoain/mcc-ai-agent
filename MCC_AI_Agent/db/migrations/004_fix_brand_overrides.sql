-- Correct brand overrides for major airlines
INSERT INTO brand_mcc_overrides (brand_key, domain_pattern, mcc_code, notes)
VALUES
  ('delta', 'delta.com', '3058', 'Delta Air Lines'),
  ('lufthansa', 'lufthansa.com', '3008', 'Lufthansa')
ON DUPLICATE KEY UPDATE
  domain_pattern=VALUES(domain_pattern),
  mcc_code=VALUES(mcc_code),
  notes=VALUES(notes);


