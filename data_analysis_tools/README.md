# Voter data anomaly reports

This file describes `voter_data_anomaly_report.py`, which sits in the same folder. The script opens a Minnesota voter SQLite database read-only and writes a Markdown report, an HTML report, and one CSV per finding under `anomaly_reports/`.

These checks look for inconsistent or incomplete records. Most hits are data entry, a repeated line in the history file, or two different people with the same name. They are not, by themselves, evidence of fraud.

## How to run

```bash
python3 voter_data_anomaly_report.py
python3 voter_data_anomaly_report.py --db WO261115.db --out anomaly_reports
python3 voter_data_anomaly_report.py --county 27 --year 2024 --election 2024-11-05 --CD4 --SD41
```

With no `--db`, the script uses the newest non-empty `.db` next to itself.

| Argument | Effect |
| --- | --- |
| `--county 27` or `--county 2` | Keep that `CountyCode`. A one-digit code is stored as two digits, so `2` becomes `02`. |
| `--year 2024` | Limit history checks to that election year. Name, address, ZIP, and the voter-record completeness counts ignore the year. |
| `--election 2024-11-05` | Limit history checks to that `ElectionDate`. `11/05/2024` is accepted and stored as `2024-11-05`. Every contest on that date is included. Name, address, ZIP, and the voter-record completeness counts ignore it. |
| `--CD4` | Keep voters whose `Congressional` field is `4`. This extract stores districts `1` through `8`. `--cd4` is accepted. Pass only one. |
| `--SD41` | Keep voters whose `StateSen` field is `41`. This extract stores senate districts `1` through `67`. `--sd41` is accepted. Pass only one. |
| `--limit 25` | Rows shown in the Markdown and HTML tables. The default is 25. |
| `--csv-limit 5000` | Maximum rows in each CSV. The default is 5000. The duplicate-vote CSV and the permanent-absentee CSV include every match. |

County, congressional district, and senate district can be combined. A history row with no voter record has none of those fields, so the orphan check is skipped when any of them is set.

`--year` and `--election` must fall from 1900 through 2100. An election date has to fall inside `--year` when both are set. The database is never modified.

## What the script does not check

`RegistrationDate` is the current registration. Minnesota replaces it when a record is updated, and the original date is gone. Votes dated before that field are not reported.

Fuzzy name matching is not implemented. The voter file has one current address per `VoterId`, so there is no address history to scan.

## Reports

The CSV names match the order below.

### 1. Duplicate votes in the same election

File: `csv/01_duplicate_votes.csv`

A group is one voter, one election date, and one election description with more than one history row. The history file has no unique key, so a repeated source line is stored as repeated rows.

`VoteCount` is the number of rows. `VotingMethods` lists each distinct method, separated by a comma, in alphabetical order. Methods are `A` absentee, `E` early, `M` mail, `N` unknown, and `P` in person. One method means the file repeated a line. More than one method is the stronger conflict. A blank method is an empty entry, so a blank plus mail is `, M`.

The CSV includes every group, ordered by the most recent election date and then the largest `VoteCount`. The table shows the first rows of that order. Names and ZIP are filled for every exported group.

### 2. Votes in or before DOBYear

File: `csv/02_votes_before_birth.csv`

`DOBYear` is a year, not a birthday. `YearsBeforeBirth` is `DOBYear` minus the election year. A value of `1` or more means the election was in an earlier calendar year. A value of `0` means the election was in the birth year. Both are included. The CSV keeps the largest gaps, up to the CSV cap.

### 3. Registration dated before the birth year

File: `csv/03_registration_before_birth.csv`

The registration year on the voter record is earlier than `DOBYear`. This uses the registration field itself. A later renewal does not explain a registration year before the birth year. One known placeholder of this kind is `1850-01-01`. The CSV keeps the earliest registration dates, up to the CSV cap.

### 4. Possible duplicate registrations

File: `csv/04_duplicate_names.csv`

Same first name, middle name, last name, and `DOBYear` on more than one `VoterId`. The middle name has to match exactly. A blank middle name matches only another blank middle name. An initial does not match a full middle name. Padding around the middle name is ignored. Blank first or last names are excluded.

This is a candidate list. Common names still collide. A year filter does not apply. `example_ids` lists up to eight `VoterId` values for the group. The CSV keeps the largest groups, up to the CSV cap.

### 5. Same name and birth year at more than one address

File: `csv/05_same_name_multiple_addresses.csv`

The same groups as report 4, restricted to groups whose house number, street, city, or first five ZIP digits differ. Each voter has one current address, so this is a stand-in for an address change or a second registration. It is not an address history. The CSV keeps the groups with the most addresses, up to the CSV cap.

### 6. Most active voters

File: `csv/06_most_active_voters.csv`

Voters with the most history rows. A repeated election line increases the count. Compare the duplicate-vote report before treating a high number as turnout. The CSV keeps the highest counts, up to the CSV cap.

### 7. Votes at an implausible age

File: `csv/07_implausible_age.csv`

Age is election year minus `DOBYear`, so it can be off by one year. The report flags:

- a history row before the year the person turns 18
- a history row at an age over 110
- a voter who has history and whose age in the latest election year of this run is under 18 or over 110

Someone who turns 18 in the election year is not listed. Minnesota lets some 17-year-olds vote in a primary when they will be 18 by the general election, and that case falls in the year they turn 18.

Current age uses the latest election year in the filtered history, not the year the script is run. For voters over 110, the summary also counts those whose latest vote is within four years of that year. The CSV keeps the most extreme ages, up to the CSV cap.

### 8. Residence ZIP codes

File: `csv/08_zip_codes.csv`

The residence `ZipCode` is judged on its first five digits, against `55001` through `56763`. A ZIP+4 such as `55401-1234` stays in Minnesota when those digits are in range. A string comparison of the whole value would mislabel it.

The detail lists blank ZIPs, malformed ZIPs, Minnesota ZIPs with an unusual suffix, and ZIPs outside that range. Border codes such as North Dakota `582xx` can be real and are still outside the range. Mailing ZIP is not checked. A year filter does not apply. The CSV keeps the largest ZIP counts, up to the CSV cap.

### 9. Election rows with no voter record

File: `csv/09_orphaned_elections.csv`

History rows whose `VoterId` is not in the voter table. This check is statewide. It is not computed when a county, congressional district, or senate district filter is set.

### 10. Permanent-absentee flag with an in-person vote

File: `csv/10_permanent_absentee_in_person.csv`

`PermanentAbsentee` is `X`, and `VotingMethod` is `P`. A permanent-absentee voter is still allowed to vote in person, so this is a pattern to review, not a conflict by itself. The summary also counts history rows whose method is outside `A`, `E`, `M`, `N`, and `P`.

The CSV includes every matching in-person row, newest election date first. The table shows the first rows of that order.

### 11. Completeness of the voter record

No CSV. The summary counts blank first names, blank last names, one-letter first names, and missing birth years, and it shows the birth-year and registration-date ranges.

Voters with no history row are counted only when no election year and no election date are selected. Either filter sees only part of each voter's history, so that count is omitted. The count of voters with at least one history row still follows the history filter.

## Still open

- Fuzzy duplicate detection is not part of this script.
- Precinct-level analysis would need more than this extract.
