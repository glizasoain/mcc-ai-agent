-- Seed common first-party airline brand overrides (dev/local)
INSERT INTO brand_mcc_overrides (brand_key, domain_pattern, mcc_code, notes)
VALUES
  ('united', 'united.com', '3000', 'United Airlines'),
  ('aa', 'aa.com', '3000', 'American Airlines'),
  ('americanairlines', 'aa.com', '3000', 'American Airlines alt key'),
  ('delta', 'delta.com', '3000', 'Delta Air Lines'),
  ('southwest', 'southwest.com', '3000', 'Southwest Airlines'),
  ('alaska', 'alaskaair.com', '3000', 'Alaska Airlines'),
  ('jetblue', 'jetblue.com', '3000', 'JetBlue Airways')
ON DUPLICATE KEY UPDATE
  domain_pattern=VALUES(domain_pattern),
  mcc_code=VALUES(mcc_code),
  notes=VALUES(notes);


