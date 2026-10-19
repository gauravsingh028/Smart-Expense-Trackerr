"""
Bank statement parsers — CSV, PDF, and Excel.

Handles various Indian bank statement formats by auto-detecting column layouts.
Each parser normalises rows into the standard format:
    {date, description, amount, category, payment_method}

Supported banks:
    - Canara Bank
    - SBI, HDFC, ICICI, Axis, and other Indian banks
    - Generic auto-detect for any tabular statement

Supported formats:
    - CSV / TXT
    - PDF (via pdfplumber table extraction)
    - Excel (.xlsx, .xls via openpyxl)
"""

import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


# ──────────── Category auto-detection rules ────────────

CATEGORY_RULES = [
    (r'(?i)(swiggy|zomato|dominos|pizza|restaurant|food|dining|cafe|bakery|bigbasket|blinkit|zepto|grofers|dmart|grocery|milk|kitchen|canteen|mess|tiffin|biryani|burger|kfc|mcdonalds)', 'Food & Dining'),
    (r'(?i)(uber|ola|rapido|metro|irctc|railway|train|bus|petrol|diesel|fuel|parking|toll|cab|auto|rickshaw|flight|airline|indigo|spicejet|vistara|redbus|ksrtc|tsrtc)', 'Transportation'),
    (r'(?i)(amazon|flipkart|myntra|ajio|meesho|nykaa|shopping|purchase|buy|store|mall|market|reliance\s*retail|croma|vijay\s*sales)', 'Shopping'),
    (r'(?i)(electricity|elec\.?\s*bill|water|gas|lpg|internet|broadband|wifi|jio|airtel|vi\b|bsnl|mobile\s*recharge|rent|maintenance|society|phone\s*bill|dth|tata\s*sky|act\s*fibernet|hathway)', 'Bills & Utilities'),
    (r'(?i)(hospital|doctor|clinic|pharmacy|medical|medicine|health|lab|diagnostic|apollo|fortis|insurance|lic\b|star\s*health|medplus|netmeds|pharmeasy|1mg)', 'Healthcare'),
    (r'(?i)(netflix|spotify|hotstar|prime\s*video|youtube|movie|cinema|pvr|inox|game|gaming|play\s*store|google\s*play|app\s*store|sony\s*liv|zee5|jiocinema)', 'Entertainment'),
    (r'(?i)(course|udemy|coursera|book|college|university|school|tuition|exam|education|study|library|stationery|unacademy|byju|vedantu)', 'Education'),
    (r'(?i)(hotel|resort|booking|makemytrip|goibibo|oyo|travel|trip|tour|sightseeing|visa|passport|cleartrip|yatra)', 'Travel'),
    (r'(?i)(salary|sal\b|credit\s*interest|int\.?\s*cr|refund|cashback|rev\b|reversal|neft\s*cr|imps\s*cr|credited)', '_income'),
    (r'(?i)(atm|cash\s*withdrawal|cash\s*wd|atm-wdl|self\s*transfer|transfer\s*to\s*self)', 'Other'),
]


def _guess_category(narration):
    """Try to guess category from narration/description text."""
    if not narration:
        return 'Other'
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, narration):
            return category
    return 'Other'


def _guess_payment_method(narration):
    """Try to guess payment method from narration."""
    if not narration:
        return 'Other'
    n = narration.upper()
    if 'UPI' in n or 'IMPS' in n:
        return 'UPI'
    if 'NEFT' in n or 'RTGS' in n or 'NET BANKING' in n or 'NETBANKING' in n:
        return 'Net Banking'
    if 'ATM' in n or 'CASH WD' in n or 'CASH WITHDRAWAL' in n:
        return 'Cash'
    if 'POS' in n or 'ECOM' in n or 'DEBIT CARD' in n:
        return 'Debit Card'
    if 'CREDIT CARD' in n or 'CC ' in n:
        return 'Credit Card'
    if any(w in n for w in ['PAYTM', 'PHONEPE', 'GPAY', 'GOOGLE PAY', 'AMAZONPAY', 'FREECHARGE', 'MOBIKWIK']):
        return 'Wallet'
    return 'Other'


