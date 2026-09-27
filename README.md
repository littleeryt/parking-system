# SmartPark Kenya

A modern, web-based parking management system built for a Kenyan client who
wants to automate lot operations: live bay availability, automatic vehicle
recording on arrival, and automatic time/fee calculation with barrier release
on exit.

**Stack:** Python 3, Flask, SQLite (standard library `sqlite3`), vanilla
HTML/CSS/JS. No paid services or external accounts required.

## Running it

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000`. A SQLite file `parking.db` is created
automatically on first run, seeded with 20 free bays.

## Project layout

```
app.py               Flask routes -- the four modules described below
data_structures.py   SlotAllocator (min-heap) and WaitingQueue (FIFO)
database.py          SQLite schema + CRUD helpers (the "dynamic database")
templates/index.html Dashboard page
static/style.css     Styling
static/app.js        Front-end polling + form logic
```

---

## Task One: design write-up

### Client terms of reference, restated

- Drivers must see available bays before entering (visual display).
- The system records a vehicle the moment it arrives.
- On exit, the system works out how long the vehicle stayed and what it owes.
- The barrier only opens once the fee is paid.
- Fee schedule: free up to 30 min; Kshs 50 up to 2 h; Kshs 100 up to 4 h;
  Kshs 300 up to 6 h; Kshs 500 beyond that.

### a) Modules and algorithms

**1. Slot Display Module**
- Read every bay's status from the database.
- Render each bay as free (green) or occupied (red); refresh every few
  seconds so the display stays live without a manual reload.

**2. Vehicle Entry Module**
```
INPUT plate
IF plate already parked OR already waiting: reject
IF a free bay exists:
    bay = smallest available bay number      # SlotAllocator.allocate()
    record entry_time = now
    INSERT session row (plate, bay, entry_time)
    mark bay OCCUPIED
ELSE:
    add plate to the back of the waiting queue
```

**3. Exit & Billing Module**
```
INPUT plate
FIND that plate's open session                # O(1) hash-map lookup
duration = now - entry_time
fee = feeSchedule(duration)                    # tiered lookup, O(1)
SHOW fee to driver (no data changes yet -- this is just a quote)
```

**4. Payment & Barrier Module**
```
INPUT plate (must have an open session)
recompute fee at the moment of payment (guards against a slow driver)
CLOSE session row: exit_time = now, fee = fee, paid = 1
mark that bay FREE                             # SlotAllocator.release()
OPEN barrier
IF waiting queue is not empty:
    next_plate = front of queue                # FIFO
    automatically run the Entry algorithm for next_plate into the bay just freed
```

### b) Data structures used, and why

| Structure | Used for | Why this one |
|---|---|---|
| **Min-heap** (`heapq`, in `SlotAllocator`) | Tracking which bay numbers are free | Always hands out the *nearest* free bay in O(log n), instead of an O(n) scan of every bay each time a car arrives. |
| **Hash map** (`dict`, `active_sessions` in `app.py`) | Looking up a parked vehicle by plate at exit | O(1) average lookup regardless of how many cars are parked -- essential since exit/billing has to feel instant to a waiting driver. |
| **FIFO queue** (`collections.deque`, in `WaitingQueue`) | Vehicles that arrive when the lot is full | Guarantees first-come-first-served order; `deque` gives O(1) enqueue/dequeue from opposite ends, unlike a Python list (O(n) to pop from the front). |
| **Relational table rows** (SQLite) | The permanent record of every session | Durable audit trail that survives a restart/crash -- a plain in-memory structure would lose all history the moment the server stopped. |

### c) Dynamic database design

Two tables, both updated continuously as vehicles move through the lot
(this is what makes it *dynamic* rather than a static, pre-filled dataset):

**`slots`**
| column | type | notes |
|---|---|---|
| id | INTEGER PK | bay number, 1..N |
| status | TEXT | `'free'` or `'occupied'`, flipped on every entry/exit |

**`sessions`**
| column | type | notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | one row per parking visit |
| plate | TEXT | vehicle number plate |
| slot_id | INTEGER | which bay this visit used |
| entry_time | TEXT (ISO datetime) | set on arrival |
| exit_time | TEXT (ISO datetime), nullable | `NULL` while the vehicle is still parked |
| fee | INTEGER, nullable | filled in only once paid |
| paid | INTEGER | 0/1 flag |

A row with `exit_time IS NULL` *is* the definition of "currently parked" --
that single condition drives both the live slot display and the O(1)
in-memory lookup used for billing. Closing a session (rather than deleting
it) keeps a full, queryable history for management reporting (revenue per
day, average stay length, peak occupancy, etc.) without any extra tables.

---

## Notes on scope

The waiting queue is kept in memory only (not written to `parking.db`) since
it represents cars physically idling at the entrance right now, not a
billable historical record -- if the server restarts, that line naturally
re-forms from real traffic rather than needing to be replayed from disk.
