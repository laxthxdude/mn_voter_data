import sqlite3
from datetime import datetime

def parse_date(date_str):
    """Parse date string with flexible formats."""
    if not date_str:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None

def voter_election_report(db_name="voters.db", first_name=None, last_name=None, zip_code=None):
    # Connect to the database
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Validate input parameters
    if not all([first_name, last_name, zip_code]):
        conn.close()
        return {"error": "FirstName, LastName, and ZipCode are required parameters."}

    # Get all matching VoterIds
    cursor.execute('''
        SELECT DISTINCT v.VoterId
        FROM voters v
        WHERE 
            LOWER(v.FirstName) = LOWER(?)
            AND LOWER(v.LastName) = LOWER(?)
            AND v.ZipCode = ?
    ''', (first_name, last_name, zip_code))
    voter_ids = cursor.fetchall()

    if not voter_ids:
        conn.close()
        return {"error": f"No voters found with FirstName='{first_name}', LastName='{last_name}', ZipCode='{zip_code}'."}

    results = []
    # Process each VoterId
    for voter_id in voter_ids:
        voter_id = voter_id[0]

        # Query all voter data
        cursor.execute('''
            SELECT 
                VoterId, CountyCode, FirstName, MiddleName, LastName, NameSuffix, 
                HouseNumber, StreetName, UnitType, UnitNumber, Address2, City, 
                State, ZipCode, MailAddress, MailCity, MailState, MailZipCode, 
                PhoneNumber, RegistrationDate, DOBYear, StateMcdCode, McdName, 
                PrecinctCode, PrecinctName, WardCode, School, SchSub, Judicial, 
                Legislative, StateSen, Congressional, Commissioner, Park, 
                SoilWater, Hospital, LegacyId, PermanentAbsentee
            FROM 
                voters
            WHERE 
                VoterId = ?
        ''', (voter_id,))
        voter_data = cursor.fetchone()
        all_headers = [description[0] for description in cursor.description]
        voter_dict = dict(zip(all_headers, voter_data)) if voter_data else {}

        # Define primary fields (current key info)
        primary_fields = [
            "VoterId", "FirstName", "MiddleName", "LastName", "ZipCode", 
            "RegistrationDate", "DOBYear", "City", "State"
        ]
        primary_info = {k: voter_dict[k] for k in primary_fields if k in voter_dict}

        # Additional details (all other fields)
        additional_details = {k: v for k, v in voter_dict.items() if k not in primary_fields}

        # Query election history
        cursor.execute('''
            SELECT 
                VoterId AS "Voter ID",
                ElectionDate AS "Election Date",
                ElectionDescription AS "Election Description",
                VotingMethod AS "Voting Method"
            FROM 
                election_history
            WHERE 
                VoterId = ?
            ORDER BY 
                ElectionDate DESC
        ''', (voter_id,))
        election_data = cursor.fetchall()
        election_headers = [description[0] for description in cursor.description]
        election_list = [dict(zip(election_headers, row)) for row in election_data] if election_data else []

        results.append({
            "voter_info": primary_info,
            "additional_details": additional_details,
            "election_history": election_list
        })

    conn.close()
    return {"results": results}