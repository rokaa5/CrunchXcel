# Republic of the Philippines
# NUEVA ECIJA UNIVERSITY OF SCIENCE AND TECHNOLOGY
### Cabanatuan City, Nueva Ecija
### COLLEGE OF INFORMATION AND COMMUNICATIONS TECHNOLOGY

---

# AUTOMATED MEMBERSHIP TRACKING, TRANSACTION LEDGER, AND POS SALES MANAGEMENT SYSTEM

## CHRUNCH X FITNESS

**Class Section:** BSIT 3-H  
**Group Number:** Group #2  
**Course Code:** IPT-01 – Integrative Programming Technologies  
**Date:** November 6, 2026  

### Proponents / Members:
- Arenas, Arabela M.
- Domingo, David Ryan M.
- Villanueva, Joyce S.

### Instructor:
**JOHN SEBASTIAN P. MANGILIN**  
Instructor

---

## I. Background of the Business

Chrunch X Fitness is a fitness facility that caters to individuals seeking equipment access, personal fitness coaching, structured workout sessions, and flexible membership subscriptions. To augment its revenue, the business also retails sports beverages, supplements, and workout gear.

This study examines the gym's customer registration, membership lifecycle tracking, cash/e-wallet financial recording, and product/service retail transactions.

### Products and Services Offered
- Gym equipment access and daily workout passes
- Recurring gym memberships (weekly, monthly, annual plans)
- Personal fitness coaching and training sessions
- Bottled beverages, energy drinks, and fitness products

### Target Customers
- Regular gym-goers with recurring monthly or annual memberships
- Walk-in fitness enthusiasts availing daily passes
- Clients receiving personalized one-on-one fitness training
- Facility users purchasing gym beverages and merchandise

### a. Owner and Personnel
The gym owner and front-desk personnel handle customer inquiries, membership registrations, payment collections, and daily sales tallying. Authorized personnel operate the front-desk console to process client transactions.

### b. Business History
Chrunch X Fitness was established to provide accessible, community-oriented fitness facilities. It previously conducted administrative, registration, and financial operations through manual, paper-based logbooks.

---

## II. Existing Business Process

### a. Narrative Description
1. **Customer Inquiry:** A prospective client visits the front desk or contacts staff via social media to inquire about rates, membership tiers, or coaching availability.
2. **Registration:** Front-desk staff manually log customer details (name and contact number) into a paper registry.
3. **Membership Issuance:** Staff record membership start and expiration dates in a subscription logbook.
4. **Service & Product Purchases:** Orders for workout sessions, coaching, or beverages are hand-written on loose order notes or receipts.
5. **Payment Collection:** Payments are collected in Cash or through an E-Wallet (e.g., GCash/Maya QR). Transaction details are recorded manually on paper logs.
6. **Reconciliation:** At closing, staff manually calculate daily revenue by cross-referencing cash in drawer, e-wallet transaction screenshots, and paper tally sheets.

### b. Current Manual Business Process Flow

| Step | Actor | Action | Output |
|---|---|---|---|
| 1 | Customer | Inquires about membership, coaching, or products | Verbal inquiry |
| 2 | Staff | Searches physical logbook for existing records | Manual record search |
| 3 | Staff | Hand-writes customer and plan details | Paper registry entry |
| 4 | Customer | Renders payment via Cash or E-Wallet | Cash / E-wallet transfer |
| 5 | Staff | Notes payment method, amount, and date | Manual transaction record |
| 6 | Staff / Owner | Reviews and manually tallies paper entries | Daily paper summary |

### c. Persons Involved
- **Customers:** Provide identity and contact details and render payments.
- **Gym Staff:** Input records, check member validity, register plans, and record sales.
- **Owner / Manager:** Inspects financial tallies, membership renewals, and inventory status.

### d. Inputs and Outputs

| Process | Inputs | Existing Outputs |
|---|---|---|
| Customer Registration | First name, last name, phone number | Paper customer registry |
| Membership Handling | Customer ID, plan type, start date, duration | Subscription logbook entry |
| Payment Collection | Customer ID, description, amount, payment method | Paper ledger receipt |
| Product / Service Sale | Customer ID, product ID, quantity, payment method | Loose order note |
| Reporting | Daily/monthly ledger entries and e-wallet logs | Manual calculator totals |

---

## III. Problems Identified

