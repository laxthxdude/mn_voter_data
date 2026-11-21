#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write data-quality reports for a Minnesota voter SQLite database.

The checks follow voter_data_anomaly_reports.md. A few of the draft queries
are adjusted so they match how this extract actually works:

- ZipCode is sometimes ZIP+4 (55302-3473). The first five digits are tested
  against the Minnesota range 55001-56763. A string comparison of the raw
  value mislabels those rows.
- DOBYear is a year, not a birthday. Age is election year minus birth year,
  so it can be off by one year. Voting in the year the person turns 18 is
  not flagged; that is when a 17-year-old may vote in a Minnesota primary.
- Election history has no unique key, and the source files repeat some rows.
  Duplicate votes are split into one voting method (a repeated line) and
  more than one method (a stronger conflict). The table lists those methods.

The database is opened read-only. Output is a Markdown report, an HTML
report, and one CSV per finding. Fuzzy name matching is not part of this
script: the voter file has one current address per VoterId, so duplicate
names are exact first name, middle name, last name, and birth year.
"""

import argparse
import csv
import heapq
import html
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DISPLAY_LIMIT = 25
CSV_LIMIT = 5000
MN_ZIP_LOW = 55001
MN_ZIP_HIGH = 56763
YOUNG_AGE = 18
OLD_AGE = 110
RECENT_YEARS = 4
VOTING_METHODS = ("A", "E", "M", "N", "P")


class Filters:
    def __init__(self, county, year, congressional=None, cd_label=None, senate=None, sd_label=None, election=None):
        self.county = county
        self.year = year
        self.congressional = congressional
        self.cd_label = cd_label
        self.senate = senate
        self.sd_label = sd_label
        self.election = election

    @property
    def limits_voters(self):
        return bool(self.county or self.congressional or self.senate)

    def describe(self):
        parts = []
        if self.county:
            parts.append(f"county {self.county}")
        if self.cd_label:
            parts.append(self.cd_label)
        if self.sd_label:
            parts.append(self.sd_label)
        if self.election:
            parts.append(f"election {self.election}")
        elif self.year:
            parts.append(f"election year {self.year}")
        return ", ".join(parts) if parts else "none"

    def _scope_names(self):
        names = []
        if self.county:
            names.append("county")
        if self.congressional:
            names.append("congressional district")
        if self.senate:
            names.append("senate district")
        return names

    def scope_omitted(self):
        """Why a check that needs a voter row was skipped, or None."""
        names = self._scope_names()
        if not names:
            return None
        if len(names) == 1:
            joined = names[0]
        elif len(names) == 2:
            joined = f"{names[0]} and {names[1]}"
        else:
            joined = ", ".join(names[:-1]) + f", and {names[-1]}"
        return f"not computed for a {joined} filter"

    def election_clauses(self, election="eh", voter="v"):
        clauses, params = [], []
        if self.county:
            clauses.append(f"{voter}.CountyCode = ?")
            params.append(self.county)
        if self.congressional:
            clauses.append(f"{voter}.Congressional = ?")
            params.append(self.congressional)
        if self.senate:
            clauses.append(f"{voter}.StateSen = ?")
            params.append(self.senate)
        date_clauses, date_params = self.history_date_clauses(election)
        return clauses + date_clauses, params + date_params

    def history_date_clauses(self, election="eh"):
        """Limit history rows to one election date, or to one calendar year."""
        if self.election:
            return [f"{election}.ElectionDate = ?"], [self.election]
        if self.year:
            return [
                f"{election}.ElectionDate >= ?",
                f"{election}.ElectionDate < ?",
            ], [f"{self.year:04d}-01-01", f"{self.year + 1:04d}-01-01"]
        return [], []

    def voter_clauses(self, alias=""):
        prefix = f"{alias}." if alias else ""
        clauses, params = [], []
        if self.county:
            clauses.append(f"{prefix}CountyCode = ?")
            params.append(self.county)
        if self.congressional:
            clauses.append(f"{prefix}Congressional = ?")
            params.append(self.congressional)
        if self.senate:
            clauses.append(f"{prefix}StateSen = ?")
            params.append(self.senate)
        return clauses, params


def where(clauses):
    if not clauses:
        return ""
    return " WHERE " + " AND ".join(clauses)


def comma(value):
    if value is None:
        return ""
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def md_cell(value):
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", "")


def html_cell(value):
    text = "" if value is None else str(value)
    return html.escape(text)


class Section:
    def __init__(self, key, title, why, notes, summary, columns, rows, csv_note=""):
        self.key = key
        self.title = title
        self.why = why
        self.notes = notes
        self.summary = summary
        self.columns = columns
        self.rows = rows
        self.csv_note = csv_note


def connect(db_path):
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA cache_size=-262144")
    conn.execute("PRAGMA temp_store=FILE")
    return conn


def require_schema(conn):
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = {"voters", "election_history"} - tables
    if missing:
        raise SystemExit(f"Database is missing table(s): {', '.join(sorted(missing))}")


def find_database(explicit):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"Database not found: {path}")
        return path
    script_dir = Path(__file__).resolve().parent
    candidates = [
        path for path in script_dir.glob("*.db")
        if path.is_file() and path.stat().st_size > 0
    ]
    if not candidates:
        raise SystemExit(
            "No SQLite database found next to this script. Pass --db PATH."
        )
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


_HEAP_SEQ = 0


def keep_largest(heap, limit, key, row):
    """Keep the `limit` rows with the greatest `key` tuples.

    A sequence number breaks ties so two equal keys never compare the row
    dicts, which Python 3 refuses to order.
    """
    global _HEAP_SEQ
    if limit <= 0:
        return
    _HEAP_SEQ += 1
    item = (key, _HEAP_SEQ, row)
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def sorted_heap(heap):
    ordered = sorted(heap, key=lambda item: (item[0], item[1]), reverse=True)
    return [row for _key, _seq, row in ordered]


def display_span(start, end):
    if not start and not end:
        return "none"
    return f"{start or 'none'} to {end or 'none'}"


def zero_counts(row):
    """SUM() over zero rows is NULL. Counts in this report should read as 0."""
    facts = dict(row)
    for key, value in list(facts.items()):
        if key in ("min_date", "max_date"):
            continue
        facts[key] = int(value or 0)
    return facts


def overview(conn, filters):
    voter_where, voter_params = filters.voter_clauses()
    voters = conn.execute(
        f"SELECT COUNT(*) AS n, MIN(RegistrationDate) AS min_reg, "
        f"MAX(RegistrationDate) AS max_reg, MIN(DOBYear) AS min_dob, "
        f"MAX(DOBYear) AS max_dob FROM voters{where(voter_where)}",
        voter_params,
    ).fetchone()
    election_where, election_params = filters.election_clauses()
    join = " JOIN voters v ON v.VoterId = eh.VoterId" if filters.limits_voters else ""
    elections = conn.execute(
        f"SELECT COUNT(*) AS n, MIN(eh.ElectionDate) AS min_date, "
        f"MAX(eh.ElectionDate) AS max_date "
        f"FROM election_history eh{join}{where(election_where)}",
        election_params,
    ).fetchone()
    return {
        "voters": voters["n"],
        "min_reg": voters["min_reg"],
        "max_reg": voters["max_reg"],
        "min_dob": voters["min_dob"],
        "max_dob": voters["max_dob"],
        "elections": elections["n"],
        "min_election": elections["min_date"],
        "max_election": elections["max_date"],
    }


def scan_election_facts(conn, filters):
    """One pass over election history for the counts that do not need groups."""
    clauses, params = filters.election_clauses()
    if filters.county:
        clauses = list(clauses)
    sql = f"""
        SELECT
          COUNT(*) AS election_rows,
          SUM(CASE WHEN v.VoterId IS NULL THEN 1 ELSE 0 END) AS orphan_rows,
          COUNT(DISTINCT CASE WHEN v.VoterId IS NULL THEN eh.VoterId END) AS orphan_ids,
          SUM(CASE WHEN v.DOBYear IS NOT NULL
                    AND CAST(strftime('%Y', eh.ElectionDate) AS INTEGER) < v.DOBYear
                   THEN 1 ELSE 0 END) AS before_birth_rows,
          COUNT(DISTINCT CASE WHEN v.DOBYear IS NOT NULL
                    AND CAST(strftime('%Y', eh.ElectionDate) AS INTEGER) < v.DOBYear
                    THEN eh.VoterId END) AS before_birth_voters,
          SUM(CASE WHEN v.DOBYear IS NOT NULL
                    AND CAST(strftime('%Y', eh.ElectionDate) AS INTEGER) = v.DOBYear
                   THEN 1 ELSE 0 END) AS birth_year_rows,
          COUNT(DISTINCT CASE WHEN v.DOBYear IS NOT NULL
                    AND CAST(strftime('%Y', eh.ElectionDate) AS INTEGER) = v.DOBYear
                    THEN eh.VoterId END) AS birth_year_voters,
          SUM(CASE WHEN v.PermanentAbsentee = 'X' AND eh.VotingMethod = 'P'
                   THEN 1 ELSE 0 END) AS in_person_rows,
          COUNT(DISTINCT CASE WHEN v.PermanentAbsentee = 'X' AND eh.VotingMethod = 'P'
                    THEN eh.VoterId END) AS in_person_voters,
          SUM(CASE WHEN eh.VotingMethod IS NULL OR TRIM(eh.VotingMethod) = ''
                     OR eh.VotingMethod NOT IN ('A', 'E', 'M', 'N', 'P')
                   THEN 1 ELSE 0 END) AS bad_method_rows,
          SUM(CASE WHEN eh.ElectionDate = '1993-01-01' THEN 1 ELSE 0 END) AS date_1993_rows,
          MIN(eh.ElectionDate) AS min_date,
          MAX(eh.ElectionDate) AS max_date
        FROM election_history eh
        LEFT JOIN voters v ON v.VoterId = eh.VoterId
        {where(clauses)}
    """
    return zero_counts(conn.execute(sql, params).fetchone())


def duplicate_votes(conn, filters, display_limit, _csv_limit):
    clauses, params = filters.election_clauses()
    join = ""
    if filters.limits_voters:
        join = " JOIN voters v ON v.VoterId = eh.VoterId"
    sql = f"""
        SELECT eh.VoterId AS VoterId,
               eh.ElectionDate AS ElectionDate,
               eh.ElectionDescription AS ElectionDescription,
               COUNT(*) AS vote_count,
               GROUP_CONCAT(DISTINCT COALESCE(eh.VotingMethod, '')
                            ORDER BY COALESCE(eh.VotingMethod, '')) AS method_list
        FROM election_history eh
        {join}
        {where(clauses)}
        GROUP BY eh.VoterId, eh.ElectionDate, eh.ElectionDescription
        HAVING vote_count > 1
    """
    groups = 0
    extra_rows = 0
    same_method = 0
    mixed_method = 0
    rows = []
    for row in conn.execute(sql, params):
        groups += 1
        extra_rows += row["vote_count"] - 1
        methods = (row["method_list"] or "").split(",")
        if len(methods) == 1:
            same_method += 1
        else:
            mixed_method += 1
        rows.append({
            "VoterId": row["VoterId"],
            "ElectionDate": row["ElectionDate"],
            "ElectionDescription": row["ElectionDescription"],
            "VoteCount": row["vote_count"],
            "VotingMethods": ", ".join(methods),
        })
    rows.sort(
        key=lambda item: (
            item["ElectionDate"] or "",
            item["VoteCount"],
            item["VoterId"] or 0,
            item["ElectionDescription"] or "",
        ),
        reverse=True,
    )
    if rows:
        ids = sorted({row["VoterId"] for row in rows})
        names = _names_for(conn, ids)
        for row in rows:
            info = names.get(row["VoterId"], {})
            row["FirstName"] = info.get("FirstName", "")
            row["LastName"] = info.get("LastName", "")
            row["ZipCode"] = info.get("ZipCode", "")
    notes = [
        "A group is one voter, one election date, and one election description.",
        "VotingMethods lists each distinct method on that election, separated by a comma. One method means the source file repeated a line. More than one method is the stronger conflict.",
        "Methods are A absentee, E early, M mail, N unknown, and P in person.",
        "The history file has no unique key, so repeated lines are stored as repeated rows.",
        "The CSV includes every matching group. The row cap does not apply to this file. The table shows the first rows of that same order.",
    ]
    summary = [
        ("Groups with more than one row", comma(groups)),
        ("Extra rows beyond one per group", comma(extra_rows)),
        ("Groups with one voting method", comma(same_method)),
        ("Groups with more than one method", comma(mixed_method)),
    ]
    columns = [
        "VoterId", "FirstName", "LastName", "ZipCode", "ElectionDate",
        "ElectionDescription", "VoteCount", "VotingMethods",
    ]
    return _section(
        "01_duplicate_votes",
        "Duplicate votes in the same election",
        "A voter should have one history row for each election.",
        notes, summary, columns, rows, display_limit, groups,
        "most recent election dates, then largest repeat counts",
    )


def votes_before_birth(conn, filters, facts, display_limit, csv_limit):
    clauses, params = filters.election_clauses()
    clauses.append("v.DOBYear IS NOT NULL")
    clauses.append(
        "CAST(strftime('%Y', eh.ElectionDate) AS INTEGER) <= v.DOBYear"
    )
    sql = f"""
        SELECT v.VoterId, v.FirstName, v.LastName, v.DOBYear, v.ZipCode,
               eh.ElectionDate, eh.ElectionDescription,
               (v.DOBYear - CAST(strftime('%Y', eh.ElectionDate) AS INTEGER)) AS YearsBeforeBirth
        FROM election_history eh
        JOIN voters v ON v.VoterId = eh.VoterId
        {where(clauses)}
        ORDER BY YearsBeforeBirth DESC, eh.ElectionDate
        LIMIT ?
    """
    rows = [dict(row) for row in conn.execute(sql, params + [csv_limit])]
    notes = [
        "Birth year is the only date of birth in the file. A value of 1 or more in YearsBeforeBirth means the election was in an earlier calendar year than the birth year.",
        "A value of 0 means the election was in the birth year. That is not in the draft query, which uses a strict less-than, but a person cannot vote in the year they were born.",
    ]
    summary = [
        ("Rows in a year before the birth year", comma(facts["before_birth_rows"])),
        ("Voters with a row before their birth year", comma(facts["before_birth_voters"])),
        ("Rows in the birth year", comma(facts["birth_year_rows"])),
        ("Voters with a row in their birth year", comma(facts["birth_year_voters"])),
    ]
    columns = [
        "VoterId", "FirstName", "LastName", "DOBYear", "ZipCode",
        "ElectionDate", "ElectionDescription", "YearsBeforeBirth",
    ]
    total = (facts["before_birth_rows"] or 0) + (facts["birth_year_rows"] or 0)
    return _section(
        "02_votes_before_birth",
        "Votes in or before DOBYear",
        "An election year earlier than DOBYear is impossible. An election in the DOBYear is also impossible.",
        notes, summary, columns, rows, display_limit, total,
        "largest gaps",
    )


def registration_before_birth(conn, filters, display_limit, csv_limit):
    clauses, params = filters.voter_clauses()
    clauses.append("DOBYear IS NOT NULL")
    clauses.append("CAST(strftime('%Y', RegistrationDate) AS INTEGER) < DOBYear")
    count = conn.execute(
        f"SELECT COUNT(*) AS n FROM voters{where(clauses)}",
        params,
    ).fetchone()["n"]
    sql = f"""
        SELECT VoterId, FirstName, LastName, DOBYear, RegistrationDate, ZipCode, CountyCode
        FROM voters
        {where(clauses)}
        ORDER BY RegistrationDate
        LIMIT ?
    """
    rows = [dict(row) for row in conn.execute(sql, params + [csv_limit])]
    notes = [
        "This is the registration field itself, not a history row. A registration year before the birth year cannot be a later renewal.",
        "One known placeholder in this kind of extract is 1850-01-01.",
    ]
    summary = [("Voters with registration year before birth year", comma(count))]
    columns = [
        "VoterId", "FirstName", "LastName", "DOBYear", "RegistrationDate",
        "ZipCode", "CountyCode",
    ]
    return _section(
        "03_registration_before_birth",
        "Registration dated before the birth year",
        "The registration date on the voter record should not fall in a year before DOBYear.",
        notes, summary, columns, rows, display_limit, count,
        "earliest registration dates",
    )


def identity_duplicates(conn, filters, display_limit, csv_limit):
    clauses, params = filters.voter_clauses()
    clauses.extend([
        "DOBYear IS NOT NULL",
        "FirstName <> ''",
        "LastName <> ''",
    ])
    sql = f"""
        SELECT FirstName, LastName, TRIM(COALESCE(MiddleName, '')) AS MiddleName, DOBYear,
               COUNT(*) AS voter_ids,
               COUNT(DISTINCT ZipCode) AS zip_codes,
               COUNT(DISTINCT HouseNumber || '|' || StreetName || '|' || City
                     || '|' || substr(COALESCE(ZipCode, ''), 1, 5)) AS addresses
        FROM voters
        {where(clauses)}
        GROUP BY FirstName, LastName, TRIM(COALESCE(MiddleName, '')), DOBYear
        HAVING voter_ids > 1
    """
    name_groups = 0
    extra_ids = 0
    address_groups = 0
    name_heap = []
    address_heap = []
    for row in conn.execute(sql, params):
        name_groups += 1
        extra_ids += row["voter_ids"] - 1
        item = {
            "FirstName": row["FirstName"],
            "MiddleName": row["MiddleName"],
            "LastName": row["LastName"],
            "DOBYear": row["DOBYear"],
            "voter_ids": row["voter_ids"],
            "zip_codes": row["zip_codes"],
            "addresses": row["addresses"],
        }
        keep_largest(
            name_heap, csv_limit,
            (
                row["voter_ids"], row["addresses"], row["LastName"],
                row["FirstName"], row["MiddleName"], row["DOBYear"],
            ),
            item,
        )
        if row["addresses"] > 1:
            address_groups += 1
            keep_largest(
                address_heap, csv_limit,
                (
                    row["addresses"], row["voter_ids"], row["LastName"],
                    row["FirstName"], row["MiddleName"], row["DOBYear"],
                ),
                dict(item),
            )
    name_rows = sorted_heap(name_heap)
    address_rows = sorted_heap(address_heap)
    _attach_example_ids(conn, name_rows, filters)
    _attach_example_ids(conn, address_rows, filters)
    name_section = _section(
        "04_duplicate_names",
        "Possible duplicate registrations",
        "Same first name, middle name, last name, and birth year on more than one VoterId.",
        [
            "The middle name has to match exactly. A blank middle name matches only another blank middle name, and an initial does not match a full middle name.",
            "Common names still collide. This is a candidate list, not a conclusion that two rows are the same person.",
            "Blank first or last names are excluded so empty records do not form one giant group.",
            "A year or election-date filter does not apply here. There is no election date on the voter row.",
        ],
        [
            ("Full name and birth-year groups with more than one VoterId", comma(name_groups)),
            ("Extra VoterIds beyond one per group", comma(extra_ids)),
        ],
        ["FirstName", "MiddleName", "LastName", "DOBYear", "voter_ids", "zip_codes", "addresses", "example_ids"],
        name_rows, display_limit, name_groups,
        "largest groups",
    )
    address_section = _section(
        "05_same_name_multiple_addresses",
        "Same first name, middle name, last name, and birth year at more than one address",
        "The voter file has one current address per VoterId, not an address history. Different addresses on the same full name and birth year are the available stand-in for an address change or a second registration.",
        [
            "This is the duplicate-name list restricted to groups whose house number, street, city, or ZIP differ.",
            "The middle name uses the same exact match as the duplicate-registration list.",
        ],
        [
            ("Groups with more than one address", comma(address_groups)),
        ],
        ["FirstName", "MiddleName", "LastName", "DOBYear", "voter_ids", "addresses", "zip_codes", "example_ids"],
        address_rows, display_limit, address_groups,
        "most distinct addresses",
    )
    return name_section, address_section


def _attach_example_ids(conn, rows, filters):
    """Add up to eight VoterIds for each retained name group."""
    if not rows:
        return
    grouped = {}
    for start in range(0, len(rows), 80):
        chunk = rows[start:start + 80]
        values = ",".join(["(?, ?, ?, ?)"] * len(chunk))
        params = []
        for row in chunk:
            params.extend([row["FirstName"], row["LastName"], row["MiddleName"], row["DOBYear"]])
        extra = []
        if filters.county:
            extra.append("CountyCode = ?")
            params.append(filters.county)
        if filters.congressional:
            extra.append("Congressional = ?")
            params.append(filters.congressional)
        if filters.senate:
            extra.append("StateSen = ?")
            params.append(filters.senate)
        extra_sql = (" AND " + " AND ".join(extra)) if extra else ""
        found = conn.execute(
            f"""
            SELECT VoterId, FirstName, LastName,
                   TRIM(COALESCE(MiddleName, '')) AS MiddleName, DOBYear
            FROM voters
            WHERE (FirstName, LastName, TRIM(COALESCE(MiddleName, '')), DOBYear)
                  IN (VALUES {values})
            {extra_sql}
            ORDER BY VoterId
            """,
            params,
        )
        for item in found:
            key = (item["FirstName"], item["LastName"], item["MiddleName"], item["DOBYear"])
            bucket = grouped.setdefault(key, [])
            if len(bucket) < 8:
                bucket.append(str(item["VoterId"]))
    for row in rows:
        key = (row["FirstName"], row["LastName"], row["MiddleName"], row["DOBYear"])
        row["example_ids"] = ", ".join(grouped.get(key, []))


def _names_for(conn, voter_ids):
    if not voter_ids:
        return {}
    found = {}
    for start in range(0, len(voter_ids), 400):
        chunk = voter_ids[start:start + 400]
        placeholders = ",".join(["?"] * len(chunk))
        for row in conn.execute(
            f"SELECT VoterId, FirstName, LastName, ZipCode FROM voters "
            f"WHERE VoterId IN ({placeholders})",
            chunk,
        ):
            found[row["VoterId"]] = {
                "FirstName": row["FirstName"],
                "LastName": row["LastName"],
                "ZipCode": row["ZipCode"],
            }
    return found


def activity_and_age(conn, filters, facts, display_limit, csv_limit):
    clauses, params = filters.election_clauses()
    sql = f"""
        SELECT v.VoterId AS VoterId, v.FirstName AS FirstName, v.LastName AS LastName,
               v.ZipCode AS ZipCode, v.DOBYear AS DOBYear, v.CountyCode AS CountyCode,
               COUNT(*) AS election_rows,
               MIN(eh.ElectionDate) AS first_vote,
               MAX(eh.ElectionDate) AS last_vote,
               MIN(CASE WHEN v.DOBYear IS NOT NULL
                   THEN CAST(strftime('%Y', eh.ElectionDate) AS INTEGER) - v.DOBYear END)
                   AS youngest_age,
               MAX(CASE WHEN v.DOBYear IS NOT NULL
                   THEN CAST(strftime('%Y', eh.ElectionDate) AS INTEGER) - v.DOBYear END)
                   AS oldest_age
        FROM election_history eh
        JOIN voters v ON v.VoterId = eh.VoterId
        {where(clauses)}
        GROUP BY v.VoterId, v.FirstName, v.LastName, v.ZipCode, v.DOBYear, v.CountyCode
    """
    max_date = facts.get("max_date") or "0000-01-01"
    as_of_year = int(max_date[:4]) if max_date and max_date[:4].isdigit() else 0
    recent_floor = as_of_year - RECENT_YEARS
    active_heap = []
    young_heap = []
    old_heap = []
    voted_under_18 = 0
    voted_over_110 = 0
    current_under_18 = 0
    current_over_110 = 0
    current_over_110_recent = 0
    flagged_age = 0
    voters_with_history = 0
    for row in conn.execute(sql, params):
        voters_with_history += 1
        active = {
            "VoterId": row["VoterId"],
            "FirstName": row["FirstName"],
            "LastName": row["LastName"],
            "ZipCode": row["ZipCode"],
            "election_rows": row["election_rows"],
            "first_vote": row["first_vote"],
            "last_vote": row["last_vote"],
        }
        keep_largest(
            active_heap, csv_limit,
            (row["election_rows"], row["last_vote"] or "", row["VoterId"] or 0),
            active,
        )
        dob = row["DOBYear"]
        if dob is None or as_of_year == 0:
            continue
        current_age = as_of_year - dob
        youngest = row["youngest_age"]
        oldest = row["oldest_age"]
        last_year = int(row["last_vote"][:4]) if row["last_vote"] else 0
        flagged_young = youngest is not None and youngest < YOUNG_AGE
        flagged_old_vote = oldest is not None and oldest > OLD_AGE
        flagged_current_young = current_age < YOUNG_AGE
        flagged_current_old = current_age > OLD_AGE
        if flagged_young:
            voted_under_18 += 1
        if flagged_old_vote:
            voted_over_110 += 1
        if flagged_current_young:
            current_under_18 += 1
        if flagged_current_old:
            current_over_110 += 1
            if last_year >= recent_floor:
                current_over_110_recent += 1
        if flagged_young or flagged_old_vote or flagged_current_young or flagged_current_old:
            flagged_age += 1
        detail = {
            "VoterId": row["VoterId"],
            "FirstName": row["FirstName"],
            "LastName": row["LastName"],
            "DOBYear": dob,
            "ZipCode": row["ZipCode"],
            "youngest_age": youngest,
            "oldest_age": oldest,
            "approx_age": current_age,
            "latest_vote": row["last_vote"],
        }
        if flagged_young or flagged_current_young:
            keep_largest(
                young_heap, csv_limit,
                (-(youngest if youngest is not None else current_age), row["VoterId"] or 0),
                detail,
            )
        if flagged_old_vote or flagged_current_old:
            keep_largest(
                old_heap, csv_limit,
                (max(oldest or 0, current_age), row["VoterId"] or 0),
                detail,
            )
    active_section = _section(
        "06_most_active_voters",
        "Most active voters",
        "Voters with the most history rows. The count is rows, so a repeated election line increases it. Compare with the duplicate-vote report before treating a high number as turnout.",
        [
            f"Age figures elsewhere in this report use {as_of_year} as the latest election year in the filtered history.",
        ],
        [
            ("Voters with at least one history row", comma(voters_with_history)),
        ],
        ["VoterId", "FirstName", "LastName", "ZipCode", "election_rows", "first_vote", "last_vote"],
        sorted_heap(active_heap), display_limit, voters_with_history,
        "highest row counts",
    )
    age_rows = _merge_age_rows(sorted_heap(young_heap), sorted_heap(old_heap))
    age_section = _section(
        "07_implausible_age",
        "Votes at an implausible age",
        "Age is election year minus DOBYear. Under 18 means the election was before the year the person turns 18. Over 110 uses the same year difference.",
        [
            "DOBYear can put the age one year high or low. Someone who turns 18 in the election year is not listed.",
            "Minnesota lets some 17-year-olds vote in a primary when they will be 18 by the general election. That case falls in the year they turn 18, so this cutoff leaves it out.",
            f"Current age uses {as_of_year}, the latest election year in this run, not the year the script happens to run.",
            f"A recent vote means the latest vote is in {recent_floor} or later.",
        ],
        [
            ("Voters with a history row before the year they turn 18", comma(voted_under_18)),
            ("Voters with a history row at age over 110", comma(voted_over_110)),
            ("Voters currently under 18 who have a history row", comma(current_under_18)),
            ("Voters currently over 110 who have a history row", comma(current_over_110)),
            (f"Of those, latest vote in {recent_floor} or later", comma(current_over_110_recent)),
        ],
        ["VoterId", "FirstName", "LastName", "DOBYear", "ZipCode",
         "youngest_age", "oldest_age", "approx_age", "latest_vote"],
        age_rows, display_limit, flagged_age,
        "most extreme ages",
    )
    return active_section, age_section, voters_with_history


def _merge_age_rows(young_rows, old_rows):
    merged = []
    seen = set()
    for row in young_rows + old_rows:
        if row["VoterId"] in seen:
            continue
        seen.add(row["VoterId"])
        merged.append(row)
    return merged


def zip_codes(conn, filters, display_limit, csv_limit):
    clauses, params = filters.voter_clauses()
    kind_sql = """
        CASE
          WHEN ZipCode IS NULL OR ZipCode = '' THEN 'blank'
          WHEN substr(ZipCode, 1, 5) NOT GLOB '[0-9][0-9][0-9][0-9][0-9]' THEN 'malformed'
          WHEN CAST(substr(ZipCode, 1, 5) AS INTEGER) BETWEEN 55001 AND 56763 THEN
            CASE
              WHEN length(ZipCode) = 5
                OR (length(ZipCode) = 10 AND substr(ZipCode, 6, 1) = '-'
                    AND substr(ZipCode, 7) GLOB '[0-9][0-9][0-9][0-9]')
              THEN 'minnesota'
              ELSE 'minnesota_nonstandard'
            END
          ELSE 'outside_minnesota'
        END
    """
    summary_rows = conn.execute(
        f"""
        SELECT kind, COUNT(*) AS voters, COUNT(DISTINCT ZipCode) AS codes
        FROM (SELECT ZipCode, {kind_sql} AS kind FROM voters{where(clauses)})
        GROUP BY kind
        """,
        params,
    ).fetchall()
    by_kind = {row["kind"]: row for row in summary_rows}
    detail = [
        dict(row) for row in conn.execute(
            f"""
            SELECT kind, ZipCode, COUNT(*) AS voters
            FROM (SELECT ZipCode, {kind_sql} AS kind FROM voters{where(clauses)})
            WHERE kind <> 'minnesota'
            GROUP BY kind, ZipCode
            ORDER BY voters DESC
            LIMIT ?
            """,
            params + [csv_limit],
        )
    ]
    outside = by_kind.get("outside_minnesota")
    malformed = by_kind.get("malformed")
    blank = by_kind.get("blank")
    odd = by_kind.get("minnesota_nonstandard")
    group_count = conn.execute(
        f"""
        SELECT COUNT(*) AS n FROM (
          SELECT 1
          FROM (SELECT ZipCode, {kind_sql} AS kind FROM voters{where(clauses)})
          WHERE kind <> 'minnesota'
          GROUP BY kind, ZipCode
        )
        """,
        params,
    ).fetchone()["n"]
    summary = [
        ("Blank ZIP", comma(blank["voters"] if blank else 0)),
        ("Malformed ZIP", comma(malformed["voters"] if malformed else 0)),
        ("Outside Minnesota 55001-56763", comma(outside["voters"] if outside else 0)),
        ("Distinct outside ZIP codes", comma(outside["codes"] if outside else 0)),
        ("Minnesota ZIP with an unusual suffix", comma(odd["voters"] if odd else 0)),
    ]
    return _section(
        "08_zip_codes",
        "Residence ZIP codes outside Minnesota or malformed",
        "The residence ZIP is checked on its first five digits. ZIP+4 values such as 55401-1234 stay in Minnesota when those digits are in range. Mailing ZIP is a different field and is not part of this check.",
        [
            "A few residence ZIPs just outside the range are real border codes (North Dakota and South Dakota). They are still outside the Minnesota USPS range.",
            "A year or election-date filter does not apply to this voter-record check.",
        ],
        summary,
        ["kind", "ZipCode", "voters"],
        detail, display_limit, group_count,
        "largest ZIP counts",
    )


def orphans_and_methods(conn, filters, facts, display_limit, csv_limit):
    orphan_rows = []
    orphan_columns = []
    omitted = filters.scope_omitted()
    orphan_notes = [
        "This check is statewide. A county, congressional district, or senate district filter drops these rows because they have no voter record.",
    ]
    orphan_total = 0
    if omitted is None:
        clauses = ["v.VoterId IS NULL"]
        params = []
        date_clauses, date_params = filters.history_date_clauses()
        clauses.extend(date_clauses)
        params.extend(date_params)
        orphan_rows = [
            dict(row) for row in conn.execute(
                f"""
                SELECT eh.VoterId, eh.ElectionDate, eh.ElectionDescription, eh.VotingMethod
                FROM election_history eh
                LEFT JOIN voters v ON v.VoterId = eh.VoterId
                {where(clauses)}
                LIMIT ?
                """,
                params + [csv_limit],
            )
        ]
        orphan_columns = ["VoterId", "ElectionDate", "ElectionDescription", "VotingMethod"]
        orphan_notes = ["These VoterIds cannot be joined to a name or address."]
        if filters.election:
            orphan_notes.append("The count and the sample use the election-date filter.")
        elif filters.year:
            orphan_notes.append("The count and the sample use the election-year filter.")
        orphan_total = facts["orphan_rows"]
    orphan_section = _section(
        "09_orphaned_elections",
        "Election rows with no voter record",
        "A history row whose VoterId is not in the voter table.",
        orphan_notes,
        [
            ("Orphaned history rows", omitted or comma(facts["orphan_rows"])),
            ("Distinct missing VoterIds", omitted or comma(facts["orphan_ids"])),
        ],
        orphan_columns,
        orphan_rows, display_limit, orphan_total,
        "first matching rows",
    )
    clauses, params = filters.election_clauses()
    clauses.append("v.PermanentAbsentee = 'X'")
    clauses.append("eh.VotingMethod = 'P'")
    sample = [
        dict(row) for row in conn.execute(
            f"""
            SELECT v.VoterId, v.FirstName, v.LastName, v.ZipCode,
                   eh.ElectionDate, eh.ElectionDescription, eh.VotingMethod
            FROM election_history eh
            JOIN voters v ON v.VoterId = eh.VoterId
            {where(clauses)}
            ORDER BY eh.ElectionDate DESC
            """,
            params,
        )
    ]
    method_section = _section(
        "10_permanent_absentee_in_person",
        "Permanent-absentee flag with an in-person vote",
        "PermanentAbsentee is X for voters the export marks as permanent absentee. VotingMethod P is an in-person vote. A permanent absentee voter is still allowed to vote in person, so this is a pattern to review, not a conflict by itself.",
        [
            "Voting methods in this extract are A absentee, E early, M mail, N unknown, and P in person.",
            f"History rows whose method is outside that set: {comma(facts['bad_method_rows'])}.",
            "The CSV includes every matching in-person row. The row cap does not apply to this file. The table shows the first rows of that same order.",
        ],
        [
            ("In-person rows for permanent-absentee voters", comma(facts["in_person_rows"])),
            ("Distinct voters", comma(facts["in_person_voters"])),
            ("Rows with an unexpected voting method", comma(facts["bad_method_rows"])),
        ],
        ["VoterId", "FirstName", "LastName", "ZipCode", "ElectionDate",
         "ElectionDescription", "VotingMethod"],
        sample, display_limit, facts["in_person_rows"],
        "latest in-person rows",
    )
    return orphan_section, method_section


def completeness(conn, filters, overview_stats, voters_with_history):
    clauses, params = filters.voter_clauses()
    row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS voters,
          SUM(CASE WHEN FirstName IS NULL OR TRIM(FirstName) = '' THEN 1 ELSE 0 END) AS blank_first,
          SUM(CASE WHEN LastName IS NULL OR TRIM(LastName) = '' THEN 1 ELSE 0 END) AS blank_last,
          SUM(CASE WHEN DOBYear IS NULL THEN 1 ELSE 0 END) AS missing_dob,
          SUM(CASE WHEN FirstName IS NOT NULL AND TRIM(FirstName) <> ''
                    AND length(TRIM(FirstName)) <= 1 THEN 1 ELSE 0 END) AS short_first
        FROM voters
        {where(clauses)}
        """,
        params,
    ).fetchone()
    no_history = None
    if not filters.year and not filters.election:
        exists = "SELECT 1 FROM election_history eh WHERE eh.VoterId = voters.VoterId"
        no_history = conn.execute(
            f"SELECT COUNT(*) AS n FROM voters{where(clauses + [f'NOT EXISTS ({exists})'])}",
            params,
        ).fetchone()["n"]
    summary = [
        ("Voters in this filter", comma(row["voters"] or 0)),
        ("Blank first name", comma(row["blank_first"] or 0)),
        ("Blank last name", comma(row["blank_last"] or 0)),
        ("First name of one letter", comma(row["short_first"] or 0)),
        ("Missing birth year", comma(row["missing_dob"] or 0)),
        ("Birth year range", display_span(overview_stats["min_dob"], overview_stats["max_dob"])),
        ("Registration date range", display_span(overview_stats["min_reg"], overview_stats["max_reg"])),
    ]
    notes = [
        "A short first name or a missing birth year is a data-entry quality flag, not evidence about the registration.",
    ]
    if no_history is None:
        summary.append(("Voters with no history rows", "not computed when an election year or election date is selected"))
        notes.append(
            "The no-history count is omitted because an election year or election date only sees part of each voter's history."
        )
    else:
        summary.append(("Voters with no history rows", comma(no_history)))
        notes.append(
            "Voters with no history rows are current registrations that have no joined election line in this extract."
        )
    summary.append(("Voters with at least one history row", comma(voters_with_history)))
    return _section(
        "11_completeness",
        "Completeness of the voter record",
        "Blank names, missing birth years, and registrations that never join to a history row.",
        notes, summary, [], [], 0, 0, "",
    )


