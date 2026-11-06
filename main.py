
import os
import re
import sys
import textwrap
import unicodedata
import uuid
import requests
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from models import CATEGORY_TO_TYPE, PRODUCT_CATEGORIES, clean_phone, ph_now, ph_today

API = "http://127.0.0.1:8000"
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
) -> bool:
    header("CONFIRM PURCHASE", input_screen=False, width=width)
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
    print(f"Customer:    {sale.get('customer_name', 'Walk-in')}")
    if sale.get("customer_id") is not None:
        print(f"Customer ID: {sale['customer_id']}")
    print("-" * width)
    for it in sale.get("items", []):
        disc_val = Decimal(str(it.get("discount", 0)))
        disc_str = f" (-{format_currency(it['discount'])})" if disc_val > 0 else ""
        line = f"{it['item_name'][:24]:<24} {it['quantity']} x {format_currency(it['unit_price']):>7}{disc_str}  {format_currency(it['line_amount']):>8}"
        print(line)
    print("-" * width)
    disc_total = Decimal(str(sale.get("discount", 0)))
    if disc_total > 0:
        print(f"{'Subtotal':<44} {format_currency(sale.get('subtotal', sale['total'])):>12}")
        print(f"{'Discount':<44} -{format_currency(sale['discount']):>11}")
    print(f"{'Total':<44} {format_currency(sale['total']):>12}")
    print(f"Payment:     {sale.get('payment_method', '-')}")
    print(f"{'Tendered':<44} {format_currency(sale.get('amount_tendered', sale['total'])):>12}")
    print(f"{'Change':<44} {format_currency(sale.get('change', '0.00')):>12}")
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


def format_cell(value, width, align="left"):
    lines = wrap_cell(value, width)
    first = lines[0]
    return first.rjust(width) if align == "right" else first.ljust(width)


def print_table_row(rec, columns):
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
        print(" | ".join(row_cells))


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
        nav.append("[N] Next")
    if page > 1:
        nav.append("[P] Previous")
    if include_back:
        nav.append("[0] Back")
    return "   ".join(nav)


def render_data_table(title, records, columns, page, width=None, always_show_back=False, banner=None, footer_text=None, cancel_label=False):
    if width is None:
        width = sum(col[2] for col in columns) + 3 * (len(columns) - 1)
    total_records = len(records)
    total_pages = (total_records + PAGE_SIZE - 1) // PAGE_SIZE
    start = (page - 1) * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_records)

    header(title, input_screen=False, width=width, banner=banner)
    header_cells = []
    for col in columns:
        label, _, w = col[0], col[1], col[2]
        align = col[3] if len(col) > 3 else "left"
        header_cells.append(format_cell(label, w, align=align))
    print(" | ".join(header_cells))
    print("-" * width)

    for rec in records[start:end]:
        print_table_row(rec, columns)

    print("-" * width)
    print(f"Page {page} of {total_pages} | Showing {start + 1}-{end} of {total_records}")
    if footer_text:
        print(footer_text)
    if total_pages > 1 or always_show_back:
        if cancel_label:
            nav = []
            if page < total_pages:
                nav.append("[N] Next")
            if page > 1:
                nav.append("[P] Previous")
            nav.append("[0] Cancel")
            print("   ".join(nav))
        else:
            print(page_nav_options(page, total_pages, include_back=True))
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


