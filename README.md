# MNEIS Voter Report Project

Welcome to the Minnesota Election Integrity Solutions (MNEIS) Voter Report project! This tool allows Minnesota citizens to verify their voter registration information and election history using publicly available data from the Minnesota Secretary of State. The project aims to enhance election integrity by enabling individuals to ensure the accuracy of their voter records. This project contains various elements which might be useful for others working with the MN OSS public voter data. 

## Overview

The goal of this project is to provide a web-based application designed to provide Minnesota voters with access to their voter registration details and election participation history. The system uses a SQLite database populated with voter and election data, a Flask web server for the frontend, and Python scripts to process and query the data. Users can input their first name, last name, and zip code to retrieve a personalized report.

The project emphasizes transparency, privacy, and compliance with Minnesota Statutes Chapter 13, ensuring that all data usage aligns with legal requirements and prioritizes user consent.

The project aims to expand in the future to provide additional useful data analysis tooling to analyze and report on data quality issues and compliance topics as related to Minnesota Statue for voter data. For example, in the future the ability to quickly and easily search on duplicate data, voters that are missing data, voters who are active but should not be, etc. 

## Features

- Importing to a modern database: Python3 script which can import the provided MN OSS voter history data into a sqlite database (making data querying fast and easy).
- Voter Information Lookup: Search for voter records by first name, last name, and zip code.
- Election History: View a detailed history of elections in which the voter participated, including dates, descriptions, and voting methods.
- Data Validation: Client-side validation ensures accurate input (e.g., valid Minnesota zip codes between 55001 and 56763).
- Responsive Design: Built with Bootstrap for a user-friendly experience across devices.
- Command-Line Alternative: Scripts are available for generating reports directly from the terminal.

This Python script `import_to_sqlite3.py` creates a SQLite database (`voters.db`) and imports voter registration and election history data from a set of CSV files (`Voter01.txt` to `Voter08.txt` and `Election01.txt` to `Election08.txt`). It processes the files, handles encoding detection, and logs errors, providing a summary of total and imported rows for both voter and election data. The CSV files are part of the data set as obtained from the Minnesota OSS when requesting a full voter history data set for $46 as a Minnesota resident. 

## Technical Details for `import_to_sqlite3.py`
- Using python, creates a local sqlite (open source, free) database, with two tables:
  - `voters`: Stores voter registration details (e.g., `VoterId`, `FirstName`, `LastName`, `City`, `State`, `DOBYear`, etc.).
  - `election_history`: Stores voting history (e.g., `VoterId`, `ElectionDate`, `ElectionDescription`, `VotingMethod`).
- Imports data from 8 voter files (`Voter01.txt` to `Voter08.txt`) in `voters` and 8 election files (`Election01.txt` to `Election08.txt`) into `election_history`. 
- Detects file encoding using `chardet` to handle various text formats.
- Includes error handling for malformed rows and provides a detailed error log.
- Adds indexes on `FirstName`, `LastName`, and `ZipCode` for efficient querying.
- Normalizes dates to `YYYY-MM-DD` format.
- Prints a summary of total rows vs. imported rows, with warnings for discrepancies.

## Prerequisites for use of `import_to_sqlite3.py`
- A computer with internet access and at least 4GB of free space.
- Python 3 installed (see installation steps below if you don’t have it).
- Required Python libraries: `sqlite3` (built-in), `csv` (built-in), `chardet`, `os` (built-in), `sys` (built-in), `datetime` (built-in).

## Installation

### Step 1: Install Python
If you don’t have Python installed, follow these steps based on your operating system:

#### macOS
1. **Check if Python is Installed**:
   - Open Terminal (Applications > Utilities > Terminal).
   - Run: `python3 --version`
   - If you see a version (e.g., `Python 3.9.6`), skip to Step 2. Otherwise, proceed.
2. **Install Homebrew (if not installed)**:
   - Run: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
   - Follow the prompts to install.
3. **Install Python**:
   - Run: `brew install python`
   - Verify: `python3 --version`

