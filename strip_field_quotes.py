#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remove the quotes wrapped around every field of SOS voter and election files.

The Secretary of State files are comma-separated, and every field is wrapped
in double quotes, including fields that do not need them:

    "ROYAL","ALAN","ANDERSON","","207","STEVENS AVE "

Those wrapping quotes are syntax, not data. This script parses each row and
writes it back with quotes only on a field that contains a comma, a quote,
or a line break:

    ROYAL,ALAN,ANDERSON,,207,STEVENS AVE ,"P.O, BOX 384"

The comma inside "P.O, BOX 384" is part of the address. The quotes stay on
that field so the comma is not read as a new column. Every other character
is unchanged, including trailing spaces and characters such as ½.

Each output file is checked by reading it back and comparing every field to
the original. The original is replaced only after that check passes.
"""

import argparse
import codecs
import csv
import os
import sys
import tempfile

csv.field_size_limit(sys.maxsize)


def detect_encoding(path):
    """utf-8-sig when the file is valid UTF-8, otherwise Windows-1252.

    Voter07 contains a single ½ (byte 0xBD). That byte is not UTF-8.
    Writing the file back in the same encoding keeps that character intact.
    """
    # 'utf-8', not 'utf-8-sig': writing with utf-8-sig would insert a BOM
    # that was not in the source file.
    decoder = codecs.getincrementaldecoder("utf-8")()
    with open(path, "rb") as raw:
        while True:
            chunk = raw.read(1 << 20)
            if not chunk:
                break
            try:
                decoder.decode(chunk)
            except UnicodeDecodeError:
                return "cp1252"
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return "cp1252"
    return "utf-8"


def field_needs_quotes(field):
    return any(char in field for char in ',"\r\n')


def convert_file(source_path, dest_path, encoding):
    """Write source_path to dest_path with unnecessary quotes removed.

    Returns (rows, fields_still_quoted).
    """
    rows = 0
    fields_still_quoted = 0
    with open(source_path, "r", encoding=encoding, newline="") as source, \
            open(dest_path, "w", encoding=encoding, newline="") as dest:
        reader = csv.reader(source, delimiter=",", quotechar='"', doublequote=True)
        writer = csv.writer(
            dest,
            delimiter=",",
            quotechar='"',
            doublequote=True,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\r\n",
        )
        for row in reader:
            writer.writerow(row)
            rows += 1
            fields_still_quoted += sum(1 for field in row if field_needs_quotes(field))
    return rows, fields_still_quoted


def verify_files(source_path, dest_path, encoding):
    """Raise SystemExit if any parsed field differs from the original."""
    with open(source_path, "r", encoding=encoding, newline="") as source, \
            open(dest_path, "r", encoding=encoding, newline="") as dest:
        original = csv.reader(source, delimiter=",", quotechar='"', doublequote=True)
        rewritten = csv.reader(dest, delimiter=",", quotechar='"', doublequote=True)
        for line_num, (left, right) in enumerate(zip(original, rewritten), start=1):
            if left != right:
                raise SystemExit(
                    f"{os.path.basename(source_path)}:{line_num} field mismatch\n"
                    f"  original: {left}\n"
                    f"  rewritten: {right}"
                )
        extra_original = next(original, None)
        extra_rewritten = next(rewritten, None)
    if extra_original is not None or extra_rewritten is not None:
        raise SystemExit(
            f"{os.path.basename(source_path)} row count changed during rewrite"
        )


def target_files(directory):
    chosen = []
    for name in os.listdir(directory):
        stem, ext = os.path.splitext(name)
        if ext.lower() != ".txt":
            continue
        lower = stem.lower()
        if lower.startswith("voter") or lower.startswith("election"):
            suffix = lower[5:] if lower.startswith("voter") else lower[8:]
            if suffix.isdigit():
                chosen.append(os.path.join(directory, name))
    chosen.sort(key=lambda path: os.path.basename(path).lower())
    return chosen


def strip_directory(directory):
    directory = os.path.abspath(directory)
    paths = target_files(directory)
    if not paths:
        raise SystemExit(f"No VoterNN.txt or ElectionNN.txt files in {directory}")

    print(f"Directory: {directory}")
    print(f"Files:     {len(paths)}\n")
    total_rows = 0
    total_kept = 0
    for path in paths:
        encoding = detect_encoding(path)
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=os.path.basename(path) + ".",
            suffix=".stripping",
            dir=directory,
        )
        os.close(tmp_fd)
        try:
            print(f"→ {os.path.basename(path)} ({encoding})", flush=True)
            rows, kept = convert_file(path, tmp_path, encoding)
            verify_files(path, tmp_path, encoding)
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        total_rows += rows
        total_kept += kept
        print(f"   {rows:,} rows verified, {kept:,} fields kept their quotes\n", flush=True)

    print("=" * 60)
    print(f"Rows verified             : {total_rows:,}")
    print(f"Fields that kept quotes   : {total_kept:,}")
    print("Every field matches the original file.")
    return 0


def _self_test():
    """Round-trip a file that has the same quoting patterns as the SOS extract."""
    import shutil

    directory = tempfile.mkdtemp(prefix="strip-quotes-")
    try:
        voter_path = os.path.join(directory, "Voter01.txt")
        election_path = os.path.join(directory, "Election01.txt")
        rows = [
            ["VoterId", "CountyCode", "FirstName", "StreetName", "MailAddress", "Note"],
            ["4758438", "23", "ROYAL", "STEVENS AVE ", "P.O, BOX 384", ""],
            ["3051616", "83", "PAMELA", "290TH ST ", "P O BOX 161", "MADELIA,"],
            ["42", "69", "HALF", "12½ ST", "", 'SAY "HI"'],
            ["5815561", "27", "RHEA", "UNIVERSITY AVE SE", "912-B1,B2", "line\nbreak"],
        ]
        elections = [
            ["VoterId", "ElectionDate", "ElectionDescription", "VotingMethod"],
            ["646212", "11/06/2001", "NOVEMBER 6, 2001", "P"],
            ["520137", "11/04/1997", "MUNICIPAL GENERAL", "P"],
        ]

        def write_quoted(path, data, encoding):
            with open(path, "w", encoding=encoding, newline="") as handle:
                writer = csv.writer(
                    handle,
                    quoting=csv.QUOTE_ALL,
                    lineterminator="\r\n",
                )
                writer.writerows(data)

        write_quoted(voter_path, rows, "cp1252")
        write_quoted(election_path, elections, "utf-8")

        # The ½ must be the single Windows-1252 byte, not a UTF-8 sequence.
        raw = open(voter_path, "rb").read()
        if b"\xbd" not in raw or b"\xc2\xbd" in raw:
            raise SystemExit("fixture did not store ½ as Windows-1252 byte 0xBD")

        strip_directory(directory)

        def parsed(path, encoding):
            with open(path, "r", encoding=encoding, newline="") as handle:
                return list(csv.reader(handle))

        if parsed(voter_path, "cp1252") != rows:
            raise SystemExit("voter fields changed")
        if parsed(election_path, "utf-8") != elections:
            raise SystemExit("election fields changed")

        voter_text = open(voter_path, "r", encoding="cp1252", newline="").read()
        if '"ROYAL"' in voter_text or '"STEVENS AVE "' in voter_text:
            raise SystemExit("quotes were left on fields that do not need them")
        if "ROYAL,STEVENS AVE ," not in voter_text.replace("\r\n", "\n"):
            raise SystemExit("trailing space in a street name was changed")
        if '"P.O, BOX 384"' not in voter_text:
            raise SystemExit("the comma inside the mailing address lost its quotes")
        if '"SAY ""HI"""' not in voter_text:
            raise SystemExit("a quote character inside a field was not preserved")
        rewritten = open(voter_path, "rb").read()
        if not rewritten.endswith(b"\r\n"):
            raise SystemExit("line endings were not kept as CRLF")
        if b"\xbd" not in rewritten or b"\xc2\xbd" in rewritten:
            raise SystemExit("½ was not kept as Windows-1252 byte 0xBD")

        election_text = open(election_path, "r", encoding="utf-8", newline="").read()
        if '"MUNICIPAL GENERAL"' in election_text or '"P"' in election_text:
            raise SystemExit("plain election fields are still quoted")
        if '"NOVEMBER 6, 2001"' not in election_text:
            raise SystemExit("election description with a comma lost its quotes")

        # A second pass must not change a single byte.
        voter_before = open(voter_path, "rb").read()
        election_before = open(election_path, "rb").read()
        strip_directory(directory)
        if open(voter_path, "rb").read() != voter_before:
            raise SystemExit("running the strip a second time changed the voter file")
        if open(election_path, "rb").read() != election_before:
            raise SystemExit("running the strip a second time changed the election file")
    finally:
        shutil.rmtree(directory)
    print("Self-test passed.")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Remove the double quotes wrapped around every field of "
            "VoterNN.txt and ElectionNN.txt. Quotes stay only on fields "
            "that contain a comma, a quote, or a line break, so the field "
            "values do not change."
        )
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=os.path.dirname(os.path.abspath(__file__)),
        help="Folder containing the voter and election files. Default: this script's folder.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run the built-in integrity test and do not modify the voter files.",
    )
    args = parser.parse_args(argv)
    if args.test:
        _self_test()
        return 0
    return strip_directory(args.directory)


if __name__ == "__main__":
    sys.exit(main())