def select_customer_from_list(title, empty_action, eligibility=None, empty_message=None, columns=None, width=56, on_not_found=None, banner=None):
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
        render_data_table(title, customers, cols, page, width=width, always_show_back=True, banner=active_banner)
        active_banner = None

        while True:
            value = input("Enter customer ID: ").strip()
            low = value.lower()
            if low in ("0", "b", "back"):
                raise GoBack()
            if low in ("n", "next") and page < total_pages:
                page += 1
                break
            if low in ("p", "prev", "previous") and page > 1:
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
    if width is None:
        width = sum(col[2] for col in columns) + 3 * (len(columns) - 1)

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
            if choice in ("n", "next") and page < total_pages:
                page += 1
                break
            if choice in ("p", "prev", "previous") and page > 1:
                page -= 1
                break

            if page < total_pages and page > 1:
                print("Invalid choice. Enter N, P, or 0.")
            elif page < total_pages:
                print("Invalid choice. Enter N or 0.")
            else:
                print("Invalid choice. Enter P or 0.")


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
            if choice in ("n", "next") and page < total_pages:
                page += 1
                break
            if choice in ("p", "prev", "previous") and page > 1:
                page -= 1
                break

            if page < total_pages and page > 1:
                print("Invalid choice. Enter N, P, or 0.")
            elif page < total_pages:
                print("Invalid choice. Enter N or 0.")
            else:
                print("Invalid choice. Enter P or 0.")


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

        width = 68
        header("CUSTOMER OVERVIEW", input_screen=False, width=width)
        if search_query:
            print(f"Filter: '{search_query}' (Enter empty search to reset)")
        print(f"{'ID':<4} | {'Customer':<20} | {'Yearly':<11} | {'Monthly':<11} | {'Last Visit':<10}")
        print("-" * width)
        if not page_customers:
            print("No customers found.")
        else:
            for c in page_customers:
                cname = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()[:20]
                ystatus = c.get("yearly_status") or "-"
                mstatus = c.get("monthly_status") or "-"
                lvisit = c.get("last_visit") or "-"
                print(f"{c['id']:<4} | {cname:<20} | {ystatus:<11} | {mstatus:<11} | {lvisit:<10}")

        print("-" * width)
        nav = [f"Page {page} of {total_pages}"]
        if page < total_pages:
            nav.append("[N] Next")
        if page > 1:
            nav.append("[P] Prev")
        nav.append("[S] Search")
        nav.append("[0] Back")
        print(" | ".join(nav))
        print("-" * width)
        val = input("Enter Customer ID to view details (or choice): ").strip()
        low = val.lower()

        if low in ("0", "b", "back"):
            return
        if low in ("n", "next") and page < total_pages:
            page += 1
            continue
        if low in ("p", "prev", "previous") and page > 1:
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
    width = 70
    header("MEMBERSHIP HISTORY", input_screen=False, width=width)
    print(f"Customer: {customer_name}")
    print("-" * width)
    if not mems:
        print("No membership history found.")
    else:
        print(f"{'ID':<4} | {'Plan':<18} | {'Start':<10} | {'End':<10} | {'Status':<11} | {'Receipt':<8}")
        print("-" * width)
        for m in mems:
            rc = m.get("receipt_no") or "-"
            print(f"{m['id']:<4} | {m['plan'][:18]:<18} | {m['start_date']:<10} | {m['end_date']:<10} | {m['status']:<11} | {rc:<8}")
    print("-" * width)
    pause()


def view_customer_purchase_history(customer_id, customer_name):
    while True:
        sales = request("GET", f"/customers/{customer_id}/sales") or []
        width = 68
        header("PURCHASE HISTORY", input_screen=False, width=width)
        print(f"Customer: {customer_name}")
        print("-" * width)
        if not sales:
            print("No purchase history found.")
            print("-" * width)
            pause()
            return
        print(f"{'Receipt No':<10} | {'Date':<10} | {'Items':<5} | {'Total':>9} | {'Status':<9}")
        print("-" * width)
        for s in sales:
            dt_str = s.get("created_at", "")[:10]
            items_cnt = len(s.get("items", []))
            print(f"{s['receipt_no']:<10} | {dt_str:<10} | {items_cnt:<5} | {format_currency(s['total']):>9} | {s['status']:<9}")
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
    width = 58
    header("VISIT HISTORY", input_screen=False, width=width)
    print(f"Customer: {customer_name}")
    print("-" * width)
    if not visits:
        print("No visit history found.")
    else:
        print(f"{'ID':<6} | {'Check-in Time':<20} | {'Receipt':<10}")
        print("-" * width)
        for v in visits:
            rc = v.get("receipt_no") or "-"
            print(f"{v['id']:<6} | {v['check_in_at']:<20} | {rc:<10}")
    print("-" * width)
    pause()