def _section(key, title, why, notes, summary, columns, rows, display_limit, total, order_note):
    shown = rows[:display_limit]
    csv_note = ""
    if total and len(rows) < total:
        csv_note = (
            f"The CSV has {len(rows):,} of {comma(total)} rows, ordered by {order_note}."
        )
    elif rows:
        csv_note = f"The CSV has {len(rows):,} rows, ordered by {order_note}."
    return Section(key, title, why, notes, summary, columns, shown, csv_note), rows


def write_csv(directory, section, all_rows):
    if not section.columns or not all_rows:
        return None
    path = directory / f"{section.key}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=section.columns, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow({column: row.get(column, "") for column in section.columns})
    return path


def render_markdown(path, db_path, filters, generated, overview_stats, facts, sections):
    lines = [
        "# Voter data anomaly report",
        "",
        "These checks look for inconsistent or incomplete records in the Minnesota voter extract. Most hits are data entry, a repeated line in the history file, or two different people with the same name. They are not, by themselves, evidence of fraud.",
        "",
        f"- Database: `{Path(db_path).name}`",
        f"- Generated: {generated}",
        f"- Filters: {filters.describe()}",
        f"- Voters: {comma(overview_stats['voters'])}",
        f"- Election rows: {comma(overview_stats['elections'])}",
        f"- Election dates: {display_span(overview_stats['min_election'], overview_stats['max_election'])}",
        "",
    ]
    if facts.get("date_1993_rows"):
        lines.append(
            f"Election rows dated 1993-01-01: {comma(facts['date_1993_rows'])}. "
            "That is the oldest history date in this kind of extract, and January 1 is sometimes a placeholder rather than an election day."
        )
        lines.append("")
    if filters.election:
        lines.append("The election-date filter applies to history checks. It does not change the name, address, ZIP, or completeness checks.")
        lines.append("")
    elif filters.year:
        lines.append("The election-year filter applies to history checks. It does not change the name, address, ZIP, or completeness checks.")
        lines.append("")
    for section, _rows in sections:
        lines.append(f"## {section.title}")
        lines.append("")
        lines.append(section.why)
        lines.append("")
        for note in section.notes:
            lines.append(f"- {note}")
        if section.notes:
            lines.append("")
        for label, value in section.summary:
            lines.append(f"- {label}: {value}")
        lines.append("")
        if section.columns and section.rows:
            lines.append("| " + " | ".join(section.columns) + " |")
            lines.append("| " + " | ".join("---" for _ in section.columns) + " |")
            for row in section.rows:
                lines.append("| " + " | ".join(md_cell(row.get(column, "")) for column in section.columns) + " |")
            lines.append("")
        elif section.columns:
            lines.append("None found.")
            lines.append("")
        if section.csv_note:
            lines.append(section.csv_note)
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_html(path, db_path, filters, generated, overview_stats, facts, sections):
    parts = [
        "<!DOCTYPE html>",
        "<html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<title>Voter data anomaly report</title>",
        "<style>",
        "body{font-family:Georgia,serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#1c1c1c;line-height:1.45}",
        "h1,h2{font-weight:600} table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:0.92rem}",
        "th,td{border-bottom:1px solid #ccc;text-align:left;padding:0.35rem 0.5rem;vertical-align:top}",
        "th{background:#f4f1ea} .note{color:#333} .meta{background:#f7f7f5;padding:0.8rem 1rem}",
        "</style></head><body>",
        "<h1>Voter data anomaly report</h1>",
        "<p>These checks look for inconsistent or incomplete records. Most hits are data entry, a repeated history line, or two people with the same name. They are not, by themselves, evidence of fraud.</p>",
        "<div class=\"meta\">",
        f"<div>Database: {html_cell(Path(db_path).name)}</div>",
        f"<div>Generated: {html_cell(generated)}</div>",
        f"<div>Filters: {html_cell(filters.describe())}</div>",
        f"<div>Voters: {comma(overview_stats['voters'])}</div>",
        f"<div>Election rows: {comma(overview_stats['elections'])}</div>",
        f"<div>Election dates: {html_cell(display_span(overview_stats['min_election'], overview_stats['max_election']))}</div>",
        "</div>",
    ]
    if facts.get("date_1993_rows"):
        parts.append(
            f"<p>Election rows dated 1993-01-01: {comma(facts['date_1993_rows'])}. "
            "January 1 at the start of the history file is sometimes a placeholder.</p>"
        )
    for section, _rows in sections:
        parts.append(f"<h2>{html_cell(section.title)}</h2>")
        parts.append(f"<p>{html_cell(section.why)}</p>")
        if section.notes:
            parts.append("<ul class=\"note\">")
            for note in section.notes:
                parts.append(f"<li>{html_cell(note)}</li>")
            parts.append("</ul>")
        parts.append("<ul>")
        for label, value in section.summary:
            parts.append(f"<li>{html_cell(label)}: {html_cell(value)}</li>")
        parts.append("</ul>")
        if section.columns and section.rows:
            parts.append("<table><thead><tr>")
            for column in section.columns:
                parts.append(f"<th>{html_cell(column)}</th>")
            parts.append("</tr></thead><tbody>")
            for row in section.rows:
                parts.append("<tr>")
                for column in section.columns:
                    parts.append(f"<td>{html_cell(row.get(column, ''))}</td>")
                parts.append("</tr>")
            parts.append("</tbody></table>")
        elif section.columns:
            parts.append("<p>None found.</p>")
        if section.csv_note:
            parts.append(f"<p class=\"note\">{html_cell(section.csv_note)}</p>")
    parts.append("</body></html>")
    path.write_text("\n".join(parts), encoding="utf-8")