def _parse_date_flexible(date_str):
    """Parse dates in DD/MM/YYYY, DD-MM-YYYY, DD/MM/YY, YYYY-MM-DD, etc."""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    if not date_str:
        return None

    formats = [
        '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y',
        '%Y-%m-%d', '%Y/%m/%d',
        '%d %b %Y', '%d-%b-%Y', '%d/%b/%Y',
        '%d %B %Y', '%d-%B-%Y',
        '%m/%d/%Y', '%m-%d-%Y',
        '%d.%m.%Y', '%d.%m.%y',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _parse_amount(val):
    """Parse amount string, handling commas, negatives, and currency symbols."""
    if val is None:
        return None
    val = str(val).strip()
    if not val or val == '-' or val == '0' or val == '0.00' or val.lower() == 'nan' or val.lower() == 'none':
        return None
    val = val.replace(',', '').replace(' ', '')
    if val.startswith('(') and val.endswith(')'):
        val = '-' + val[1:-1]
    val = re.sub(r'[₹$€£]', '', val).strip()
    val = re.sub(r'^INR\s*', '', val, flags=re.IGNORECASE).strip()
    try:
        amount = Decimal(val)
        return abs(amount) if amount != 0 else None
    except (InvalidOperation, ValueError):
        return None


# ──────────── Column detection ────────────

def _normalise_header(h):
    """Normalise a header string for matching."""
    if h is None:
        return ''
    return re.sub(r'[^a-z0-9]', '', str(h).lower().strip())


HEADER_MAP = {
    'txndate': 'date', 'transactiondate': 'date', 'txndt': 'date',
    'date': 'date', 'valuedate': 'value_date', 'valdate': 'value_date',
    'postingdate': 'date', 'bookingdate': 'date', 'transdate': 'date',

    'narration': 'description', 'description': 'description',
    'particulars': 'description', 'remarks': 'description',
    'transactionremarks': 'description', 'details': 'description',
    'transactiondetails': 'description', 'narrative': 'description',
    'transactionparticulars': 'description',

    'debit': 'debit', 'debitamount': 'debit', 'withdrawal': 'debit',
    'withdrawalamount': 'debit', 'dr': 'debit', 'dramount': 'debit',
    'debitamt': 'debit', 'withdrawalamt': 'debit', 'withdrawals': 'debit',

    'credit': 'credit', 'creditamount': 'credit', 'deposit': 'credit',
    'depositamount': 'credit', 'cr': 'credit', 'cramount': 'credit',
    'creditamt': 'credit', 'depositamt': 'credit', 'deposits': 'credit',

    'balance': 'balance', 'closingbalance': 'balance',
    'runningbalance': 'balance', 'availablebalance': 'balance',

    'amount': 'amount',

    'chequeno': 'ref', 'refno': 'ref', 'referenceno': 'ref',
    'transactionid': 'ref', 'utrno': 'ref', 'chqno': 'ref',

    'category': 'category',
    'paymentmethod': 'payment_method', 'mode': 'payment_method',
}


def _detect_columns(headers):
    """Map headers to semantic column meanings."""
    mapping = {}
    for i, h in enumerate(headers):
        norm = _normalise_header(h)
        if norm in HEADER_MAP:
            mapping[HEADER_MAP[norm]] = i
        else:
            # Partial match for compound headers
            for key, sem in HEADER_MAP.items():
                if key in norm and sem not in mapping:
                    mapping[sem] = i
                    break
    return mapping


def _process_rows(headers, data_rows, start_row_offset=2):
    """
    Core processing: takes headers and data rows, returns (valid, errors).
    Used by CSV, PDF, and Excel parsers.
    """
    col_map = _detect_columns(headers)

    has_debit_credit = 'debit' in col_map and 'credit' in col_map
    has_amount = 'amount' in col_map
    has_date = 'date' in col_map
    has_description = 'description' in col_map

    if not has_date and 'value_date' in col_map:
        col_map['date'] = col_map['value_date']
        has_date = True

    if not has_date:
        return [], [{'row': 1, 'errors': f'Could not detect date column. Found: {", ".join(str(h) for h in headers)}', 'data': {}}]
    if not has_description:
        return [], [{'row': 1, 'errors': f'Could not detect description/narration column. Found: {", ".join(str(h) for h in headers)}', 'data': {}}]
    if not has_debit_credit and not has_amount:
        return [], [{'row': 1, 'errors': f'Could not detect amount columns. Found: {", ".join(str(h) for h in headers)}', 'data': {}}]

    valid_rows = []
    error_rows = []

    for row_idx, row in enumerate(data_rows):
        row_num = row_idx + start_row_offset

        # Skip empty rows
        if not any(str(cell).strip() for cell in row if cell is not None):
            continue

        # Pad row
        while len(row) < len(headers):
            row.append('')

        errors = []

        # Date
        raw_date = str(row[col_map['date']]).strip() if col_map['date'] < len(row) else ''
        parsed_date = _parse_date_flexible(raw_date)
        if not parsed_date:
            if raw_date and not any(kw in raw_date.lower() for kw in ['total', 'opening', 'closing', 'statement', 'balance']):
                errors.append(f'Invalid date: "{raw_date}"')
            else:
                continue  # summary row, skip

        # Description
        desc_idx = col_map.get('description', 0)
        raw_desc = str(row[desc_idx]).strip() if desc_idx < len(row) else ''
        # Skip summary/header-like rows
        if raw_desc.lower() in ('', 'total', 'opening balance', 'closing balance', 'grand total'):
            continue
        if not raw_desc:
            errors.append('Empty description')

        # Amount
        amount = None
        is_expense = True

        if has_debit_credit:
            debit_val = _parse_amount(row[col_map['debit']] if col_map['debit'] < len(row) else '')
            credit_val = _parse_amount(row[col_map['credit']] if col_map['credit'] < len(row) else '')
            if debit_val and debit_val > 0:
                amount = debit_val
                is_expense = True
            elif credit_val and credit_val > 0:
                amount = credit_val
                is_expense = False
            else:
                continue
        elif has_amount:
            amount = _parse_amount(row[col_map['amount']] if col_map['amount'] < len(row) else '')
            if amount is None:
                errors.append(f'Invalid amount')

        # Skip income/credit transactions
        if not is_expense:
            continue

        category = _guess_category(raw_desc)
        if category == '_income':
            continue

        if amount is None and not errors:
            errors.append('Could not parse amount')

        if errors:
            error_rows.append({
                'row': row_num,
                'errors': '; '.join(errors),
                'data': dict(zip([str(h) for h in headers], [str(c) for c in row])),
            })
        else:
            valid_rows.append({
                'date': parsed_date.strftime('%Y-%m-%d'),
                'description': raw_desc[:500],
                'amount': str(amount.quantize(Decimal('0.01'))),
                'category': category,
                'payment_method': _guess_payment_method(raw_desc),
            })

    return valid_rows, error_rows


# ──────────── CSV Parser ────────────

def parse_csv_statement(file_content):
    """Parse a CSV bank statement. Returns (valid_rows, error_rows)."""
    if isinstance(file_content, bytes):
        for enc in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
            try:
                file_content = file_content.decode(enc)
                break
            except (UnicodeDecodeError, AttributeError):
                continue

    lines = [l for l in file_content.splitlines() if l.strip()]

    # Find header row
    header_idx = 0
    for i, line in enumerate(lines):
        norm_line = _normalise_header(line)
        matches = sum(1 for kw in ['date', 'narration', 'description', 'debit', 'credit',
                                    'amount', 'particulars', 'withdrawal', 'deposit']
                      if kw in norm_line)
        if matches >= 2:
            header_idx = i
            break

    csv_text = '\n'.join(lines[header_idx:])
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return [], [{'row': 1, 'errors': 'Empty file', 'data': {}}]

    headers = rows[0]
    data_rows = rows[1:]
    return _process_rows(headers, data_rows, start_row_offset=header_idx + 2)


# ──────────── PDF Parser ────────────

def parse_pdf_statement(file_bytes, password=None):
    """
    Parse a PDF bank statement using pdfplumber.
    Extracts tables from all pages, merges them, and processes.
    Supports password-protected PDFs (common with Indian banks).
    Returns (valid_rows, error_rows).
    """
    try:
        import pdfplumber
    except ImportError:
        return [], [{'row': 0, 'errors': 'pdfplumber is not installed. Run: pip install pdfplumber', 'data': {}}]

    all_rows = []
    headers = None
    pdf_obj = None

    try:
        pdf_stream = io.BytesIO(file_bytes)

        # Try opening with password first if provided
        if password:
            try:
                pdf_obj = pdfplumber.open(pdf_stream, password=password)
            except Exception:
                pdf_stream.seek(0)
                try:
                    pdf_obj = pdfplumber.open(pdf_stream)
                except Exception as e:
                    err_msg = str(e).lower()
                    if 'password' in err_msg or 'encrypt' in err_msg or 'decrypt' in err_msg:
                        return [], [{'row': 0, 'errors': 'Incorrect PDF password. Please check and try again.', 'data': {}}]
                    return [], [{'row': 0, 'errors': f'Failed to read PDF: {str(e)}', 'data': {}}]
        else:
            try:
                pdf_obj = pdfplumber.open(pdf_stream)
            except Exception as e:
                err_msg = str(e).lower()
                if 'password' in err_msg or 'encrypt' in err_msg or 'decrypt' in err_msg:
                    return [], [{'row': 0, 'errors': 'PDF_PASSWORD_REQUIRED', 'data': {}}]
                return [], [{'row': 0, 'errors': f'Failed to read PDF: {str(e)}', 'data': {}}]

        with pdf_obj as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if not tables:
                    # Try extracting text and parsing line by line
                    text = page.extract_text()
                    if text:
                        for line in text.split('\n'):
                            parts = re.split(r'\s{2,}|\t', line.strip())
                            if len(parts) >= 3:
                                all_rows.append(parts)
                    continue

                for table in tables:
                    if not table:
                        continue
                    for row_idx, row in enumerate(table):
                        if row is None:
                            continue
                        cleaned = [str(cell).strip() if cell is not None else '' for cell in row]
                        if not any(cleaned):
                            continue

                        # Detect if this is a header row
                        if headers is None:
                            norm = ' '.join(cleaned).lower()
                            if sum(1 for kw in ['date', 'narration', 'description', 'debit',
                                                  'credit', 'amount', 'particulars', 'withdrawal']
                                   if kw in norm) >= 2:
                                headers = cleaned
                                continue

                        all_rows.append(cleaned)

    except Exception as e:
        return [], [{'row': 0, 'errors': f'Failed to read PDF: {str(e)}', 'data': {}}]

    if headers is None:
        # Try using first row as header
        if all_rows:
            headers = all_rows[0]
            all_rows = all_rows[1:]
        else:
            return [], [{'row': 0, 'errors': 'Could not find table headers in PDF. Ensure your statement has a tabular format.', 'data': {}}]

    # Normalise column count
    max_cols = len(headers)
    for i, row in enumerate(all_rows):
        if len(row) < max_cols:
            all_rows[i] = row + [''] * (max_cols - len(row))
        elif len(row) > max_cols:
            all_rows[i] = row[:max_cols]

    return _process_rows(headers, all_rows, start_row_offset=2)


# ──────────── Excel Parser ────────────

def parse_excel_statement(file_bytes):
    """
    Parse an Excel bank statement (.xlsx).
    Returns (valid_rows, error_rows).
    """
    try:
        import openpyxl
    except ImportError:
        return [], [{'row': 0, 'errors': 'openpyxl is not installed. Run: pip install openpyxl', 'data': {}}]

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
    except Exception as e:
        return [], [{'row': 0, 'errors': f'Failed to read Excel file: {str(e)}', 'data': {}}]

    all_rows = []
    for row in ws.iter_rows(values_only=True):
        cleaned = [str(cell).strip() if cell is not None else '' for cell in row]
        if any(cleaned):
            all_rows.append(cleaned)

    if not all_rows:
        return [], [{'row': 0, 'errors': 'Empty spreadsheet', 'data': {}}]

    # Find header row
    headers = None
    data_start = 0
    for i, row in enumerate(all_rows):
        norm = ' '.join(row).lower()
        if sum(1 for kw in ['date', 'narration', 'description', 'debit', 'credit',
                              'amount', 'particulars', 'withdrawal']
               if kw in norm) >= 2:
            headers = row
            data_start = i + 1
            break

    if headers is None:
        headers = all_rows[0]
        data_start = 1

    return _process_rows(headers, all_rows[data_start:], start_row_offset=data_start + 1)


# ──────────── Universal entry point ────────────

def parse_bank_statement(file_content, filename='', password=None):
    """
    Auto-detect file type and parse accordingly.
    Returns (valid_rows, error_rows, file_type).
    """
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''

    if ext == 'pdf':
        if isinstance(file_content, str):
            file_content = file_content.encode()
        valid, errors = parse_pdf_statement(file_content, password=password)
        return valid, errors, 'PDF'
    elif ext in ('xlsx', 'xls'):
        if isinstance(file_content, str):
            file_content = file_content.encode()
        valid, errors = parse_excel_statement(file_content)
        return valid, errors, 'Excel'
    else:
        # CSV / TXT
        valid, errors = parse_csv_statement(file_content)
        return valid, errors, 'CSV'
