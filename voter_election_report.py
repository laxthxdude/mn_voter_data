import sqlite3
import sys
from datetime import datetime
import argparse
from tabulate import tabulate

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
        print("Error: FirstName, LastName, and ZipCode are required parameters.")
        conn.close()
        return

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
        print(f"No voters found with FirstName='{first_name}', LastName='{last_name}', ZipCode='{zip_code}'.")
        conn.close()
        return

    # Process each VoterId
    for voter_id in voter_ids:
        voter_id = voter_id[0]  # Extract the VoterId value

        # Query voter data
        cursor.execute('''
            SELECT 
                v.VoterId AS "Voter ID",
                v.FirstName AS "First Name",
                v.MiddleName AS "Middle Name",
                v.LastName AS "Last Name",
                v.ZipCode AS "Zip Code",
                v.RegistrationDate AS "Registration Date",
                v.DOBYear AS "Birth Year",
                v.City AS "City",
                v.State AS "State"
            FROM 
                voters v
            WHERE 
                v.VoterId = ?
        ''', (voter_id,))
        voter_data = cursor.fetchone()
        if voter_data:
            # Get column names from cursor description
            headers = [description[0] for description in cursor.description]
            # Print voter data as a table with proper headers
            print(tabulate([voter_data], headers=headers, tablefmt="pretty", showindex=False))

        # Print separator
        print(tabulate([["--------------------------------- Voter Election History --------------------------------- "]], tablefmt="pretty"))

        # Query election history
        cursor.execute('''
            SELECT 
                eh.VoterId AS "Voter ID",
                eh.ElectionDate AS "Election Date",
                eh.ElectionDescription AS "Election Description",
                eh.VotingMethod AS "Voting Method"
            FROM 
                election_history eh
            WHERE 
                eh.VoterId = ?
            ORDER BY 
                eh.ElectionDate DESC
        ''', (voter_id,))
        election_data = cursor.fetchall()
        if election_data:
            # Get column names from cursor description
            headers = [description[0] for description in cursor.description]
            print(tabulate(election_data, headers=headers, tablefmt="pretty", showindex=False))
        else:
            print(tabulate([["No election history found."]], tablefmt="pretty"))
        print()  # Blank line between voters

    # Close connection
    conn.close()

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Generate a report of voter data and election history.")
    parser.add_argument("--first-name", required=True, help="First name of the voter")
    parser.add_argument("--last-name", required=True, help="Last name of the voter")
    parser.add_argument("--zip-code", required=True, help="Zip code of the voter")
    parser.add_argument("--db-name", default="voters.db", help="Database name (default: voters.db)")

    # Parse arguments
    args = parser.parse_args()

    # Run the report
    voter_election_report(args.db_name, args.first_name, args.last_name, args.zip_code)