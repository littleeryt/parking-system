"""
app.py
------
SmartPark Kenya -- a modern, web-based parking management system.

Modules (Task One, part a -- see README.md for full algorithms):
  1. Slot Display Module      -> GET  /            and GET /api/state
  2. Vehicle Entry Module     -> POST /api/entry
  3. Exit & Billing Module    -> POST /api/checkout
  4. Payment & Barrier Module -> POST /api/pay

Run with:
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000 in a browser.
"""

from datetime import datetime
from threading import Lock

from flask import Flask, jsonify, render_template, request

import database
from data_structures import SlotAllocator, WaitingQueue

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TOTAL_SLOTS = 20
SYSTEM_NAME = "SmartPark Kenya"

app = Flask(__name__)
lock = Lock()  # guards the in-memory structures against concurrent requests

# ---------------------------------------------------------------------------
# In-memory structures (rebuilt from the database on every startup)
# ---------------------------------------------------------------------------
database.init_db(TOTAL_SLOTS)

allocator = SlotAllocator(TOTAL_SLOTS)
allocator.rebuild_from(database.get_free_slot_ids())

waiting_queue = WaitingQueue()

# Hash map: plate -> open session dict {id, slot_id, entry_time}.
# A dict gives O(1) average lookup, which is why exit/checkout is fast
# even with hundreds of vehicles parked at once.
active_sessions = {}
for row in database.get_open_sessions():
    active_sessions[row["plate"]] = row


# ---------------------------------------------------------------------------
# Core algorithm: tiered fee calculation
# ---------------------------------------------------------------------------
def calculate_fee(minutes: float) -> int:
    """
    Fee schedule supplied by the client:
        <= 30 min   -> free
        <= 2 hours  -> Kshs 50
        <= 4 hours  -> Kshs 100
        <= 6 hours  -> Kshs 300
        >  6 hours  -> Kshs 500
    """
    if minutes <= 30:
        return 0
    if minutes <= 120:
        return 50
    if minutes <= 240:
        return 100
    if minutes <= 360:
        return 300
    return 500


def _elapsed_minutes(entry_time_iso: str) -> float:
    entry_dt = datetime.fromisoformat(entry_time_iso)
    return (datetime.now() - entry_dt).total_seconds() / 60.0


def _assign_slot_to(plate: str) -> int:
    """Shared by manual entry and auto-assignment from the waiting queue."""
    slot_id = allocator.allocate()
    entry_time = datetime.now().isoformat(timespec="seconds")
    session_id = database.create_session(plate, slot_id, entry_time)
    database.set_slot_status(slot_id, "occupied")
    active_sessions[plate] = {
        "id": session_id,
        "slot_id": slot_id,
        "entry_time": entry_time,
    }
    return slot_id


# ---------------------------------------------------------------------------
# Module 1: Slot Display
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", system_name=SYSTEM_NAME, total_slots=TOTAL_SLOTS)


@app.route("/api/state")
def api_state():
    """Polled by the front end to keep the visual slot display live."""
    with lock:
        slots = database.get_all_slots()
        occupied = sum(1 for s in slots if s["status"] == "occupied")
        return jsonify(
            {
                "slots": slots,
                "occupied": occupied,
                "total": TOTAL_SLOTS,
                "waiting_queue": waiting_queue.as_list(),
            }
        )


# ---------------------------------------------------------------------------
# Module 2: Vehicle Entry
# ---------------------------------------------------------------------------
@app.route("/api/entry", methods=["POST"])
def api_entry():
    """
    Algorithm:
      1. Reject blank plates, plates already parked, or plates already queued.
      2. If a free slot exists (heap non-empty) -> allocate nearest slot,
         record entry_time, write a new session row.
      3. Else -> push the plate onto the FIFO waiting queue.
    """
    plate = (request.json or {}).get("plate", "").strip().upper()
    if not plate:
        return jsonify({"error": "License plate is required."}), 400

    with lock:
        if plate in active_sessions:
            return jsonify({"error": f"{plate} is already parked."}), 409
        if waiting_queue.contains(plate):
            return jsonify({"error": f"{plate} is already in the waiting queue."}), 409

        if allocator.has_free_slot():
            slot_id = _assign_slot_to(plate)
            return jsonify({"status": "parked", "plate": plate, "slot": slot_id})
        else:
            position = waiting_queue.enqueue(plate)
            return jsonify({"status": "queued", "plate": plate, "position": position})


# ---------------------------------------------------------------------------
# Module 3: Exit & Billing (quote only -- does not close the session yet)
# ---------------------------------------------------------------------------
@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    """
    Algorithm:
      1. Look up the plate in the active_sessions hash map -- O(1).
      2. duration = now - entry_time.
      3. fee = calculate_fee(duration).
      Nothing is written to the database here; this just quotes the fee
      so the driver can see it before paying.
    """
    plate = (request.json or {}).get("plate", "").strip().upper()

    with lock:
        session = active_sessions.get(plate)
        if not session:
            return jsonify({"error": f"No parked vehicle found for {plate}."}), 404

        minutes = _elapsed_minutes(session["entry_time"])
        fee = calculate_fee(minutes)
        return jsonify(
            {
                "plate": plate,
                "slot": session["slot_id"],
                "minutes_parked": round(minutes, 1),
                "fee": fee,
            }
        )


# ---------------------------------------------------------------------------
# Module 4: Payment & Barrier Control
# ---------------------------------------------------------------------------
@app.route("/api/pay", methods=["POST"])
def api_pay():
    """
    Algorithm:
      1. Re-confirm the vehicle is still parked and compute the final fee
         (guards against a long delay between quote and payment).
      2. Close the session row (exit_time, fee, paid=1) in the database.
      3. Release the slot back onto the min-heap and mark it free in the DB.
      4. Barrier opens (the response tells the front end to play the
         opening animation).
      5. If anyone is waiting, automatically dequeue the next plate and
         assign it the slot that was just freed.
    """
    plate = (request.json or {}).get("plate", "").strip().upper()

    with lock:
        session = active_sessions.get(plate)
        if not session:
            return jsonify({"error": f"No parked vehicle found for {plate}."}), 404

        minutes = _elapsed_minutes(session["entry_time"])
        fee = calculate_fee(minutes)
        exit_time = datetime.now().isoformat(timespec="seconds")

        database.close_session(session["id"], exit_time, fee)
        database.set_slot_status(session["slot_id"], "free")
        allocator.release(session["slot_id"])
        del active_sessions[plate]

        auto_assigned = None
        if not waiting_queue.is_empty():
            next_plate = waiting_queue.dequeue()
            new_slot = _assign_slot_to(next_plate)
            auto_assigned = {"plate": next_plate, "slot": new_slot}

        return jsonify(
            {
                "plate": plate,
                "fee": fee,
                "barrier": "open",
                "auto_assigned": auto_assigned,
            }
        )


if __name__ == "__main__":
    # use_reloader=False: the reloader's file-watcher can otherwise trip
    # over writes to parking.db in the same folder and restart the server
    # mid-request. debug=True still gives helpful tracebacks in the browser.
    app.run(debug=True, use_reloader=False)
