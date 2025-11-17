```markdown
# Voter Database Change Analyzer

**`compare_voters_history.py`** — A Python script to compare two Minnesota voter registration databases (`*.db`) and generate **per-county** and **master** reports on voter changes.

---

## Features

| Feature | Description |
|-------|-----------|
| **Last 5 Elections** | Shows **most recent 5 elections** (by date) with **voter turnout** |
| **Voters Removed** | Voters in old DB but **not in new DB** |
| **Histories Changed** | Election records that **differ** (date, description, method) |
| **Voters Who Moved** | Same `VoterId` + same name + **changed address** |
| **Per-County Reports** | `diff_XX_COUNTY.csv` + `summary_XX_COUNTY.md` |
| **Master Summary** | `summary_all_counties.csv` + `summary_all_counties.md` |

---

## Output Files

| File | Description |
|------|-----------|
| `diff_01_AITKIN.csv` | All changed voters (history + moved) |
| `summary_01_AITKIN.md` | County summary + last 5 elections + definitions |
| `summary_all_counties.csv` | All 87 counties in one table |
| `summary_all_counties.md` | Markdown version of master summary |

---

## Requirements

```bash
Python 3.9+
pandas
sqlite3 (built-in)
```

Install dependencies:

```bash
pip install pandas
```

---

## Usage

```bash
python3 compare_voters_history.py <new_db> <old_db>
```

### Example

```bash
python3 compare_voters_history.py ems251109.db ems251005.db
```

> Compares `ems251109.db` (new) vs `ems251005.db` (old)

---

## Sample Output: `summary_01_AITKIN.md`

```markdown
# Voter Change Summary: AITKIN County (01)

**Total Voters (New DB):** 12,006

## Last 5 Elections (by Date)

| Election Date | Description | Voters Who Voted |
|---------------|-------------|------------------|
| 2025-11-04 | 11/04/2025 - SD SPEC ELECT ISD 1 - AITKIN | 3,125 |
| 2024-11-05 | 2024 General Election | 8,201 |
| 2024-08-13 | 2024 Primary Election | 2,104 |
| 2022-11-08 | 2022 General Election | 7,889 |
| 2022-08-09 | 2022 Primary Election | 3,412 |

## Change Breakdown

| Category | Count | % of Total |
|----------|-------|------------|
| voters removed | 29 | 0.24% |
| histories changed | 0 | 0.00% |
| voters who moved | 72 | 0.60% |

## Definitions

### voters removed
- **Meaning**: Voter was in old DB but not in new DB.
- **Example**:
  ```
  Old DB: VoterId 12345 (active)
  New DB: VoterId 12345 (gone)
  → Counts as 1 "removed"
  ```

### histories changed
- **Meaning**: Existing voter with mismatched election history.
- **Example**:
  ```
  Old DB: 2024 General, In-Person
  New DB: 2024 General, Absentee
  → Counts as 1 "history changed"
  ```

### voters who moved
- **Meaning**: Voter changed residential address but kept same name and ID.
- **Conditions**:
  - Same `VoterId`
  - Exact same full name
  - At least one address field changed
- **Example**:
  ```
  Old DB: 123 Main St, Aitkin, 56431
  New DB: 456 Oak Ave, Aitkin, 56431
  → Counts as 1 "moved"
  ```
```

---

## How It Works

1. **Attach old DB** as `db_old`
2. **For each county**:
   - Query **last 5 elections** (by date) in new DB
   - Compare `election_history` and `voters` tables
   - Detect **removed**, **changed**, **moved**
3. **Generate CSVs + MDs**

---

## Database Schema (Expected)

```sql
-- voters
VoterId, FirstName, MiddleName, LastName, CountyCode,
HouseNumber, StreetName, UnitType, UnitNumber, City, ZipCode

-- election_history
VoterId, ElectionDate, ElectionDescription, VotingMethod
```

---

## Counties Supported

87 Minnesota counties (01–87) — full list in script.

---

## License

MIT © 2025
```

---

**Copy this into `README.md` and push to GitHub.**  
**Ready for public use.**
```
