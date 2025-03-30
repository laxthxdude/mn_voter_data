# Minnesota Voter Data

This repository provides tools to work with voter data from the Minnesota Office of the Secretary of State (OSS). The `import_to_sqlite3.py` script imports raw voter and election history data files into a SQLite3 database (`voters.db`) for easier querying and analysis. The `voter_election_report_print.py` script allows you to query the database for specific voter records.

## Prerequisites

1. **System Requirements**:
   - A system capable of running Python 3.8 or higher (Python 3.11+ recommended as of 2025).
   - Ensure you have sufficient storage:
     - Around 5–6 GB total for the OSS archive (~350 MB compressed).
     - Creation of the SQLite3 database (`voters.db`) will require approximately 3.5 GB of additional space.

2. **Python Dependencies**:
   - The script requires the following Python packages:
     - `sqlite3`, `csv`, `os`, `sys`, and `datetime` (included in Python's standard library).
     - `chardet` (for detecting file encoding).
   - Install the required external package using `pip`:
     ```bash
     pip install chardet
     ```
   - Note: The `voter_election_report_print.py` script (if used) may require additional dependencies like `argparse` and `tabulate`, as mentioned in the original README. Install them if needed:
     ```bash
     pip install tabulate
     ```

3. **OSS Voter Data Files**:
   - Obtain the voter data files from the Minnesota OSS. The file is provided as compressed archives (e.g., `.zip` files) containing raw `.txt` files for voter and election history data. See the included `readme.txt` file in the provided archive for more information on the data.

## Setup and Usage

### Step 1: Download and Uncompress OSS Voter Data
- Download the provided dataset from the Minnesota OSS provide URL, obtained and sent to you after submitting the request to the OSS for the full voter set. For example, for the February 2, 2025 exported dataset, you might have a file named `w0254202.zip`.
- Uncompress the `.zip` file to access the raw data. After extraction, you should see the following files:
  - Voter files: `Voter01.txt`, `Voter02.txt`, ..., `Voter08.txt` (voter records).
  - Election history files: `Election01.txt`, `Election02.txt`, ..., `Election08.txt` (election history).
  - A `readme.txt` file may also be included for reference.
- The script expects exactly eight voter files and eight election files, as supplied by the OSS.

### Step 2: Clone the Repository
Clone this repository to your local machine:
```bash
git clone https://github.com/laxthxdude/mn_voter_data.git
cd mn_voter_data
```

### Step 3: Import Data into SQLite3 Database
- Place the extracted `.txt` files (e.g., `Voter01.txt`, `Election01.txt`, etc.) into the same directory as the `import_to_sqlite3.py` script.
- Run the `import_to_sqlite3.py` script to parse the raw data files and create a SQLite3 database (`voters.db`):
  ```bash
  python3 import_to_sqlite3.py
  ```
- **What the Script Does**:
  - Creates a SQLite3 database named `voters.db` with two tables:
    - `voters`: Stores voter information (e.g., VoterId, FirstName, LastName, ZipCode, etc.).
    - `election_history`: Stores election history (e.g., VoterId, ElectionDate, ElectionDescription, VotingMethod).
  - Adds indexes on `FirstName`, `LastName`, and `ZipCode` in the `voters` table for faster querying.
  - Processes each `VoterXX.txt` and `ElectionXX.txt` file:
    - Detects the file encoding using `chardet`.
    - Parses the `.txt` files as CSV (with `"` as the quote character).
    - Inserts data into the respective tables, handling errors gracefully.
  - Normalizes dates to `YYYY-MM-DD` format using the `parse_date` function.
- **Notes**:
  - The script includes verbose logging to track progress, including the number of rows processed and imported for each file.
  - The OSS data may contain duplicate records (e.g., "David D. Director" appearing in multiple files like `Voter04.txt` and `Voter07.txt`). These duplicates are expected and will be skipped with a `UNIQUE constraint failed: voters.VoterID` error.
  - If a row has an incorrect number of fields or other errors (e.g., invalid data types), the script will log the error and skip the row.
  - At the end, the script provides a summary of total rows processed versus imported, along with any errors encountered (up to the first 10 errors are displayed).

### Step 4: Query the Database
- After running the script, a `voters.db` SQLite3 database will be created in the same directory.
- Use the `voter_election_report_print.py` script to query records from the database. For example, to query records for a voter with the first name "Cory" and last name "Johnson":
  ```bash
  python3 voter_election_report_print.py --first-name "Cory" --last-name "Johnson" --zip
  ```
- **Options for `voter_election_report_print.py`** (assumed based on original README):
  - `--first-name`: Specify the voter's first name.
  - `--last-name`: Specify the voter's last name.
  - `--zip`: Optionally include the voter's ZIP code in the output.
- Alternatively, you can query the database directly using any SQLite3-compatible tool (e.g., the `sqlite3` command-line tool):
  ```bash
  sqlite3 voters.db
  SELECT * FROM voters WHERE FirstName = 'Cory' AND LastName = 'Johnson';
  ```

### Step 5: Analyze and Explore
- The `voters.db` database contains two tables:
  - `voters`: Includes fields like `VoterId`, `FirstName`, `LastName`, `ZipCode`, `RegistrationDate`, `DOBYear`, etc.
  - `election_history`: Includes fields like `VoterId`, `ElectionDate`, `ElectionDescription`, and `VotingMethod`.
- The database can be explored using tools like DBeaver, SQLiteStudio, or custom Python scripts.

## Additional Notes
- **Performance**: Importing large datasets may take some time depending on your system. The script provides verbose logging to track progress, including total rows processed and imported.
- **Data Quality**:
  - The OSS data may contain inconsistencies, such as duplicate voter records. The script handles these by enforcing a `UNIQUE` constraint on `VoterId` and skipping duplicates.
  - Rows with incorrect field counts or unparseable data (e.g., invalid dates) are skipped, with errors logged for review.
- **Date Parsing**: The script normalizes dates to `YYYY-MM-DD` format and supports multiple input formats (e.g., `MM/DD/YYYY`, `YYYY-MM-DD HH:MM:SS`).
- **Error Handling**: The script logs errors for rows that fail to import (e.g., due to missing fields, invalid data types, or duplicate `VoterId` values). Check the output for details.
- **Updates**: As of March 30, 2025, this script is designed to work with the OSS voter data format described. If the OSS changes their data structure (e.g., number of fields or file naming), the script may need to be updated.

## Contributing
Contributions are welcome! If you encounter issues, have suggestions for improvements, or want to add new features (e.g., support for additional file formats or enhanced error reporting), please open an issue or submit a pull request on GitHub.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Happy Querying! 😄
