-- MCC portfolio benchmarks (IC rates, optional decline rates)
CREATE TABLE IF NOT EXISTS mcc_portfolio (
  mcc_code VARCHAR(10) PRIMARY KEY,
  mcc_description VARCHAR(255),
  weighted_avg_ic_rate DECIMAL(10,6) NULL,
  decline_rate_pct DECIMAL(5,2) NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

