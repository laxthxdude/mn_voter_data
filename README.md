# Minnesota Voter Data

Working with data from OSS for MN Voter Data.

Prerequisites 
1. System capable of running python3
2. System with python3 additional dependencies installed (sqlite3, csv, chardet, os, sys, datatime, argparse, tabulate)
3. System with available storage (Around 5-6GB in tota: ~350MB for OSS archive, will expand to several GB flat files, creation of sqlite3 database will require ~3.5GB)

Basic Steps: 
1. Uncompress the received file from OSS. The file should be the FULL dataset (all available fields). Example: `WO250202.zip` for the February 2, 2025 exported data set.
2. The resulting `Voter01.txt`...`Voter08.txt` files and `Election01.txt`...`Election08.txt` are expanded along with a `readme.txt` file.
3. Execute the `import_to_sqlite3.py` in the same working directory as the `Voter01.txt`...`Election01.txt` files to parse the raw data files into a sqlite3 database. It expects the standard eight files for each (Voters, Election History) as supplied from the OSS. Import speed depends on your system, verbose logging will display as things run. The OSS inserts some dummy duplicate records (David D. Director) into each Voter0x.txt file so 7 errors showing up from Voter02.txt...Voter03.txt is expected as those will be skipped (duplicates).
   ``` bash
   python3 import_to_sqlite3.py
   ```
   You should now have a newly created `voters.db` sqlite3 database in the same directory. 
4. Execute the `voter_election_report.py` to query for records in the resulting database.
   ``` bash
   python3 voter_election_report.py --first-name "Cory" --last-name "Johnson" --zip-code "55947" --db-name "voters.db"
   ```
5. Happy querying :-) 
