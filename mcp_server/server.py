import sqlite3
from pathlib import Path

from mcp.server.mcpserver import MCPServer

DB = Path(__file__).parent / "air_quality.db"
VALID = {"CO", "NO2", "O3", "SO2", "PM10", "PM2.5"}

mcp = MCPServer("air-quality")


def run_query(sql: str, params: tuple = ()) -> list[dict]:
    # Read-only connection: the tools below can never modify the data.
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def clean_pollutant(pollutant: str) -> str:
    code = pollutant.upper().replace(" ", "")
    if code not in VALID:
        raise ValueError(f"Unknown pollutant '{pollutant}'. Use one of: {sorted(VALID)}")
    return code


@mcp.tool()
def get_yearly_average(pollutant: str) -> list[dict]:
    """Yearly average concentration and year-over-year change for one pollutant.
    Years with fewer than 12 months of data are marked is_partial_year."""
    code = clean_pollutant(pollutant)
    return run_query(
        """SELECT CAST(year AS INTEGER) AS year, avg_concentration, months_with_data, yoy_change_pct,
                  CASE WHEN months_with_data < 12 THEN 1 ELSE 0 END AS is_partial_year
           FROM gold_agg_yearly WHERE pollutant_code = ? ORDER BY year""",
        (code,),
    )


@mcp.tool()
def top_worst_months(pollutant: str, n: int = 5) -> list[dict]:
    """The n months (1 to 12) with the highest concentration for one pollutant."""
    code = clean_pollutant(pollutant)
    n = max(1, min(int(n), 12))
    return run_query(
        """SELECT d.year_month, f.concentration
           FROM gold_fact_air_quality f
           JOIN gold_dim_date d ON f.date_key = d.date_key
           JOIN gold_dim_pollutant p ON f.pollutant_key = p.pollutant_key
           WHERE p.pollutant_code = ?
           ORDER BY f.concentration DESC LIMIT ?""",
        (code, n),
    )


@mcp.tool()
def get_anomalies(pollutant: str) -> list[dict]:
    """Months flagged as unusual (robust z-score and/or Isolation Forest).
    flag_both = 1 means both methods agree. A flag is a prompt to investigate, not proof of an event."""
    code = clean_pollutant(pollutant)
    return run_query(
        """SELECT reading_month, concentration, robust_z, flag_zscore, flag_isoforest, flag_both
           FROM gold_anomalies
           WHERE pollutant_code = ? AND (flag_zscore OR flag_isoforest)
           ORDER BY ABS(robust_z) DESC""",
        (code,),
    )


@mcp.tool()
def data_quality_summary() -> list[dict]:
    """Results of the latest data quality run (9 checks)."""
    return run_query(
        """SELECT check_name, severity, status, violations, description
           FROM gold_dq_results
           WHERE run_ts = (SELECT MAX(run_ts) FROM gold_dq_results)"""
    )


if __name__ == "__main__":
    mcp.run()
