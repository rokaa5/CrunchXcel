
import os
import shutil
import re
import sys
import textwrap
import unicodedata
import uuid
import requests
import getpass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from models import CATEGORY_TO_TYPE, PRODUCT_CATEGORIES, clean_phone, ph_now, ph_today

API = "http://127.0.0.1:8000"
AUTH_TOKEN = None
CURRENT_ROLE = None
PAGE_SIZE = 10
ITEM_NAME_WIDTH = 40
MAX_ITEM_NAME_LENGTH = 80


class GoBack(Exception):
    pass


# GENERAL FUNCTIONS

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def header(title, input_screen=False, width=55, banner=None):
    clear_screen()
    if banner:
        print(banner)
        print()
    print("=" * width)
    print(title.center(width))
    print("=" * width)

    if input_screen:
        print("[0] Back")
        print("-" * width)


def press_enter_to_continue(message="Press Enter to continue..."):
    print(message, end="", flush=True)

    if not sys.stdin.isatty():
        input()
        return

    if sys.platform == "win32":
        import msvcrt
        while msvcrt.kbhit():              # discard keys typed earlier
            msvcrt.getwch()
        while True:
            key = msvcrt.getwch()
            if key in ("\r", "\n"):
                break
            if key == "\x03":              # Ctrl+C
                raise KeyboardInterrupt
            if key in ("\x00", "\xe0"):    # arrow and function keys send two codes
                msvcrt.getwch()
    else:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            termios.tcflush(fd, termios.TCIFLUSH)   # discard keys typed earlier
            tty.setcbreak(fd)                       # no echo, no line buffering
            while sys.stdin.read(1) not in ("\n", "\r"):
                pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    print()


def pause():
    print()
    press_enter_to_continue("Press Enter to continue...")


def ask(prompt, allow_blank=False, allow_zero=False):
    while True:
        value = input(prompt).strip()

        if value == "0" and not allow_zero:
            raise GoBack()

        if value or allow_blank:
            return value

        print("This field is required.")


def ask_number(prompt):
    while True:
        value = ask(prompt)

        try:
            number = int(value)

            if number > 0:
                return number

            print("Enter a positive number.")
        except ValueError:
            print("Please enter a valid number.")


def ask_amount(prompt, allow_zero=False):
    while True:
        value = ask(prompt, allow_zero=allow_zero)

        try:
            amount = Decimal(value)

            if not amount.is_finite():
                print("Enter a finite amount.")
                continue

            if amount > 0 or (allow_zero and amount == 0):
                if amount.as_tuple().exponent < -2:
                    print("Use at most two decimal places.")
                    continue
                return str(amount)

            print("Amount must be positive.")
        except InvalidOperation:
            print("Please enter a valid amount.")


def add_one_month(start_dt: date) -> date:
    year = start_dt.year
    month = start_dt.month + 1
    if month > 12:
        month = 1
        year += 1
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    day = min(start_dt.day, max_day)
    return date(year, month, day)