1. **Fragmented Paper Records:** Paper logbooks degrade over time, are susceptible to physical loss or damage, and make customer search slow and cumbersome.
2. **Membership Tracking Errors:** Without automated date calculation, expired memberships are difficult to detect, resulting in lost revenue from uncollected renewals.
3. **Data Inconsistency and Typos:** Manual name entries frequently contain duplicate, misspelled, or illegible data with no input validation.
4. **Disconnected Sales & Financials:** Product sales and coaching fees are recorded separately from member payment logs, leading to discrepancies during end-of-day cash reconciliation.
5. **Slow Financial Audits:** Calculating monthly revenue across Cash and E-Wallet methods requires manual sorting and recalculation.

---

## IV. Proposed Program Solution

### a. Purpose
The **Gym Membership and Transaction Management System** digitizes customer records, membership lifecycles, point-of-sale transactions, and financial auditing for Chrunch X Fitness. The architecture decouples business logic and data persistence (FastAPI REST backend with SQLite) from front-desk presentation (interactive Python CLI terminal client).

### b. Intended Users
The system is built exclusively for the gym owner and authorized front-desk personnel. It is an internal operational console rather than an open public client portal.

### c. Major Functions
1. **Customer Management:**
   - Registers customers with separate, validated first and last names.
   - Updates contact numbers and name information with input guardrails.
   - Deletes customer records with referential integrity protection (blocks deletion if transactions exist).
   - Guards against operations on empty tables before asking for user input.
2. **Membership Lifecycle Management:**
   - Registers new memberships with automatic end-date computation based on duration.
   - Categorizes memberships dynamically into **Active**, **Expired**, and **Upcoming**.
   - Handles membership renewals with automatic customer verification.
3. **Payment Management & Financial Ledger:**
   - Records payments classified strictly as **Cash** or **E-Wallet**.
   - Stores currency as exact integer cents to avoid floating-point inaccuracies.
   - Filters and searches transaction history by payment method.
4. **Products and Services Catalog & POS:**
   - Manages product and coaching offerings with guaranteed strictly positive prices (`price > 0`).
   - Processes purchases through atomic database transactions linking purchase records with generated payment ledger entries.
5. **Search & Intelligence Engine:**
   - Dual-field case-insensitive name searching (`first_name` and `last_name`).
   - Fast numeric ID lookups with dedicated validation.
6. **Business Intelligence Reports:**
   - Daily and Monthly sales summaries aggregated automatically.
   - Payment method breakdown (Cash vs. E-Wallet total volume and count).
   - Real-time membership distribution (Active, Expired, Upcoming counts).

### d. Scope and Limitations

#### Scope
- Local multi-tier application (Terminal Client `main.py` + REST API `api.py`).
- SQLite persistence (`gym.db`) with active foreign key constraints (`PRAGMA foreign_keys = ON`).
- Strict v2 input validation (Unicode Latin accents, compound names, length checks).
- Point-of-Sale transaction linkage between products, purchases, and payments.
- Real-time aggregation reports for sales and membership metrics.

#### Limitations
- **Local Host Architecture:** Designed for local network/on-premise deployment; not currently deployed to a public cloud infrastructure.
- **Manual Payment Verification:** Staff confirm receipt of cash or e-wallet transfer; does not directly integrate with third-party payment gateway webhooks (e.g., GCash/PayMongo API).
- **Staff-Facing Console:** Does not feature a mobile self-service app or online customer portal.
- **No SMS/Email Automated Alerts:** Expiration warnings are visible on staff dashboards rather than pushed to members via automated SMS or email.
- **Renewal In-Place Update:** Renewing a membership updates the record's current active cycle rather than appending to a detached multi-year archive table.
- **No Role-Based Access Control (RBAC):** All front-desk staff share access to the operational terminal without role-based login barriers.

---

## V. Major Program Functions & Technical Implementation

### Business Problem to System Function Mapping

| Business Problem | System Function | REST Endpoint & Method | Expected Benefit |
|---|---|---|---|
| Paper customer records | Register & Retrieve Customers | `POST /customers`<br>`GET /customers` | Instant digital search, no lost records |
| Typographical & invalid entries | Strict v2 Regex Validation | Client validation & Pydantic validators | Rejects non-letters, invalid symbols, and bad lengths |
| Premature input on empty tables | Empty Record Guards | `GET /customers/exists` | Halts operations immediately with clear notification |
| Inaccurate membership checking | Dynamic Status Tracking | `GET /memberships?status={status}` | Real-time classification: Active, Expired, Upcoming |
| Cash vs E-Wallet tracking | Payment Method Classification | `POST /payments`<br>`GET /payments?method={method}` | Fast and accurate payment reconciliation |
| Disconnected beverage/service sales | Unified POS & Purchases | `POST /purchases` | Atomic linkage between sales and payment ledger |
| Slow manual reporting | Automated Aggregate Analytics | `GET /reports/sales`<br>`GET /reports/payment-methods`<br>`GET /reports/memberships` | Instant daily/monthly summaries with zero manual math |

