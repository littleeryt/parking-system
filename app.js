// ---------------------------------------------------------------------
// SmartPark Kenya -- front-end controller
// Talks to the Flask API (app.py) and keeps the visual display in sync.
// ---------------------------------------------------------------------

const slotGrid = document.getElementById("slot-grid");
const occupiedCount = document.getElementById("occupied-count");
const queueList = document.getElementById("queue-list");
const clockEl = document.getElementById("clock");

const entryForm = document.getElementById("entry-form");
const entryMessage = document.getElementById("entry-message");

const checkoutForm = document.getElementById("checkout-form");
const exitMessage = document.getElementById("exit-message");
const feeResult = document.getElementById("fee-result");
const feeSlot = document.getElementById("fee-slot");
const feeMinutes = document.getElementById("fee-minutes");
const feeAmount = document.getElementById("fee-amount");
const payButton = document.getElementById("pay-button");
const barrierArm = document.getElementById("barrier-arm");

let plateAwaitingPayment = null;

// ---- Live clock -------------------------------------------------------
function tickClock() {
  clockEl.textContent = new Date().toLocaleTimeString("en-GB");
}
setInterval(tickClock, 1000);
tickClock();

// ---- Slot display (Module 1) ------------------------------------------
async function refreshState() {
  const res = await fetch("/api/state");
  const data = await res.json();

  occupiedCount.textContent = data.occupied;

  slotGrid.innerHTML = "";
  data.slots.forEach((slot) => {
    const div = document.createElement("div");
    div.className = `slot ${slot.status}`;
    div.innerHTML = `<span class="id">${slot.id}</span>` +
      (slot.plate ? `<span class="plate">${slot.plate}</span>` : "");
    slotGrid.appendChild(div);
  });

  if (data.waiting_queue.length === 0) {
    queueList.innerHTML = '<li class="empty">No vehicles waiting</li>';
  } else {
    queueList.innerHTML = data.waiting_queue
      .map((plate) => `<li>${plate}</li>`)
      .join("");
  }
}
refreshState();
setInterval(refreshState, 3000);

// ---- Vehicle entry (Module 2) ------------------------------------------
entryForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const plateInput = document.getElementById("entry-plate");
  const plate = plateInput.value.trim();
  if (!plate) return;

  const res = await fetch("/api/entry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plate }),
  });
  const data = await res.json();

  if (!res.ok) {
    entryMessage.textContent = data.error;
    entryMessage.className = "message error";
  } else if (data.status === "parked") {
    entryMessage.textContent = `${data.plate} assigned to bay ${data.slot}.`;
    entryMessage.className = "message ok";
  } else {
    entryMessage.textContent = `Lot full -- ${data.plate} is #${data.position} in the waiting queue.`;
    entryMessage.className = "message";
  }
  plateInput.value = "";
  refreshState();
});

// ---- Exit & billing quote (Module 3) ------------------------------------
checkoutForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const plateInput = document.getElementById("exit-plate");
  const plate = plateInput.value.trim();
  if (!plate) return;

  const res = await fetch("/api/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plate }),
  });
  const data = await res.json();

  if (!res.ok) {
    exitMessage.textContent = data.error;
    exitMessage.className = "message error";
    feeResult.classList.add("hidden");
    return;
  }

  exitMessage.textContent = "";
  feeSlot.textContent = `Bay ${data.slot}`;
  feeMinutes.textContent = `${data.minutes_parked} min`;
  feeAmount.textContent = `Kshs ${data.fee}`;
  feeResult.classList.remove("hidden");
  plateAwaitingPayment = data.plate;
});

// ---- Payment & barrier (Module 4) ----------------------------------------
payButton.addEventListener("click", async () => {
  if (!plateAwaitingPayment) return;

  const res = await fetch("/api/pay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plate: plateAwaitingPayment }),
  });
  const data = await res.json();

  if (!res.ok) {
    exitMessage.textContent = data.error;
    exitMessage.className = "message error";
    return;
  }

  // Play the barrier-opening animation, then reset it.
  barrierArm.classList.add("open");
  setTimeout(() => barrierArm.classList.remove("open"), 2200);

  let msg = `Paid Kshs ${data.fee}. Barrier open -- safe travels, ${data.plate}.`;
  if (data.auto_assigned) {
    msg += ` Bay ${data.auto_assigned.slot} now assigned to ${data.auto_assigned.plate} from the queue.`;
  }
  exitMessage.textContent = msg;
  exitMessage.className = "message ok";

  feeResult.classList.add("hidden");
  document.getElementById("exit-plate").value = "";
  plateAwaitingPayment = null;
  refreshState();
});
