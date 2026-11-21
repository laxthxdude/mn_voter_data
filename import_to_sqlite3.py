#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import a Minnesota Secretary of State WO*.zip into SQLite.

The original extract is quoted CSV: every field is wrapped in double quotes,
and a comma inside a field stays inside those quotes. The quotes are syntax,
not data. This script reads the zip in place (no extraction, no quote
stripping) and stores field values only.

Stripping the quote characters out of the file first turns those interior
commas into extra columns. Pass the original zip instead.

A few districts are Windows-1252 rather than UTF-8 (for example a ½ in an
address). Each file is decoded as UTF-8 when that is valid, and as
Windows-1252 otherwise.
"""

import argparse
import codecs
import csv
import hashlib
import io
import os
import sqlite3
import sys
import time
import zipfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path

BATCH_SIZE = 50_000
REPORT_EVERY = 500_000
MAX_ERRORS_KEPT = 100
VERIFY_BATCH = 400
VERIFY_SAMPLES = 30
# Election history is tens of millions of rows and has no unique key, so each
# voter's rows are reduced to a count plus a 128-bit fingerprint. Adding the
# digests (instead of XOR) keeps duplicate rows from cancelling each other.
_FP_MASK = (1 << 128) - 1

VOTER_COLUMNS = [
    "VoterId", "CountyCode", "FirstName", "MiddleName", "LastName", "NameSuffix",
    "HouseNumber", "StreetName", "UnitType", "UnitNumber", "Address2",
    "City", "State", "ZipCode",
    "MailAddress", "MailCity", "MailState", "MailZipCode",
    "PhoneNumber", "RegistrationDate", "DOBYear",
    "StateMcdCode", "McdName", "PrecinctCode", "PrecinctName",
    "WardCode", "School", "SchSub", "Judicial", "Legislative",
    "StateSen", "Congressional", "Commissioner", "Park",
    "SoilWater", "Hospital", "LegacyId", "PermanentAbsentee",
]

ELECTION_COLUMNS = [
    "VoterId", "ElectionDate", "ElectionDescription", "VotingMethod",
]

VOTER_INSERT_SQL = (
    "INSERT OR IGNORE INTO voters VALUES ("
    + ",".join(["?"] * len(VOTER_COLUMNS)) + ")"
)
ELECTION_INSERT_SQL = (
    "INSERT INTO election_history VALUES ("
    + ",".join(["?"] * len(ELECTION_COLUMNS)) + ")"
)

# Search indexes are built after the load. Maintaining them row-by-row
# during a multi-million-row insert dominates the runtime.
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_voters_first ON voters(FirstName);",
    "CREATE INDEX IF NOT EXISTS idx_voters_last ON voters(LastName);",
    "CREATE INDEX IF NOT EXISTS idx_voters_zip ON voters(ZipCode);",
    "CREATE INDEX IF NOT EXISTS idx_election_voter ON election_history(VoterId);",
]


def parse_date(date_str):
    """Normalize a date to ISO 'YYYY-MM-DD'.

    Voter registration values look like 'YYYY-MM-DD HH:MM:SS'. Election
    dates look like 'MM/DD/YYYY'. Repeated dates are cached.
    """
    if not date_str:
        return None
    s = date_str.strip()
    if not s:
        return None
    return _parse_date_cached(s)


@lru_cache(maxsize=65536)
def _parse_date_cached(s):
    # YYYY-MM-DD and YYYY-MM-DD HH:MM:SS
    if len(s) >= 10 and s[4] == "-" and s[7] == "-" \
            and s[:4].isdigit() and s[5:7].isdigit() and s[8:10].isdigit() \
            and (len(s) == 10 or s[10] == " "):
        year, month, day = int(s[:4]), int(s[5:7]), int(s[8:10])
        if 1 <= month <= 12 and _valid_day(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"

    # MM/DD/YYYY
    if len(s) == 10 and s[2] == "/" and s[5] == "/" \
            and s[:2].isdigit() and s[3:5].isdigit() and s[6:].isdigit():
        month, day, year = int(s[:2]), int(s[3:5]), int(s[6:])
        if 1 <= month <= 12 and _valid_day(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"

    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _valid_day(year, month, day):
    days = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if day <= days[month - 1]:
        return True
    return month == 2 and day == 29 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def voter_record(row):
    """Map one parsed voter row to the INSERT tuple. Quotes are already gone."""
    voter_id = row[0].strip()
    if not voter_id:
        raise ValueError("blank VoterId")
    dob = row[20].strip()
    return (
        int(voter_id),
        *row[1:19],
        parse_date(row[19]),
        int(dob) if dob else None,
        *row[21:],
    )


def election_record(row):
    voter_id = row[0].strip()
    if not voter_id:
        raise ValueError("blank VoterId")
    return (
        int(voter_id),
        parse_date(row[1]),
        row[2],
        row[3],
    )


def detect_encoding(open_binary):
    """Return 'utf-8-sig' or 'cp1252' for one source file.

    utf-8-sig also accepts a leading BOM and plain ASCII. A single
    Windows-1252 byte (common for ½ and similar) fails that decode, and
    the whole file is then read as cp1252.
    """
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    with open_binary() as raw:
        while True:
            chunk = raw.read(1 << 20)
            if not chunk:
                break
            try:
                decoder.decode(chunk)
            except UnicodeDecodeError:
                return "cp1252"
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return "cp1252"
    return "utf-8-sig"


@contextmanager
def open_text(open_binary):
    encoding = detect_encoding(open_binary)
    raw = open_binary()
    text = io.TextIOWrapper(raw, encoding=encoding, newline="")
    try:
        yield text, encoding
    finally:
        text.close()


def _csv_reader(stream, label, warn_unquoted=True):
    """CSV reader for SOS quoted files.

    newline='' on the stream lets csv handle embedded newlines and CRLF.
    quotechar='"' drops the wrapping quotes and keeps commas inside fields.
    """
    first = stream.readline()
    if not first:
        raise SystemExit(f"{label} is empty")
    if first.startswith("\ufeff"):
        first = first[1:]
    if warn_unquoted and not first.startswith('"'):
        print(
            f"Warning: {label} is not quote-delimited. Commas inside a field "
            f"will be read as extra columns. Import the original WO*.zip, "
            f"not a copy that has had the quote characters removed."
        )
    return csv.reader(
        _chain_first(first, stream),
        delimiter=",",
        quotechar='"',
        doublequote=True,
    )


def _chain_first(first, stream):
    yield first
    for line in stream:
        yield line


class ErrorLog:
    def __init__(self):
        self.count = 0
        self.samples = []

    def add(self, message):
        self.count += 1
        if len(self.samples) < MAX_ERRORS_KEPT:
            self.samples.append(message)


class ZipSource:
    def __init__(self, path):
        self.path = path
        self._zip = zipfile.ZipFile(path)
        names = [
            name for name in self._zip.namelist()
            if _is_data_member(name)
        ]
        self.voters = _matching(names, "voter")
        self.elections = _matching(names, "election")

    def close(self):
        self._zip.close()

    def label(self, name):
        return os.path.basename(name)

    def open_binary(self, name):
        return lambda: self._zip.open(name, "r")


class DirectorySource:
    def __init__(self, path):
        self.path = path
        names = [
            os.path.join(path, name)
            for name in os.listdir(path)
            if _is_data_member(name)
        ]
        self.voters = _matching(names, "voter")
        self.elections = _matching(names, "election")

    def close(self):
        return None

    def label(self, name):
        return os.path.basename(name)

    def open_binary(self, name):
        return lambda: open(name, "rb")


def _is_data_member(name):
    base = os.path.basename(name)
    if not base or base.startswith(".") or base.startswith("._"):
        return False
    lowered = name.replace("\\", "/")
    if lowered.startswith("__MACOSX/") or "/__MACOSX/" in lowered:
        return False
    return base.lower().endswith(".txt")


def _matching(names, kind):
    prefix = kind.lower()
    chosen = []
    for name in names:
        base = os.path.basename(name).lower()
        # Voter01.txt / Election08.txt. Ignore readme.txt and anything else.
        stem, ext = os.path.splitext(base)
        if ext != ".txt" or not stem.startswith(prefix):
            continue
        suffix = stem[len(prefix):]
        if suffix.isdigit():
            chosen.append(name)
    chosen.sort(key=lambda name: (len(os.path.basename(name)), os.path.basename(name).lower()))
    return chosen


def open_source(path):
    path = os.path.abspath(path)
    if os.path.isdir(path):
        return DirectorySource(path)
    if not os.path.isfile(path):
        raise SystemExit(f"Error: {path} not found")
    if not zipfile.is_zipfile(path):
        raise SystemExit(f"Error: {path} is not a zip file or a directory of voter files")
    return ZipSource(path)


def tune(conn):
    """Bulk-load settings. A crash leaves a partial *.building file, which
    the next run replaces. The finished database is swapped in only after
    the load and indexes succeed."""
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-131072")  # 128 MiB
    conn.execute("PRAGMA locking_mode=EXCLUSIVE")


def create_schema(conn):
    conn.execute("""
        CREATE TABLE voters (
            VoterId INTEGER PRIMARY KEY,
            CountyCode TEXT, FirstName TEXT, MiddleName TEXT, LastName TEXT, NameSuffix TEXT,
            HouseNumber TEXT, StreetName TEXT, UnitType TEXT, UnitNumber TEXT, Address2 TEXT,
            City TEXT, State TEXT, ZipCode TEXT,
            MailAddress TEXT, MailCity TEXT, MailState TEXT, MailZipCode TEXT,
            PhoneNumber TEXT, RegistrationDate TEXT, DOBYear INTEGER,
            StateMcdCode TEXT, McdName TEXT, PrecinctCode TEXT, PrecinctName TEXT,
            WardCode TEXT, School TEXT, SchSub TEXT, Judicial TEXT, Legislative TEXT,
            StateSen TEXT, Congressional TEXT, Commissioner TEXT, Park TEXT,
            SoilWater TEXT, Hospital TEXT, LegacyId TEXT, PermanentAbsentee TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE election_history (
            VoterId INTEGER,
            ElectionDate TEXT,
            ElectionDescription TEXT,
            VotingMethod TEXT
        )
    """)


def _check_header(header, expected, label):
    got = [column.strip() for column in header]
    if got != expected:
        raise SystemExit(
            f"{label} header does not match the expected SOS layout.\n"
            f"  expected: {', '.join(expected)}\n"
            f"  got:      {', '.join(got)}"
        )


def import_file(conn, source, name, kind, errors):
    label = source.label(name)
    expected = VOTER_COLUMNS if kind == "voter" else ELECTION_COLUMNS
    convert = voter_record if kind == "voter" else election_record
    insert_sql = VOTER_INSERT_SQL if kind == "voter" else ELECTION_INSERT_SQL
    width = len(expected)

    inserted = 0
    pending = []
    seen = 0
    next_report = REPORT_EVERY

    def flush():
        nonlocal inserted
        if not pending:
            return
        before = conn.total_changes
        conn.executemany(insert_sql, pending)
        inserted += conn.total_changes - before
        pending.clear()

    with open_text(source.open_binary(name)) as (stream, encoding):
        print(f"→ {label} (encoding: {encoding})", flush=True)
        reader = _csv_reader(stream, label)
        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit(f"{label} is empty")
        _check_header(header, expected, label)

        for line_num, row in enumerate(reader, start=2):
            if not row or (len(row) == 1 and row[0] == ""):
                continue
            if len(row) != width:
                errors.add(f"{label}:{line_num} wrong column count ({len(row)})")
                continue
            try:
                pending.append(convert(row))
            except ValueError as exc:
                errors.add(f"{label}:{line_num} {exc}")
                continue

            seen += 1
            if len(pending) >= BATCH_SIZE:
                flush()
                if seen >= next_report:
                    print(f"   {seen:,} rows read", flush=True)
                    next_report += REPORT_EVERY
        flush()

    skipped = seen - inserted if kind == "voter" else 0
    noun = "voters" if kind == "voter" else "election rows"
    extra = f" ({skipped:,} duplicate VoterIds ignored)" if skipped else ""
    print(f"   {inserted:,} {noun}{extra}\n", flush=True)
    return inserted


def canonical_bytes(values):
    """Unambiguous encoding of one stored row, for the election fingerprint."""
    parts = []
    for value in values:
        if value is None:
            parts.append(b"N\x1e")
        elif isinstance(value, int):
            parts.append(b"I" + str(value).encode("ascii") + b"\x1e")
        else:
            parts.append(b"T" + str(value).encode("utf-8") + b"\x1e")
    return b"".join(parts)


def row_fingerprint(values):
    digest = hashlib.blake2b(canonical_bytes(values), digest_size=16).digest()
    return int.from_bytes(digest, "little")


def _iter_records(source, name, kind, warn_unquoted):
    """Yield source rows using the same rules as the importer.

    A yielded item is ("row", line_number, record) or ("skip", message).
    """
    label = source.label(name)
    expected = VOTER_COLUMNS if kind == "voter" else ELECTION_COLUMNS
    convert = voter_record if kind == "voter" else election_record
    width = len(expected)
    with open_text(source.open_binary(name)) as (stream, _encoding):
        reader = _csv_reader(stream, label, warn_unquoted=warn_unquoted)
        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit(f"{label} is empty")
        _check_header(header, expected, label)
        for line_num, row in enumerate(reader, start=2):
            if not row or (len(row) == 1 and row[0] == ""):
                continue
            if len(row) != width:
                yield ("skip", f"{label}:{line_num} wrong column count ({len(row)})")
                continue
            try:
                record = convert(row)
            except ValueError as exc:
                yield ("skip", f"{label}:{line_num} {exc}")
                continue
            yield ("row", line_num, record)


class VerifyReport:
    def __init__(self):
        self.voter_rows = 0
        self.voter_duplicates = 0
        self.election_rows = 0
        self.mismatch_count = 0
        self.election_voter_mismatches = 0
        self.samples = []

    def add(self, message):
        self.mismatch_count += 1
        self.note(message)

    def note(self, message):
        if len(self.samples) < VERIFY_SAMPLES:
            self.samples.append(message)

    @property
    def ok(self):
        return self.mismatch_count == 0 and self.election_voter_mismatches == 0


def _fetch_voters(cur, voter_ids):
    placeholders = ",".join(["?"] * len(voter_ids))
    columns = ",".join(VOTER_COLUMNS)
    cur.execute(
        f"SELECT {columns} FROM voters WHERE VoterId IN ({placeholders})",
        voter_ids,
    )
    return {row[0]: row for row in cur.fetchall()}


def _voter_differences(expected, stored):
    differences = []
    for name, source_value, db_value in zip(VOTER_COLUMNS, expected, stored):
        if source_value != db_value:
            differences.append((name, source_value, db_value))
    return differences


def verify_voters(source, conn, report):
    print("Verifying voters...", flush=True)
    cur = conn.cursor()
    seen = set()
    checked = 0
    next_report = REPORT_EVERY
    batch = []

    def flush():
        nonlocal checked, next_report
        if not batch:
            return
        found = _fetch_voters(cur, [record[0] for _file, _line, record in batch])
        for file_label, line_num, record in batch:
            voter_id = record[0]
            where = f"{file_label}:{line_num} VoterId {voter_id}"
            stored = found.get(voter_id)
            if voter_id in seen:
                report.voter_duplicates += 1
                if stored is None:
                    report.add(f"{where}: duplicate source row, and the database has no row")
                elif tuple(stored) != tuple(record):
                    fields = ", ".join(name for name, _a, _b in _voter_differences(record, stored))
                    report.add(
                        f"{where}: duplicate source row differs from the stored voter "
                        f"({fields or 'values'})"
                    )
                continue
            seen.add(voter_id)
            if stored is None:
                report.add(f"{where}: missing from the database")
                continue
            differences = _voter_differences(record, stored)
            if differences:
                shown = differences[:3]
                detail = "; ".join(
                    f"{name}: source {source_value!r}, database {db_value!r}"
                    for name, source_value, db_value in shown
                )
                report.add(f"{where}: {detail}")
        checked += len(batch)
        batch.clear()
        if checked >= next_report:
            print(f"   {checked:,} voter rows checked", flush=True)
            next_report += REPORT_EVERY

    for name in source.voters:
        label = source.label(name)
        print(f"→ {label}", flush=True)
        file_rows = 0
        for item in _iter_records(source, name, "voter", warn_unquoted=False):
            if item[0] == "skip":
                report.add(item[1] + " was not imported")
                continue
            _kind, line_num, record = item
            batch.append((label, line_num, record))
            file_rows += 1
            report.voter_rows += 1
            if len(batch) >= VERIFY_BATCH:
                flush()
        flush()
        print(f"   {file_rows:,} source rows", flush=True)

    db_count = conn.execute("SELECT COUNT(*) FROM voters").fetchone()[0]
    if db_count > len(seen):
        extras = []
        for (voter_id,) in conn.execute("SELECT VoterId FROM voters"):
            if voter_id not in seen:
                extras.append(voter_id)
                if len(extras) == 10:
                    break
        shown = ", ".join(str(voter_id) for voter_id in extras)
        report.add(
            f"Voter table has {db_count - len(seen):,} rows that are not in the source. "
            f"Extra VoterIds include {shown}."
        )
    duplicate_note = ""
    if report.voter_duplicates:
        duplicate_note = f", {report.voter_duplicates:,} duplicate source ids"
    print(
        f"   {report.voter_rows:,} voter rows checked"
        f"{duplicate_note}\n",
        flush=True,
    )


def verify_elections(source, conn, report):
    print("Verifying election history...", flush=True)
    fingerprints = {}
    checked = 0
    next_report = REPORT_EVERY

    def add(voter_id, values, sign):
        count, total = fingerprints.get(voter_id, (0, 0))
        digest = row_fingerprint(values)
        fingerprints[voter_id] = (count + sign, (total + sign * digest) & _FP_MASK)

    for name in source.elections:
        label = source.label(name)
        print(f"→ {label}", flush=True)
        file_rows = 0
        for item in _iter_records(source, name, "election", warn_unquoted=False):
            if item[0] == "skip":
                report.add(item[1] + " was not imported")
                continue
            _kind, _line_num, record = item
            add(record[0], record, 1)
            file_rows += 1
            report.election_rows += 1
            checked += 1
            if checked >= next_report:
                print(f"   {checked:,} election rows checked", flush=True)
                next_report += REPORT_EVERY
        print(f"   {file_rows:,} source rows", flush=True)

    print("   reading the database...", flush=True)
    db_rows = 0
    for record in conn.execute(
        "SELECT VoterId, ElectionDate, ElectionDescription, VotingMethod "
        "FROM election_history"
    ):
        add(record[0], record, -1)
        db_rows += 1
        if db_rows % REPORT_EVERY == 0:
            print(f"   {db_rows:,} database rows read", flush=True)

    bad_ids = [voter_id for voter_id, (count, total) in fingerprints.items() if count or total]
    if bad_ids:
        report.election_voter_mismatches = len(bad_ids)
        noun = "voter" if len(bad_ids) == 1 else "voters"
        report.note(
            f"{len(bad_ids):,} {noun} have election rows that do not match the source"
        )
        sample_ids = bad_ids[:10]
        source_rows = {voter_id: [] for voter_id in sample_ids}
        wanted = set(sample_ids)
        for name in source.elections:
            for item in _iter_records(source, name, "election", warn_unquoted=False):
                if item[0] != "row":
                    continue
                record = item[2]
                if record[0] in wanted:
                    source_rows[record[0]].append(record)
        for voter_id in sample_ids:
            db_for_voter = conn.execute(
                "SELECT VoterId, ElectionDate, ElectionDescription, VotingMethod "
                "FROM election_history WHERE VoterId = ?",
                (voter_id,),
            ).fetchall()
            source_count, _total = fingerprints[voter_id]
            # source_count is source minus database, so database count is
            # len(db_for_voter). Report the actual rows that do not match.
            missing, extra = _multiset_diff(source_rows[voter_id], db_for_voter)
            print_missing = ", ".join(repr(row[1:]) for row in missing[:2]) or "none"
            print_extra = ", ".join(repr(row[1:]) for row in extra[:2]) or "none"
            report.note(
                f"VoterId {voter_id}: election rows differ "
                f"(source {len(source_rows[voter_id])}, "
                f"database {len(db_for_voter)}, "
                f"count delta {source_count}). "
                f"Missing from database: {print_missing}. "
                f"Extra in database: {print_extra}."
            )
    print(
        f"   {report.election_rows:,} source rows, "
        f"{db_rows:,} database rows\n",
        flush=True,
    )


def _multiset_diff(source_rows, db_rows):
    source_counts = Counter(tuple(row) for row in source_rows)
    db_counts = Counter(tuple(row) for row in db_rows)
    missing = list((source_counts - db_counts).elements())
    extra = list((db_counts - source_counts).elements())
    return missing, extra


def verify_database(source, db_path):
    """Re-read the source and compare it to the finished database.

    Voters are compared column by column. Election rows are compared as a
    multiset per voter. Returns 0 when every imported value matches.
    """
    print("=" * 60)
    print("VERIFYING IMPORTED DATA")
    print(f"Database: {db_path}\n")
    started = time.monotonic()
    report = VerifyReport()
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        verify_voters(source, conn, report)
        verify_elections(source, conn, report)
    finally:
        conn.close()

    elapsed = time.monotonic() - started
    print("=" * 60)
    if report.ok:
        print("VERIFICATION PASSED")
    else:
        print("VERIFICATION FAILED")
    print(f"Voters checked            : {report.voter_rows:,}")
    print(f"Duplicate voter ids       : {report.voter_duplicates:,}")
    print(f"Election rows checked     : {report.election_rows:,}")
    print(
        f"Mismatches                : "
        f"{report.mismatch_count + report.election_voter_mismatches:,}"
    )
    print(f"Verification elapsed      : {elapsed:,.0f}s")
    if report.samples:
        print("First mismatches:")
        for message in report.samples:
            print(f"   • {message}")
    return 0 if report.ok else 1


def build_database(source_path, db_path, verbose=False):
    source_path = os.path.abspath(source_path)
    db_path = os.path.abspath(db_path)
    source = open_source(source_path)
    tmp_path = db_path + ".building"
    started = time.monotonic()
    try:
        if not source.voters and not source.elections:
            raise SystemExit(
                f"No VoterNN.txt or ElectionNN.txt files found in {source_path}"
            )
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        print(f"Source:   {source_path}")
        print(f"Database: {db_path}")
        print(
            f"Files:    {len(source.voters)} voter, "
            f"{len(source.elections)} election\n"
        )

        conn = sqlite3.connect(tmp_path)
        verification_failed = False
        try:
            tune(conn)
            create_schema(conn)
            errors = ErrorLog()
            total_voters = 0
            total_elections = 0
            for name in source.voters:
                total_voters += import_file(conn, source, name, "voter", errors)
                conn.commit()
            if source.elections:
                print("Election history\n")
            for name in source.elections:
                total_elections += import_file(conn, source, name, "election", errors)
                conn.commit()

            print("Building search indexes...", flush=True)
            for sql in INDEXES:
                conn.execute(sql)
            conn.commit()
            conn.close()
            conn = None
            os.replace(tmp_path, db_path)
            verification_failed = False
            if verbose:
                verification_failed = verify_database(source, db_path) != 0
        finally:
            if conn is not None:
                conn.close()
            # A failed load must not leave a partial database behind.
            # On success the file has already been renamed away.
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    finally:
        source.close()

    elapsed = time.monotonic() - started
    print("=" * 60)
    if errors.count and verbose and verification_failed:
        print("IMPORT FINISHED WITH SKIPPED ROWS AND VERIFICATION FAILED")
    elif errors.count:
        print("IMPORT FINISHED WITH SKIPPED ROWS")
    elif verbose and verification_failed:
        print("IMPORT FINISHED, VERIFICATION FAILED")
    else:
        print("IMPORT COMPLETED SUCCESSFULLY")
    print(f"Database                  : {db_path}")
    print(f"Voters imported           : {total_voters:,}")
    print(f"Election rows imported    : {total_elections:,}")
    print(f"Elapsed                   : {elapsed:,.0f}s")
    if verbose:
        print(f"Verification              : {'FAILED' if verification_failed else 'passed'}")
    if errors.count:
        shown = len(errors.samples)
        print(f"Rows skipped              : {errors.count:,} (showing {shown})")
        for message in errors.samples:
            print(f"   • {message}")
        return 1
    if verification_failed:
        return 1
    print("No rows skipped.")
    return 0


def find_default_source():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs = []
    for directory in (os.getcwd(), script_dir, os.path.dirname(script_dir)):
        directory = os.path.abspath(directory)
        if directory not in search_dirs and os.path.isdir(directory):
            search_dirs.append(directory)

    found = []
    for directory in search_dirs:
        for name in sorted(os.listdir(directory)):
            if name.startswith("WO") and name.lower().endswith(".zip"):
                path = os.path.join(directory, name)
                if os.path.isfile(path) and path not in found:
                    found.append(path)

    cwd = os.path.abspath(os.getcwd())
    in_cwd = [path for path in found if os.path.dirname(path) == cwd]
    if len(in_cwd) == 1:
        return in_cwd[0]
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        print("More than one WO*.zip found. Pass the file to import:", file=sys.stderr)
        for path in found:
            print(f"  {path}", file=sys.stderr)
        raise SystemExit(1)
    if os.path.isfile(os.path.join(cwd, "Voter01.txt")):
        return cwd
    print("No WO*.zip found. Pass the original zip, for example:", file=sys.stderr)
    print("  python3 import_to_sqlite3.py /path/to/WO261108.zip", file=sys.stderr)
    raise SystemExit(1)


def default_db_path(source_path):
    source_path = os.path.abspath(source_path)
    if os.path.isdir(source_path):
        return os.path.join(source_path, "voters.db")
    stem, _ext = os.path.splitext(source_path)
    return stem + ".db"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Import a Minnesota Secretary of State WO*.zip into SQLite. "
            "The zip is quoted CSV; quotes are not stored. Do not strip "
            "quotes from the files before importing."
        )
    )
    parser.add_argument(
        "source",
        nargs="?",
        help=(
            "Original WO*.zip, or a directory of the original quoted "
            "VoterNN.txt and ElectionNN.txt files. If omitted, uses the "
            "single WO*.zip in the current directory, next to this script, "
            "or in the parent directory."
        ),
    )
    parser.add_argument(
        "-o", "--output",
        help="SQLite file to create. Default: <zipname>.db beside the zip.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help=(
            "After the import, re-read the source files and verify the "
            "database. Every voter column is compared. Election rows are "
            "compared per voter, including repeated elections. Exit status "
            "is 1 if anything does not match."
        ),
    )
    parser.add_argument(
        "-cleanup",
        action="store_true",
        help=(
            "Ignored. The zip is read in place, so there is nothing to delete. "
            "The original zip is left untouched."
        ),
    )
    args = parser.parse_args(argv)
    if args.cleanup:
        print("Nothing to clean up. The source zip is read in place and kept.")

    source = os.path.abspath(args.source) if args.source else find_default_source()
    db_path = os.path.abspath(args.output) if args.output else default_db_path(source)
    return build_database(source, db_path, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
