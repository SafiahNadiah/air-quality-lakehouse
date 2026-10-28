# Databricks notebook source
# MAGIC %md
# MAGIC # 06 Anomaly detection (PM2.5 and NO2)
# MAGIC
# MAGIC **Goal:** flag unusual months in the monthly air quality series.
# MAGIC
# MAGIC Two simple methods are compared:
# MAGIC 1. **Robust z-score** (median and MAD, so outliers do not distort the baseline). Flag when |z| > 3.5.
# MAGIC 2. **Isolation Forest** (scikit-learn, unsupervised). Flag the most isolated 5% of months.
# MAGIC
# MAGIC This is a learning project, not a production model. It does not remove seasonality or trend, so a flagged month is a prompt to investigate, not proof of an event.

# COMMAND ----------

spark.sql("USE CATALOG workspace")
spark.sql("USE SCHEMA air_quality")

# COMMAND ----------

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest

POLLUTANTS = ["PM2.5", "NO2"]

# COMMAND ----------

df = spark.sql("""
    SELECT d.full_date AS reading_month, p.pollutant_code, f.concentration
    FROM gold_fact_air_quality f
    JOIN gold_dim_date d      ON f.date_key = d.date_key
    JOIN gold_dim_pollutant p ON f.pollutant_key = p.pollutant_key
    WHERE p.pollutant_code IN ('PM2.5', 'NO2')
    ORDER BY p.pollutant_code, d.full_date
""").toPandas()
df["reading_month"] = pd.to_datetime(df["reading_month"])
print(df.groupby("pollutant_code").size())

# COMMAND ----------

def flag_anomalies(s, contamination=0.05, z_threshold=3.5):
    s = s.sort_values("reading_month").copy()
    median = s["concentration"].median()
    mad = (s["concentration"] - median).abs().median()
    if mad > 0:
        s["robust_z"] = 0.6745 * (s["concentration"] - median) / mad
    else:
        s["robust_z"] = 0.0
    s["flag_zscore"] = s["robust_z"].abs() > z_threshold

    X = s[["concentration"]].to_numpy()
    iso = IsolationForest(contamination=contamination, random_state=42).fit(X)
    s["flag_isoforest"] = iso.predict(X) == -1
    s["flag_both"] = s["flag_zscore"] & s["flag_isoforest"]
    return s

# COMMAND ----------

result = pd.concat(
    [flag_anomalies(g) for _, g in df.groupby("pollutant_code")],
    ignore_index=True,
)
summary = result.groupby("pollutant_code")[["flag_zscore", "flag_isoforest", "flag_both"]].sum()
display(summary.reset_index())

# COMMAND ----------

# Flagged months, most unusual first
flagged = result[result["flag_zscore"] | result["flag_isoforest"]].copy()
flagged["abs_z"] = flagged["robust_z"].abs()
flagged = flagged.sort_values(["pollutant_code", "abs_z"], ascending=[True, False])
display(flagged[["pollutant_code", "reading_month", "concentration", "robust_z",
                 "flag_zscore", "flag_isoforest", "flag_both"]])

# COMMAND ----------

fig, axes = plt.subplots(len(POLLUTANTS), 1, figsize=(11, 7), sharex=True)
for ax, code in zip(axes, POLLUTANTS):
    g = result[result["pollutant_code"] == code]
    ax.plot(g["reading_month"], g["concentration"], color="#4c78a8", lw=1.5, label=code)
    iso = g[g["flag_isoforest"]]
    ax.scatter(iso["reading_month"], iso["concentration"], color="#f58518", s=60,
               label="Isolation Forest", zorder=3)
    both = g[g["flag_both"]]
    ax.scatter(both["reading_month"], both["concentration"], color="#e45756", s=110,
               marker="X", label="Both methods", zorder=4)
    ax.set_title(f"{code}: monthly concentration with flagged months")
    ax.set_ylabel("Concentration")
    ax.legend(loc="upper right")
axes[-1].set_xlabel("Month")
plt.tight_layout()
plt.show()

# COMMAND ----------

# Save the results as a table so they can be queried or charted
out = result[["reading_month", "pollutant_code", "concentration", "robust_z",
              "flag_zscore", "flag_isoforest", "flag_both"]].copy()
out["reading_month"] = out["reading_month"].dt.date
(spark.createDataFrame(out)
      .write.format("delta").mode("overwrite").option("overwriteSchema", True)
      .saveAsTable("gold_anomalies"))
print("Saved gold_anomalies:", len(out), "rows")