---

## VI. REST API Specification

| Method | Endpoint | Purpose | Success Status |
|---|---|---|---|
| `GET` | `/customers/exists` | Fast boolean check using `SELECT EXISTS` | 200 OK |
| `GET` | `/customers` | List all customers or search by `first_name` & `last_name` | 200 OK |
| `POST` | `/customers` | Create new customer (validated `first_name`, `last_name`, `phone`) | 201 Created |
| `GET` | `/customers/{id}` | Retrieve specific customer record | 200 OK |
| `PUT` | `/customers/{id}` | Update customer name or contact information | 200 OK |
| `DELETE` | `/customers/{id}` | Delete customer (blocked if transaction history exists) | 204 No Content |
| `GET` | `/memberships` | List memberships filtered by `status` (`all`, `active`, `expired`, `upcoming`) | 200 OK |
| `POST` | `/memberships` | Create membership (validates customer existence and date sequence) | 201 Created |
| `PUT` | `/memberships/{id}` | Renew membership plan and update valid date range | 200 OK |
| `GET` | `/payments` | Retrieve payment ledger, optionally filtered by `method` | 200 OK |
| `POST` | `/payments` | Record direct payment (Cash or E-Wallet) | 201 Created |
| `GET` | `/products` | List all catalog products and coaching services | 200 OK |
| `POST` | `/products` | Add new catalog product/service (`price > 0`) | 201 Created |
| `PUT` | `/products/{id}` | Update product name, category, or unit price | 200 OK |
| `DELETE` | `/products/{id}` | Delete product (blocked if purchase history exists) | 204 No Content |
| `POST` | `/purchases` | Process purchase; atomically records payment and purchase rows | 201 Created |
| `GET` | `/reports/sales` | Aggregate sales grouped by period (`daily` or `monthly`) | 200 OK |
| `GET` | `/reports/payment-methods` | Aggregate transaction count and totals by payment method | 200 OK |
| `GET` | `/reports/memberships` | Real-time counts of Active, Expired, and Upcoming memberships | 200 OK |

---

## VII. Data Validation and Business Logic Rules

### 1. Customer Input Validation (v2 Rules)
- **Split Names:** Names are strictly divided into `first_name` and `last_name`, validated independently.
- **Allowed Characters:** Latin letters (`A-Z`, `a-z`) and Latin accented characters (`Muñoz`, `José`).
- **Allowed Separators:** Spaces between words (`De la Cruz`), hyphens between letters (`Anne-Marie`), and apostrophes between letters (`O'Brien`, `D’Angelo`).
- **Disallowed:** Digits, punctuation (`!`, `@`, `#`), symbols, starting/ending with non-letters (`-Maria`, `Maria-`), and consecutive separators (`Anne--Marie`, `O''Brien`).
- **Normalization:** Leading and trailing spaces are trimmed; internal repeated whitespace is collapsed to a single space (`De   la   Cruz` → `De la Cruz`).
- **Length Constraint:** 1 to 50 characters maximum.
- **Validation Messages:**
  - Empty: `{Field} is required.`
  - Invalid format: `{Field} may contain only letters, spaces, hyphens, and apostrophes.`
  - Too long: `{Field} must be 50 characters or fewer.`

### 2. Customer ID Validation
- Pattern: `^[0-9]+$` (digits only).
- Leading zeros are accepted and normalized to integer (`007` → `7`).
- Messages:
  - Empty: `Customer ID is required.`
  - Non-digits: `Customer ID must contain numbers only.`
  - Non-existent ID: `Customer with ID {id} was not found.`

### 3. Philippine Mobile SIM Phone Validation
- **Supported Formats:** Local format (`09XXXXXXXXX` / 11 digits total) and international format (`+639XXXXXXXXX` / 13 characters total).
- **Format-Only Verification:** Validated via regex pattern `^(09|\+639)\d{9}$`. Format and length only are enforced; fixed prefix lists have been removed to avoid false rejections of valid customer prefixes (such as `0962`).
- **Input Cleaning:** Spaces and hyphens (`[\s-]`) are stripped before validation, so inputs like `0962 616 4040` and `+63 962-616-4040` are smoothly accepted.
- **Standardized Storage:** All valid international inputs (`+639...`) are normalized to standard 11-digit local format (`09XXXXXXXXX`) before persisting to SQLite, ensuring uniform duplicate checking and search lookup.
- **Unified Validation Message:** All format, length, letter, or character errors return a single message: `Enter a valid mobile number: 09XXXXXXXXX or +639XXXXXXXXX.`

