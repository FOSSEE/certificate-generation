"""Read a participant list uploaded as a CSV file.

Organisers export these files from Excel, Google Sheets or LibreOffice, so
the reader accepts the variations those programs produce:

* a UTF-8 byte order mark (Excel's "CSV UTF-8"),
* older Windows encodings (Excel's plain "CSV (Comma delimited)"),
* comma, semicolon or tab separators,
* quoted cells that contain the separator ("Dept of CS, IIT Bombay"),
* blank columns and blank rows at the end of the sheet.
"""
import csv
import io
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

REQUIRED_COLUMNS = ('email', 'name')
RESERVED_COLUMNS = ('serial_key', 'qr_code')
ENCODINGS = ('utf-8-sig', 'cp1252', 'latin-1')  # latin-1 never fails
SEPARATORS = (',', ';', '\t')


class CSVImportError(Exception):
    """The file cannot be used at all; the message is shown to the organiser."""


def _decode(raw):
    if raw.startswith(b'PK\x03\x04'):
        raise CSVImportError(
            'This looks like an Excel (.xlsx) file. In your spreadsheet '
            'program choose "Save As" or "Download" and pick CSV, then '
            'upload that file.')
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue


def _separator(header_line):
    counts = {sep: header_line.count(sep) for sep in SEPARATORS}
    best = max(counts, key=counts.get)
    return best if counts[best] else ','


def normalise_column(name):
    """'  Course Name ' -> 'course_name' so it can be used as $course_name."""
    return re.sub(r'\s+', '_', name.strip().lower())


def parse_participants(raw):
    """Parse the uploaded bytes.

    Returns ``(participants, problems)`` where ``participants`` is a list of
    ``(email, details)`` tuples and ``problems`` is a list of messages about
    rows that were skipped. Raises ``CSVImportError`` if the file cannot be
    used at all.
    """
    text = _decode(raw)
    if text is None or not text.strip():
        raise CSVImportError('The file is empty.')

    first_line = text.lstrip('\r\n').splitlines()[0]
    reader = csv.reader(io.StringIO(text, newline=''),
                        delimiter=_separator(first_line))
    try:
        rows = list(reader)
    except csv.Error as e:
        raise CSVImportError(f'The file could not be read as CSV ({e}).')

    # Skip blank lines before the header row.
    while rows and not any(cell.strip() for cell in rows[0]):
        rows.pop(0)
    if not rows:
        raise CSVImportError('The file is empty.')

    header = [normalise_column(h) for h in rows[0]]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        found = ', '.join(h for h in header if h) or 'none'
        raise CSVImportError(
            f'The first row must contain the column headings '
            f'{" and ".join(REQUIRED_COLUMNS)}. Missing: {", ".join(missing)}. '
            f'Found: {found}.')

    duplicates = sorted({h for h in header if h and header.count(h) > 1})
    if duplicates:
        raise CSVImportError(
            f'These column headings appear more than once: '
            f'{", ".join(duplicates)}. Each heading must be unique.')

    reserved = [c for c in RESERVED_COLUMNS if c in header]
    if reserved:
        raise CSVImportError(
            f'Remove the column(s) {", ".join(reserved)}: the system fills '
            f'these in itself.')

    # Ignore columns without a heading (blank columns at the end of a sheet).
    columns = [(i, h) for i, h in enumerate(header) if h]

    participants, problems = [], []
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue  # blank row
        values = {h: (row[i].strip() if i < len(row) else '')
                  for i, h in columns}
        email = values.pop('email').lower()
        if not email:
            problems.append(f'Row {line_no}: no email address, skipped.')
            continue
        try:
            validate_email(email)
        except ValidationError:
            problems.append(
                f'Row {line_no}: "{email}" is not a valid email address, skipped.')
            continue
        participants.append((email, values))
    return participants, problems