def parse_election_date(text):
    """Return an ISO election date, or None. Accepts YYYY-MM-DD and MM/DD/YYYY."""
    if text is None or not str(text).strip():
        return None
    raw = str(text).strip()
    parsed = None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if parsed is None or not 1900 <= parsed.year <= 2100:
        raise SystemExit("--election must be a date from 1900 through 2100, for example 2024-11-05 or 11/05/2024.")
    return parsed.strftime("%Y-%m-%d")


def take_district_flags(argv):
    """Remove --CD1 and --SD1 style flags. Those voter fields store the number."""
    source = list(sys.argv[1:] if argv is None else argv)
    kinds = {
        "CD": "congressional district",
        "SD": "senate district",
    }
    remaining = []
    found = {prefix: [] for prefix in kinds}
    for arg in source:
        match = re.fullmatch(r"--(CD|SD)(\d+)", arg, flags=re.IGNORECASE)
        if not match:
            remaining.append(arg)
            continue
        prefix = match.group(1).upper()
        number = int(match.group(2))
        if number < 1:
            raise SystemExit(f"Use a {kinds[prefix]} such as --{prefix}1.")
        found[prefix].append(number)
    selected = {}
    for prefix, kind in kinds.items():
        numbers = found[prefix]
        if len(numbers) > 1:
            labels = ", ".join(f"--{prefix}{number}" for number in numbers)
            raise SystemExit(f"Pass only one {kind}. Got {labels}.")
        if numbers:
            selected[prefix] = (f"{prefix}{numbers[0]}", str(numbers[0]))
    return selected, remaining


