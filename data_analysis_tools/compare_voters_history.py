#!/usr/bin/env python3
"""
compare_voters_history.py
Tracks:
  • Last 5 elections (by date) with voter turnout
  • voters removed
  • histories changed
  • voters who moved
Usage:
    python3 compare_voters_history.py ems251109.db ems251005.db
"""

import sqlite3
import pandas as pd
import sys
from pathlib import Path

# -------------------------------------------------
COUNTY_LIST = [
    ('01', 'AITKIN'), ('02', 'ANOKA'), ('03', 'BECKER'), ('04', 'BELTRAMI'),
    ('05', 'BENTON'), ('06', 'BIG STONE'), ('07', 'BLUE EARTH'), ('08', 'BROWN'),
    ('09', 'CARLTON'), ('10', 'CARVER'), ('11', 'CASS'), ('12', 'CHIPPEWA'),
    ('13', 'CHISAGO'), ('14', 'CLAY'), ('15', 'CLEARWATER'), ('16', 'COOK'),
    ('17', 'COTTONWOOD'), ('18', 'CROW WING'), ('19', 'DAKOTA'), ('20', 'DODGE'),
    ('21', 'DOUGLAS'), ('22', 'FARIBAULT'), ('23', 'FILLMORE'), ('24', 'FREEBORN'),
    ('25', 'GOODHUE'), ('26', 'GRANT'), ('27', 'HENNEPIN'), ('28', 'HOUSTON'),
    ('29', 'HUBBARD'), ('30', 'ISANTI'), ('31', 'ITASCA'), ('32', 'JACKSON'),
    ('33', 'KANABEC'), ('34', 'KANDIYOHI'), ('35', 'KITTSON'), ('36', 'KOOCHICHING'),
    ('37', 'LAC QUI PARLE'), ('38', 'LAKE'), ('39', 'LAKE OF THE WOODS'), ('40', 'LE SUEUR'),
    ('41', 'LINCOLN'), ('42', 'LYON'), ('43', 'MCLEOD'), ('44', 'MAHNOMEN'),
    ('45', 'MARSHALL'), ('46', 'MARTIN'), ('47', 'MEEKER'), ('48', 'MILLE LACS'),
    ('49', 'MORRISON'), ('50', 'MOWER'), ('51', 'MURRAY'), ('52', 'NICOLLET'),
    ('53', 'NOBLES'), ('54', 'NORMAN'), ('55', 'OLMSTED'), ('56', 'OTTER TAIL'),
    ('57', 'PENNINGTON'), ('58', 'PINE'), ('59', 'PIPESTONE'), ('60', 'POLK'),
    ('61', 'POPE'), ('62', 'RAMSEY'), ('63', 'RED LAKE'), ('64', 'REDWOOD'),
    ('65', 'RENVILLE'), ('66', 'RICE'), ('67', 'ROCK'), ('68', 'ROSEAU'),
    ('69', 'ST. LOUIS'), ('70', 'SCOTT'), ('71', 'SHERBURNE'), ('72', 'SIBLEY'),
    ('73', 'STEARNS'), ('74', 'STEELE'), ('75', 'STEVENS'), ('76', 'SWIFT'),
    ('77', 'TODD'), ('78', 'TRAVERSE'), ('79', 'WABASHA'), ('80', 'WADENA'),
    ('81', 'WASECA'), ('82', 'WASHINGTON'), ('83', 'WATONWAN'), ('84', 'WILKIN'),
    ('85', 'WINONA'), ('86', 'WRIGHT'), ('87', 'YELLOW MEDICINE')
]