#### Windows
1. **Download Python**:
   - Visit [python.org/downloads](https://www.python.org/downloads/).
   - Download the latest Python 3 installer (e.g., Python 3.11.x).
2. **Run the Installer**:
   - Double-click the downloaded file.
   - Check "Add Python to PATH" at the bottom of the installer window.
   - Click "Install Now" and follow the prompts.
3. **Verify Installation**:
   - Open Command Prompt (search "cmd" in Start menu).
   - Run: `python --version`
   - You should see the version number.

#### Linux (Ubuntu/Debian)
1. **Update Package List**:
   - Open a terminal.
   - Run: `sudo apt update`
2. **Install Python**:
   - Run: `sudo apt install python3 python3-pip`
   - Verify: `python3 --version`

### Step 2: Install Dependencies
The script requires the `chardet` library for encoding detection. Install it using `pip`:

1. **Open a Terminal/Command Prompt**:
   - macOS: Terminal
   - Windows: Command Prompt
   - Linux: Terminal
2. **Install `chardet`**:
   - Run: `python3 -m pip install chardet`
   - On Windows, you might use `python -m pip install chardet` if `python3` isn’t recognized.
   - Other required modules (`sqlite3`, `csv`, `os`, `sys`, `datetime`) are part of Python’s standard library and don’t need separate installation.

## Usage

1. **Prepare Your Input Files**:
   - Ensure the script `import_to_sqlite3.py` in the same directory as your input files (as extracted from the MN OSS provided archive:
     - Voter files: `Voter01.txt` to `Voter08.txt` (CSV format, 38 columns).
     - Election files: `Election01.txt` to `Election08.txt` (CSV format, 4 columns).
   - **Voter File Format** (38 columns, with headers):
     ```
     VoterId,CountyCode,FirstName,MiddleName,LastName,NameSuffix,HouseNumber,StreetName,UnitType,UnitNumber,Address2,City,State,ZipCode,MailAddress,MailCity,MailState,MailZipCode,PhoneNumber,RegistrationDate,DOBYear,StateMcdCode,McdName,PrecinctCode,PrecinctName,WardCode,School,SchSub,Judicial,Legislative,StateSen,Congressional,Commissioner,Park,SoilWater,Hospital,LegacyId,PermanentAbsentee
     ```
   - **Election File Format** (4 columns, with headers):
     ```
     VoterId,ElectionDate,ElectionDescription,VotingMethod
     ```
   - Example `Voter01.txt`:
     ```
     VoterId,CountyCode,FirstName,MiddleName,LastName,NameSuffix,HouseNumber,StreetName,UnitType,UnitNumber,Address2,City,State,ZipCode,MailAddress,MailCity,MailState,MailZipCode,PhoneNumber,RegistrationDate,DOBYear,StateMcdCode,McdName,PrecinctCode,PrecinctName,WardCode,School,SchSub,Judicial,Legislative,StateSen,Congressional,Commissioner,Park,SoilWater,Hospital,LegacyId,PermanentAbsentee
     12345,HOU,John,A,Doe,,123,Main St,APT,4,,Houston,MN,55943,PO Box 123,Houston,MN,55943,555-1234,2020-01-15,1980,001,Houston City,001,Precinct 1,01,Houston ISD,01,01,01,01,01,01,01,01,,Y
     ```
   - Example `Election01.txt`:
     ```
     VoterId,ElectionDate,ElectionDescription,VotingMethod
     12345,11/03/2020,General Election,In-Person
     ```

2. **Run the Script**:
   - Save the script as `voter_db_importer.py`.
   - Open a terminal in the directory containing the script and input files.
   - Run: `python3 voter_db_importer.py`
   - The script uses a default database name (`voters.db`), which you can modify by editing the `create_database()` call if desired.

3. **Output**:
   - Creates `voters.db` with two tables: `voters` and `election_history`.
   - Prints processing details, including:
     - Number of rows processed per file.
     - Total rows vs. imported rows for voters and elections.
     - Warnings for missing files or row discrepancies.
     - Error log for malformed rows (first 10 errors shown).
   - Example output:
     ```
     Processing voter files...
     Processing Voter01.txt with 100 rows.
     Imported 99 rows from Voter01.txt.
     ...
     Processing election history files...
     Processing Election01.txt with 50 rows.
     Imported 50 rows from Election01.txt.
     ...
     Total voter rows across all files (excluding headers): 800
     Total imported voter rows into voters.db: 795
     Warning: Imported voter rows (795) do not match total voter rows in files (800).
     Total election rows across all files (excluding headers): 400
     Total imported election rows into voters.db: 400
     Encountered 5 errors across all files:
       Row 2 in Voter01.txt: Incorrect number of fields (37 instead of 38). Skipping.
       ...
     ```

## Notes
- **File Requirements**: The script expects exactly 8 voter and 8 election files named as specified. Missing files are skipped with a warning.
- **Error Handling**: Rows with incorrect field counts or unparseable data (e.g., invalid dates, non-integer `VoterId`) are logged and skipped.
- **Date Parsing**: Supports formats like `MM/DD/YYYY`, `YYYY-MM-DD HH:MM:SS`, and normalizes to `YYYY-MM-DD`.
- **Performance**: Indexes on `FirstName`, `LastName`, and `ZipCode` improve query performance for large datasets.
- **Customization**: To use a different database name, modify the `create_database()` call, e.g., `create_database("custom_voters.db")`.
- **Import Time**: On an M4 Mac mini 64GB, the import time is just a few minutes. Your importing time may vary. 

## Technical Details for ## Technical Details for `voter_election_report_printf.py`
- Using `voter_election_report_printf.py`, you can use your Terminal (Command Prompt) to directly query the resulting sqlite database (`voters.db`). 
- Example: Run the report script with arguments: `python3 voter_election_report_printf.py --first-name "John" --last-name "Doe" --zip-code "55101"`
- Output will display voter information and election history in a tabulated format.

```
+----------+------------+-------------+-----------+----------+------------------+------------+----------+-------+
| Voter ID | First Name | Middle Name | Last Name | Zip Code | Registration Date | Birth Year | City     | State |
+----------+------------+-------------+-----------+----------+------------------+------------+----------+-------+
| 123456   | John       | A           | Doe       | 55101    | 2020-01-15       | 1980       | St. Paul | MN    |
+----------+------------+-------------+-----------+----------+------------------+------------+----------+-------+
+---------------------------------------------------------------+
| --------------------- Voter Election History ----------------- |
+---------------------------------------------------------------+
+----------+-----------------+-------------------------+--------------+
| Voter ID | Election Date   | Election Description    | Voting Method |
+----------+-----------------+-------------------------+--------------+
| 123456   | 2022-11-08      | State General Election  | P            |
| 123456   | 2020-11-03      | State General Election  | A            |
+----------+-----------------+-------------------------+--------------+
```


## Technical Details for `voter_election_report.py`
- Core logic for querying the database and returning voter reports as a dictionary (used by the web app).

## Technical Details for `app.py`
- Flask application to serve the web interface.

### Requirements for use via web browser
- Python 3.7+
- SQLite3
- Flask (`pip install flask`)
- Tabulate (`pip install tabulate`) - for command-line reporting
- Web Browser (e.g., Safari, Chrome, Firefox) for the web interface

### Installation for use via web browser
- Ensure you have generated the required `voters.db`
- Ensure you have installed the required dependencies for `flask` and `tabulate`
- With the `voters.db` and `app.py` and `index.html` in the same directory, execute `phthon3 app.py`. This starts the Flask server, on port 5000.
- Open a browser and navigate to `http://127.0.0.1:5000`. You should see a nice HTML page you can use to look up voter information. 

## Technical Details for `readme.txt`
- Documentation from the Minnesota Secretary of State about voter file formats and abbreviations.

## Technical Details for `index.html`
- HTML template for the web interface, styled with Bootstrap. Handles form input and displays results.


## Contributing
Feel free to fork this repository, submit issues, or create pull requests with enhancements (e.g., additional file support, custom date formats).

## License
This project is unlicensed and provided as-is for personal use. No warranty is implied.
