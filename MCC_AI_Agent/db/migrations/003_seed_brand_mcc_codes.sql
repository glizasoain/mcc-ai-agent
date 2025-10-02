-- Seed brand-specific MCC codes if missing (example: United Airlines)
INSERT INTO mcc_codes (mcc_code, description)
VALUES ('3000', 'UNITED AIRLINES')
ON DUPLICATE KEY UPDATE description=VALUES(description);

INSERT INTO mcc_codes (mcc_code, description)
VALUES ('3058', 'DELTA AIR LINES')
ON DUPLICATE KEY UPDATE description=VALUES(description);

INSERT INTO mcc_codes (mcc_code, description)
VALUES ('3008', 'LUFTHANSA')
ON DUPLICATE KEY UPDATE description=VALUES(description);


