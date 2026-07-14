# Raw Source Data

This folder holds the 8 source Excel files (one per bus corporation), used for the one-time Bronze ingestion. The files themselves are **not committed** to this repo (see root `.gitignore`) since they contain real operational/financial data.

| File | Corporation |
|---|---|
| MTC.xlsx | MTC (Chennai) |
| SALEM.xlsx | Salem |
| SETC.xlsx | SETC |
| TIRUNELVELI.xlsx | Tirunelveli |
| VILLUPURAM.xlsx | Villupuram |
| coimbatore.xlsx | Coimbatore |
| kumbakonam.xlsx | Kumbakonam |
| madurai.xlsx | Madurai |

Place the 8 files in this folder locally before running the Bronze ingestion notebook. See `CLAUDE.md` §3 for the canonical column list and known data quality issues.