### 4. Single-Call List Loading & Empty-Record Handling
List screens query the collection endpoint directly (`GET /customers`, `GET /memberships`, `GET /payments`). If the response returns zero records, the screen immediately renders the clean empty-state layout without `[0] Back` or secondary input prompts, exiting directly via `Press Enter to continue...`:
- **Customers:** `There are no customers to view/update/delete.`
- **Payments:** `There are no payments to search.` (or `There are no payment records right now.` on view)
- **Memberships:** `There are no memberships to renew.` (or `There are no membership records right now.` on view)

### 5. Paginated Customer Tables (`View`, `Update`, & `Delete Customer`)
- **Configurable Page Size:** Controlled globally by `PAGE_SIZE = 10` (configurable from 10 to 15 rows per page).
- **View Customers Table (78 columns):** Displays `ID`, `First Name`, `Last Name`, `Phone`, `Membership`, and `Subscription`.
- **Update and Delete Customer Lists (69 columns):** Displays `ID`, `Name`, `Phone` (with middle digits masked: `0967***2356`), `Membership`, and `Subscription` above the selection prompt, allowing staff to distinguish customers sharing identical names.
- **Pre-Confirmation Deletion Check:** When an ID is selected in `Delete Customer`, the system verifies whether the customer has existing memberships or payments before asking for confirmation. If history exists, it displays `"This customer has memberships or payments and cannot be deleted."` and returns safely without prompting `(y/n)`.
- **Formatting Guarantees:** Missing membership/subscription values render as `-`, and long values truncate with `...` to preserve strict column alignment.

### 6. Financial & Currency Accuracy
- Stored as integer cents (`amount_cents`, `price_cents`) in SQLite to eliminate binary floating-point roundoff errors.
- Displayed consistently across all endpoints and terminal views as two-decimal standard currency (`f"{Decimal(cents) / 100:.2f}"`).

### 7. CrunchX Fitness Product & Service Catalog (Services vs. Products Separation)
All 19 catalog items are stored in the unified `products` table with an automatic `type` column (`Service` or `Product`) derived strictly from `CATEGORY_TO_TYPE`:
- **Service Categories (IDs 1–7):** `Membership`, `Gym Access`, `Coaching`
- **Product Categories (IDs 8–19):** `Beverage`, `Supplement`, `Merchandise`
- **Display & Navigation:** Prices are right-aligned with two decimals and thousands commas (`1,200.00`). Multi-page tables place `[0] Back` on the bottom navigation line (`[N] Next   [0] Back`) directly above the prompt.
- **Sales Report Income Split:** Daily and monthly sales reports break down **Service Income** (and transaction count) vs. **Product Income** (and transaction count), summing to **Total Sales**.

| ID | Item | Category | Price (PHP) | Stored Cents | Basis |
|---|---|---|---|---|---|
| 1 | Yearly membership | Membership | 300.00 | `30000` | Posted |
| 2 | Member session, daily | Gym Access | 50.00 | `5000` | Posted |
| 3 | Monthly session | Gym Access | 1,200.00 | `120000` | Posted |
| 4 | Walk-in non-member, daily | Gym Access | 70.00 | `7000` | Posted |
| 5 | Personal trainer, member, daily session | Coaching | 120.00 | `12000` | Posted |
| 6 | Personal trainer, member, per session (monthly basis) | Coaching | 70.00 | `7000` | Posted |
| 7 | Personal trainer, non-member | Coaching | 140.00 | `14000` | Posted |
| 8 | Bottled water | Beverage | 10.00 | `1000` | Posted |
| 9 | Cobra | Beverage | 25.00 | `2500` | Posted |
| 10 | Sting | Beverage | 25.00 | `2500` | Posted |
| 11 | Vitamilk | Beverage | 35.00 | `3500` | Posted |
| 12 | Gatorade | Beverage | 40.00 | `4000` | Posted |
| 13 | Fit N Right Pineapple | Beverage | 40.00 | `4000` | Posted |
| 14 | Optimum Nutrition Micronized Creatine Powder, 300 g (60 servings) | Supplement | 1,845.00 | `184500` | Reference |
| 15 | ProtHN Monohydrate Creatine Powder, 60 servings | Supplement | 1,200.00 | `120000` | Estimate |
| 16 | Optimum Nutrition Superior Amino 2222, 160 tablets | Supplement | 1,900.00 | `190000` | Estimate |
| 17 | ProtHN Whey Protein, box | Supplement | 1,800.00 | `180000` | Estimate |
| 18 | Mass gainer, bag | Supplement | 2,500.00 | `250000` | Estimate |
| 19 | Insulated tumbler (white, pink, or blue) | Merchandise | 650.00 | `65000` | Estimate |