# -------------------------------------------------
def write_county_md(code, county_name, stats, total_new, last_5_elections):
    md_path = f"summary_{code}_{county_name.replace(' ', '_')}.md"
    with open(md_path, 'w') as f:
        f.write(f"# Voter Change Summary: {county_name} County ({code})\n\n")
        f.write(f"**Total Voters (New DB):** {total_new:,}\n\n")

        # -----------------------------
        # LAST 5 ELECTIONS
        # -----------------------------
        f.write("## Last 5 Elections (by Date)\n\n")
        if not last_5_elections.empty:
            f.write("| Election Date | Description | Voters Who Voted |\n")
            f.write("|---------------|-------------|------------------|\n")
            for _, row in last_5_elections.iterrows():
                f.write(f"| {row['ElectionDate']} | {row['ElectionDescription']} | {row['VotersWhoVoted']:,} |\n")
        else:
            f.write("_No election history found in new database._\n")
        f.write("\n")

        # -----------------------------
        # CHANGE BREAKDOWN
        # -----------------------------
        f.write("## Change Breakdown\n\n")
        f.write("| Category | Count | % of Total |\n")
        f.write("|----------|-------|------------|\n")
        for label, count in [
            ("voters removed", stats['voters_removed']),
            ("histories changed", stats['histories_changed']),
            ("voters who moved", stats['voters_who_moved'])
        ]:
            pct = (count / total_new * 100) if total_new > 0 else 0
            f.write(f"| {label} | {count:,} | {pct:.2f}% |\n")
        f.write("\n")

        # -----------------------------
        # DEFINITIONS
        # -----------------------------
        f.write("## Definitions\n\n")

        f.write("### voters removed\n")
        f.write("- **Meaning**: Voter was **in old DB** but **not in new DB**.\n")
        f.write("- **Conditions**:\n")
        f.write("  - `VoterId` exists in old DB\n")
        f.write("  - `VoterId` **missing** in new DB\n")
        f.write("- **Example**:\n")
        f.write("  ```\n")
        f.write("  Old DB: VoterId 12345 (active)\n")
        f.write("  New DB: VoterId 12345 (gone)\n")
        f.write("  → Counts as 1 \"removed\"\n")
        f.write("  ```\n\n")

        f.write("### histories changed\n")
        f.write("- **Meaning**: Existing voter with **mismatched election history** (not just new votes).\n")
        f.write("- **Conditions**:\n")
        f.write("  - Voter in both DBs\n")
        f.write("  - At least one election record has:\n")
        f.write("    - Different `ElectionDate`\n")
        f.write("    - Different `ElectionDescription`\n")
        f.write("    - Different `VotingMethod`\n")
        f.write("- **Example**:\n")
        f.write("  ```\n")
        f.write("  Old DB: 2024 General, In-Person\n")
        f.write("  New DB: 2024 General, Absentee\n")
        f.write("  → Counts as 1 \"history changed\"\n")
        f.write("  ```\n\n")

        f.write("### voters who moved\n")
        f.write("- **Meaning**: Voter **changed residential address** but kept same name and ID.\n")
        f.write("- **Conditions**:\n")
        f.write("  - Same `VoterId`\n")
        f.write("  - **Exact same full name**\n")
        f.write("  - **At least one address field changed**:\n")
        f.write("    - HouseNumber, StreetName, UnitType, UnitNumber, City, ZipCode\n")
        f.write("- **Example**:\n")
        f.write("  ```\n")
        f.write("  Old DB: 123 Main St, Aitkin, 56431\n")
        f.write("  New DB: 456 Oak Ave, Aitkin, 56431\n")
        f.write("  → Counts as 1 \"moved\"\n")
        f.write("  ```\n")

    print(f"  → {md_path}")