def view_plan_memberships(plan_name, status="all"):
    is_yearly = (plan_name == "Yearly membership")
    if is_yearly:
        if status == "active":
            title = "ACTIVE YEARLY MEMBERSHIPS"
        elif status == "expired":
            title = "EXPIRED YEARLY MEMBERSHIPS"
        else:
            title = "ALL YEARLY MEMBERSHIPS"
        empty_msg = "No yearly memberships found."
    else:
        if status == "active":
            title = "ACTIVE MONTHLY SESSIONS"
        elif status == "expired":
            title = "EXPIRED MONTHLY SESSIONS"
        else:
            title = "ALL MONTHLY SESSIONS"
        empty_msg = "No monthly sessions found."

    columns = [
        ("ID", "id", 4),
        ("Customer", "customer_name", 18),
        ("Start Date", "start_date", 10),
        ("End Date", "end_date", 10),
        ("Status", "status", 8),
    ]
    sort_key = lambda r: (r.get("customer_id", 0), r.get("start_date", ""), r.get("id", 0))

    paginated_view(
        title,
        lambda: request("GET", "/memberships", params={"status": status, "plan": plan_name}),
        columns,
        empty_message=empty_msg,
        sort_key=sort_key,
        width=62
    )


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


def yearly_membership_menu():
    submenu("YEARLY MEMBERSHIP", [
        ("Register", lambda: register_plan("Yearly membership")),
        ("Renew", lambda: renew_plan("Yearly membership")),
        ("View All", lambda: view_plan_memberships("Yearly membership", "all")),
        ("View Active", lambda: view_plan_memberships("Yearly membership", "active")),
        ("View Expired", lambda: view_plan_memberships("Yearly membership", "expired")),
    ])