def main(argv=None):
    districts, argv = take_district_flags(argv)
    cd_label, congressional = districts.get("CD", (None, None))
    sd_label, senate = districts.get("SD", (None, None))
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a Minnesota voter SQLite database and write anomaly "
            "reports in Markdown, HTML, and CSV."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "congressional district:\n"
            "  --CD1, --CD2, --CD3, ...  voters whose Congressional field is that district.\n"
            "  --CD4 selects Congressional 4.\n"
            "\n"
            "senate district:\n"
            "  --SD1, --SD2, --SD3, ...  voters whose StateSen field is that district.\n"
            "  --SD41 selects StateSen 41.\n"
            "\n"
            "Pass only one congressional district and only one senate district. The two can be used together."
        ),
    )
    parser.add_argument("--db", help="SQLite database. Default: the newest non-empty .db next to this script.")
    parser.add_argument("--out", help="Output directory. Default: anomaly_reports next to this script.")
    parser.add_argument("--county", help="CountyCode to include, for example 27 or 02.")
    parser.add_argument("--year", type=int, help="Limit history checks to one election year, for example 2024.")
    parser.add_argument(
        "--election",
        help="Limit history checks to one election date, for example 2024-11-05 or 11/05/2024.",
    )
    parser.add_argument("--limit", type=int, default=DISPLAY_LIMIT, help="Rows to show in the Markdown and HTML tables.")
    parser.add_argument(
        "--csv-limit", type=int, default=CSV_LIMIT,
        help="Maximum rows to write in each CSV. The duplicate-vote and permanent-absentee CSVs include every match.",
    )
    args = parser.parse_args(argv)
    if args.limit < 1 or args.csv_limit < 1:
        raise SystemExit("--limit and --csv-limit must be at least 1.")
    if args.year is not None and not 1900 <= args.year <= 2100:
        raise SystemExit("--year must be between 1900 and 2100.")
    county = None
    if args.county and args.county.strip():
        text = args.county.strip()
        county = f"{int(text):02d}" if text.isdigit() else text
    election = parse_election_date(args.election)
    if election and args.year is not None and int(election[:4]) != args.year:
        raise SystemExit(f"--election {election} is not in --year {args.year}.")
    filters = Filters(county, args.year, congressional, cd_label, senate, sd_label, election)
    db_path = find_database(args.db)
    out_dir = Path(args.out).expanduser().resolve() if args.out else Path(__file__).resolve().parent / "anomaly_reports"
    display_limit = args.limit
    csv_limit = max(args.csv_limit, args.limit)

    conn = connect(db_path)
    try:
        require_schema(conn)
        print(f"Database: {db_path}", file=sys.stderr, flush=True)
        print("Reading database overview...", file=sys.stderr, flush=True)
        stats = overview(conn, filters)
        print("Scanning election history...", file=sys.stderr, flush=True)
        facts = scan_election_facts(conn, filters)
        print("Duplicate votes...", file=sys.stderr, flush=True)
        sections = [
            duplicate_votes(conn, filters, display_limit, csv_limit),
            votes_before_birth(conn, filters, facts, display_limit, csv_limit),
            registration_before_birth(conn, filters, display_limit, csv_limit),
        ]
        print("Name and address groups...", file=sys.stderr, flush=True)
        sections.extend(identity_duplicates(conn, filters, display_limit, csv_limit))
        print("Activity and age...", file=sys.stderr, flush=True)
        active, age, voters_with_history = activity_and_age(
            conn, filters, facts, display_limit, csv_limit
        )
        print("ZIP codes...", file=sys.stderr, flush=True)
        zips = zip_codes(conn, filters, display_limit, csv_limit)
        print("Orphans and voting method...", file=sys.stderr, flush=True)
        orphan, methods = orphans_and_methods(conn, filters, facts, display_limit, csv_limit)
        print("Completeness...", file=sys.stderr, flush=True)
        complete = completeness(conn, filters, stats, voters_with_history)
        sections.extend([active, age, zips, orphan, methods, complete])
    finally:
        conn.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_dir = out_dir / "csv"
    csv_dir.mkdir(exist_ok=True)
    rendered = []
    for section, rows in sections:
        written = write_csv(csv_dir, section, rows)
        if written:
            suffix = f" File: csv/{written.name}."
            section.csv_note = (section.csv_note + suffix).strip()
        rendered.append((section, rows))

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    md_path = out_dir / "voter_data_anomaly_report.md"
    html_path = out_dir / "voter_data_anomaly_report.html"
    render_markdown(md_path, db_path, filters, generated, stats, facts, rendered)
    render_html(html_path, db_path, filters, generated, stats, facts, rendered)
    print(md_path)
    print(html_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
