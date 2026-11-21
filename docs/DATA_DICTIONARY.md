# Data Dictionary & Data Quality Findings

## Source File Schemas

### 1. `booking_register.csv` (6 rows, UTF-8 with BOM)

| Column | Type | Nullable | Validation Rule & Notes |
|---|---|---|---|
| `booking_id` | string | No | Pattern `^B\d{3,}$`; unique primary identifier (first row kept on duplicate, flagged as error). |
| `service` | string | Yes | Service type; `Elder companionship` and `Childcare` classify as dependant-care services (`CARE_SERVICES`). |
| `locality` | string | Yes | Bengaluru neighbourhood (e.g. `HSR Layout`); informative only — **never** sole match key (`M10`). |
| `scheduled_start_ist` | datetime | Yes | Format `%Y-%m-%d %H:%M`; null is valid when `operations_record` states `"Booking closed."` (`B103`, `B106`). |
| `updated_at_ist` | datetime | Yes | Format `%Y-%m-%d %H:%M`; compared against `scheduled_start_ist` and snapshot (`09:00`) for staleness. |
| `operations_record` | string | Yes | Source of truth for assignment, arrival, Sourcing check, or closure (`derive_booking_facts`). |
| `billing_record` | string | Yes | Source of truth for payment, refund status (`approved` vs `under_review`), amount, and payout date. Null = no recorded facts, **not** proof of non-payment. |

### 2. `shift_inbox.csv` (12 rows, UTF-8 with BOM)

| Column | Type | Nullable | Validation Rule & Notes |
|---|---|---|---|
| `event_id` | string | No | Pattern `^[A-Z]\d{2,}$`; unique evidence ID (`M01`–`M12`). Never dropped on duplicate. |
| `received_at_ist` | datetime | Yes | Format `%Y-%m-%d %H:%M`; used for chronological sorting and deadline context. |
| `thread_id` | string | Yes | Pattern `^[A-Z]\d{2,}$`; links follow-ups within a channel (`T01`–`T08`, `S11`). |
| `booking_id` | string | Yes | Empty on `M05` (prospect) and `M10` (unidentified existing customer). |
| `channel` | string | Yes | `WhatsApp`, `Sales handoff`, or `Call note`. |
| `sender` | string | Yes | `Customer`, `Prospect`, or `Sales` (`Sales` / internal notes set `is_internal=True`). |
| `message` | string | No | Preserved verbatim in `Message.message`; derived `Message.text_normalised` stores NFKC/lowercase copy. |

## Data Lineage & Immutability

- **Original Input:** Preserved verbatim in `BookingRecord.raw`, `Message.raw`, and `Message.message`, plus raw CSV bytes in SQL table `datasets`.
- **Derived Normalisation:** `clean_cell()` strips BOM/whitespace; `normalise_text()` standardises curly quotes/dashes and case into `text_normalised`.
- **Derived Facts:** `BookingFacts` extracts structured boolean/enum fields deterministically from `operations_record` and `billing_record`.

## Actual Data-Quality Report (Supplied Files: 15 Findings)

| File | Record | Field | Type | Severity | Review? | Finding Summary |
|---|---|---|---|---|---|---|
| `booking_register.csv` | `(file)` | `(encoding)` | `encoding` | Info | No | UTF-8 BOM detected and stripped cleanly before CSV parsing. |
| `shift_inbox.csv` | `(file)` | `(encoding)` | `encoding` | Info | No | UTF-8 BOM detected and stripped cleanly before CSV parsing. |
| `booking_register.csv` | `B101` | `billing_record` | `missing_value` | Info | No | Blank billing field = no facts recorded (not proof no payment exists). |
| `booking_register.csv` | `B102` | `billing_record` | `missing_value` | Info | No | Blank billing field = no facts recorded. |
| `booking_register.csv` | `B104` | `billing_record` | `missing_value` | Info | No | Blank billing field = no facts recorded. |
| `booking_register.csv` | `B105` | `billing_record` | `missing_value` | Info | No | Blank billing field = no facts recorded. |
| `booking_register.csv` | `B103` | `scheduled_start_ist` | `missing_value` | Info | No | Missing start time is consistent with `Booking closed.` (missing, not incorrect). |
| `booking_register.csv` | `B106` | `scheduled_start_ist` | `missing_value` | Info | No | Missing start time is consistent with `Booking closed.` |
| `shift_inbox.csv` | `M05` | `booking_id` | `missing_value` | Info | No | Expected blank booking ID for a new `Prospect` enquiry. |
| `shift_inbox.csv` | `M10` | `booking_id` | `missing_value` | **Warning** | **Yes** | Customer message missing `booking_id`; matches `B101` & `B104` by HSR locality only — must not be guessed. |
| `shift_inbox.csv` | `B101` | `thread_id` | `cross_reference` | Info | No | `B101` appears in 2 threads (`S11`, `T01`); merged into `ISS-01`. |
| `booking_register.csv` | `B101` | `updated_at_ist` | `reconciliation` | **Warning** | **Yes** | Register last updated 15h before snapshot (`22 Nov 18:10`) before `08:00` start; stale relative to `M01`. |
| `booking_register.csv` | `B101` | `operations_record` | `reconciliation` | Info | No | Customer message `M01` arrived after register update. |
| `booking_register.csv` | `B102` | `updated_at_ist` | `reconciliation` | **Warning** | **Yes** | Register updated `08:12` before `08:15` start; arrival status stale until reconciled with `M08`. |
| `booking_register.csv` | `B102` | `operations_record` | `reconciliation` | Info | No | Customer messages `M02`, `M08` arrived after register update; close & update register. |

## Record Reconciliation Summary

- **12 inbox messages -> 8 distinct issues:** `(M01, M07) -> ISS-01 [B101]`, `(M02, M08) -> ISS-02 [B102]`, `(M03, M09) -> ISS-03 [B103]`, `(M04) -> ISS-04 [B104]`, `(M05) -> ISS-05 [Prospect]`, `(M06, M12) -> ISS-06 [B105]`, `(M10) -> ISS-07 [Unknown]`, `(M11) -> ISS-08 [B106]`.
- Zero records dropped or silently mutated.