### 8. Plans, Term Automation, and Point of Sale Daily Rates
To accurately reflect the CrunchX Fitness price catalog and prevent operational errors:
1. **Two-Plan Term Model**:
   - **Yearly Membership (ID 1, ₱300.00):** 1-year term (`today + 1 year`). Open to any customer.
   - **Monthly Session (ID 3, ₱1,200.00):** 1-month term (same day next month, clamped to month-end). Open to any customer, member or non-member.
2. **Per-Plan Status Calculation**:
   - Customer status is calculated from the record with the latest end date for that specific plan (`None`, `Active`, `Expired`, or `Upcoming`).
   - `Membership` column displays Yearly Membership status; `Subscription` column displays Monthly Session status.
3. **Plan-First Architecture & Structured Navigation**:
   - `MEMBERSHIP MANAGEMENT` presents top-level options: `[1] Yearly Membership`, `[2] Monthly Session`, and `[3] Customer Overview`.
   - Each plan submenu provides five actions: `[1] Register`, `[2] Renew`, `[3] View All`, `[4] View Active`, `[5] View Expired`.
   - All screen headers explicitly name the active plan (e.g., `REGISTER YEARLY MEMBERSHIP`, `ACTIVE MONTHLY SESSIONS`).
4. **Register Workflow Per Plan**:
   - Displays customer selection list containing only customers who do not currently hold the plan (`ID | Name | Phone`).
   - If an ID is typed that already has the plan, the system informs staff: `"This customer already has a {plan}. Use Renew instead."` and prevents registration.
   - For eligible customers, displays term, prompts Payment Method (`[1] Cash`, `[2] E-Wallet`), and registers plan atomically with payment.
   - When no customers can be registered, displays a clean notice (`"All customers already have a yearly membership/monthly session. Use Renew to extend an existing membership."`) and pauses on Enter.
5. **Renew Workflow Per Plan**:
   - Lists eligible customers (`Active` or `Expired`), showing current end date.
   - Computes early renewal term (from existing end date) or expired renewal term (from today).
   - Prompts Payment Method and confirms atomically.
6. **Separated View Screens & Customer Overview**:
   - View screens list only the selected plan without mixing rows; `Plan` column is omitted since the title specifies it. Rows are sorted by customer ID, then start date.
   - Early renewals are marked `Upcoming` and listed in `View All`.
   - Empty lists render clear plan-specific notifications (`No yearly memberships found.` / `No monthly sessions found.`).
   - `CUSTOMER OVERVIEW` presents a unified view-only summary with each customer listed once, showing their latest status for both `Yearly Membership` and `Monthly Session`.
7. **Clean "Press Enter to continue..." Processing**:
   - Built-in terminal key-capture flushes pre-buffered keystrokes, rejects all non-Enter keys without echoing, and proceeds immediately on Enter.
7. **Unified Sales & Point of Sale Daily Services**:
   - Dedicated `Record Payment` prompt in Payment Management is retired in favor of catalog sales in Products and Services (`Record Purchase`).
   - Chooser allows selecting `[1] Services` or `[2] Products`.
   - When recording a service sale, the system checks membership status:
     - **Members (Yearly Membership Active):**
       - If customer has an active monthly session, displays `"Monthly session active until {date}"` and daily gym session is omitted. Personal trainer options offered: `[1] Personal trainer session` (₱120.00 with ₱20.00 member discount displayed from ₱140.00), `[2] Personal trainer, per session (monthly basis)` (₱70.00).
       - If no active monthly session: offers `[1] Daily session` (₱50.00 with ₱20.00 member discount displayed from ₱70.00), `[2] Personal trainer session` (₱120.00 with ₱20.00 discount), `[3] Personal trainer, per session (monthly basis)` (₱70.00).
     - **Non-Members:** Offered `[1] Daily session` (₱70.00), `[2] Personal trainer session` (₱140.00). No discount line is displayed.
     - Daily services automatically default quantity to `1`.
     - Prompts for Payment Method (`[1] Cash`, `[2] E-Wallet`) and confirmation prompt `"Record payment? (y/n): "`.
6. **Upcoming Renewals View**:
   - Renamed from "Upcoming Memberships" to `"View Upcoming Renewals"`, displaying saved renewals with future start dates (`start_date > today`). Empty state: `"There are no upcoming renewals right now."`.

---

## VIII. System Architecture & Database Design

