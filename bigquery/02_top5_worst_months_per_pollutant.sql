SELECT pollutant_code, year_month, concentration, worst_rank
FROM (
  SELECT p.pollutant_code, d.year_month, f.concentration,
         ROW_NUMBER() OVER (PARTITION BY p.pollutant_code ORDER BY f.concentration DESC) AS worst_rank
  FROM `air-quality-portfolio.air_quality.gold_fact_air_quality` f
  JOIN `air-quality-portfolio.air_quality.gold_dim_date` d
    ON f.date_key = d.date_key
  JOIN `air-quality-portfolio.air_quality.gold_dim_pollutant` p
    ON f.pollutant_key = p.pollutant_key
) ranked
WHERE worst_rank <= 5
ORDER BY pollutant_code, worst_rank
