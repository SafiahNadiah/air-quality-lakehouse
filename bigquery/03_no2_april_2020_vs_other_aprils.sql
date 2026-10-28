SELECT
  ROUND(AVG(CASE WHEN d.year = 2020 THEN f.concentration END), 4)  AS april_2020,
  ROUND(AVG(CASE WHEN d.year <> 2020 THEN f.concentration END), 4) AS avg_other_aprils,
  ROUND(100.0 * (AVG(CASE WHEN d.year = 2020 THEN f.concentration END)
       / AVG(CASE WHEN d.year <> 2020 THEN f.concentration END) - 1), 1) AS pct_difference
FROM `air-quality-portfolio.air_quality.gold_fact_air_quality` f
JOIN `air-quality-portfolio.air_quality.gold_dim_date` d
  ON f.date_key = d.date_key
JOIN `air-quality-portfolio.air_quality.gold_dim_pollutant` p
  ON f.pollutant_key = p.pollutant_key
WHERE p.pollutant_code = 'NO2' AND d.month = 4