### a. File Structure
- [`main.py`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/main.py): Terminal user interface, menu dispatchers, input validation loops, and HTTP request handling.
- [`api.py`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/api.py): FastAPI REST service exposing endpoints, relational database queries, status evaluators, and aggregation reporting.
- [`database.py`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/database.py): SQLite connection manager, foreign-key enforcement, schema initialization, and automated table migrations.
- [`models.py`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/models.py): Pydantic models for data validation, whitespace stripping, and serialization.
- [`create_test_records.py`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/create_test_records.py): Standalone testing utility to safely populate or clean demo/test customer records without polluting production data.
- [`requirements.txt`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/requirements.txt): Runtime dependencies (`fastapi`, `uvicorn`, `requests`, `pydantic`).
- `gym.db`: Local SQLite database file automatically created and migrated.

### b. Data Flow Architecture
```text
Staff Input (Console)
       │
       ▼
Input Validation (main.py regex & rules)
       │
       ▼
HTTP / REST JSON Request
       │
       ▼
FastAPI Route Handler (api.py)
       │
       ▼
Pydantic Serialization & Business Logic (models.py)
       │
       ▼
SQLite Transaction & Parameterized Queries (database.py)
       │
       ▼
gym.db (Persistent Storage with Foreign Keys)
       │
       ▼
JSON Response → CLI Terminal Formatted Display
```

### c. Relational Database Schema

```sql
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT NOT NULL
);

CREATE TABLE memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    plan TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);

CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    method TEXT NOT NULL CHECK(method IN ('Cash', 'E-Wallet')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('Service', 'Product')),
    price_cents INTEGER NOT NULL CHECK(price_cents > 0)
);

CREATE TABLE purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price_cents INTEGER NOT NULL,
    payment_id INTEGER NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id),
    FOREIGN KEY(product_id) REFERENCES products(id),
    FOREIGN KEY(payment_id) REFERENCES payments(id)
);
```

---

## IX. Program Testing & Acceptance Verification

