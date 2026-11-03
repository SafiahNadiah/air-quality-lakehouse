import sqlite3
from pathlib import Path
import pandas as pd

DATA = Path(__file__).parent / "data"
DB = Path(__file__).parent / "air_quality.db"

con = sqlite3.connect(DB)
for csv in sorted(DATA.glob("gold_*.csv")):
	df = pd.read_csv(csv)
	df.to_sql(csv.stem, con, if_exists="replace", index=False)
	print(f"loaded {csv.stem}: {len(df)} rows")
con.close()