def add_one_year(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def ask_date(prompt, default=None, min_date=None):
    while True:
        value = ask(
            prompt,
            allow_blank=default is not None
        )

        if not value and default is not None:
            d = default
        else:
            try:
                d = date.fromisoformat(value)
            except ValueError:
                print("Invalid date. Use YYYY-MM-DD.")
                continue

        if min_date and d < min_date:
            print("Start date cannot be in the past.")
            continue

        return d


def ask_choice(prompt, choices):
    while True:
        value = ask(prompt)
        low = value.lower()

        for choice in choices:
            if low == choice.lower():
                return choice

        if low in ("yes", "y") and any(c.lower() == "y" for c in choices):
            return next(c for c in choices if c.lower() == "y")
        if low in ("no", "n") and any(c.lower() == "n" for c in choices):
            return next(c for c in choices if c.lower() == "n")
        if low in ("c", "cash") and any(c.lower() == "cash" for c in choices):
            return next(c for c in choices if c.lower() == "cash")
        if low in ("e", "ewallet", "e-wallet") and any(c.lower() == "e-wallet" for c in choices):
            return next(c for c in choices if c.lower() == "e-wallet")

        print("Choose: " + ", ".join(choices))


def ask_payment_method(show_cancel=True):
    print("\nPayment Method:")
    print("[1] Cash")
    print("[2] E-Wallet")
    if show_cancel:
        print("[0] Cancel")
    else:
        print("[0] Back")
    while True:
        choice = input("Choice: ").strip()
        if choice == "1":
            return "Cash"
        if choice == "2":
            return "E-Wallet"
        if choice.lower() in ("0", "b", "back", "cancel"):
            raise GoBack()
        print("Invalid choice. Enter 1 or 2.")


def confirm(prompt="Confirm? (y/n, 0 to cancel): "):
    while True:
        value = input(prompt).strip().lower()
        if value in ("0", "n", "no", "cancel"):
            return False
        if value in ("y", "yes"):
            return True
        print("Choose: y or n (0 to cancel)")


def request(method, endpoint, data=None, params=None, silent_404=False):
    try:
        response = requests.request(
            method,
            API + endpoint,
            json=data,
            params=params,
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"} if AUTH_TOKEN else {},
            timeout=10
        )

        if response.status_code >= 400:
            try:
                detail = response.json().get(
                    "detail", response.text
                )
            except ValueError:
                detail = response.text

            if response.status_code == 404:
                if not silent_404:
                    print("\nThat record was not found.")
            elif response.status_code == 409:
                print(f"\n{detail}")
            elif response.status_code == 422:
                print("\nSome of the information entered is not valid.")
            elif response.status_code >= 500:
                print("\nSomething went wrong. Please try again.")
            else:
                print(f"\n{detail}")
            return None

        if response.status_code == 204:
            return True

        return response.json()

    except requests.RequestException:
        print("\nCannot connect to the server. Check that it is running.")
        return None


def show(records, empty_message="There are no records right now."):
    if records is None:
        return

    if not records:
        print(f"\n{empty_message}")
        return

    if isinstance(records, dict):
        records = [records]

    for record in records:
        print("-" * 55)

        for key, value in record.items():
            label = key.replace("_", " ").title()
            if key in ("price", "amount", "total", "service_income", "product_income") and value is not None:
                display_val = format_currency(value)
            else:
                display_val = "-" if value is None or str(value).strip() == "" else value
            print(f"{label}: {display_val}")


def submenu(title, options):
    while True:
        header(title)

        for i, (label, _) in enumerate(options, 1):
            print(f"[{i}] {label}")

        print("-" * 55)

        if title == "GYM MANAGEMENT SYSTEM":
            print("[0] Exit")
        else:
            print("[0] Back")

        print("-" * 55)

        choice = input("Choice: ").strip()
        low = choice.lower()

        if low in ("0", "b", "back", "exit"):
            return

        matched_idx = None
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            matched_idx = int(choice) - 1
        else:
            for i, (label, _) in enumerate(options):
                if low == label.lower():
                    matched_idx = i
                    break

        if matched_idx is not None:
            try:
                options[matched_idx][1]()
            except GoBack:
                pass
        else:
            print("\nInvalid choice.")
            pause()




def is_valid_id(value):
    return bool(re.match(r"^[0-9]+$", str(value).strip()))


def is_latin_letter(ch: str) -> bool:
    return len(ch) == 1 and ch.isalpha() and "LATIN" in unicodedata.name(ch, "")


def clean_name(raw_name: str) -> str:
    if not raw_name:
        return ""
    return re.sub(r"\s+", " ", raw_name.strip())


def is_valid_name(raw_name: str) -> bool:
    name = clean_name(raw_name)
    if not name or len(name) > 50:
        return False
    if not is_latin_letter(name[0]) or not is_latin_letter(name[-1]):
        return False
    allowed_separators = {" ", "-", "'", "’"}
    for i, ch in enumerate(name):
        if is_latin_letter(ch):
            continue
        elif ch in allowed_separators:
            if i == 0 or i == len(name) - 1:
                return False
            if not is_latin_letter(name[i - 1]) or not is_latin_letter(name[i + 1]):
                return False
        else:
            return False
    return True


def ask_id():
    while True:
        value = input("Enter customer ID: ").strip()
        if value == "0":
            raise GoBack()
        if value == "":
            print("Customer ID is required.")
        elif not is_valid_id(value) or int(value) > 9223372036854775807:
            print("Customer ID must contain numbers only.")
        else:
            return int(value)


def ask_name(label, prompt=None, allow_blank=False):
    if prompt is None:
        prompt = f"Enter {label}: "
    while True:
        raw_val = input(prompt)
        trimmed = raw_val.strip()
        if trimmed == "0":
            raise GoBack()
        if trimmed == "":
            if allow_blank:
                return ""
            print(f"{label} is required.")
            continue

        cleaned = clean_name(trimmed)
        if len(cleaned) > 50:
            print(f"{label} must be 50 characters or fewer.")
        elif not is_valid_name(cleaned):
            print(f"{label} may contain only letters, spaces, hyphens, and apostrophes.")
        else:
            return cleaned


def ask_phone(prompt="Phone: ", allow_blank=False):
    while True:
        raw_val = input(prompt)
        trimmed = raw_val.strip()
        if trimmed == "0":
            raise GoBack()
        if trimmed == "":
            if allow_blank:
                return ""
            print("Enter a valid mobile number: 09XXXXXXXXX or +639XXXXXXXXX.")
            continue

        cleaned = clean_phone(trimmed)
        if not cleaned:
            print("Enter a valid mobile number: 09XXXXXXXXX or +639XXXXXXXXX.")
            continue

        return cleaned

def has_records(entity):
    result = request("GET", f"/{entity}/exists")
    if result is None:
        return None
    return result.get("exists", False)


def guard_records(entity, action, title, input_screen=True):
    exists = has_records(entity)
    if exists is None:
        return False
    if not exists:
        header(title, input_screen=False)
        print(f"\nThere are no {entity} to {action}.")
        pause()
        return False
    header(title, input_screen=input_screen)
    return True


def has_customers(eligibility=None):
    params = {"eligibility": eligibility} if eligibility else None
    result = request("GET", "/customers/exists", params=params)
    if result is None:
        return None
    return result.get("exists", False)


def guard_customers(action, title, input_screen=True):
    return guard_records("customers", action, title, input_screen=input_screen)


# CUSTOMER MANAGEMENT

def collect_new_customer_data(title="REGISTER CUSTOMER"):
    """Validate personal details without creating a record before purchase confirmation."""
    header(title, input_screen=True)
    print("Enter the customer's information.")
    print("-" * 55)
    return {
        "first_name": ask_name("First name", prompt="First name: "),
        "last_name": ask_name("Last name", prompt="Last name: "),
        "phone": ask_phone("Phone: "),
    }


def add_customer():
    details = collect_new_customer_data()
    result = request("POST", "/customers", details)
    if result:
        print("\nCustomer registered successfully!")
        print(f"Customer ID: {result['id']}")
    pause()


def format_currency(value):
    if value is None or str(value).strip() == "":
        return "-"
    try:
        d = Decimal(str(value).replace(",", "").strip())
        return f"{d:,.2f}"
    except InvalidOperation:
        return str(value)


def confirm_purchase_screen(
    customer_name: str,
    membership_label: str,
    items_count: int,
    subtotal: str,
    discount: str,
    total: str,
    payment_method: str,
    tendered: str,
    change: str,
    width: int = 50,
    anonymous_product: bool = False,
) -> bool:
    header("CONFIRM PURCHASE", input_screen=False, width=width)
    if not anonymous_product:
        print(f"{'Customer:':<18}{customer_name}")
        print(f"{'Membership:':<18}{membership_label}")
    print(f"{'Items:':<18}{items_count}")
    print(f"{'Subtotal:':<18}{format_currency(subtotal)}")
    print(f"{'Discount:':<18}{format_currency(discount)}")
    print(f"{'Total Due:':<18}{format_currency(total)}")
    print(f"{'Payment Method:':<18}{payment_method}")
    print(f"{'Amount Tendered:':<18}{format_currency(tendered)}")
    print(f"{'Change:':<18}{format_currency(change)}")
    print("-" * width)
    choice = input("Save this purchase? (Y/N): ").strip().upper()
    return choice == "Y"


def print_receipt(sale, width=58):
    header("RECEIPT", input_screen=False, width=width)
    print(f"Receipt no.: {sale.get('receipt_no', '-')}")
    print(f"Date:        {sale.get('created_at', '-')}")
    if str(sale.get("kind", "")).lower() != "product" or sale.get("customer_id") is not None:
        print(f"Customer:    {sale.get('customer_name', 'Walk-in')}")
        if sale.get("customer_id") is not None:
            print(f"Customer ID: {sale['customer_id']}")
    print("-" * width)
    for it in sale.get("items", []):
        for name_line in wrap_cell(it["item_name"], width - 4):
            print(f"  {name_line}")
        print(
            f"  {it['quantity']} x {format_currency(it['unit_price'])} = "
            f"{format_currency(it['line_amount'])}"
        )
        if Decimal(str(it.get("discount", 0))) > 0:
            print(f"  Discount: -{format_currency(it['discount'])}")
    print("-" * width)
    disc_total = Decimal(str(sale.get("discount", 0)))
    if disc_total > 0:
        print(f"{'Subtotal':<44} {format_currency(sale.get('subtotal', sale['total'])):>12}")
        print(f"{'Discount':<44} -{format_currency(sale['discount']):>11}")
    print(f"{'Total':<44} {format_currency(sale['total']):>12}")
    print(f"Payment:     {sale.get('payment_method', '-')}")
    print(f"{'Tendered':<44} {format_currency(sale.get('amount_tendered', sale['total'])):>12}")
    print(f"{'Change':<44} {format_currency(sale.get('change', '0.00')):>12}")
    if sale.get("status") == "Refunded":
        print("-" * width)
        print(f"Status:      Refunded ({sale.get('refund_no', '-')})")
        print(f"Amount:      {format_currency(sale.get('refunded_amount', '0.00'))}")
        print(f"Refund Date: {sale.get('refunded_at', '-')}")
    print("-" * width)


def wrap_cell(value, width):
    text = re.sub(r"\s+", " ", str(value).strip()) if value is not None else ""
    if not text:
        return ["-"]
    return textwrap.wrap(
        text,
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
    ) or ["-"]


TABLE_SEPARATOR = "  |  "


def table_width(columns, minimum=0):
    return max(minimum, sum(col[2] for col in columns) + len(TABLE_SEPARATOR) * (len(columns) - 1))


def print_table_header(columns, compact=False):
    if not compact:
        print()
    cells = []
    for col in columns:
        label, width = col[0], col[2]
        align = col[3] if len(col) > 3 else "left"
        cells.append(format_cell(label, width, align))
    print(TABLE_SEPARATOR.join(cells))
    if not compact:
        print()


def format_cell(value, width, align="left"):
    lines = wrap_cell(value, width)
    first = lines[0]
    return first.rjust(width) if align == "right" else first.ljust(width)


def print_table_row(rec, columns, compact=False):
    wrapped_cols = []
    for col in columns:
        _, getter, w = col[0], col[1], col[2]
        align = col[3] if len(col) > 3 else "left"
        val = getter(rec) if callable(getter) else rec.get(getter)
        lines = wrap_cell(val, w)
        wrapped_cols.append((lines, w, align))

    num_lines = max(len(lines) for lines, _, _ in wrapped_cols)
    for line_idx in range(num_lines):
        row_cells = []
        for lines, w, align in wrapped_cols:
            if line_idx < len(lines):
                txt = lines[line_idx]
                row_cells.append(txt.rjust(w) if align == "right" else txt.ljust(w))
            else:
                row_cells.append(" " * w)
        print(TABLE_SEPARATOR.join(row_cells))
    if not compact:
        print()


def mask_phone(phone: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", str(phone or ""))
    if len(cleaned) == 11 and cleaned.startswith("09"):
        return f"{cleaned[:4]}***{cleaned[7:]}"
    elif len(cleaned) == 13 and cleaned.startswith("+639"):
        return f"{cleaned[:6]}***{cleaned[9:]}"
    elif len(cleaned) >= 8:
        return f"{cleaned[:4]}***{cleaned[-4:]}"
    return cleaned


def format_phone_display(phone):
    if phone is None:
        return "-"
    text = str(phone).strip()
    if not text:
        return "-"
    if (text.startswith("+639") or text.startswith("+638")) and len(text) == 13 and text[1:].isdigit():
        return "0" + text[3:]
    return text


def page_nav_options(page, total_pages, include_back=True):
    nav = []
    if page < total_pages:
        nav.append("[>] Next")
    if page > 1:
        nav.append("[<] Previous")
    if include_back:
        nav.append("[0] Back")
    return "        ".join(nav)


def print_controls(text, width):
    available = min(width, shutil.get_terminal_size(fallback=(120, 24)).columns)
    print(textwrap.fill(text, width=max(1, available), break_long_words=False, break_on_hyphens=False))


def render_data_table(title, records, columns, page, width=None, always_show_back=False, banner=None, footer_text=None, cancel_label=False, compact=False):
    width = table_width(columns, width or 0)
    total_records = len(records)
    total_pages = (total_records + PAGE_SIZE - 1) // PAGE_SIZE
    start = (page - 1) * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_records)

    header(title, input_screen=False, width=width, banner=banner)
    print_table_header(columns, compact=compact)
    print("-" * width)

    for rec in records[start:end]:
        print_table_row(rec, columns, compact=compact)

    print("-" * width)
    summary = f"Page {page} of {total_pages}    Showing {start + 1}-{end} of {total_records}"
    navigation = ""
    if total_pages > 1 or always_show_back:
        navigation = page_nav_options(page, total_pages, include_back=True)
        if cancel_label:
            navigation = navigation.replace("[0] Back", "[0] Cancel").replace("        ", "   ")
    if compact:
        print_controls(summary + ("    " + navigation if navigation else ""), width)
        if footer_text:
            print(footer_text)
    else:
        print(summary)
        if footer_text:
            print(footer_text)
        if navigation:
            print(navigation)
    if not compact:
        print()


def render_customer_selection_list(title, customers, page, banner=None):
    columns = [
        ("ID", "id", 4),
        ("Name", lambda c: f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(), 19),
        ("Membership", "membership", 10),
        ("Subscription", "subscription", 12),
    ]
    render_data_table(title, customers, columns, page, width=56, always_show_back=True, banner=banner)


def render_update_customer_list(customers, page):
    render_customer_selection_list("UPDATE CUSTOMER", customers, page)


def select_customer_from_list(title, empty_action, eligibility=None, empty_message=None, columns=None, width=56, on_not_found=None, banner=None, compact=False):
    page = 1
    params = {"eligibility": eligibility} if eligibility else None
    active_banner = banner
    while True:
        customers = request("GET", "/customers", params=params)
        if customers is None:
            return None
        if not customers:
            header(title, input_screen=False, width=width, banner=active_banner)
            msg = empty_message if empty_message else f"There are no customers to {empty_action}."
            print(f"\n{msg}")
            pause()
            return None

        customers = sorted(customers, key=lambda c: c.get("id", 0))
        total_pages = (len(customers) + PAGE_SIZE - 1) // PAGE_SIZE
        if page > total_pages:
            page = total_pages

        cols = columns if columns else [
            ("ID", "id", 4),
            ("Name", lambda c: f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(), 19),
            ("Membership", "membership", 10),
            ("Subscription", "subscription", 12),
        ]
        render_data_table(title, customers, cols, page, width=width, always_show_back=True, banner=active_banner, compact=compact)
        active_banner = None
        if compact:
            print("-" * table_width(cols, width))

        while True:
            value = input("Enter customer ID: ").strip()
            low = value.lower()
            if low in ("0", "b", "back"):
                raise GoBack()
            if low in (">", "n", "next") and page < total_pages:
                page += 1
                break
            if low in ("<", "p", "prev", "previous") and page > 1:
                page -= 1
                break
            if value == "":
                print("Customer ID is required.")
                continue
            if not is_valid_id(value) or int(value) > 9223372036854775807:
                print("Customer ID must contain numbers only.")
                continue

            cid = int(value)
            found = next((c for c in customers if c.get("id") == cid), None)
            if not found:
                if on_not_found:
                    on_not_found(cid)
                    break
                else:
                    cust = request("GET", f"/customers/{cid}", silent_404=True)
                    if not cust:
                        print("\nThat customer was not found.")
                    else:
                        print("\nID not in this list.")
                    pause()
                    break

            return found


def paginated_view(title, fetch_fn, columns, empty_message, sort_key="id", width=None, footer_fn=None):
    width = table_width(columns, width or 0)

    page = 1
    while True:
        records = fetch_fn()
        if records is None:
            return
        if isinstance(records, dict):
            records = [records]
        if not records:
            header(title, input_screen=False, width=width)
            print(f"\n{empty_message}")
            pause()
            return

        if sort_key:
            if callable(sort_key):
                records = sorted(records, key=sort_key)
            else:
                records = sorted(records, key=lambda r: r.get(sort_key, 0))

        total_pages = (len(records) + PAGE_SIZE - 1) // PAGE_SIZE
        if page > total_pages:
            page = total_pages

        footer_text = footer_fn(records) if footer_fn else None
        render_data_table(title, records, columns, page, width=width, footer_text=footer_text)

        if total_pages == 1:
            pause()
            return

        while True:
            choice = input("Enter choice: ").strip().lower()
            if choice in ("0", "b", "back"):
                raise GoBack()
            if choice in (">", "n", "next") and page < total_pages:
                page += 1
                break
            if choice in ("<", "p", "prev", "previous") and page > 1:
                page -= 1
                break

            if page < total_pages and page > 1:
                print("Invalid choice. Enter >, <, or 0.")
            elif page < total_pages:
                print("Invalid choice. Enter > or 0.")
            else:
                print("Invalid choice. Enter < or 0.")


def render_view_customers_table(customers, page):
    columns = [
        ("ID", "id", 4),
        ("First Name", "first_name", 12),
        ("Last Name", "last_name", 14),
        ("Phone", lambda c: format_phone_display(c.get("phone")), 11),
        ("Membership", "membership", 10),
        ("Subscription", "subscription", 12),
    ]
    render_data_table("VIEW CUSTOMERS", customers, columns, page, width=78)


def view_customers():
    page = 1
    while True:
        customers = request("GET", "/customers")
        if customers is None:
            return
        if not customers:
            header("VIEW CUSTOMERS", input_screen=False, width=78)
            print("\nThere are no customers to view.")
            pause()
            return

        customers = sorted(customers, key=lambda c: c.get("id", 0))
        total_pages = (len(customers) + PAGE_SIZE - 1) // PAGE_SIZE
        if page > total_pages:
            page = total_pages

        render_view_customers_table(customers, page)

        if total_pages == 1:
            pause()
            return

        while True:
            choice = input("Enter choice: ").strip().lower()
            if choice in ("0", "b", "back"):
                raise GoBack()
            if choice in (">", "n", "next") and page < total_pages:
                page += 1
                break
            if choice in ("<", "p", "prev", "previous") and page > 1:
                page -= 1
                break

            if page < total_pages and page > 1:
                print("Invalid choice. Enter >, <, or 0.")
            elif page < total_pages:
                print("Invalid choice. Enter > or 0.")
            else:
                print("Invalid choice. Enter < or 0.")


def update_customer():
    cust_cols = [
        ("ID", "id", 4),
        ("Name", lambda c: f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(), 19),
        ("Phone", lambda c: mask_phone(c.get("phone", "")), 12),
        ("Membership", "membership", 10),
        ("Subscription", "subscription", 12),
    ]

    def on_not_found(cid):
        cust = request("GET", f"/customers/{cid}", silent_404=True)
        if not cust:
            print("\nThat customer was not found.")
            pause()
            return

    banner = None
    while True:
        try:
            current = select_customer_from_list(
                "UPDATE CUSTOMER",
                "update",
                columns=cust_cols,
                width=69,
                on_not_found=on_not_found,
                banner=banner
            )
        except GoBack:
            break
        banner = None

        if not current:
            break

        customer_id = current["id"]

        print("\nCurrent Customer Information")
        print(f"First Name: {current['first_name']}")
        print(f"Last Name: {current['last_name']}")
        print(f"Phone: {current['phone']}")
        print("\nLeave blank to keep existing information. Enter 0 at any prompt to cancel.\n")

        try:
            first_name = ask_name(
                "First name",
                prompt="New First name: ",
                allow_blank=True
            )

            last_name = ask_name(
                "Last name",
                prompt="New Last name: ",
                allow_blank=True
            )

            phone = ask_phone(
                "New Phone: ",
                allow_blank=True
            )
        except GoBack:
            banner = "Cancelled. Nothing was saved."
            continue

        if not confirm("\nSave changes? (y/n, 0 to cancel): "):
            banner = "Cancelled. Nothing was saved."
            continue

        result = request(
            "PUT",
            f"/customers/{customer_id}",
            {
                "first_name": first_name or current["first_name"],
                "last_name": last_name or current["last_name"],
                "phone": phone or current["phone"]
            }
        )

        if result:
            print("\nCustomer updated successfully!")

        pause()


def delete_customer():
    cust_cols = [
        ("ID", "id", 4),
        ("Name", lambda c: f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(), 19),
        ("Phone", lambda c: mask_phone(c.get("phone", "")), 12),
        ("Membership", "membership", 10),
        ("Subscription", "subscription", 12),
    ]

    def on_not_found(cid):
        cust = request("GET", f"/customers/{cid}", silent_404=True)
        if not cust:
            print("\nThat customer was not found.")
            pause()
            return
        print("\nThis customer has memberships or payments and cannot be deleted.")
        pause()

    banner = None
    while True:
        try:
            customer = select_customer_from_list(
                "DELETE CUSTOMER",
                "delete",
                eligibility="delete",
                empty_message="No customers can be deleted.\nCustomers with memberships or payments are kept for records.",
                columns=cust_cols,
                width=69,
                on_not_found=on_not_found,
                banner=banner
            )
        except GoBack:
            break
        banner = None

        if not customer:
            break

        customer_id = customer["id"]
        full_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
        phone = customer.get("phone", "")

        print(f"\nCustomer: {full_name}")
        print(f"Phone: {phone}")

        if not confirm("\nDelete this customer? (y/n, 0 to cancel): "):
            banner = "Cancelled. Nothing was saved."
            continue

        result = request(
            "DELETE",
            f"/customers/{customer_id}"
        )

        if result:
            print("\nCustomer deleted successfully!")
        pause()


def customer_management():
    if CURRENT_ROLE == "staff":
        submenu("CUSTOMER MANAGEMENT", [("View All Customers", view_customers)])
        return
    submenu("CUSTOMER MANAGEMENT", [
        ("View All Customers", view_customers),
        ("Update Customer Information", update_customer),
        ("Delete Customer", delete_customer),
    ])


# MEMBERSHIP MANAGEMENT

def customer_overview():
    page = 1
    page_size = 10
    search_query = ""

    while True:
        params = {}
        if search_query:
            params["search"] = search_query
        customers = request("GET", "/customers", params=params) or []

        total_pages = max(1, (len(customers) + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        page_customers = customers[start_idx:start_idx + page_size]

        cols = [
            ("ID", "id", 4),
            ("Customer", lambda row: f"{row.get('first_name', '')} {row.get('last_name', '')}".strip(), 26),
            ("Yearly", lambda row: row.get("yearly_status") or "-", 12),
            ("Monthly", lambda row: row.get("monthly_status") or "-", 12),
            ("Last Visit", lambda row: row.get("last_visit") or "-", 12),
        ]
        width = table_width(cols, 90)
        header("CUSTOMER OVERVIEW", input_screen=False, width=width)
        if search_query:
            print(f"Filter: '{search_query}' (Enter empty search to reset)")
        print_table_header(cols)
        print("-" * width)
        if not page_customers:
            print("No customers found.")
        else:
            for c in page_customers:
                print_table_row(c, cols)

        print("-" * width)
        nav = [f"Page {page} of {total_pages}"]
        if page < total_pages:
            nav.append("[>] Next")
        if page > 1:
            nav.append("[<] Prev")
        nav.append("[S] Search")
        nav.append("[0] Back")
        print("        ".join(nav))
        print("-" * width)
        val = input("Enter Customer ID to view details (or choice): ").strip()
        low = val.lower()

        if low in ("0", "b", "back"):
            return
        if low in (">", "n", "next") and page < total_pages:
            page += 1
            continue
        if low in ("<", "p", "prev", "previous") and page > 1:
            page -= 1
            continue
        if low in ("s", "search"):
            search_query = input("Search by ID, name, or phone [Enter to clear]: ").strip()
            page = 1
            continue

        if val.isdigit():
            target_id = int(val)
            cust_check = request("GET", f"/customers/{target_id}", silent_404=True)
            if cust_check:
                customer_details_view(target_id)
            else:
                print(f"Customer with ID {target_id} was not found.")
                pause()
        else:
            if val:
                search_query = val
                page = 1


def customer_details_view(customer_id):
    while True:
        ov = request("GET", f"/customers/{customer_id}/overview")
        if not ov:
            print(f"Customer with ID {customer_id} not found.")
            pause()
            return

        width = 60
        header("CUSTOMER DETAILS", input_screen=False, width=width)
        print(f"{'Customer ID:':<24}{ov['id']}")
        print(f"{'Name:':<24}{ov['name']}")
        print(f"{'Phone:':<24}{mask_phone(ov['phone'])}")

        y_exp = f"{ov['yearly_end_date']} ({ov['yearly_label']})" if ov.get("yearly_end_date") else ov["yearly_label"]
        print(f"{'Yearly Expiration:':<24}{y_exp}")

        m_exp = f"{ov['monthly_end_date']} ({ov['monthly_label']})" if ov.get("monthly_end_date") else ov["monthly_label"]
        print(f"{'Monthly Expiration:':<24}{m_exp}")

        print(f"{'Daily Access:':<24}{ov['daily_access']}")
        print(f"{'Discount Eligibility:':<24}{ov['discount_eligibility']}")
        print(f"{'Total Purchases:':<24}{ov['total_purchases']}")
        print(f"{'Lifetime Spending:':<24}{format_currency(ov['lifetime_spending'])}")
        print(f"{'Total Visits:':<24}{ov['total_visits']}")
        print(f"{'Last Visit:':<24}{ov['last_visit'] or 'None'}")
        print("-" * width)
        print("[1] Membership History")
        print("[2] Purchase History")
        print("[3] Visit History")
        print("-" * width)
        print("[0] Back")
        print("-" * width)
        choice = input("Choice: ").strip()

        if choice in ("0", "b", "back"):
            return
        elif choice == "1":
            view_customer_membership_history(customer_id, ov["name"])
        elif choice == "2":
            view_customer_purchase_history(customer_id, ov["name"])
        elif choice == "3":
            view_customer_visit_history(customer_id, ov["name"])
        else:
            print("Invalid choice.")
            pause()


def view_customer_membership_history(customer_id, customer_name):
    mems = request("GET", f"/customers/{customer_id}/memberships") or []
    cols = [
        ("ID", "id", 4), ("Plan", "plan", 24),
        ("Start", "start_date", 10), ("End", "end_date", 10),
        ("Status", "status", 12),
        ("Receipt", lambda row: row.get("receipt_no") or "-", 12),
    ]
    width = table_width(cols, 96)
    header("MEMBERSHIP HISTORY", input_screen=False, width=width)
    print(f"Customer: {customer_name}")
    print("-" * width)
    if not mems:
        print("No membership history found.")
    else:
        print_table_header(cols)
        print("-" * width)
        for m in mems:
            print_table_row(m, cols)
    print("-" * width)
    pause()


def view_customer_purchase_history(customer_id, customer_name):
    while True:
        sales = request("GET", f"/customers/{customer_id}/sales") or []
        cols = [
            ("Receipt No", "receipt_no", 12),
            ("Date", lambda row: row.get("created_at", "")[:10], 12),
            ("Items", lambda row: len(row.get("items", [])), 7),
            ("Total", lambda row: format_currency(row["total"]), 12, "right"),
            ("Status", "status", 12),
        ]
        width = table_width(cols, 88)
        header("PURCHASE HISTORY", input_screen=False, width=width)
        print(f"Customer: {customer_name}")
        print("-" * width)
        if not sales:
            print("No purchase history found.")
            print("-" * width)
            pause()
            return
        print_table_header(cols)
        print("-" * width)
        for sale in sales:
            print_table_row(sale, cols)
        print("-" * width)
        print("Enter Receipt No / ID to view receipt, or [0] Back.")
        choice = input("Choice: ").strip()
        if choice in ("0", "b", "back", ""):
            return
        matched = None
        for s in sales:
            if choice.lower() == s["receipt_no"].lower() or (choice.isdigit() and int(choice) == s["id"]):
                matched = s
                break
        if matched:
            print_receipt(matched)
            pause()
        else:
            print("Receipt not found.")
            pause()


def view_customer_visit_history(customer_id, customer_name):
    visits = request("GET", f"/customers/{customer_id}/visits") or []
    cols = [
        ("ID", "id", 6),
        ("Check-in Time", "check_in_at", 22),
        ("Receipt", lambda row: row.get("receipt_no") or "-", 12),
    ]
    width = table_width(cols, 66)
    header("VISIT HISTORY", input_screen=False, width=width)
    print(f"Customer: {customer_name}")
    print("-" * width)
    if not visits:
        print("No visit history found.")
    else:
        print_table_header(cols)
        print("-" * width)
        for visit in visits:
            print_table_row(visit, cols)
    print("-" * width)
    pause()


def view_plan_memberships(plan_name, status="all"):
    title = "YEARLY MEMBERSHIPS" if plan_name == "Yearly membership" else "MONTHLY SESSIONS"
    columns = [
        ("ID", "id", 4),
        ("Customer", "customer_name", 18),
        ("Start Date", "start_date", 10),
        ("End Date", "end_date", 10),
        ("Status", "status", 10),
    ]
    width = table_width(columns, 68)
    statuses = {"1": "active", "2": "expired", "3": "all"}
    page = 1
    while True:
        records = request("GET", "/memberships", params={"status": status, "plan": plan_name})
        if records is None:
            pause()
            return
        records = sorted(records, key=lambda r: (
            r.get("status", "").casefold() != "active",
            r.get("customer_id", 0), r.get("start_date", ""), r.get("id", 0),
        ))
        pages = max(1, (len(records) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        header(title, input_screen=False, width=width)
        print(f"Status: {status.title()}    Records: {len(records)}    Page {page} of {pages}")
        print("-" * width)
        print_table_header(columns, compact=True)
        print("-" * width)
        for record in records[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]:
            print_table_row(record, columns, compact=True)
        if not records:
            print("No matching memberships found.")
        print("-" * width)
        controls = "[1] Active        [2] Expired        [3] All"
        if pages > 1:
            controls += "        [<] Previous page        [>] Next page"
        print(controls + "        [0] Back")
        print("-" * width)
        choice = input("Choice: ").strip().casefold()
        if choice in ("0", "b", "back"):
            return
        if choice in statuses:
            status, page = statuses[choice], 1
        elif choice in ("<", "p", "prev"):
            page = max(1, page - 1)
        elif choice in (">", "n", "next"):
            page = min(pages, page + 1)
        else:
            print("Invalid option.")
            pause()


def register_plan(plan_name):
    is_yearly = (plan_name == "Yearly membership")
    title = "REGISTER YEARLY MEMBERSHIP" if is_yearly else "REGISTER MONTHLY SESSION"
    fee_str = "300.00" if is_yearly else "1,200.00"
    term_calc = add_one_year if is_yearly else add_one_month
    eligibility = "register_yearly" if is_yearly else "register_monthly"

    empty_msg = (
        "All customers already have a yearly membership.\nUse Renew to extend an existing membership."
        if is_yearly else
        "All customers already have a monthly session.\nUse Renew to extend an existing monthly session."
    )

    cols = [
        ("ID", "id", 4),
        ("Name", lambda c: f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(), 19),
        ("Phone", lambda c: mask_phone(c.get("phone", "")), 12),
    ]

    def on_not_found(cid):
        cust = request("GET", f"/customers/{cid}", silent_404=True)
        if not cust:
            print("\nThat customer was not found.")
            pause()
            return
        if is_yearly:
            print("\nThis customer already has a yearly membership. Use Renew instead.")
        else:
            print("\nThis customer already has a monthly session. Use Renew instead.")
        pause()

    while True:
        header(title, input_screen=False, width=58)
        print("[1] Select Existing Customer")
        print("[2] Register New Customer")
        print("-" * 58)
        print("[0] Back")
        print("-" * 58)
        option = input("Choice: ").strip().lower()
        if option in ("0", "b", "back"):
            return

        new_customer = None
        if option == "1":
            try:
                customer = select_customer_from_list(
                    title,
                    "register a membership",
                    compact=True,
                    eligibility=eligibility,
                    empty_message=empty_msg,
                    columns=cols,
                    width=56,
                    on_not_found=on_not_found,
                )
            except GoBack:
                continue
            if not customer:
                continue
        elif option == "2":
            try:
                new_customer = collect_new_customer_data("REGISTER NEW CUSTOMER")
            except GoBack:
                continue
            customer = {"id": None, **new_customer}
        else:
            print("Invalid choice.")
            pause()
            continue

        start = ph_today()
        end = term_calc(start)
        full_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()

        print(f"\nCustomer: {full_name}")
        print(f"Plan: {plan_name}")
        print(f"Price: {fee_str}")
        print(f"Start Date: {start}")
        print(f"End Date: {end}")

        try:
            method = ask_payment_method(show_cancel=True)
        except GoBack:
            banner = "Cancelled. Nothing was saved."
            continue

        fee_dec = Decimal(fee_str.replace(",", ""))
        if method == "Cash":
            cancelled_tender = False
            while True:
                t_input = input(f"Amount tendered [0 to cancel]: ").strip()
                if t_input in ("0", "cancel", "b", "back"):
                    cancelled_tender = True
                    break
                try:
                    tendered_dec = Decimal(t_input)
                    if tendered_dec < fee_dec:
                        print("Amount is less than the total due")
                        continue
                    break
                except Exception:
                    print("Enter a valid amount")
            if cancelled_tender:
                banner = "Cancelled. Nothing was saved."
                continue
            tendered_str = f"{tendered_dec:.2f}"
            change_str = f"{tendered_dec - fee_dec:.2f}"
        else:
            tendered_str = f"{fee_dec:.2f}"
            change_str = "0.00"

        confirmed = confirm_purchase_screen(
            customer_name=full_name,
            membership_label="Active",
            items_count=1,
            subtotal=fee_str,
            discount="0.00",
            total=fee_str,
            payment_method=method,
            tendered=tendered_str,
            change=change_str,
        )
        if not confirmed:
            banner = "Cancelled. Nothing was saved."
            continue

        req_id = str(uuid.uuid4())
        result = request(
            "POST",
            "/memberships",
            {
                "customer_id": customer["id"],
                "new_customer": new_customer,
                "plan": plan_name,
                "start_date": str(start),
                "end_date": str(end),
                "method": method,
                "amount_tendered": tendered_str,
                "request_id": req_id
            }
        )

        if result:
            print("\nMembership registered successfully!")
            if "sale" in result:
                print_receipt(result["sale"])
            else:
                show(result)
            pause()
        else:
            pause()


def renew_plan(plan_name):
    is_yearly = (plan_name == "Yearly membership")
    title = "RENEW YEARLY MEMBERSHIP" if is_yearly else "RENEW MONTHLY SESSION"
    status_key = "yearly_status" if is_yearly else "monthly_status"
    end_date_key = "yearly_end_date" if is_yearly else "monthly_end_date"
    eligibility = "renew_yearly" if is_yearly else "renew_monthly"
    fee_str = "300.00" if is_yearly else "1,200.00"
    term_calc = add_one_year if is_yearly else add_one_month
    empty_msg = f"No {plan_name.lower()}s found to renew."

    renew_columns = [
        ("ID", "id", 4),
        ("Name", lambda c: f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(), 17),
        ("Phone", lambda c: mask_phone(c.get("phone", "")), 12),
        ("Status", lambda c: c.get(status_key) or "-", 10),
        ("End Date", lambda c: c.get(end_date_key) or "-", 10),
    ]

    def on_not_found(cid):
        cust = request("GET", f"/customers/{cid}", silent_404=True)
        if not cust:
            print("\nThat customer was not found.")
            pause()
            return
        if is_yearly:
            print("\nThis customer has never had a yearly membership. Use Register instead.")
        else:
            print("\nThis customer has never had a monthly session. Use Register instead.")
        pause()

    banner = None
    while True:
        try:
            customer = select_customer_from_list(
                title,
                "renew",
                compact=True,
                eligibility=eligibility,
                empty_message=empty_msg,
                columns=renew_columns,
                width=65,
                on_not_found=on_not_found,
                banner=banner
            )
        except GoBack:
            break
        banner = None

        if not customer:
            break

        current_end_str = customer.get(end_date_key)
        current_status = customer.get(status_key)
        today = ph_today()

        if current_status == "Active" and current_end_str:
            start = date.fromisoformat(current_end_str)
            status_label = "(Active)"
        else:
            start = today
            status_label = "(Expired)"

        end = term_calc(start)
        full_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()

        print(f"\nCustomer: {full_name}")
        print(f"Plan: {plan_name}")
        print(f"Price: {fee_str}")
        print(f"Current End Date: {current_end_str or '-'} {status_label}")
        print(f"Renewal Start Date: {start}")
        print(f"Renewal End Date: {end}")

        try:
            method = ask_payment_method(show_cancel=True)
        except GoBack:
            banner = "Cancelled. Nothing was saved."
            continue

        fee_dec = Decimal(fee_str.replace(",", ""))
        if method == "Cash":
            cancelled_tender = False
            while True:
                t_input = input(f"Amount tendered [0 to cancel]: ").strip()
                if t_input in ("0", "cancel", "b", "back"):
                    cancelled_tender = True
                    break
                try:
                    tendered_dec = Decimal(t_input)
                    if tendered_dec < fee_dec:
                        print("Amount is less than the total due")
                        continue
                    break
                except Exception:
                    print("Enter a valid amount")
            if cancelled_tender:
                banner = "Cancelled. Nothing was saved."
                continue
            tendered_str = f"{tendered_dec:.2f}"
            change_str = f"{tendered_dec - fee_dec:.2f}"
        else:
            tendered_str = f"{fee_dec:.2f}"
            change_str = "0.00"

        confirmed = confirm_purchase_screen(
            customer_name=full_name,
            membership_label="Active",
            items_count=1,
            subtotal=fee_str,
            discount="0.00",
            total=fee_str,
            payment_method=method,
            tendered=tendered_str,
            change=change_str,
        )
        if not confirmed:
            banner = "Cancelled. Nothing was saved."
            continue

        req_id = str(uuid.uuid4())
        result = request(
            "POST",
            "/memberships/renew",
            {
                "customer_id": customer["id"],
                "plan": plan_name,
                "start_date": str(start),
                "end_date": str(end),
                "method": method,
                "amount_tendered": tendered_str,
                "request_id": req_id
            }
        )

        if result:
            print("\nMembership renewed successfully!")
            if "sale" in result:
                print_receipt(result["sale"])
            else:
                show(result)
            pause()
        else:
            pause()


def browse_plan_memberships(plan):
    view_plan_memberships(plan)


def yearly_membership_menu():
    submenu("YEARLY MEMBERSHIP", [
        ("Register", lambda: register_plan("Yearly membership")),
        ("Renew", lambda: renew_plan("Yearly membership")),
        ("View Memberships", lambda: browse_plan_memberships("Yearly membership")),
    ])


def monthly_session_menu():
    submenu("MONTHLY SESSION", [
        ("Register", lambda: register_plan("Monthly session")),
        ("Renew", lambda: renew_plan("Monthly session")),
        ("View Memberships", lambda: browse_plan_memberships("Monthly session")),
    ])


def select_sale_customer(title):
    """Choose a verified active yearly member or an anonymous non-member sale."""
    while True:
        header(title, input_screen=False, width=58)
        print("[1] Member (discounted rate)")
        print("[2] Non-member (regular rate)")
        print("-" * 58)
        print("[0] Back")
        print("-" * 58)
        choice = input("Choice: ").strip().lower()

        if choice in ("0", "b", "back", "cancel"):
            return None
        if choice == "2":
            return None, "Walk-in", "Non-member"
        if choice != "1":
            print("Invalid choice.")
            pause()
            continue

        columns = [
            ("ID", "id", 4),
            ("Name", lambda c: f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(), 22),
            ("Yearly", "yearly_status", 10),
            ("Expires", lambda c: c.get("yearly_end_date") or "-", 10),
        ]
        try:
            customer = select_customer_from_list(
                "SELECT ACTIVE MEMBER",
                "select for a member-rate sale",
                eligibility="active_yearly",
                empty_message="No active yearly members found.",
                columns=columns,
                width=62,
                compact=True,
            )
        except GoBack:
            continue

        if not customer:
            continue
        if customer.get("yearly_status") != "Active":
            print("This customer does not have an active yearly membership.")
            pause()
            continue

        full_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
        return customer["id"], full_name, "Active (Yearly)"


def daily_session_flow():
    while True:
        chosen = select_sale_customer("DAILY SESSION")
        if chosen is None:
            return
        customer_id, customer_name, membership_label = chosen

        if customer_id is not None:
            ov = request("GET", f"/customers/{customer_id}/overview")
            if ov is None:
                pause()
                continue
            if ov.get("has_gym_access"):
                header("DAILY SESSION", input_screen=False, width=58)
                print(f"Customer: {customer_name}")
                print("This customer already has valid monthly gym access.")
                print("A daily session is not required.")
                print("-" * 58)
                print("[1] Purchase daily session anyway")
                print("[0] Cancel")
                if input("Choice: ").strip() != "1":
                    return

        # Resolve the current daily-session product ID instead of assuming a seeded ID.
        daily_products = request("GET", "/products")
        if daily_products is None:
            pause()
            return
        daily_product = next(
            (p for p in daily_products if p.get("name") == "Daily session" and p.get("is_active", 1) == 1),
            None,
        )
        if not daily_product:
            print("Daily session is not available.")
            pause()
            return

        # A daily pass always represents exactly one session.
        prod_quote = request("POST", "/quotes", {
            "customer_id": customer_id,
            "items": [{"product_id": daily_product["id"], "quantity": 1}]
        })
        if not prod_quote:
            print("Error retrieving product details.")
            pause()
            return

        subtotal_str = prod_quote["subtotal"]
        discount_str = prod_quote["discount"]
        total_str = prod_quote["total"]
        total_dec = Decimal(total_str)

        header("PAYMENT", input_screen=False, width=58)
        print(f"Customer:    {customer_name}")
        print(f"Total due:   {format_currency(total_str)}")
        print("-" * 58)
        print("Payment method:")
        print("[1] Cash")
        print("[2] E-Wallet")
        print("-" * 58)
        print("[0] Cancel")
        print("-" * 58)
        pm_choice = input("Choice: ").strip()
        if pm_choice in ("0", "cancel", "b", "back"):
            return
        if pm_choice == "1":
            method = "Cash"
            cancelled_tender = False
            while True:
                t_input = input(f"Amount tendered [0 to cancel]: ").strip()
                if t_input in ("0", "cancel", "b", "back"):
                    cancelled_tender = True
                    break
                try:
                    tendered_dec = Decimal(t_input)
                    if tendered_dec < total_dec:
                        print("Amount is less than the total due")
                        continue
                    break
                except Exception:
                    print("Enter a valid amount")
            if cancelled_tender:
                continue
            tendered_str = f"{tendered_dec:.2f}"
            change_str = f"{tendered_dec - total_dec:.2f}"
        elif pm_choice == "2":
            method = "E-Wallet"
            tendered_str = total_str
            change_str = "0.00"
        else:
            print("Invalid payment method.")
            pause()
            continue

        confirmed = confirm_purchase_screen(
            customer_name=customer_name,
            membership_label=membership_label,
            items_count=1,
            subtotal=subtotal_str,
            discount=discount_str,
            total=total_str,
            payment_method=method,
            tendered=tendered_str,
            change=change_str,
        )

        if not confirmed:
            print("\nTransaction cancelled. No changes made.")
            pause()
            return

        req_id = str(uuid.uuid4())
        res = request("POST", "/daily-sessions", {
            "customer_id": customer_id,
            "payment_method": method,
            "amount_tendered": tendered_str,
            "request_id": req_id
        })
        if res:
            print("\nDaily session purchased and visit checked in successfully!")
            print_receipt(res)
            pause()
            return
        else:
            pause()
            return


def refund_purchase_session():
    """Issue a full refund against an existing sale; keep the original receipt for audit."""
    page = 1
    query = ""
    page_size = PAGE_SIZE
    width = 130
    columns = [
        ("Receipt No.", "reference", 12),
        ("Product / Service", "item_names", 43),
        ("Amount", lambda row: format_currency(row["amount"]), 13, "right"),
        ("Status", "status", 11),
        ("Date", lambda row: str(row.get("created_at", ""))[:10], 12),
        ("Customer", lambda row: row.get("customer_name") if row.get("customer_id") is not None else "-", 24),
    ]

    while True:
        params = {"query": query} if query else None
        records = request("GET", "/transactions/search", params=params)
        if records is None:
            pause()
            return
        eligible = [
            record for record in records
            if record["record_type"] == "sale" and record["status"] == "Completed"
        ]
        total_pages = max(1, (len(eligible) + page_size - 1) // page_size)
        page = min(page, total_pages)
        visible = eligible[(page - 1) * page_size:page * page_size]

        header("REFUND PURCHASE / SESSION", input_screen=False, width=width)
        print("Only completed, unrefunded receipts can be refunded.")
        print("A full refund is recorded in the database; money must be returned manually.")
        if query:
            print(f"Search filter: {query}")
        print(f"Eligible sales: {len(eligible)}   |   Page {page} of {total_pages}")
        print("-" * width)
        print_table_header(columns, compact=True)
        print("-" * width)
        if eligible:
            for transaction in visible:
                print_table_row(transaction, columns, compact=True)
        else:
            print("No eligible sales found.")
        print("-" * width)
        controls = "[S] Search by customer, item, or receipt"
        if total_pages > 1:
            controls += "    [<] Previous page    [>] Next page"
        controls += "    [C] Clear search    [0] Back"
        print_controls(controls, width)
        print()
        choice = input("Receipt number or choice: ").strip()
        lower = choice.casefold()
        if lower in ("0", "b", "back"):
            if query:
                query = ""
                page = 1
                continue
            return
        if lower in (">", "n", "next"):
            if page < total_pages:
                page += 1
            continue
        if lower in ("<", "p", "prev", "previous"):
            if page > 1:
                page -= 1
            continue
        if lower in ("c", "clear"):
            query = ""
            page = 1
            continue
        if lower in ("s", "search"):
            query = input("Search customer, item, or receipt [0 to cancel]: ").strip()
            if query == "0":
                query = ""
            page = 1
            continue

        selected = next(
            (r for r in eligible if r["reference"].casefold() == lower),
            None,
        )
        if not selected:
            print("Enter an eligible receipt number from the list.")
            pause()
            continue

        sale = request("GET", f"/sales/{selected['record_id']}")
        if not sale:
            pause()
            continue

        header("CONFIRM REFUND DETAILS", input_screen=False, width=width)
        print(f"Original Receipt:  {sale['receipt_no']}")
        print(f"Customer:          {sale['customer_name']}")
        print(f"Original Payment:  {sale['payment_method']}")
        print(f"Refund Amount:     {format_currency(sale['total'])}")
        print("Purchased items:")
        for item in sale.get("items", []):
            for line in wrap_cell(f"  {item['quantity']} x {item['item_name']}", width - 2):
                print(line)
        print("-" * width)
        print("This refunds the entire receipt, not individual items.")
        if str(sale.get("kind", "")).lower() == "membership":
            print("The purchased membership/session will be cancelled.")
        if str(sale.get("kind", "")).lower() == "trainer":
            print("The corresponding trainer appointment will be cancelled.")
        print("Attendance records remain as historical records.")
        print("This does NOT send money automatically to a payment provider.")
        print("-" * width)

        try:
            reason = ask("Reason for refund [0 to cancel]: ")
            if len(reason.strip()) < 3:
                print("Reason must have at least 3 characters.")
                pause()
                continue
            method = ask_payment_method()
        except GoBack:
            continue

        print(f"Refund method:  {method}")
        print(f"Refund amount:  {format_currency(sale['total'])}")
        print("Return this amount to the customer manually before confirming.")
        if not confirm("Have you issued this full refund? (Y/N, 0 to cancel): "):
            continue
        result = request("POST", f"/sales/{selected['record_id']}/refund", {
            "reason": reason,
            "refund_method": method,
        })
        if not result:
            pause()
            continue
        header("REFUND RECORDED", input_screen=False, width=width)
        print(f"Refund No.:       {result['refund_no']}")
        print(f"Original Receipt: {result['receipt_no']}")
        print(f"Amount:           {format_currency(result['amount'])}")
        print(f"Method:           {result['method']}")
        print(f"Reason:           {result['reason']}")
        print(f"Date:             {result['created_at']}")
        print("-" * width)
        print("Manual refund acknowledged and recorded in the refund ledger.")
        print("No payment-provider transfer was performed by this system.")
        pause()
        page = 1
        query = ""


def refund_history():
    refunds = request("GET", "/refunds")
    if refunds is None:
        pause()
        return
    if not refunds:
        header("REFUND HISTORY", input_screen=False)
        print("No refunds have been recorded.")
        pause()
        return

    paginated_view(
        "REFUND HISTORY",
        lambda: refunds,
        [
            ("Refund No.", "refund_no", 12),
            ("Original Receipt", "receipt_no", 16),
            ("Date", lambda row: row["created_at"][:16], 16),
            ("Amount", lambda row: format_currency(row["amount"]), 12, "right"),
            ("Method", "method", 10),
        ],
        empty_message="No refunds have been recorded.",
        sort_key=None,
        width=92,
    )


def product_service_management():
    if CURRENT_ROLE == "staff":
        submenu("PRODUCT/SERVICE MANAGEMENT", [
            ("Yearly Membership", yearly_membership_menu),
            ("Monthly Session", monthly_session_menu),
            ("Daily Session", daily_session_flow),
            ("Services/Products", services_products_menu),
            ("Customer Overview", customer_overview),
        ])
        return
    submenu("PRODUCT/SERVICE MANAGEMENT", [
        ("Yearly Membership", yearly_membership_menu),
        ("Monthly Session", monthly_session_menu),
        ("Daily Session", daily_session_flow),
        ("Services/Products", services_products_menu),
        ("Customer Overview", customer_overview),
        ("Refund Purchase / Session", refund_purchase_session),
        ("Refund History", refund_history),
    ])


membership_management = product_service_management


def view_payments(method=""):
    if method == "Cash":
        title = "CASH PAYMENTS"
        empty_msg = "There are no cash payments to view."
    elif method == "E-Wallet":
        title = "E-WALLET PAYMENTS"
        empty_msg = "There are no e-wallet payments to view."
    else:
        title = "PAYMENT HISTORY"
        empty_msg = "There are no payments to view."

    columns = [
        ("ID", "id", 4),
        ("Customer", "customer_name", 18),
        ("Item", "description", 24),
        ("Amount", lambda r: format_currency(r.get("amount")), 10, "right"),
        ("Date", lambda r: str(r.get("created_at", ""))[:10], 10),
    ]

    footer_fn = None
    if method in ("Cash", "E-Wallet"):
        footer_fn = lambda recs: f"Total {method.lower()}: {format_currency(sum(Decimal(r['amount']) for r in recs))}"

    paginated_view(
        title,
        lambda: request("GET", "/payments", params={"method": method} if method else None),
        columns,
        empty_message=empty_msg,
        sort_key=None,
        width=78,
        footer_fn=footer_fn
    )


def payment_management():
    submenu("PAYMENT MANAGEMENT", [
        ("View Payment History", lambda: view_payments()),
        ("View Cash Payments", lambda: view_payments("Cash")),
        ("View E-Wallet Payments", lambda: view_payments("E-Wallet")),
    ])


# PRODUCTS AND SERVICES

def ask_product_category():
    categories = list(PRODUCT_CATEGORIES)
    print("\nCategories:")
    for idx, cat in enumerate(categories, 1):
        print(f"[{idx}] {cat} ({CATEGORY_TO_TYPE[cat]})")
    print("[0] Cancel")
    while True:
        val = ask("Select Category (1-6 or name, 0 to cancel): ")
        if val in ("0", "cancel"):
            raise GoBack()
        if val.isdigit() and 1 <= int(val) <= len(categories):
            return categories[int(val) - 1]
        for cat in categories:
            if val.lower() == cat.lower():
                return cat
        print("Invalid category. Choose: " + ", ".join(categories))


def item_table_columns(name_header="Item Name"):
    return [
        ("ID", "id", 3),
        (name_header, "name", ITEM_NAME_WIDTH),
        ("Category", "category", 12),
        ("Price", lambda r: format_currency(r.get("price")), 12, "right"),
    ]


def ask_item_name(prompt="Product/Service Name (0 to cancel): "):
    while True:
        val = re.sub(r"\s+", " ", ask(prompt))
        if val == "0":
            raise GoBack()
        if len(val) > MAX_ITEM_NAME_LENGTH:
            print(f"Item name must be {MAX_ITEM_NAME_LENGTH} characters or fewer.")
            continue
        return val


def product_data():
    name = ask_item_name("Product/Service Name (0 to cancel): ")
    category = ask_product_category()
    item_type = CATEGORY_TO_TYPE[category]
    price = ask_amount("Price (0 to cancel): ")

    print(f"\nName: {name}")
    print(f"Category: {category}")
    print(f"Type: {item_type}")
    print(f"Price: {format_currency(price)}")

    return {
        "name": name,
        "category": category,
        "price": price
    }


def add_product():
    header("ADD PRODUCT OR SERVICE", input_screen=True)

    try:
        data = product_data()
    except GoBack:
        header("PRODUCTS AND SERVICES", input_screen=False, banner="Cancelled. Nothing was saved.")
        pause()
        return

    if not confirm("\nSave product/service? (y/n, 0 to cancel): "):
        header("PRODUCTS AND SERVICES", input_screen=False, banner="Cancelled. Nothing was saved.")
        pause()
        return

    result = request(
        "POST",
        "/products",
        data
    )

    if result:
        print("\nProduct/Service added successfully!")
        show(result)

    pause()


def filter_items_by_type(records, item_type):
    if records is None:
        return None
    if not item_type:
        return records
    return [
        r for r in records
        if (r.get("type") or CATEGORY_TO_TYPE.get(r.get("category"))) == item_type
    ]


def item_type_meta(item_type, action_prefix=""):
    if item_type == "Service":
        title = f"{action_prefix} SERVICE" if action_prefix else "SERVICES"
        return title, "Service Name", "There are no services to view."
    elif item_type == "Product":
        title = f"{action_prefix} PRODUCT" if action_prefix else "PRODUCTS"
        return title, "Product Name", "There are no products to view."
    else:
        title = f"{action_prefix} PRODUCT OR SERVICE" if action_prefix else "PRODUCTS AND SERVICES"
        return title, "Item Name", "There are no items to view."


def choose_item_type(title, allow_all=True):
    width = 78
    while True:
        header(title, input_screen=False, width=width)
        print("[1] Services")
        print("[2] Products")
        if allow_all:
            print("[3] All")
        print("[0] Back")
        print("-" * width)

        choice = input("Enter choice: ").strip().lower()
        if choice in ("0", "b", "back"):
            return None
        elif choice in ("1", "s", "service", "services"):
            return "Service"
        elif choice in ("2", "p", "product", "products"):
            return "Product"
        elif allow_all and choice in ("3", "a", "all"):
            return ""
        else:
            print("\nInvalid choice.")
            pause()


def view_items_list(title, item_type, name_header, empty_message):
    columns = item_table_columns(name_header)
    paginated_view(
        title,
        lambda: filter_items_by_type(request("GET", "/products"), item_type),
        columns,
        empty_message=empty_message,
        sort_key="id"
    )


def view_services():
    view_items_list("SERVICES", "Service", "Service Name", "There are no services to view.")


def view_only_products():
    view_items_list("PRODUCTS", "Product", "Product Name", "There are no products to view.")


def view_all_items():
    view_items_list("PRODUCTS AND SERVICES", "", "Item Name", "There are no items to view.")


def view_products():
    while True:
        chosen_type = choose_item_type("PRODUCTS AND SERVICES", allow_all=True)
        if chosen_type is None:
            return
        title, name_col, empty_msg = item_type_meta(chosen_type, action_prefix="")
        try:
            view_items_list(title, chosen_type, name_col, empty_msg)
        except GoBack:
            pass


def select_item_from_table(title, item_type="", name_header="Item Name", empty_message="There are no items to view.", eligibility=None, on_not_found=None, banner=None):
    columns = item_table_columns(name_header)
    width = table_width(columns)
    page = 1

    params = {}
    if item_type:
        params["type"] = item_type
    if eligibility:
        params["eligibility"] = eligibility

    active_banner = banner
    while True:
        records = request("GET", "/products", params=params if params else None)
        if records is None:
            pause()
            return None
        if not records:
            header(title, input_screen=False, width=width, banner=active_banner)
            print(f"\n{empty_message}")
            pause()
            return None

        records = sorted(records, key=lambda r: r.get("id", 0))
        total_pages = (len(records) + PAGE_SIZE - 1) // PAGE_SIZE
        if page > total_pages:
            page = total_pages

        render_data_table(title, records, columns, page, width=width, always_show_back=True, banner=active_banner)
        active_banner = None

        while True:
            val = input("Item ID: ").strip()
            low = val.lower()
            if low in ("0", "b", "back"):
                raise GoBack()
            if low in (">", "n", "next") and page < total_pages:
                page += 1
                break
            if low in ("<", "p", "prev", "previous") and page > 1:
                page -= 1
                break
            if val == "":
                print("Item ID is required.")
                continue
            if not val.isdigit() or int(val) <= 0:
                print("Item ID must contain numbers only.")
                continue
            pid = int(val)
            matched = next((r for r in records if r.get("id") == pid), None)
            if not matched:
                if on_not_found:
                    on_not_found(pid)
                    break
                else:
                    prod = request("GET", f"/products/{pid}", silent_404=True)
                    if not prod:
                        print(f"\nThat item was not found.")
                    else:
                        print("\nID not in this list.")
                    pause()
                    break
            return matched


def update_product():
    while True:
        chosen_type = choose_item_type("UPDATE PRODUCT OR SERVICE", allow_all=True)
        if chosen_type is None:
            return
        title, name_col, empty_msg = item_type_meta(chosen_type, action_prefix="UPDATE")

        def on_not_found(pid):
            prod = request("GET", f"/products/{pid}", silent_404=True)
            if not prod:
                print("\nThat item was not found.")
                pause()
                return

        banner = None
        while True:
            try:
                current = select_item_from_table(
                    title,
                    item_type=chosen_type,
                    name_header=name_col,
                    empty_message=empty_msg,
                    on_not_found=on_not_found,
                    banner=banner
                )
            except GoBack:
                break
            banner = None
            if not current:
                break

            product_id = current["id"]
            print("\nCurrent Information")
            show(current)

            print("\nEnter New Information\n")
            try:
                data = product_data()
            except GoBack:
                banner = "Cancelled. Nothing was saved."
                continue

            if not confirm("\nSave changes? (y/n, 0 to cancel): "):
                banner = "Cancelled. Nothing was saved."
                continue

            result = request(
                "PUT",
                f"/products/{product_id}",
                data
            )
            if result:
                print("\nProduct updated successfully!")
                show(result)
            pause()


def delete_product():
    while True:
        chosen_type = choose_item_type("DELETE PRODUCT OR SERVICE", allow_all=True)
        if chosen_type is None:
            return

        if chosen_type == "Service":
            title = "DELETE SERVICE"
            name_col = "Service Name"
            empty_msg = "All services have purchase history and cannot be deleted."
        elif chosen_type == "Product":
            title = "DELETE PRODUCT"
            name_col = "Product Name"
            empty_msg = "All products have purchase history and cannot be deleted."
        else:
            title = "DELETE PRODUCT OR SERVICE"
            name_col = "Item Name"
            empty_msg = "All items have purchase history and cannot be deleted."

        def on_not_found(pid):
            prod = request("GET", f"/products/{pid}", silent_404=True)
            if not prod:
                print("\nThat item was not found.")
                pause()
                return
            print("\nThis item has purchase history and cannot be deleted.")
            pause()

        banner = None
        while True:
            try:
                product = select_item_from_table(
                    title,
                    item_type=chosen_type,
                    name_header=name_col,
                    empty_message=empty_msg,
                    eligibility="delete",
                    on_not_found=on_not_found,
                    banner=banner
                )
            except GoBack:
                break
            banner = None
            if not product:
                break

            product_id = product["id"]
            print(f"\nItem: {product['name']}")
            print(f"Category: {product['category']}")
            print(f"Price: {format_currency(product['price'])}")

            if not confirm("\nDelete this item? (y/n, 0 to cancel): "):
                banner = "Cancelled. Nothing was saved."
                continue

            result = request(
                "DELETE",
                f"/products/{product_id}"
            )
            if result:
                print("\nItem deleted successfully!")
            pause()


def record_purchase():
    """Physical product sales remain anonymous; only the sale and receipt are recorded."""
    customer_id = None
    customer_name = "Walk-in"
    membership_label = "Anonymous purchase"
    cart = []
    manage_purchase_cart(customer_id, customer_name, membership_label, cart)


def manage_purchase_cart(customer_id, customer_name, membership_label, cart):
    if not cart:
        pick_purchase_items(customer_id, customer_name, membership_label, cart)
        if not cart:
            return

    while True:
        quote_res = request("POST", "/quotes", {
            "customer_id": customer_id,
            "items": [{"product_id": it["product_id"], "quantity": it["quantity"]} for it in cart]
        })
        if not quote_res:
            print("Error retrieving cart pricing.")
            pause()
            return

        items = quote_res.get("items", [])
        subtotal_str = quote_res.get("subtotal", "0.00")
        discount_str = quote_res.get("discount", "0.00")
        total_str = quote_res.get("total", "0.00")

        cart_columns = [
            ("No", "number", 3), ("Item Name", "name", 28),
            ("Qty", "qty", 4, "right"), ("Unit", "unit", 10, "right"),
            ("Disc", "discount", 9, "right"), ("Total", "total", 10, "right"),
        ]
        cart_width = table_width(cart_columns, 92)
        header("PURCHASE CART", input_screen=False, width=cart_width)
        print("-" * cart_width)
        print_table_header(cart_columns)
        print("-" * cart_width)

        for idx, it in enumerate(items, 1):
            print_table_row({
                "number": idx, "name": it["name"], "qty": it["quantity"],
                "unit": it["unit_price"], "discount": it["discount"],
                "total": it["total"],
            }, cart_columns)
        print("-" * cart_width)
        print(f"{'Subtotal:':<78} {format_currency(subtotal_str):>12}")
        print(f"{'Discount:':<78} {format_currency(discount_str):>12}")
        print(f"{'Total Due:':<78} {format_currency(total_str):>12}")
        print("-" * cart_width)
        print()
        print("PURCHASE ACTIONS")
        print("  [A] Add Item           [R] Remove Item          [C] Checkout")
        print("  [0] Cancel Sale")
        print()
        choice = input("Enter choice: ").strip().lower()

        if choice in ("a", "add"):
            pick_purchase_items(customer_id, customer_name, membership_label, cart)
        elif choice in ("r", "remove"):
            if not cart:
                print("Cart is empty.")
                pause()
                continue
            line_str = input("Enter line number to remove: ").strip()
            if not line_str.isdigit() or int(line_str) < 1 or int(line_str) > len(cart):
                print("Invalid line number.")
                pause()
                continue
            del cart[int(line_str) - 1]
            if not cart:
                print("Cart is now empty.")
                pause()
                pick_purchase_items(customer_id, customer_name, membership_label, cart)
                if not cart:
                    return
        elif choice in ("c", "checkout", "continue"):
            if not cart:
                print("Add at least one item first")
                pause()
                continue
            completed = checkout_purchase(customer_id, customer_name, membership_label, cart, quote_res)
            if completed:
                return
        elif choice in ("0", "cancel"):
            if cart:
                confirm = input("Discard this sale? (Y/N): ").strip().lower()
                if confirm == "y":
                    return
            else:
                return
        else:
            print("Invalid choice.")
            pause()


def pick_purchase_items(customer_id, customer_name, membership_label, cart):
    all_products = request("GET", "/products")
    if not all_products:
        print("\nThere are no products or services available.")
        pause()
        return

    eligible_items = []
    for p in all_products:
        if p.get("is_active", 1) != 1:
            continue
        if p.get("type") != "Product":
            continue
        eligible_items.append(p)

    if not eligible_items:
        print("\nNo eligible items available.")
        pause()
        return

    page = 1
    total_pages = (len(eligible_items) + PAGE_SIZE - 1) // PAGE_SIZE
    item_columns = [
        ("ID", "id", 4), ("Item Name", "name", 40),
        ("Category", "category", 14),
        ("Price", lambda item: format_currency(item["price"]), 12, "right"),
    ]
    width = table_width(item_columns, 90)

    while True:
        header("SELECT ITEM", input_screen=False, width=width)
        print_table_header(item_columns)
        print("-" * width)

        start = (page - 1) * PAGE_SIZE
        end = min(start + PAGE_SIZE, len(eligible_items))
        for p in eligible_items[start:end]:
            print_table_row(p, item_columns)

        print("-" * width)
        nav = [f"Page {page} of {total_pages}"]
        if page < total_pages:
            nav.append("[>] Next")
        if page > 1:
            nav.append("[<] Previous")
        nav.append("[0] Done")
        print("        ".join(nav))

        val = input("Enter item ID: ").strip()
        low = val.lower()
        if low in ("0", "done", "d", "b", "back"):
            return
        if low in (">", "n", "next") and page < total_pages:
            page += 1
            continue
        if low in ("<", "p", "prev", "previous") and page > 1:
            page -= 1
            continue
        if val == "":
            print("Item ID is required.")
            pause()
            continue
        if not val.isdigit():
            print("Invalid item ID.")
            pause()
            continue

        pid = int(val)
        matched = next((p for p in eligible_items if p["id"] == pid), None)
        if not matched:
            print("Item not available.")
            pause()
            continue

        while True:
            q_input = input("Enter quantity [1]: ").strip()
            if q_input == "":
                qty = 1
                break
            try:
                qty = int(q_input)
                if qty < 1 or qty > 99:
                    print("Enter a quantity from 1 to 99")
                    continue
                break
            except ValueError:
                print("Enter a quantity from 1 to 99")
                continue

        existing = next((it for it in cart if it["product_id"] == matched["id"]), None)
        if existing:
            new_qty = existing["quantity"] + qty
            if new_qty > 99:
                print("Total quantity for this item cannot exceed 99.")
                pause()
                continue
            existing["quantity"] = new_qty
        else:
            cart.append({
                "product_id": matched["id"],
                "name": matched["name"],
                "category": matched["category"],
                "price": Decimal(str(matched["price"])),
                "quantity": qty
            })
        return


def checkout_purchase(customer_id, customer_name, membership_label, cart, quote_res):
    total_str = quote_res["total"]
    subtotal_str = quote_res["subtotal"]
    discount_str = quote_res["discount"]
    total_dec = Decimal(total_str)

    while True:
        header("PAYMENT", input_screen=False, width=58)
        print(f"Total due:   {format_currency(total_str)}")
        print("-" * 58)
        print("Payment method:")
        print("[1] Cash")
        print("[2] E-Wallet")
        print("-" * 58)
        print("[0] Back")
        print("-" * 58)
        choice = input("Choice: ").strip()
        if choice in ("0", "b", "back"):
            return False

        if choice not in ("1", "2"):
            print("Invalid choice")
            pause()
            continue

        payment_method = "Cash" if choice == "1" else "E-Wallet"

        if payment_method == "Cash":
            cancelled_tender = False
            while True:
                tendered_input = input("Amount tendered [0 to cancel]: ").strip()
                if tendered_input in ("0", "cancel", "b", "back"):
                    cancelled_tender = True
                    break
                try:
                    tendered_dec = Decimal(tendered_input)
                    if tendered_dec < total_dec:
                        print("Amount is less than the total due")
                        continue
                    break
                except InvalidOperation:
                    print("Enter a valid amount.")
                    continue
            if cancelled_tender:
                continue
            tendered_str = f"{tendered_dec:.2f}"
            change_str = f"{tendered_dec - total_dec:.2f}"
        else:
            tendered_str = total_str
            change_str = "0.00"

        confirmed = confirm_purchase_screen(
            customer_name=customer_name,
            membership_label=membership_label,
            items_count=len(cart),
            subtotal=subtotal_str,
            discount=discount_str,
            total=total_str,
            payment_method=payment_method,
            tendered=tendered_str,
            change=change_str,
            anonymous_product=True,
        )
        if not confirmed:
            print("\nTransaction cancelled. Purchase not saved.")
            pause()
            return False

        req_id = str(uuid.uuid4())
        payload = {
            "customer_id": customer_id,
            "payment_method": payment_method,
            "amount_tendered": tendered_str,
            "request_id": req_id,
            "items": [{"product_id": it["product_id"], "quantity": it["quantity"]} for it in cart]
        }
        sale = request("POST", "/sales", payload)
        if not sale:
            pause()
            return False

        print("\nPurchase recorded successfully!")
        print_receipt(sale)
        pause()
        return True


def trainer_session_label(product):
    """Show one clear session-type name regardless of customer membership."""
    name = product["name"].lower()
    if "monthly" in name:
        return "Personal Trainer - Monthly-basis Session"
    if "daily" in name:
        return "Personal Trainer - Daily Session"
    return "Personal Trainer Session"


def identify_trainer_customer():
    """Identify customers by full name; collect new customer details only if necessary."""
    while True:
        header("TRAINER CUSTOMER", input_screen=False, width=66)
        print("Enter the customer's full name to check existing records.")
        print("Use at least a first and last name. [0] Back")
        print("-" * 66)
        try:
            full_name = ask_name("Full name", prompt="Customer full name: ")
        except GoBack:
            return None

        parts = full_name.split(" ", 1)
        if len(parts) != 2 or not parts[1].strip():
            print("Enter both the first and last name.")
            pause()
            continue

        customers = request("GET", "/customers")
        if customers is None:
            pause()
            return None

        normalize = lambda value: " ".join(value.casefold().split())
        matches = [
            cust for cust in customers
            if normalize(f"{cust.get('first_name', '')} {cust.get('last_name', '')}") == normalize(full_name)
        ]
        selected = None
        register_new = not matches

        if len(matches) == 1:
            selected = matches[0]
        elif len(matches) > 1:
            page = 0
            while True:
                total_pages = (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE
                columns = [
                    ("ID", "id", 5),
                    ("Customer", lambda row: f"{row['first_name']} {row['last_name']}", 30),
                    ("Phone", lambda row: mask_phone(row.get("phone", "")), 14),
                    ("Yearly", lambda row: row.get("yearly_status") or "None", 12),
                ]
                width = table_width(columns, 85)
                header("MATCHING CUSTOMERS", input_screen=False, width=width)
                print(f"Multiple customers are named {full_name}. Select the correct ID.")
                print("-" * width)
                print_table_header(columns)
                print("-" * width)
                for cust in matches[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
                    print_table_row(cust, columns)
                print("-" * width)
                print(f"Page {page + 1} of {total_pages}")
                if page + 1 < total_pages:
                    print("[>] Next")
                if page > 0:
                    print("[<] Previous")
                print("[R] Register a different person with this name")
                print("[0] Back")
                pick = input("Customer ID or choice: ").strip().lower()
                if pick in ("0", "b", "back"):
                    return None
                if pick in (">", "n", "next") and page + 1 < total_pages:
                    page += 1
                    continue
                if pick in ("<", "p", "previous") and page > 0:
                    page -= 1
                    continue
                if pick in ("r", "register"):
                    register_new = True
                    break
                if pick.isdecimal():
                    selected = next((cust for cust in matches if cust["id"] == int(pick)), None)
                    if selected is not None:
                        break
                print("Select a listed customer ID or an available option.")
                pause()

        if selected is not None:
            customer_name = f"{selected['first_name']} {selected['last_name']}"
            member = selected.get("yearly_status") == "Active"
            return {
                "customer_id": selected["id"],
                "customer_name": customer_name,
                "new_customer": None,
                "is_member": member,
            }

        if register_new:
            header("NEW TRAINER CUSTOMER", input_screen=False, width=66)
            print(f"No selected customer record for: {full_name}")
            print("A phone number is needed to identify the customer in future bookings.")
            print("The customer will be saved only after purchase confirmation.")
            print("[0] Back")
            print("-" * 66)
            try:
                phone = ask_phone("Phone: ")
            except GoBack:
                return None

            phone_match = next((cust for cust in customers if cust.get("phone") == phone), None)
            if phone_match:
                print(f"Phone already belongs to customer ID {phone_match['id']}.")
                print("Check the name and try again to avoid duplicate records.")
                pause()
                continue

            return {
                "customer_id": None,
                "customer_name": full_name,
                "new_customer": {
                    "first_name": parts[0],
                    "last_name": parts[1],
                    "phone": phone,
                },
                "is_member": False,
            }


def trainer_session_flow():
    while True:
        all_products = request("GET", "/products")
        if all_products is None:
            pause()
            return

        coaching_items = [
            p for p in all_products
            if p.get("category") == "Coaching" and p.get("is_active", 1) == 1
        ]
        # The session-type list is identical for members and non-members.
        session_types = [
            p for p in coaching_items if p.get("applies_to") in ("Members only", "Anyone")
        ] or coaching_items
        if not session_types:
            header("TRAINER SESSION", input_screen=False)
            print("No trainer session types are available.")
            pause()
            return

        header("TRAINER SESSION", input_screen=False, width=64)
        print("Select a session type.")
        print("-" * 64)
        for index, item in enumerate(session_types, 1):
            print(f"[{index}] {trainer_session_label(item)}")
        print("-" * 64)
        print("[0] Back")
        print("-" * 64)
        pick = input("Choice: ").strip().lower()
        if pick in ("0", "b", "back"):
            return
        if not pick.isdecimal() or not 1 <= int(pick) <= len(session_types):
            print("Invalid session type.")
            pause()
            continue

        requested_session = session_types[int(pick) - 1]
        selected_label = trainer_session_label(requested_session)

        trainers = request("GET", "/trainers", params={"status": "Active"})
        if not trainers:
            header("TRAINER SESSION", input_screen=False)
            print("No active trainers available.")
            pause()
            return

        header("SELECT TRAINER", input_screen=False, width=64)
        print(f"Session: {selected_label}")
        print("-" * 64)
        for index, trainer in enumerate(trainers, 1):
            print(f"[{index}] {trainer['name']}")
        print("-" * 64)
        print("[0] Back")
        t_choice = input("Choice: ").strip().lower()
        if t_choice in ("0", "b", "back"):
            continue
        if not t_choice.isdecimal() or not 1 <= int(t_choice) <= len(trainers):
            print("Invalid trainer.")
            pause()
            continue
        chosen_trainer = trainers[int(t_choice) - 1]

        identified = identify_trainer_customer()
        if identified is None:
            continue

        customer_id = identified["customer_id"]
        customer_name = identified["customer_name"]
        new_customer = identified["new_customer"]
        is_member = identified["is_member"]

        if is_member and requested_session.get("applies_to") != "Non-members only":
            chosen_session = requested_session
        elif not is_member and requested_session.get("applies_to") == "Anyone":
            chosen_session = requested_session
        else:
            eligible_rate = "Members only" if is_member else "Non-members only"
            chosen_session = next(
                (p for p in coaching_items if p.get("applies_to") == eligible_rate),
                None,
            )

        if not chosen_session:
            header("TRAINER SESSION", input_screen=False)
            print("No trainer rate is configured for this customer type.")
            pause()
            continue

        member_tag = "Active yearly member" if is_member else "Non-member"
        price = Decimal(str(chosen_session["price"]))
        header("TRAINER BOOKING", input_screen=False, width=64)
        print(f"Session:    {selected_label}")
        print(f"Trainer:    {chosen_trainer['name']}")
        print(f"Customer:   {customer_name}")
        if customer_id is not None:
            print(f"Customer ID: {customer_id}")
        else:
            print("Customer ID: Assigned after payment")
        print(f"Rate:       {member_tag}")
        print(f"Total:      {format_currency(price)}")
        print("-" * 64)
        print("Press Enter to choose a booking date, or 0 to cancel.")
        if input("Continue: ").strip().lower() in ("0", "b", "back", "cancel"):
            continue

        now_dt = ph_now()
        today_str = now_dt.strftime("%Y-%m-%d")
        now_time_str = now_dt.strftime("%H:%M")

        # Step A: session date
        cancelled = False
        while True:
            d_input = input(f"Session date (YYYY-MM-DD) [default: {today_str}, 0 to cancel]: ").strip()
            if d_input.lower() in ("0", "cancel", "b", "back"):
                cancelled = True
                break
            if not d_input:
                session_date = now_dt.date()
                break
            try:
                session_date = datetime.strptime(d_input, "%Y-%m-%d").date()
            except ValueError:
                print("Enter a valid date as YYYY-MM-DD")
                continue
            break

        if cancelled:
            continue

        # Step B: session time
        is_today = session_date == now_dt.date()
        while True:
            if is_today:
                t_input = input(f"Session time (HH:MM, 24-hour) [default: {now_time_str}, 0 to cancel]: ").strip()
                if not t_input:
                    t_input = now_time_str
            else:
                t_input = input("Session time (HH:MM, 24-hour) [0 to cancel]: ").strip()
                if not t_input:
                    print("Session time is required")
                    continue
            if t_input.lower() in ("0", "cancel", "b", "back"):
                cancelled = True
                break
            try:
                parsed_time = datetime.strptime(t_input, "%H:%M").time()
            except ValueError:
                print("Enter a valid time as HH:MM (for example 14:30)")
                continue
            break

        if cancelled:
            continue

        session_time = datetime.combine(session_date, parsed_time).strftime("%Y-%m-%d %H:%M")

        price = Decimal(str(chosen_session["price"]))
        while True:
            header("PAYMENT", input_screen=False, width=58)
            print(f"Total due: {format_currency(str(price))}")
            print("-" * 58)
            print("Payment method:")
            print("[1] Cash")
            print("[2] E-Wallet")
            print("-" * 58)
            print("[0] Back")
            print("-" * 58)
            p_choice = input("Choice: ").strip()
            if p_choice in ("0", "b", "back"):
                break
            if p_choice not in ("1", "2"):
                print("Invalid choice")
                pause()
                continue

            pay_method = "Cash" if p_choice == "1" else "E-Wallet"

            if pay_method == "Cash":
                while True:
                    tendered_input = input("Amount tendered: ").strip()
                    if tendered_input == "0":
                        break
                    try:
                        tendered = Decimal(tendered_input)
                        if not tendered.is_finite() or tendered.as_tuple().exponent < -2:
                            print("Enter a finite amount with at most two decimal places.")
                            continue
                        if tendered < price:
                            print("Amount is less than the total due.")
                            continue
                        change = tendered - price
                        break
                    except InvalidOperation:
                        print("Enter a valid amount.")
                        continue
                if tendered_input == "0":
                    continue
            else:
                tendered = price
                change = Decimal("0.00")

            header("CONFIRM TRAINER SESSION", input_screen=False, width=58)
            print(f"Customer:        {customer_name}")
            print(f"Session type:    {selected_label}")
            print(f"Membership:      {member_tag}")
            print(f"Trainer:         {chosen_trainer['name']}")
            print(f"Session date:    {session_time[:10]}")
            print(f"Session time:    {session_time[11:16]}")
            print(f"Total due:       {format_currency(str(price))}")
            print(f"Payment method:  {pay_method}")
            print(f"Amount tendered: {format_currency(str(tendered))}")
            if pay_method == "Cash":
                print(f"Change:          {format_currency(str(change))}")
            print("-" * 58)
            confirm = input("Save this session? (Y/N): ").strip().lower()
            if confirm != "y":
                print("Session not saved.")
                pause()
                break

            payload = {
                "customer_id": customer_id,
                "new_customer": new_customer,
                "trainer_id": chosen_trainer["id"],
                "product_id": chosen_session["id"],
                "session_label": selected_label,
                "session_datetime": session_time,
                "payment_method": pay_method,
                "amount_tendered": str(tendered),
                "request_id": str(uuid.uuid4()),
            }
            res = request("POST", "/trainer-sessions", payload)
            if not res:
                pause()
                break

            header("RECEIPT", input_screen=False, width=58)
            print(f"Receipt no.: {res['receipt_no']}")
            print(f"Date:        {res['created_at']}")
            print(f"Customer:    {res['customer_name']}")
            print(f"Customer ID: {res['customer_id']}")
            print("-" * 58)
            print(f"{res['session_type']}")
            print(f"Trainer: {res['trainer_name']}")
            print(f"Session date: {res['session_date_time'][:10]}")
            print(f"Session time: {res['session_date_time'][11:16]}")
            print("-" * 58)
            print(f"{'Total':<46} {format_currency(res['total']):>10}")
            print(f"Payment: {res['payment_method']}")
            print(f"{'Tendered':<46} {format_currency(res['amount_tendered']):>10}")
            print(f"{'Change':<46} {format_currency(res['change']):>10}")
            print("-" * 58)
            pause()
            break


def services_products_menu():
    if CURRENT_ROLE == "staff":
        submenu("SERVICES/PRODUCTS", [
            ("Product Purchase", record_purchase),
            ("Book Trainer Session", trainer_session_flow),
            ("View Products and Services", view_products),
        ])
        return
    submenu("SERVICES/PRODUCTS", [
        ("Product Purchase", record_purchase),
        ("Book Trainer Session", trainer_session_flow),
        ("Manage Products and Services", products_services),
    ])


def products_services():
    submenu("PRODUCTS AND SERVICES", [
        ("Add Product or Service", add_product),
        ("View Products and Services", view_products),
        ("Update Product or Service", update_product),
        ("Delete Product or Service", delete_product)
    ])


# SEARCH RECORDS

def search_customer():
    """Search registered customers by ID, first name, surname, or full name."""
    records = request("GET", "/customers")
    if records is None:
        pause()
        return
    columns = [
        ("ID", "id", 7),
        ("First Name", "first_name", 25),
        ("Last Name", "last_name", 25),
        ("Phone", lambda r: mask_phone(r.get("phone", "")), 17),
    ]
    query, page = "", 1
    while True:
        needle = " ".join(query.casefold().split())
        matches = [row for row in records if not needle or (
            needle in str(row.get("id", "")) if needle.isdecimal() else
            needle in " ".join(
                f"{row.get('first_name', '')} {row.get('last_name', '')}".casefold().split()
            )
        )]
        pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        header("SEARCH CUSTOMER", input_screen=False, width=90)
        print(f"Records: {len(matches)}    Page {page} of {pages}")
        if query:
            print(f"Search: {query}")
        print("-" * 90)
        print_table_header(columns)
        for row in matches[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]:
            print_table_row(row, columns)
        if not matches:
            print("No matching customers.")
        print("-" * 90)
        if pages > 1:
            print("[<] Previous page     [>] Next page")
        print("[C] Clear search     [0] Back")
        choice = input("Search by ID or name: ").strip()
        key = choice.casefold()
        if key in ("0", "b", "back"):
            return
        if key in ("<", ">"):
            page = max(1, page - 1) if key == "<" else min(pages, page + 1)
        elif key in ("c", "clear"):
            query, page = "", 1
        else:
            query, page = choice, 1


def show_legacy_payment_details(transaction):
    header("PAYMENT DETAILS", input_screen=False, width=80)
    print(f"Reference:       {transaction['reference']}")
    print(f"Date:            {transaction['created_at']}")
    if transaction.get("customer_id") is not None:
        print(f"Customer:        {transaction['customer_name']}")
        print(f"Customer ID:     {transaction['customer_id']}")
    print("Product / Service:")
    for line in wrap_cell(transaction["item_names"], 76):
        print(f"  {line}")
    print(f"Payment Method:  {transaction['payment_method']}")
    print(f"Amount:          {format_currency(transaction['amount'])}")
    print(f"Status:          {transaction['status']}")
    pause()


def show_refund_details(refund_id):
    record = request("GET", f"/refunds/{refund_id}")
    if not record:
        pause()
        return
    header("REFUND DETAILS", input_screen=False, width=84)
    print(f"Refund Number:    {record['refund_no']}")
    print(f"Original Receipt: {record['receipt_no']}")
    print(f"Refund Date:      {record['created_at']}")
    print(f"Amount Refunded:  {format_currency(record['amount'])}")
    print(f"Refund Method:    {record['method']}")
    print(f"Original Method:  {record['original_payment_method']}")
    print(f"Customer:         {record['customer_name']}")
    print(f"Reason:           {record['reason']}")
    print("-" * 84)
    print("This is a manual refund record; no electronic transfer is initiated.")
    pause()


def search_transactions_ui():
    """Browse all transactions and switch categories within the table."""
    categories = {
        "1": ("yearly", "Yearly Membership"),
        "2": ("monthly", "Monthly Session"),
        "3": ("daily", "Daily Session"),
        "4": ("trainer", "Trainer Service"),
        "5": ("products", "Products"),
        "6": (None, "All Transactions"),
    }
    columns = [
        ("Receipt No.", "reference", 14),
        ("Date", lambda r: str(r.get("created_at", ""))[:10], 12),
        ("Time", lambda r: str(r.get("created_at", ""))[11:16], 7),
        ("Product / Service", "item_names", 44),
        ("Amount", lambda r: format_currency(r["amount"]), 15, "right"),
        ("Status", "status", 12),
    ]
    width = table_width(columns, 120)

    category, name = categories["6"]
    query, page = "", 1
    page_size = PAGE_SIZE

    while True:
        params = {"query": query} if query else None
        records = request("GET", "/transactions/search", params=params)
        if records is None:
            pause()
            return
        if category is not None:
            records = [r for r in records if category in r.get("categories", [])]
        pages = max(1, (len(records) + page_size - 1) // page_size)
        page = min(page, pages)
        visible = records[(page - 1) * page_size:page * page_size]
        header(f"TRANSACTIONS - {name.upper()}", input_screen=False, width=width)
        print(f"Records: {len(records)}    Page {page} of {pages}")
        if query:
            print(f"Search: {query}")
        print("-" * width)
        print_table_header(columns)
        print("-" * width)
        for record in visible:
            print_table_row(record, columns)
        if not visible:
            print("No matching transactions.")
        print("-" * width)
        print()
        for index, (hotkey, (_, label)) in enumerate(categories.items(), 1):
            print(f"[{hotkey}] {label}", end="\n" if index % 3 == 0 else "    ")
        print()
        print("[S] Search within this category     [C] Clear search")
        if pages > 1:
            print("[<] Previous page                  [>] Next page")
        print("[0] Back to Search Records")
        print()
        print("Enter a receipt number to view details.")
        choice = input("Choice: ").strip()
        key = choice.casefold()
        if key in ("0", "b", "back"):
            return
        if key in categories:
            category, name = categories[key]
            page = 1
            continue
        if key in ("<", "p", "prev"):
            page = max(1, page - 1)
            continue
        if key in (">", "n", "next"):
            page = min(pages, page + 1)
            continue
        if key in ("c", "clear"):
            query, page = "", 1
            continue
        if key in ("s", "search"):
            print("Search by customer name, product/service, or receipt.")
            term = input("Search [0 to cancel]: ").strip()
            if term != "0":
                query, page = term, 1
            continue
        selected = next(
            (r for r in records if r["reference"].casefold() == key), None
        )
        if selected is None:
            print("Invalid receipt or option.")
            pause()
            continue
        if selected["record_type"] == "sale":
            view_sale_details(selected["record_id"])
        elif selected["record_type"] == "refund":
            show_refund_details(selected["record_id"])
        else:
            show_legacy_payment_details(selected)


def view_sale_details(sale_id):
    while True:
        sale = request("GET", f"/sales/{sale_id}")
        if not sale:
            pause()
            return

        detail_columns = [
            ("Item Name", "item_name", 40),
            ("Qty", "quantity", 4, "right"),
            ("Price", lambda row: format_currency(row["unit_price"]), 12, "right"),
            ("Amount", lambda row: format_currency(row["line_amount"]), 12, "right"),
        ]
        detail_width = table_width(detail_columns, 86)
        header("PURCHASE DETAILS", input_screen=False, width=detail_width)
        print(f"Receipt No:     {sale['receipt_no']}")
        print(f"Date & Time:    {sale['created_at']}")
        if str(sale.get("kind", "")).lower() != "product" or sale.get("customer_id") is not None:
            print(f"Customer:       {sale['customer_name']} ({sale['customer_type']})")
        print(f"Status:         {sale['status']}")
        if sale["status"] == "Voided":
            print(f"Voided At:      {sale.get('voided_at', '-')}")
            print(f"Void Reason:    {sale.get('void_reason', '-')}")
        print("-" * detail_width)
        print_table_header(detail_columns)
        print("-" * detail_width)
        for it in sale.get("items", []):
            print_table_row(it, detail_columns)
        print("-" * detail_width)
        print(f"{'Total:':<46} {format_currency(sale['total']):>10}")
        print(f"Payment Method: {sale['payment_method']}")
        print(f"{'Amount Tendered:':<46} {format_currency(sale['amount_tendered']):>10}")
        print(f"{'Change:':<46} {format_currency(sale['change']):>10}")
        print("=" * detail_width)

        if sale["status"] == "Refunded":
            print(f"Refund Ref.:     {sale.get('refund_no', '-')}")
            print(f"Refund Amount:   {format_currency(sale.get('refunded_amount', '0.00'))}")
            print(f"Refund Date:     {sale.get('refunded_at', '-')}")
            print(f"Refund Method:   {sale.get('refund_method', '-')}")
            print(f"Refund Reason:   {sale.get('refund_reason', '-')}")
        print("-" * detail_width)
        print("[0] Back")
        choice = input("Choice: ").strip().lower()
        if choice in ("0", "b", "back", ""):
            return


def search_records():
    submenu("SEARCH RECORDS", [
        ("Search Customer (Name or ID)", search_customer),
        ("Search Transactions", search_transactions_ui)
    ])


# SALES REPORTS

def daily_transactions():
    """Show all daily transaction records in one chronological, paginated list."""
    periods = request("GET", "/reports/sales", params={"period": "daily"})
    if periods is None:
        pause()
        return
    transactions = [
        {"date": day["period"], **record}
        for day in periods for record in day.get("transactions", [])
    ]
    gross = sum(Decimal(str(day.get("gross_sales", day.get("total_sales", "0"))).replace(",", "")) for day in periods)
    refunds = sum(Decimal(str(day.get("refunds_total", "0")).replace(",", "")) for day in periods)
    net = gross - refunds
    transactions.sort(
        key=lambda row: (row["date"], row.get("time", ""), row["receipt_no"]),
        reverse=True,
    )

    if not transactions:
        header("DAILY TRANSACTIONS", input_screen=False, width=100)
        print("No daily transactions are recorded.")
        pause()
        return

    columns = [
        ("Receipt No.", "receipt_no", 13),
        ("Date", "date", 12),
        ("Time", "time", 7),
        ("Product / Service", "item_name", 44),
        ("Amount", lambda row: format_currency(row["total"]), 13, "right"),
        ("Status", "status", 10),
    ]
    width = table_width(columns, 116)
    page = 1
    page_size = 10
    pages = (len(transactions) + page_size - 1) // page_size

    while True:
        header("DAILY TRANSACTIONS", input_screen=False, width=width)
        print(f"Transactions: {len(transactions)}    Page {page} of {pages}")
        print("-" * width)
        print_table_header(columns)
        print("-" * width)
        for record in transactions[(page - 1) * page_size:page * page_size]:
            print_table_row(record, columns)
        print("-" * width)
        print(f"Gross Sales:       {format_currency(gross)}")
        print(f"Refunds Issued:    -{format_currency(refunds)}")
        print(f"Net Sales:         {format_currency(net)}")
        print("-" * width)
        print()

        if pages == 1:
            pause()
            return

        print(page_nav_options(page, pages, include_back=True))
        choice = input("Choice: ").strip().lower()
        if choice in ("0", "b", "back"):
            return
        if choice in (">", "n", "next") and page < pages:
            page += 1
            continue
        if choice in ("<", "p", "prev", "previous") and page > 1:
            page -= 1
            continue
        print("Choose <, >, or 0.")
        pause()


def monthly_sales_report():
    """Display the monthly summary; use Enter for a single month."""
    periods = request("GET", "/reports/sales", params={"period": "monthly"})
    if periods is None:
        pause()
        return
    if not periods:
        header("MONTHLY SALES REPORT", input_screen=False, width=104)
        print("There are no monthly sales records.")
        pause()
        return

    columns = [
        ("Category", "category", 38),
        ("Transactions", "transactions", 24, "right"),
        ("Amount", lambda row: format_currency(row["amount"]), 30, "right"),
    ]
    width = table_width(columns, 112)
    page = 1
    pages = len(periods)

    while True:
        record = periods[page - 1]
        header("MONTHLY SALES REPORT", input_screen=False, width=width)
        print(f"Month: {record['period']}")
        print()
        print_table_header(columns)
        print("-" * width)
        for category in record.get("categories", []):
            print_table_row(category, columns)
        print("-" * width)
        print(f"Gross Sales:       {format_currency(record.get('gross_sales', record['total_sales']))}")
        print(f"Refunds Issued:    -{format_currency(record.get('refunds_total', '0.00'))}")
        print_table_row({
            "category": "Net Sales",
            "transactions": record["total_transactions"],
            "amount": record["total_sales"],
        }, columns)
        print("-" * width)
        if record.get("voided_count"):
            print(f"Historical voided sales excluded: {record['voided_count']}")
        print()

        if pages == 1:
            pause()
            return

        print(f"Month {page} of {pages}")
        print(page_nav_options(page, pages, include_back=True))
        choice = input("Choice: ").strip().lower()
        if choice in ("0", "b", "back"):
            return
        if choice in (">", "n", "next") and page < pages:
            page += 1
            continue
        if choice in ("<", "p", "prev", "previous") and page > 1:
            page -= 1
            continue
        print("Choose <, >, or 0.")
        pause()


def report(endpoint, title, params=None):
    if endpoint == "/reports/sales":
        columns = [
            ("Period", "period", 12),
            ("Service Income", lambda r: f"{format_currency(r.get('service_income', '0.00'))} ({r.get('service_transactions', 0)})", 20, "right"),
            ("Product Income", lambda r: f"{format_currency(r.get('product_income', '0.00'))} ({r.get('product_transactions', 0)})", 20, "right"),
            ("Total Sales", lambda r: f"{format_currency(r.get('total', '0.00'))} ({r.get('transactions', 0)})", 17, "right"),
        ]
        sort_key = None
    elif endpoint == "/reports/payment-methods":
        columns = [
            ("Method", "method", 24),
            ("Transactions", "transactions", 20),
            ("Total Amount", lambda r: format_currency(r.get("total")), 28, "right"),
        ]
        sort_key = None
    elif endpoint == "/reports/memberships":
        def fetch_mem_summary():
            data = request("GET", "/reports/memberships")
            if not data:
                return []
            return [
                {
                    "plan": "Yearly membership",
                    "active": data.get("yearly", {}).get("active", 0),
                    "expired": data.get("yearly", {}).get("expired", 0),
                    "upcoming": data.get("yearly", {}).get("upcoming", 0),
                    "cancelled": data.get("yearly", {}).get("cancelled", 0),
                    "total": data.get("yearly", {}).get("total", 0)
                },
                {
                    "plan": "Monthly session",
                    "active": data.get("monthly", {}).get("active", 0),
                    "expired": data.get("monthly", {}).get("expired", 0),
                    "upcoming": data.get("monthly", {}).get("upcoming", 0),
                    "cancelled": data.get("monthly", {}).get("cancelled", 0),
                    "total": data.get("monthly", {}).get("total", 0)
                },
                {
                    "plan": "Overall Total",
                    "active": data.get("active", 0),
                    "expired": data.get("expired", 0),
                    "upcoming": data.get("upcoming", 0),
                    "cancelled": data.get("cancelled", 0),
                    "total": data.get("total", 0)
                }
            ]
        columns = [
            ("Plan", "plan", 24),
            ("Active", "active", 12, "right"),
            ("Expired", "expired", 12, "right"),
            ("Upcoming", "upcoming", 12, "right"),
            ("Cancelled", "cancelled", 12, "right"),
            ("Total", "total", 10, "right")
        ]
        paginated_view(
            title,
            fetch_mem_summary,
            columns,
            empty_message=f"There are no records for {title.lower()} right now.",
            sort_key=None,
            width=78
        )
        return
    else:
        columns = [
            ("Active", "active", 24),
            ("Expired", "expired", 24),
            ("Upcoming", "upcoming", 24),
        ]
        sort_key = None

    paginated_view(
        title,
        lambda: request("GET", endpoint, params=params),
        columns,
        empty_message=f"There are no records for {title.lower()} right now.",
        sort_key=sort_key,
        width=78
    )


def sales_reports():
    submenu("SALES REPORTS", [
        (
            "Daily Transactions",
            daily_transactions
        ),
        (
            "Monthly Sales Report",
            monthly_sales_report
        ),
        (
            "Membership Summary",
            lambda: report(
                "/reports/memberships",
                "MEMBERSHIP SUMMARY"
            )
        )
    ])


# MAIN MENU

def login_screen():
    global AUTH_TOKEN, CURRENT_ROLE
    while True:
        header("CRUNCH X FITNESS - LOGIN")
        print("Username:")
        print("Password:")
        print("-" * 55)
        print("[0] Exit")
        print("-" * 55)
        username = input("Enter username: ").strip()
        if username == "0":
            return False
        password = input("Enter password: ")
        if password == "0":
            return False
        try:
            response = requests.post(
                API + "/auth/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                AUTH_TOKEN = data["token"]
                CURRENT_ROLE = data["role"]
                return True
            print("Invalid username or password.")
        except requests.RequestException:
            print("Cannot connect to the API. Start the server first.")
        pause()


def main():
    global AUTH_TOKEN, CURRENT_ROLE
    if not login_screen():
        return
    options = [

        ("Product/Service Management", product_service_management),
        ("Customer Management", customer_management),
        ("Payment Management", payment_management),
        ("Search Records", search_records),
        ("Sales Reports", sales_reports),
    ]
    submenu("GYM MANAGEMENT SYSTEM", options)
    try:
        requests.post(API + "/auth/logout", headers={"Authorization": f"Bearer {AUTH_TOKEN}"}, timeout=5)
    except requests.RequestException:
        pass
    AUTH_TOKEN = None
    CURRENT_ROLE = None

    clear_screen()
    print("Thank you for using Gym Management System.")


if __name__ == "__main__":
    main()
