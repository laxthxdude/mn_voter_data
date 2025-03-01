import sqlite3
import csv
import chardet
import os
import sys
from datetime import datetime

def create_database(db_name="voters.db"):
    # Initialize connection and cursor
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Create voters table with appropriate types and allow NULL for optional fields
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voters (
            VoterId INTEGER PRIMARY KEY,
            CountyCode TEXT,
            FirstName TEXT,
            MiddleName TEXT,
            LastName TEXT,
            NameSuffix TEXT,
            HouseNumber TEXT,
            StreetName TEXT,
            UnitType TEXT,
            UnitNumber TEXT,
            Address2 TEXT,
            City TEXT,
            State TEXT,
            ZipCode TEXT,
            MailAddress TEXT,
            MailCity TEXT,
            MailState TEXT,
            MailZipCode TEXT,
            PhoneNumber TEXT,
            RegistrationDate TEXT,
            DOBYear INTEGER,
            StateMcdCode TEXT,
            McdName TEXT,
            PrecinctCode TEXT,
            PrecinctName TEXT,
            WardCode TEXT,
            School TEXT,
            SchSub TEXT,
            Judicial TEXT,
            Legislative TEXT,
            StateSen TEXT,
            Congressional TEXT,
            Commissioner TEXT,
            Park TEXT,
            SoilWater TEXT,
            Hospital TEXT,
            LegacyId TEXT,
            PermanentAbsentee TEXT
        )
    ''')

    # List of voter files
    voter_files = [f"Voter{i:02d}.txt" for i in range(1, 9)]  # Generates Voter01.txt to Voter08.txt
    current_dir = os.getcwd()

    total_rows = 0
    imported_rows = 0
    error_log = []

    # Process each voter file
    for file_name in voter_files:
        file_path = os.path.join(current_dir, file_name)
        if not os.path.exists(file_path):
            print(f"Warning: File {file_path} does not exist. Skipping.")
            continue

        # Detect encoding
        with open(file_path, 'rb') as raw_file:
            raw_data = raw_file.read(10000)  # Read first 10KB to detect encoding
            result = chardet.detect(raw_data)
            encoding = result['encoding'] or 'utf-8'
            if result['confidence'] < 0.8:
                print(f"Warning: Low confidence ({result['confidence']}) in detected encoding {encoding} for {file_name}.")

        # Count total rows (excluding header)
        with open(file_path, 'r', encoding=encoding) as csvfile:
            reader = csv.reader(csvfile, quotechar='"', skipinitialspace=True)
            next(reader, None)  # Skip header
            file_rows = sum(1 for _ in reader)
            total_rows += file_rows
            print(f"Processing {file_name} with {file_rows} rows.")

        # Process CSV file with error handling
        with open(file_path, 'r', encoding=encoding) as csvfile:
            reader = csv.reader(csvfile, quotechar='"', skipinitialspace=True)
            header = next(reader, None)  # Skip header
            if not header or len(header) != 38:
                print(f"Error: Invalid header in {file_path}. Expected 38 fields. Skipping file.")
                continue

            file_imported_rows = 0
            for row in reader:
                if len(row) != 38:
                    error_log.append(f"Row {file_imported_rows + 2} in {file_name}: Incorrect number of fields ({len(row)} instead of 38). Skipping.")
                    continue

                try:
                    # Map row data to table fields with error handling
                    voter_data = {
                        "VoterId": int(row[0]) if row[0] else None,
                        "CountyCode": row[1] if row[1] else None,
                        "FirstName": row[2] if row[2] else None,
                        "MiddleName": row[3] if row[3] else None,
                        "LastName": row[4] if row[4] else None,
                        "NameSuffix": row[5] if row[5] else None,
                        "HouseNumber": row[6] if row[6] else None,
                        "StreetName": row[7] if row[7] else None,
                        "UnitType": row[8] if row[8] else None,
                        "UnitNumber": row[9] if row[9] else None,
                        "Address2": row[10] if row[10] else None,
                        "City": row[11] if row[11] else None,
                        "State": row[12] if row[12] else None,
                        "ZipCode": row[13] if row[13] else None,
                        "MailAddress": row[14] if row[14] else None,
                        "MailCity": row[15] if row[15] else None,
                        "MailState": row[16] if row[16] else None,
                        "MailZipCode": row[17] if row[17] else None,
                        "PhoneNumber": row[18] if row[18] else None,
                        "RegistrationDate": parse_date(row[19]) if row[19] else None,
                        "DOBYear": int(row[20]) if row[20] and row[20].strip() else None,
                        "StateMcdCode": row[21] if row[21] else None,
                        "McdName": row[22] if row[22] else None,
                        "PrecinctCode": row[23] if row[23] else None,
                        "PrecinctName": row[24] if row[24] else None,
                        "WardCode": row[25] if row[25] else None,
                        "School": row[26] if row[26] else None,
                        "SchSub": row[27] if row[27] else None,
                        "Judicial": row[28] if row[28] else None,
                        "Legislative": row[29] if row[29] else None,
                        "StateSen": row[30] if row[30] else None,
                        "Congressional": row[31] if row[31] else None,
                        "Commissioner": row[32] if row[32] else None,
                        "Park": row[33] if row[33] else None,
                        "SoilWater": row[34] if row[34] else None,
                        "Hospital": row[35] if row[35] else None,
                        "LegacyId": row[36] if row[36] else None,
                        "PermanentAbsentee": row[37] if row[37] else None
                    }

                    # Insert data into the table
                    cursor.execute('''
                        INSERT INTO voters (VoterId, CountyCode, FirstName, MiddleName, LastName, NameSuffix, 
                            HouseNumber, StreetName, UnitType, UnitNumber, Address2, City, State, ZipCode, 
                            MailAddress, MailCity, MailState, MailZipCode, PhoneNumber, RegistrationDate, 
                            DOBYear, StateMcdCode, McdName, PrecinctCode, PrecinctName, WardCode, School, 
                            SchSub, Judicial, Legislative, StateSen, Congressional, Commissioner, Park, 
                            SoilWater, Hospital, LegacyId, PermanentAbsentee)
                        VALUES (:VoterId, :CountyCode, :FirstName, :MiddleName, :LastName, :NameSuffix, 
                            :HouseNumber, :StreetName, :UnitType, :UnitNumber, :Address2, :City, :State, 
                            :ZipCode, :MailAddress, :MailCity, :MailState, :MailZipCode, :PhoneNumber, 
                            :RegistrationDate, :DOBYear, :StateMcdCode, :McdName, :PrecinctCode, 
                            :PrecinctName, :WardCode, :School, :SchSub, :Judicial, :Legislative, 
                            :StateSen, :Congressional, :Commissioner, :Park, :SoilWater, :Hospital, 
                            :LegacyId, :PermanentAbsentee)
                    ''', voter_data)
                    file_imported_rows += 1
                    imported_rows += 1

                except ValueError as ve:
                    error_log.append(f"Row {file_imported_rows + 2} in {file_name}: ValueError - {str(ve)}. Skipping row.")
                except Exception as e:
                    error_log.append(f"Row {file_imported_rows + 2} in {file_name}: Unexpected error - {str(e)}. Skipping row.")

        print(f"Imported {file_imported_rows} rows from {file_name}.")

    # Commit changes
    conn.commit()

    # Print overall summary with total rows comparison
    print(f"Total rows across all files (excluding headers): {total_rows}")
    print(f"Total imported rows into {db_name}: {imported_rows}")
    if imported_rows != total_rows:
        print(f"Warning: Imported rows ({imported_rows}) do not match total rows in files ({total_rows}).")
    if error_log:
        print(f"Encountered {len(error_log)} errors across all files:")
        for error in error_log[:10]:  # Show first 10 errors, adjust as needed
            print(f"  {error}")
        if len(error_log) > 10:
            print(f"  ...and {len(error_log) - 10} more errors (full log available in script output).")

    # Close connection
    conn.close()

def parse_date(date_str):
    """Parse date string with flexible formats."""
    if not date_str:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d %H:%M:%S')  # Normalize to standard format
        except ValueError:
            continue
    return None  # Return None if unparseable

# Run the script without command-line argument
if __name__ == "__main__":
    create_database()