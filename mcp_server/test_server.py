"""Automated tests for the air quality MCP server.

They build a tiny temporary SQLite database, so they run anywhere (also in CI)
without the real data. They check that bad input is rejected or clamped and that
the database cannot be written to.
"""
import sqlite3

import pytest

import server


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE gold_dim_pollutant (pollutant_key INTEGER, pollutant_code TEXT);
        CREATE TABLE gold_dim_date (date_key INTEGER, full_date TEXT, year INTEGER,
                                    quarter INTEGER, month INTEGER, year_month TEXT);
        CREATE TABLE gold_fact_air_quality (date_key INTEGER, pollutant_key INTEGER, concentration REAL);
        CREATE TABLE gold_agg_yearly (year REAL, pollutant_code TEXT, months_with_data INTEGER,
                                      avg_concentration REAL, min_concentration REAL,
                                      max_concentration REAL, yoy_change_pct REAL);
        CREATE TABLE gold_anomalies (reading_month TEXT, pollutant_code TEXT, concentration REAL,
                                     robust_z REAL, flag_zscore INTEGER, flag_isoforest INTEGER,
                                     flag_both INTEGER);
        CREATE TABLE gold_dq_results (run_ts TEXT, check_name TEXT, severity TEXT,
                                      status TEXT, violations INTEGER, description TEXT);

        INSERT INTO gold_dim_pollutant VALUES (1, 'PM2.5'), (2, 'NO2');
        INSERT INTO gold_agg_yearly VALUES (2017.0, 'PM2.5', 8, 15.0, 10.0, 20.0, NULL),
                                           (2018.0, 'PM2.5', 12, 16.0, 11.0, 21.0, 6.7);
        INSERT INTO gold_anomalies VALUES ('2019-09-01', 'PM2.5', 52.8, 14.2, 1, 1, 1),
                                          ('2019-10-01', 'PM2.5', 20.0, 1.0, 0, 0, 0);
        INSERT INTO gold_dq_results VALUES ('2026-01-01 00:00:00', 'old_check', 'critical', 'PASS', 0, 'old'),
                                           ('2026-02-01 00:00:00', 'new_check', 'warning', 'WARN', 3, 'new');
        """
    )
    for i in range(1, 16):  # 15 months of PM2.5
        date_key = 20200000 + i * 100 + 1
        con.execute("INSERT INTO gold_dim_date VALUES (?, ?, 2020, 1, ?, ?)",
                    (date_key, f"2020-{i:02d}-01", i, f"2020-{i:02d}"))
        con.execute("INSERT INTO gold_fact_air_quality VALUES (?, 1, ?)", (date_key, 10.0 + i))
    con.commit()
    con.close()
    monkeypatch.setattr(server, "DB", path)
    return path


def row_count(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM gold_fact_air_quality").fetchone()[0]
    finally:
        con.close()


# ---- normal use -------------------------------------------------------------

def test_valid_pollutant_returns_rows(db):
    assert len(server.get_yearly_average("PM2.5")) == 2


def test_lowercase_pollutant_is_normalised(db):
    assert server.get_yearly_average("pm2.5") == server.get_yearly_average("PM2.5")


def test_partial_year_is_flagged(db):
    rows = {r["year"]: r for r in server.get_yearly_average("PM2.5")}
    assert rows[2017]["is_partial_year"] == 1
    assert rows[2018]["is_partial_year"] == 0


def test_anomalies_only_returns_flagged_months(db):
    rows = server.get_anomalies("PM2.5")
    assert [r["reading_month"] for r in rows] == ["2019-09-01"]


def test_data_quality_summary_returns_latest_run_only(db):
    rows = server.data_quality_summary()
    assert [r["check_name"] for r in rows] == ["new_check"]


# ---- malformed input --------------------------------------------------------

BAD_POLLUTANTS = [
    "XYZ",
    "",
    "PM2.5'; DROP TABLE gold_agg_yearly;--",
    "NO2' OR '1'='1",
    "PM2.5 UNION SELECT * FROM gold_dq_results",
]


@pytest.mark.parametrize("bad", BAD_POLLUTANTS)
def test_unknown_pollutant_is_rejected(db, bad):
    with pytest.raises(ValueError):
        server.get_yearly_average(bad)
    with pytest.raises(ValueError):
        server.top_worst_months(bad, 3)
    with pytest.raises(ValueError):
        server.get_anomalies(bad)


@pytest.mark.parametrize("n,expected", [(999, 12), (13, 12), (0, 1), (-5, 1), (3, 3)])
def test_n_is_clamped_between_1_and_12(db, n, expected):
    assert len(server.top_worst_months("PM2.5", n)) == expected


def test_n_that_is_not_a_number_is_rejected(db):
    with pytest.raises(ValueError):
        server.top_worst_months("PM2.5", "abc")


# ---- read-only --------------------------------------------------------------

WRITE_STATEMENTS = [
    "INSERT INTO gold_dim_pollutant VALUES (99, 'X')",
    "UPDATE gold_agg_yearly SET year = 0",
    "DELETE FROM gold_fact_air_quality",
    "DROP TABLE gold_agg_yearly",
]


@pytest.mark.parametrize("statement", WRITE_STATEMENTS)
def test_write_statements_fail_on_the_server_connection(db, statement):
    before = row_count(db)
    with pytest.raises(sqlite3.OperationalError):
        server.run_query(statement)
    assert row_count(db) == before


def test_calling_every_tool_does_not_change_the_data(db):
    before = row_count(db)
    server.get_yearly_average("PM2.5")
    server.top_worst_months("PM2.5", 5)
    server.get_anomalies("PM2.5")
    server.data_quality_summary()
    assert row_count(db) == before
