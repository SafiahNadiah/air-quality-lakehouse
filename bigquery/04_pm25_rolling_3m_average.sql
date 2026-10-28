SELECT d.full_date AS reading_month,
       f.concentration AS pm25,
       ROUND(AVG(f.concentration) OVER (ORDER BY d.full_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS pm25_rolling_3m
FROM `air-quality-portfolio.air_quality.gold_fact_air_quality` f
JOIN `air-quality-portfolio.air_quality.gold_dim_date` d
  ON f.date_key = d.date_key
JOIN `air-quality-portfolio.air_quality.gold_dim_pollutant` p
  ON f.pollutant_key = p.pollutant_key
WHERE p.pollutant_code = 'PM2.5'
ORDER BY d.full_date
