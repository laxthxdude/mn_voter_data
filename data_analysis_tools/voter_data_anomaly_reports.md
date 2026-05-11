# Voter Data Quality Analysis & Anomaly Reports

## Purpose
This document outlines data analytics strategies for identifying potential issues, inconsistencies, and anomalies in the Minnesota statewide voter registration and election history data. These reports help detect data quality problems, possible errors in the SOS data export, or (in extreme cases) potential irregularities.

**Important**: Most anomalies are likely data entry issues, address changes, or legacy data problems rather than fraud. These tools are for transparency and data cleaning.

## Database Schema Recap
- `voters`: VoterId (PK), FirstName, LastName, DOBYear, RegistrationDate, ZipCode, etc.
- `election_history`: VoterId, ElectionDate, ElectionDescription, VotingMethod

## Key Anomaly Categories

1. **Duplicate Voting**
2. **Temporal Inconsistencies** (voting before birth or registration)
3. **Identity Duplication** (multiple VoterIds for same person)
4. **Demographic Outliers** (age, ZIP validity)
5. **Data Completeness & Integrity**
6. **Behavioral Outliers** (unusually high activity)

## Top Recommended Reports

### 1. Voters with Duplicate Votes in the Same Election
**Why it matters**: A voter should have at most one record per election.

```sql
SELECT 
    v.VoterId,
    v.FirstName,
    v.LastName,
    v.ZipCode,
    eh.ElectionDate,
    eh.ElectionDescription,
    COUNT(*) as vote_count
FROM election_history eh
JOIN voters v ON eh.VoterId = v.VoterId
GROUP BY v.VoterId, eh.ElectionDate, eh.ElectionDescription
HAVING COUNT(*) > 1
ORDER BY vote_count DESC, ElectionDate DESC
LIMIT 20;
```

### 2. Votes Cast Before Registration Date

```sql
SELECT 
    v.VoterId, v.FirstName, v.LastName, v.RegistrationDate,
    eh.ElectionDate, eh.ElectionDescription
FROM election_history eh
JOIN voters v ON eh.VoterId = v.VoterId
WHERE eh.ElectionDate < v.RegistrationDate
ORDER BY eh.ElectionDate;
```

### 3. Votes Cast Before Birth Year

```sql
SELECT 
    v.VoterId, v.FirstName, v.LastName, v.DOBYear,
    eh.ElectionDate, eh.ElectionDescription
FROM election_history eh
JOIN voters v ON eh.VoterId = v.VoterId
WHERE v.DOBYear IS NOT NULL 
  AND CAST(strftime('%Y', eh.ElectionDate) AS INTEGER) < v.DOBYear
ORDER BY v.DOBYear;
```

### 4. Potential Duplicate Voter Registrations (same name + birth year)

```sql
SELECT 
    FirstName, LastName, DOBYear,
    COUNT(DISTINCT VoterId) as voter_ids,
    GROUP_CONCAT(DISTINCT ZipCode) as zips
FROM voters
WHERE DOBYear IS NOT NULL
GROUP BY FirstName, LastName, DOBYear
HAVING COUNT(DISTINCT VoterId) > 1
ORDER BY voter_ids DESC
LIMIT 50;
```

### 5. Most Active Voters (Top 50 by elections voted)

```sql
SELECT 
    v.VoterId, v.FirstName, v.LastName, v.ZipCode,
    COUNT(*) as elections_voted,
    MIN(eh.ElectionDate) as first_vote,
    MAX(eh.ElectionDate) as last_vote
FROM election_history eh
JOIN voters v ON eh.VoterId = v.VoterId
GROUP BY v.VoterId
ORDER BY elections_voted DESC
LIMIT 50;
```

### 6. Invalid or Non-Minnesota ZIP Codes

```sql
SELECT ZipCode, COUNT(*) as count
FROM voters
WHERE ZipCode NOT BETWEEN '55001' AND '56763'
   OR ZipCode IS NULL
GROUP BY ZipCode
ORDER BY count DESC;
```

### 7. Extremely Young or Very Old Voters Who Voted Recently

```sql
SELECT 
    v.VoterId, v.FirstName, v.LastName, v.DOBYear,
    (strftime('%Y', 'now') - v.DOBYear) as approx_age,
    MAX(eh.ElectionDate) as latest_vote
FROM voters v
JOIN election_history eh ON v.VoterId = eh.VoterId
GROUP BY v.VoterId
HAVING approx_age < 18 OR approx_age > 110
ORDER BY approx_age DESC;
```

### 8. Orphaned Election Records (no matching voter)

```sql
SELECT COUNT(*) as orphaned_elections
FROM election_history eh
LEFT JOIN voters v ON eh.VoterId = v.VoterId
WHERE v.VoterId IS NULL;
```

### 9. Voters with Frequent Address Changes
(Requires more advanced logic using name + DOB matching across records.)

### 10. Voting Method Anomalies
(e.g., Permanent Absentee voters casting in-person votes)

## Additional Ideas
- Name quality checks (unusually short names, special characters)
- Registration date outliers
- Precinct-level analysis (if adding more data)
- Fuzzy duplicate detection using full name + address similarity

## Next Steps
- Create `anomaly_reports.py` that runs these queries and exports nice formatted reports (CSV, Markdown, HTML)
- Add command-line options for filtering by year or county
- Implement fuzzy matching for better duplicate detection

This file lives in `data_analysis_tools/` to serve as living documentation for data integrity work on mnvoterreport.org.