| Test ID | Category | Steps / Input | Expected Result | Status |
|---|---|---|---|---|
| **T01** | Customer Creation | Register `first_name="José"`, `last_name="Muñoz"`, `phone="09123456789"` | HTTP 201; ID generated; UTF-8 accents preserved | **PASSED** |
| **T02** | Name v2 Validation | Enter invalid names: `Maria2`, `Maria!`, `-Maria`, `Anne--Marie`, `O''Brien` | Rejected with: `{Field} may contain only letters, spaces, hyphens, and apostrophes.` | **PASSED** |
| **T03** | Compound Name | Enter `first_name="De   la   Cruz"` | Whitespace collapsed to `"De la Cruz"`; accepted | **PASSED** |
| **T04** | Name Length Limit | Enter name with > 50 characters | Rejected with: `{Field} must be 50 characters or fewer.` | **PASSED** |
| **T05** | Phone Number Characters | Enter `a`, `0917abc4567`, `0917+1234567` | Rejected with: `Phone number may contain only numbers and a leading + sign.` | **PASSED** |
| **T06** | Phone Format & Length | Enter `0917123456` (10 digits), `091712345678` (12 digits), `639171234567`, `9171234567` | Rejected with: `Enter a valid mobile number: 09XXXXXXXXX or +639XXXXXXXXX.` | **PASSED** |
| **T07** | Phone Prefix Extensibility | Enter newly allocated prefix `09626164040` | Accepted; valid format recognized without obsolete prefix rejections | **PASSED** |
| **T08** | International Normalization | Register with `+639171234567` | Accepted; converted to `09171234567` and stored with leading zero | **PASSED** |
| **T09** | Customer ID Validation | Enter `12a`, `12 3`, `-5`, `1.5`, `#12` | Rejected with: `Customer ID must contain numbers only.` | **PASSED** |
| **T10** | Empty Table Guard | Attempt View/Update/Delete when customers table has 0 rows | Operations halt immediately with `There are no customers to {action}.` | **PASSED** |
| **T11** | Nonexistent ID Lookup | Search or update customer ID `999` | Displays `Customer with ID 999 was not found.` | **PASSED** |
| **T12** | Case-Insensitive Search | Search `first_name="josé"`, `last_name="muñoz"` | Returns record for `José Muñoz` regardless of case | **PASSED** |
| **T13** | Non-Matching Search | Search `first_name="Pedro"`, `last_name="Luna"` | Shows `No customers found matching "Pedro Luna".` | **PASSED** |
| **T14** | Referential Protection | Delete customer with linked membership/payments | HTTP 409 Conflict; deletion rejected, data retained | **PASSED** |
| **T15** | Clean Customer Delete | Delete customer with no transaction history | HTTP 204 No Content; customer successfully deleted | **PASSED** |
| **T16** | Membership Status Filter | Query `/memberships?status=upcoming` | HTTP 200; filters memberships starting in the future | **PASSED** |
| **T17** | Date Sequence Check | Enter `end_date` earlier than `start_date` | HTTP 422; rejected with date sequence warning | **PASSED** |
| **T18** | Positive Product Price | Add product with `price <= 0` | HTTP 422; rejected (strictly positive price required) | **PASSED** |
| **T19** | Atomic Purchase & POS | Purchase quantity `2` of product (price `50.00`) | Atomic HTTP 201; creates purchase and payment of `100.00` | **PASSED** |
| **T20** | Currency Representation | Query payments list | All amounts formatted to two decimal places (`.2f`) | **PASSED** |
| **T21** | Navigation Cancellation | Enter `0` during any submenu or form prompt | Safely returns to previous menu without modifying database | **PASSED** |
| **T22** | Persistence Guarantee | Restart backend API and terminal client | All SQLite records and constraints intact | **PASSED** |
| **T23** | Register Audience Filter | Open Register Membership screen | Shows only customers with status `None`; excludes active/expired/upcoming customers | **PASSED** |
| **T24** | Renew Audience Filter | Open Renew Membership screen | Shows only customers with status `Active` or `Expired`; excludes customers with waiting renewal | **PASSED** |
| **T25** | Early Renewal Calculation | Renew active membership with 3 days remaining | Renewal start date equals current end date; old membership end date untouched | **PASSED** |
| **T26** | Expired Renewal Calculation | Renew expired membership | Renewal starts automatically today; ends 1 year later | **PASSED** |
| **T27** | Waiting Renewal Guard | Customer with already queued future renewal attempts renewal | Customer omitted from Renew list; backend rejects second renewal (HTTP 409) | **PASSED** |
| **T28** | Unlisted ID Validation | Enter customer ID not in shown filtered list | Rejected with `ID not in this list.` | **PASSED** |
| **T29** | One-Year Leap Term | Registration/Renewal on leap day `2028-02-29` | End date computed automatically as `2029-02-28` without error | **PASSED** |
| **T30** | Empty Audience State | Open Register/Renew when 0 qualifying customers exist | Screen displays clean empty state (`There are no customers without a yearly membership.` / `There are no customers to renew.`) | **PASSED** |
| **T31** | Plan Chooser Prompt | Open Register or Renew Membership | Displays plan chooser: `[1] Yearly membership`, `[2] Monthly session`, `[0] Back` | **PASSED** |
| **T32** | Monthly Eligibility Rule | Register monthly session for non-member | Non-member excluded from Monthly list; backend rejects with HTTP 409 | **PASSED** |
| **T33** | Monthly Term Math | Register monthly session on Jan 31 | End date clamped safely to last day of next month (Feb 28 / Feb 29) | **PASSED** |
| **T34** | Point of Sale Member Rates | Record purchase for customer with active yearly membership | Displays Member status banner; offers member daily rates (`50.00`, `120.00`, `70.00`) | **PASSED** |
| **T35** | Monthly Access Omission | Record purchase for member with active monthly session | Displays active monthly notice; omits daily member session (`50.00`) | **PASSED** |
| **T36** | Point of Sale Non-Member | Record purchase for walk-in non-member | Offers non-member rates (`70.00`, `140.00`) and yearly membership (`300.00`) | **PASSED** |
| **T37** | Plan-First Architecture | Open Membership Management | Choose plan first (`[1] Yearly Membership`, `[2] Monthly Session`, `[3] Customer Overview`); plan column omitted from single-plan tables | **PASSED** |
| **T38** | Register List Filtering | Open Register Yearly or Register Monthly | Lists only customers with no record for that plan; redundant status column removed | **PASSED** |
| **T39** | Smart Guidance on Invalid ID | Enter ID of ineligible customer in Register, Renew, or Delete | Explains exact reason (`This customer already has a <plan>. Use Renew instead.`, `This customer has memberships or payments and cannot be deleted.`) | **PASSED** |
| **T40** | Delete Customer Pre-Filter | Open Delete Customer screen | Only lists customers with zero memberships and zero payments; blocks deletion upfront | **PASSED** |
| **T41** | Delete Product Pre-Filter | Open Delete Product or Service screen | Only lists items with zero purchase history; blocks deletion upfront | **PASSED** |
| **T42** | Silent Keystroke Pause | Press any key on `Press Enter to continue...` | Non-Enter keys are completely ignored and never echoed to the terminal | **PASSED** |
| **T43** | Unified Payment Search | Search Payment by name, payment ID, or customer ID | Returns matching ledger records formatted with customer names and currency | **PASSED** |
| **T44** | Delete Customer Records Notice | Open Delete Customer screen with 0 deletable records | Displays `No customers can be deleted. Customers with memberships or payments are kept for records.` | **PASSED** |
| **T45** | Universal 0-to-Cancel | Type `0` at any step in Register, Renew, or Record Purchase | Operation aborts immediately; nothing saved; shows `Cancelled. Nothing was saved.` | **PASSED** |
| **T46** | Multi-Item Record Purchase | Add multiple products/services to purchase cart | Real-time summary displays items, quantities, and totals; recorded in single atomic payment | **PASSED** |
| **T47** | Payment Management Reorg | Open Payment Management menu | Features `Record Purchase`, `View Payment History`, `View Cash Payments`, and `View E-Wallet Payments` | **PASSED** |
| **T48** | Payment Ledger Totals | Open Cash or E-Wallet Payments | Displays aggregate total line (`Total cash: <sum>` / `Total e-wallet: <sum>`) across all pages | **PASSED** |
| **T49** | Plan Exclusion in Purchases | Open Record Purchase catalog | Excludes Yearly membership and Monthly session; restricted to sales of items and drop-in services | **PASSED** |
| **T50** | Delete All Entries Script | Run `python delete_all_entries.py` with `DELETE ALL` | Creates backup, clears transaction history, resets ID counters to 1, and preserves products catalog | **PASSED** |
| **T51** | Walk-In Purchase Recording | Record sale for walk-in buyer | Processes without customer ID; snapshotted as `Walk-in` with non-member rates | **PASSED** |
| **T52** | Membership Item Eligibility | Pick items for member vs. walk-in | Member-only services blocked for non-members (`Item not available for this customer`); non-member rates blocked for members | **PASSED** |
| **T53** | Tender & Change Computation | Cash payment checkout | Enforces tender >= total due; rejects tender deficits; computes exact change | **PASSED** |
| **T54** | Atomic Sale & Clean Receipt | Confirm and commit multi-item purchase | Saves `sales` and `sale_items` atomically; generates sequential `R-000001` receipt; suppresses phone numbers | **PASSED** |
| **T55** | Historical Price Snapshots | Edit catalog product price | Old sales retain unit price and total captured at checkout time | **PASSED** |
| **T56** | Sale Voiding with Required Reason | Void completed sale via Search Purchase | Prompts mandatory reason; tags sale `Voided`; excludes from sales reports | **PASSED** |
| **T57** | Category Sales Breakdown | View Daily / Monthly Sales Report | Displays itemized totals across Membership, Gym Access, Coaching, Beverage, Supplement, and Merchandise | **PASSED** |
| **T58** | Product/Service Menu Structure | Open Product/Service Management | Contains Yearly Membership, Monthly Session, Services/Products, and Customer Overview | **PASSED** |
| **T59** | Trainer Session Workflow | Book coaching under Services/Products | Validates member/non-member rates, assigns trainer, enforces non-future date, and issues receipt | **PASSED** |