def monthly_session_menu():
    submenu("MONTHLY SESSION", [
        ("Register", lambda: register_plan("Monthly session")),
        ("Renew", lambda: renew_plan("Monthly session")),
        ("View All", lambda: view_plan_memberships("Monthly session", "all")),
        ("View Active", lambda: view_plan_memberships("Monthly session", "active")),
        ("View Expired", lambda: view_plan_memberships("Monthly session", "expired")),
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


def product_service_management():
    submenu("PRODUCT/SERVICE MANAGEMENT", [
        ("Yearly Membership", yearly_membership_menu),
        ("Monthly Session", monthly_session_menu),
        ("Daily Session", daily_session_flow),
        ("Services/Products", services_products_menu),
        ("Customer Overview", customer_overview),
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
    width = sum(col[2] for col in columns) + 3 * (len(columns) - 1)
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
            if low in ("n", "next") and page < total_pages:
                page += 1
                break
            if low in ("p", "prev", "previous") and page > 1:
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

        header("PURCHASE CART", input_screen=False, width=64)
        print(f"Customer: {customer_name} | Membership: {membership_label}")
        print("-" * 64)
        print(f"{'No':<3} | {'Item Name':<22} | {'Qty':>3} | {'Unit':>8} | {'Disc':>7} | {'Total':>8}")
        print("-" * 64)

        for idx, it in enumerate(items, 1):
            name_snip = it["name"][:22]
            print(f"{idx:<3} | {name_snip:<22} | {it['quantity']:>3} | {it['unit_price']:>8} | {it['discount']:>7} | {it['total']:>8}")
        print("-" * 64)
        print(f"{'Subtotal:':<54} {format_currency(subtotal_str):>9}")
        print(f"{'Discount:':<54} {format_currency(discount_str):>9}")
        print(f"{'Total Due:':<54} {format_currency(total_str):>9}")
        print("-" * 64)
        print("[A] Add item  [R] Remove line  [C] Checkout  [0] Cancel sale")
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
    width = 62

    while True:
        header("SELECT ITEM", input_screen=False, width=width)
        print(f"Customer: {customer_name} | Membership: {membership_label}")
        print("=" * width)
        print(f"{'ID':<4} | {'Item Name':<30} | {'Category':<12} | {'Price':>8}")
        print("-" * width)

        start = (page - 1) * PAGE_SIZE
        end = min(start + PAGE_SIZE, len(eligible_items))
        for p in eligible_items[start:end]:
            print(f"{p['id']:<4} | {p['name'][:30]:<30} | {p['category'][:12]:<12} | {format_currency(p['price']):>8}")

        print("-" * width)
        nav = [f"Page {page} of {total_pages}"]
        if page < total_pages:
            nav.append("[N] Next")
        if page > 1:
            nav.append("[P] Previous")
        nav.append("[0] Done")
        print(" | ".join(nav))

        val = input("Enter item ID: ").strip()
        low = val.lower()
        if low in ("0", "done", "d", "b", "back"):
            return
        if low in ("n", "next") and page < total_pages:
            page += 1
            continue
        if low in ("p", "prev", "previous") and page > 1:
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
        print(f"Customer:    {customer_name}")
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
                header("MATCHING CUSTOMERS", input_screen=False, width=76)
                print(f"Multiple customers are named {full_name}. Select the correct ID.")
                print("-" * 76)
                print(f"{'ID':<5} | {'Customer':<25} | {'Phone':<13} | {'Yearly':<12}")
                print("-" * 76)
                for cust in matches[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
                    name = f"{cust['first_name']} {cust['last_name']}"[:25]
                    print(f"{cust['id']:<5} | {name:<25} | {mask_phone(cust.get('phone', '')):<13} | {cust.get('yearly_status', 'None'):<12}")
                print("-" * 76)
                print(f"Page {page + 1} of {total_pages}")
                if page + 1 < total_pages:
                    print("[N] Next")
                if page > 0:
                    print("[P] Previous")
                print("[R] Register a different person with this name")
                print("[0] Back")
                pick = input("Customer ID or choice: ").strip().lower()
                if pick in ("0", "b", "back"):
                    return None
                if pick in ("n", "next") and page + 1 < total_pages:
                    page += 1
                    continue
                if pick in ("p", "previous") and page > 0:
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
    submenu("SERVICES/PRODUCTS", [
        ("Record Product Purchase", record_purchase),
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
    if not guard_customers("search", "SEARCH CUSTOMER BY NAME", input_screen=True):
        return

    first_name = ask_name("First name")
    last_name = ask_name("Last name")

    records = request(
        "GET",
        "/customers",
        params={"first_name": first_name, "last_name": last_name}
    )

    if records is None:
        pause()
        return

    if not records:
        header("SEARCH CUSTOMER BY NAME", input_screen=False)
        print(f'\nNo customers found matching "{first_name} {last_name}".')
        pause()
        return

    show(records)
    pause()


def search_customer_id():
    if not guard_customers("search", "SEARCH CUSTOMER BY ID", input_screen=True):
        return

    customer_id = ask_id()

    result = request(
        "GET",
        f"/customers/{customer_id}",
        silent_404=True
    )

    if not result:
        header("SEARCH CUSTOMER BY ID", input_screen=False)
        print("\nThat customer was not found.")
        pause()
        return

    show(result)
    pause()


def search_membership():
    if not guard_records("memberships", "search", "SEARCH MEMBERSHIP", input_screen=True):
        return

    membership_id = ask_number("Membership ID: ")

    records = request("GET", "/memberships")

    if records is None:
        pause()
        return

    membership = next(
        (
            item for item in records
            if item["id"] == membership_id
        ),
        None
    )

    if membership:
        show(membership)
    else:
        header("SEARCH MEMBERSHIP", input_screen=False)
        print("\nThat membership was not found.")

    pause()


def search_payment():
    if not guard_records("payments", "search", "SEARCH PAYMENT", input_screen=True):
        return

    query = ask("Search (Customer Name, Customer ID, or Payment ID): ")

    records = request("GET", "/payments", params={"search": query})
    if records is None:
        pause()
        return

    if not records:
        header("SEARCH PAYMENT", input_screen=False)
        print(f'\nNo payments found matching "{query}".')
        pause()
        return

    columns = [
        ("ID", "id", 4),
        ("Customer", "customer_name", 18),
        ("Description", "description", 24),
        ("Method", "method", 10),
        ("Amount", lambda r: format_currency(r.get("amount")), 10, "right"),
    ]
    paginated_view(
        "SEARCH PAYMENT RESULTS",
        lambda: records,
        columns,
        empty_message="No payments found.",
        sort_key=None,
        width=78
    )


def search_purchases():
    query = ""
    while True:
        params = {}
        if query:
            params["search"] = query
        sales = request("GET", "/sales", params=params)
        if sales is None:
            pause()
            return

        header("SEARCH PURCHASES", input_screen=True, width=72)
        if query:
            print(f"Filter: '{query}'")
            print("-" * 72)

        if not sales:
            print("No matching purchases found.")
            print("-" * 72)
        else:
            print(f"{'Receipt No':<10} | {'Date & Time':<16} | {'Customer':<20} | {'Total':>8} | {'Status':<9}")
            print("-" * 72)
            for s in sales[:10]:
                dt_str = s["created_at"][:16] if len(s["created_at"]) >= 16 else s["created_at"]
                cust_str = s["customer_name"][:20]
                status_str = s["status"]
                print(f"{s['receipt_no']:<10} | {dt_str:<16} | {cust_str:<20} | {format_currency(s['total']):>8} | {status_str:<9}")
            print("-" * 72)
            if len(sales) > 10:
                print(f"Showing top 10 of {len(sales)} results.")

        print("Enter Receipt No / ID to view details, a search term to filter, or [0] Back.")
        try:
            val = ask("Search or Receipt/ID: ", allow_blank=True)
        except GoBack:
            return

        if not val:
            query = ""
            continue

        selected_sale = None
        for s in sales:
            if val.lower() == s["receipt_no"].lower() or (val.isdigit() and int(val) == s["id"]):
                selected_sale = s
                break

        if selected_sale:
            view_sale_details(selected_sale["id"])
        else:
            query = val


def view_sale_details(sale_id):
    while True:
        sale = request("GET", f"/sales/{sale_id}")
        if not sale:
            pause()
            return

        header("PURCHASE DETAILS", input_screen=False, width=60)
        print(f"Receipt No:     {sale['receipt_no']}")
        print(f"Date & Time:    {sale['created_at']}")
        print(f"Customer:       {sale['customer_name']} ({sale['customer_type']})")
        print(f"Status:         {sale['status']}")
        if sale["status"] == "Voided":
            print(f"Voided At:      {sale.get('voided_at', '-')}")
            print(f"Void Reason:    {sale.get('void_reason', '-')}")
        print("-" * 60)
        print(f"{'Item Name':<30} {'Qty':>4} {'Price':>10} {'Amount':>10}")
        print("-" * 60)
        for it in sale.get("items", []):
            print(f"{it['item_name'][:30]:<30} {it['quantity']:>4} {format_currency(it['unit_price']):>10} {format_currency(it['line_amount']):>10}")
        print("-" * 60)
        print(f"{'Total:':<46} {format_currency(sale['total']):>10}")
        print(f"Payment Method: {sale['payment_method']}")
        print(f"{'Amount Tendered:':<46} {format_currency(sale['amount_tendered']):>10}")
        print(f"{'Change:':<46} {format_currency(sale['change']):>10}")
        print("=" * 60)

        if sale["status"] == "Completed":
            print("[V] Void sale")
            print("[0] Back")
            print("-" * 60)
            choice = input("Choice: ").strip().lower()
            if choice in ("0", "b", "back"):
                return
            elif choice == "v":
                try:
                    reason = ask("Enter void reason: ")
                except GoBack:
                    continue
                confirm = input("Confirm void this sale? (Y/N): ").strip().lower()
                if confirm == "y":
                    res = request("POST", f"/sales/{sale_id}/void", {"reason": reason})
                    if res:
                        print("\nSale has been voided successfully.")
                        pause()
                else:
                    print("Void cancelled.")
                    pause()
        else:
            pause()
            return


def search_records():
    submenu("SEARCH RECORDS", [
        ("Search Customer by Name", search_customer),
        ("Search Customer by ID", search_customer_id),
        ("Search Membership", search_membership),
        ("Search Payment", search_payment),
        ("Search Purchase", search_purchases)
    ])


# SALES REPORTS

def display_sales_report(title, period):
    data = request("GET", "/reports/sales", params={"period": period})
    if data is None:
        pause()
        return

    if not data:
        header(title, input_screen=False, width=60)
        print(f"\nThere are no records for {title.lower()} right now.")
        pause()
        return

    page = 1
    total_pages = len(data)
    width = 60

    while True:
        record = data[page - 1]
        header(title, input_screen=False, width=width)
        period_label = "Date" if period == "daily" else "Month"
        print(f"{period_label}: {record['period']}")
        print("-" * width)
        print(f"{'Category':<16} | {'Transactions':>12} | {'Amount':>16}")
        print("-" * width)
        for cat in record.get("categories", []):
            print(f"{cat['category']:<16} | {cat['transactions']:>12} | {format_currency(cat['amount']):>16}")
        print("-" * width)
        print(f"{'Total sales':<16} | {record['total_transactions']:>12} | {format_currency(record['total_sales']):>16}")
        print("-" * width)
        print(f"Voided sales excluded: {record.get('voided_count', 0)}")

        if period == "daily" and record.get("transactions"):
            print("\nTransactions:")
            print(f"{'Receipt No.':<12} | {'Time':<5} | {'Customer':<20} | {'Total':>8} | {'Status':<9}")
            print("-" * width)
            for tx in record["transactions"][:10]:
                print(f"{tx['receipt_no']:<12} | {tx['time']:<5} | {tx['customer'][:20]:<20} | {format_currency(tx['total']):>8} | {tx['status']:<9}")
            if len(record["transactions"]) > 10:
                print(f"... and {len(record['transactions']) - 10} more transactions.")

        print("-" * width)
        nav = [f"Period {page} of {total_pages}"]
        if page < total_pages:
            nav.append("[N] Next")
        if page > 1:
            nav.append("[P] Previous")
        nav.append("[0] Back")
        print(" | ".join(nav))

        choice = input("Choice: ").strip().lower()
        if choice in ("0", "b", "back"):
            return
        if choice in ("n", "next") and page < total_pages:
            page += 1
            continue
        if choice in ("p", "prev", "previous") and page > 1:
            page -= 1
            continue


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
                    "total": data.get("yearly", {}).get("total", 0)
                },
                {
                    "plan": "Monthly session",
                    "active": data.get("monthly", {}).get("active", 0),
                    "expired": data.get("monthly", {}).get("expired", 0),
                    "upcoming": data.get("monthly", {}).get("upcoming", 0),
                    "total": data.get("monthly", {}).get("total", 0)
                },
                {
                    "plan": "Overall Total",
                    "active": data.get("active", 0),
                    "expired": data.get("expired", 0),
                    "upcoming": data.get("upcoming", 0),
                    "total": data.get("total", 0)
                }
            ]
        columns = [
            ("Plan", "plan", 24),
            ("Active", "active", 12, "right"),
            ("Expired", "expired", 12, "right"),
            ("Upcoming", "upcoming", 12, "right"),
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
            "Daily Sales Report",
            lambda: display_sales_report("DAILY SALES REPORT", "daily")
        ),
        (
            "Monthly Sales Report",
            lambda: display_sales_report("MONTHLY SALES REPORT", "monthly")
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

def main():
    submenu("GYM MANAGEMENT SYSTEM", [
        ("Product/Service Management", product_service_management),
        ("Customer Management", customer_management),
        ("Payment Management", payment_management),
        ("Search Records", search_records),
        ("Sales Reports", sales_reports),
    ])

    clear_screen()
    print("Thank you for using Gym Management System.")


if __name__ == "__main__":
    main()