# -------------------------------------------------
def main():
    if len(sys.argv) != 3:
        print("Usage: python3 compare_voters_history.py <new_db> <old_db>")
        sys.exit(1)

    new_db = sys.argv[1]
    old_db = sys.argv[2]

    if not Path(new_db).exists() or not Path(old_db).exists():
        print("Error: One or both DB files not found.")
        sys.exit(1)

    print(f"Comparing:\n  New DB: {new_db}\n  Old DB: {old_db}\n")

    conn = sqlite3.connect(new_db)
    conn.execute(f"ATTACH DATABASE '{old_db}' AS db_old")

    master_summary = []

    for idx, (code, county_name) in enumerate(COUNTY_LIST, 1):
        print(f"[{idx:02d}/87] Processing County {code}: {county_name}...")

        # Total voters
        total_new = pd.read_sql_query("SELECT COUNT(*) FROM voters WHERE CountyCode = ?", conn, params=(code,)).iloc[0, 0]
        total_old = pd.read_sql_query("SELECT COUNT(*) FROM db_old.voters WHERE CountyCode = ?", conn, params=(code,)).iloc[0, 0]

        # -------------------------------------------------
        # 1. Last 5 Elections (by date) — NEW
        # -------------------------------------------------
        last_5_sql = """
        SELECT 
            ElectionDate,
            ElectionDescription,
            COUNT(DISTINCT VoterId) AS VotersWhoVoted
        FROM election_history
        WHERE VoterId IN (SELECT VoterId FROM voters WHERE CountyCode = ?)
        GROUP BY ElectionDate, ElectionDescription
        ORDER BY ElectionDate DESC
        LIMIT 5;
        """
        last_5_elections = pd.read_sql_query(last_5_sql, conn, params=(code,))

        # -------------------------------------------------
        # 2. Election history differences (for history_changed)
        # -------------------------------------------------
        diff_sql = f"""
        WITH common_voters AS (
            SELECT n.VoterId AS new_id, o.VoterId AS old_id
            FROM voters n
            JOIN db_old.voters o ON n.VoterId = o.VoterId
            WHERE n.CountyCode = ? AND o.CountyCode = ?
        ),
        matched_history AS (
            SELECT
                c.new_id AS VoterId,
                h_new.ElectionDate AS ElectionDate_new,
                h_new.ElectionDescription AS ElectionDescription_new,
                h_new.VotingMethod AS VotingMethod_new,
                h_old.ElectionDate AS ElectionDate_old,
                h_old.ElectionDescription AS ElectionDescription_old,
                h_old.VotingMethod AS VotingMethod_old
            FROM common_voters c
            LEFT JOIN election_history h_new ON h_new.VoterId = c.new_id
            LEFT JOIN db_old.election_history h_old
                ON h_old.VoterId = c.old_id
               AND h_old.ElectionDate = h_new.ElectionDate
               AND h_old.ElectionDescription = h_new.ElectionDescription
               AND h_old.VotingMethod = h_new.VotingMethod
        ),
        diff_rows AS (
            SELECT VoterId,
                   CASE
                       WHEN ElectionDate_new IS NOT NULL AND ElectionDate_old IS NULL THEN 'NEW_ELECTION'
                       WHEN ElectionDate_new IS NULL AND ElectionDate_old IS NOT NULL THEN 'MISSING_IN_NEW'
                       WHEN ElectionDate_new != ElectionDate_old
                         OR ElectionDescription_new != ElectionDescription_old
                         OR VotingMethod_new != VotingMethod_old
                         THEN 'DIFFERENT'
                       ELSE 'MATCH'
                   END AS diff_type
            FROM matched_history
            UNION ALL
            SELECT o.VoterId, 'MISSING_IN_NEW'
            FROM db_old.election_history o
            JOIN db_old.voters v ON v.VoterId = o.VoterId
            WHERE v.CountyCode = ?
              AND NOT EXISTS (SELECT 1 FROM common_voters c WHERE c.old_id = o.VoterId)
        )
        SELECT VoterId, diff_type
        FROM diff_rows
        WHERE diff_type != 'MATCH';
        """
        diff_df = pd.read_sql_query(diff_sql, conn, params=(code, code, code))

        # Classify
        voter_groups = diff_df.groupby('VoterId')['diff_type'].apply(set)
        removed_voters = voter_groups[voter_groups.apply(lambda x: 'MISSING_IN_NEW' in x)].index
        history_changed = voter_groups[voter_groups.apply(lambda x: 'DIFFERENT' in x)].index

        # -------------------------------------------------
        # 3. Address changes
        # -------------------------------------------------
        address_sql = f"""
        SELECT n.VoterId
        FROM voters n
        JOIN db_old.voters o ON n.VoterId = o.VoterId
        WHERE n.CountyCode = ? AND o.CountyCode = ?
          AND (n.HouseNumber <> o.HouseNumber
            OR n.StreetName <> o.StreetName
            OR COALESCE(n.UnitType,'') <> COALESCE(o.UnitType,'')
            OR COALESCE(n.UnitNumber,'') <> COALESCE(o.UnitNumber,'')
            OR n.City <> o.City
            OR n.ZipCode <> o.ZipCode)
          AND n.FirstName || COALESCE(n.MiddleName,'') || n.LastName
            = o.FirstName || COALESCE(o.MiddleName,'') || o.LastName;
        """
        moved_df = pd.read_sql_query(address_sql, conn, params=(code, code))
        moved_voters = len(moved_df)

        # -------------------------------------------------
        # 4. Build CSV (history + moves)
        # -------------------------------------------------
        csv_history_sql = f"""
        WITH common_voters AS (
            SELECT n.VoterId AS new_id, o.VoterId AS old_id
            FROM voters n
            JOIN db_old.voters o ON n.VoterId = o.VoterId
            WHERE n.CountyCode = ? AND o.CountyCode = ?
        ),
        matched_history AS (
            SELECT
                c.new_id AS VoterId,
                h_new.ElectionDate AS ElectionDate_new,
                h_new.ElectionDescription AS ElectionDescription_new,
                h_new.VotingMethod AS VotingMethod_new,
                h_old.ElectionDate AS ElectionDate_old,
                h_old.ElectionDescription AS ElectionDescription_old,
                h_old.VotingMethod AS VotingMethod_old,
                CASE
                    WHEN h_new.VoterId IS NULL THEN 'MISSING_IN_NEW'
                    WHEN h_old.VoterId IS NULL THEN 'NEW_ELECTION'
                    WHEN h_new.ElectionDate != h_old.ElectionDate
                      OR h_new.ElectionDescription != h_old.ElectionDescription
                      OR h_new.VotingMethod != h_old.VotingMethod
                      THEN 'DIFFERENT'
                    ELSE 'MATCH'
                END AS diff_type
            FROM common_voters c
            LEFT JOIN election_history h_new ON h_new.VoterId = c.new_id
            LEFT JOIN db_old.election_history h_old
                ON h_old.VoterId = c.old_id
               AND h_old.ElectionDate = h_new.ElectionDate
               AND h_old.ElectionDescription = h_new.ElectionDescription
               AND h_old.VotingMethod = h_new.VotingMethod
            UNION ALL
            SELECT o.VoterId, NULL, NULL, NULL,
                   o.ElectionDate, o.ElectionDescription, o.VotingMethod,
                   'MISSING_IN_NEW'
            FROM db_old.election_history o
            JOIN db_old.voters v ON v.VoterId = o.VoterId
            WHERE v.CountyCode = ?
              AND NOT EXISTS (SELECT 1 FROM common_voters c WHERE c.old_id = o.VoterId)
        )
        SELECT
            '{code}' AS CountyCode,
            '{county_name}' AS CountyName,
            mh.VoterId,
            v.FirstName || ' ' || COALESCE(v.MiddleName, '') || ' ' || v.LastName AS FullName,
            diff_type,
            ElectionDate_new,
            ElectionDescription_new,
            VotingMethod_new,
            ElectionDate_old,
            ElectionDescription_old,
            VotingMethod_old
        FROM matched_history mh
        JOIN voters v ON v.VoterId = mh.VoterId
        WHERE diff_type != 'MATCH'
        ORDER BY mh.VoterId, COALESCE(ElectionDate_new, '9999-99-99');
        """
        history_out = pd.read_sql_query(csv_history_sql, conn, params=(code, code, code))

        # Move rows
        move_names = []
        for voter_id in moved_df['VoterId']:
            voter_name = pd.read_sql_query(
                "SELECT FirstName || ' ' || COALESCE(MiddleName,'') || ' ' || LastName FROM voters WHERE VoterId = ?",
                conn, params=(voter_id,)
            ).iloc[0, 0]
            move_names.append(voter_name)

        move_out = pd.DataFrame({
            'CountyCode': [code] * moved_voters,
            'CountyName': [county_name] * moved_voters,
            'VoterId': moved_df['VoterId'],
            'FullName': move_names,
            'diff_type': ['MOVED'] * moved_voters,
            'ElectionDate_new': [None] * moved_voters,
            'ElectionDescription_new': [None] * moved_voters,
            'VotingMethod_new': [None] * moved_voters,
            'ElectionDate_old': [None] * moved_voters,
            'ElectionDescription_old': [None] * moved_voters,
            'VotingMethod_old': [None] * moved_voters
        })

        full_df = pd.concat([history_out, move_out], ignore_index=True)
        csv_name = f"diff_{code}_{county_name.replace(' ', '_')}.csv"
        full_df.to_csv(csv_name, index=False)

        # -------------------------------------------------
        # 5. Summary
        # -------------------------------------------------
        removed_count = len(removed_voters)
        history_changed_count = len(history_changed)

        stats = {
            'voters_removed': removed_count,
            'histories_changed': history_changed_count,
            'voters_who_moved': moved_voters
        }

        print(f"  voters removed: {removed_count}")
        print(f"  histories changed: {history_changed_count}")
        print(f"  voters who moved: {moved_voters}")
        print(f"  → {csv_name}")

        write_county_md(code, county_name, stats, total_new, last_5_elections)

        master_summary.append({
            'CountyCode': code,
            'CountyName': county_name,
            'total_old': total_old,
            'total_new': total_new,
            'net_change': total_new - total_old,
            'voters_removed': removed_count,
            'histories_changed': history_changed_count,
            'voters_who_moved': moved_voters
        })

    # -------------------------------------------------
    # 6. Master files
    # -------------------------------------------------
    summary_df = pd.DataFrame(master_summary)
    summary_df.to_csv('summary_all_counties.csv', index=False)

    with open('summary_all_counties.md', 'w') as f:
        f.write("# Voter Change Summary: All Counties\n\n")
        f.write(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Summary Table\n\n")
        f.write("| Code | County | Old | New | Net | Removed | History | Moved |\n")
        f.write("|------|--------|-----|-----|-----|---------|---------|-------|\n")
        for _, row in summary_df.iterrows():
            f.write(f"| {row['CountyCode']} | {row['CountyName']} | {row['total_old']:,} | {row['total_new']:,} "
                    f"| {row['net_change']:+,} | {row['voters_removed']:,} | {row['histories_changed']:,} | {row['voters_who_moved']:,} |\n")

    conn.close()
    print("\nAll done! 87 counties processed.")
    print("→ Per-county: diff_XX_COUNTY.csv + summary_XX_COUNTY.md")
    print("→ Master: summary_all_counties.csv + summary_all_counties.md")


if __name__ == '__main__':
    main()