---

## X. Conclusion

The modernized **Gym Membership and Transaction Management System** successfully resolves the operational inefficiencies of Chrunch X Fitness. By replacing vulnerable, fragmented paper logbooks with a robust multi-tier architecture, the system provides:
1. **Bulletproof Data Quality:** Enforces strict v2 validation, preventing typographical errors, invalid characters, and corrupted records.
2. **Elimination of Operational Bottlenecks:** Replaces manual calculator reconciliation with instant, real-time daily/monthly reports and Cash vs. E-Wallet breakdowns.
3. **Safe Database Architecture:** Uses foreign-key referential integrity to prevent accidental deletion of customers or products tied to transaction records.
4. **Intuitive Front-Desk Experience:** Employs smart empty-state guards that protect staff from entering IDs when records do not exist.

The software architecture is complete, verified by an automated test suite, and ready for deployment at Chrunch X Fitness.

---

## XI. Digital Access & Repository

- **Application Environment:** Python 3.10+, FastAPI, Uvicorn, SQLite3, Requests
- **Interactive OpenAPI Documentation:** `http://127.0.0.1:8000/docs`
- **Source Files:**
  - [`api.py`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/api.py) — REST API Endpoints & Aggregations
  - [`database.py`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/database.py) — SQLite Connector, Schema & Migrations
  - [`models.py`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/models.py) — Pydantic Schemas & v2 Validators
  - [`main.py`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/main.py) — Front-Desk Terminal Client & Input Guards
  - [`requirements.txt`](file:///C:/Users/domin/OneDrive/Desktop/New%20folder/IPT%20-%20Python/requirements.txt) — Dependency Specifications
