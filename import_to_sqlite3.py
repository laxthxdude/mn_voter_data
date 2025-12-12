#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import csv
import chardet
import os
from datetime import datetime

# Force UTF-8 for the entire process (essential on macOS Python 3.9)
import locale
locale.setlocale(locale.LC_ALL, 'C.UTF-8')

def detect_encoding(file_path):
    with open(file_path, 'rb') as f:
        raw = f.read(100000)
    result = chardet.detect(raw)
    return result['encoding'] or 'utf-8'

def parse_date(date_str):
    if not date_str or not date_str.strip():
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None

def create_database(db_name="voters.db"):
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()

    # Tables
    cur.execute('''
        CREATE TABLE IF NOT EXISTS voters (
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
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS election_history (
            VoterId INTEGER,
            ElectionDate TEXT,
            ElectionDescription TEXT,
            VotingMethod TEXT,
            FOREIGN KEY (VoterId) REFERENCES voters(VoterId)
        )
    ''')

    # Indexes (only once)
    for sql in [
        "CREATE INDEX IF NOT EXISTS idx_fn ON voters(FirstName);",
        "CREATE INDEX IF NOT EXISTS idx_ln ON voters(LastName);",
        "CREATE INDEX IF NOT EXISTS idx_zip ON voters(ZipCode);"
    ]:
        cur.execute(sql)

    voter_files = [f"Voter{i:02d}.txt" for i in range(1, 9)]
    election_files = [f"Election{i:02d}.txt" for i in range(1, 9)]

    total_voters = 0
    total_elections = 0
    errors = []

    print("Starting voter import...\n")

    # ==================== VOTER FILES ====================
    for fname in voter_files:
        path = os.path.join(os.getcwd(), fname)
        if not os.path.exists(path):
            print(f"Warning: {fname} missing")
            continue

        enc = detect_encoding(path)
        print(f"→ {fname} (encoding: {enc})")

        # Optional row count (safe)
        try:
            with open(path, 'r', encoding=enc, errors='replace') as f:
                rows = sum(1 for _ in csv.reader(f, quotechar='"', skipinitialspace=True))
                row_count = next(rows)  # header
                row_count = sum(rows)
            print(f"   {row_count:,} rows to import")
        except:
            row_count = "?"

        # Actual import
        with open(path, 'r', encoding=enc, errors='replace') as f:
            reader = csv.reader(f, quotechar='"', skipinitialspace=True)
            next(reader, None)  # skip header

            imported_this_file = 0
            for line_num, row in enumerate(reader, start=2):
                if len(row) != 38:
                    errors.append(f"{fname}:{line_num} wrong column count ({len(row)})")
                    continue

                try:
                    data = {
                        "VoterId": int(row[0]) if row[0].strip() else None,
                        "CountyCode": row[1], "FirstName": row[2], "MiddleName": row[3],
                        "LastName": row[4], "NameSuffix": row[5], "HouseNumber": row[6],
                        "StreetName": row[7], "UnitType": row[8], "UnitNumber": row[9],
                        "Address2": row[10], "City": row[11], "State": row[12], "ZipCode": row[13],
                        "MailAddress": row[14], "MailCity": row[15], "MailState": row[16],
                        "MailZipCode": row[17], "PhoneNumber": row[18],
                        "RegistrationDate": parse_date(row[19]),
                        "DOBYear": int(row[20]) if row[20].strip() else None,
                        "StateMcdCode": row[21], "McdName": row[22], "PrecinctCode": row[23],
                        "PrecinctName": row[24], "WardCode": row[25], "School": row[26],
                        "SchSub": row[27], "Judicial": row[28], "Legislative": row[29],
                        "StateSen": row[30], "Congressional": row[31], "Commissioner": row[32],
                        "Park": row[33], "SoilWater": row[34], "Hospital": row[35],
                        "LegacyId": row[36], "PermanentAbsentee": row[37]
                    }

                    cur.execute('''
                        INSERT OR IGNORE INTO voters VALUES (
                            :VoterId,:CountyCode,:FirstName,:MiddleName,:LastName,:NameSuffix,
                            :HouseNumber,:StreetName,:UnitType,:UnitNumber,:Address2,
                            :City,:State,:ZipCode,:MailAddress,:MailCity,:MailState,:MailZipCode,
                            :PhoneNumber,:RegistrationDate,:DOBYear,:StateMcdCode,:McdName,
                            :PrecinctCode,:PrecinctName,:WardCode,:School,:SchSub,:Judicial,
                            :Legislative,:StateSen,:Congressional,:Commissioner,:Park,
                            :SoilWater,:Hospital,:LegacyId,:PermanentAbsentee
                        )
                    ''', data)

                    imported_this_file += 1
                    total_voters += 1

                    if imported_this_file % 100000 == 0:
                        print(f"   {imported_this_file:,} rows so far...")

                except Exception as e:
                    errors.append(f"{fname}:{line_num} {e}")

            print(f"Finished {fname} → {imported_this_file:,} voters added\n")

    # ==================== ELECTION FILES ====================
    print("Processing election history files...\n")
    for fname in election_files:
        path = os.path.join(os.getcwd(), fname)
        if not os.path.exists(path):
            print(f"Warning: {fname} missing")
            continue

        enc = detect_encoding(path)
        print(f"→ {fname} (encoding: {enc})")

        with open(path, 'r', encoding=enc, errors='replace') as f:
            reader = csv.reader(f, quotechar='"', skipinitialspace=True)
            next(reader, None)  # header

            cnt = 0
            for line_num, row in enumerate(reader, start=2):
                if len(row) != 4:
                    errors.append(f"{fname}:{line_num} bad columns")
                    continue
                try:
                    cur.execute(
                        "INSERT OR IGNORE INTO election_history VALUES (?,?,?,?)",
                        (int(row[0]) if row[0].strip() else None,
                         parse_date(row[1]),
                         row[2], row[3])
                    )
                    cnt += 1
                    total_elections += 1
                except Exception as e:
                    errors.append(f"{fname}:{line_num} {e}")

            print(f"   {cnt:,} election records imported\n")

    conn.commit()
    conn.close()

    print("="*60)
    print("IMPORT COMPLETED SUCCESSFULLY")
    print(f"Total voters imported     : {total_voters:,}")
    print(f"Total election records    : {total_elections:,}")
    if errors:
        print(f"Warnings/Errors           : {len(errors)} (first 10)")
        for e in errors[:10]:
            print("   •", e)
    else:
        print("No errors!")

if __name__ == "__main__":
    create_database()
