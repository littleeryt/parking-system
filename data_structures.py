"""
data_structures.py
-------------------
Custom data-structure wrappers used by the Modern Parking System.

Why these specific structures (see README.md, Task One, part (b) for the
full write-up):

1. SlotAllocator (min-heap / priority queue via heapq)
   - Free slot numbers are kept in a binary min-heap.
   - allocate() always pops the SMALLEST free slot number in O(log n),
     which means arriving cars are always sent to the slot nearest the
     entrance instead of a random free bay.
   - release() pushes a slot back in O(log n) as soon as a car leaves.
   - A plain list would need an O(n) scan to find the minimum every time;
     the heap keeps this fast even as the lot grows.

2. WaitingQueue (FIFO queue via collections.deque)
   - When the lot is full, arriving vehicles must be served in the order
     they arrived (first-come-first-served) -- a queue is the natural fit.
   - deque gives O(1) append (enqueue) and O(1) popleft (dequeue), unlike
     a Python list where popleft-style removal from the front is O(n).
"""

import heapq
from collections import deque


class SlotAllocator:
    """Manages which parking slots are free using a min-heap."""

    def __init__(self, total_slots: int):
        self.total_slots = total_slots
        # Start with every slot number pushed onto the heap: 1..total_slots
        self._free_heap = list(range(1, total_slots + 1))
        heapq.heapify(self._free_heap)

    def has_free_slot(self) -> bool:
        return len(self._free_heap) > 0

    def free_count(self) -> int:
        return len(self._free_heap)

    def allocate(self):
        """Pop and return the nearest (smallest-numbered) free slot, or None."""
        if not self._free_heap:
            return None
        return heapq.heappop(self._free_heap)

    def release(self, slot_id: int) -> None:
        """Return a slot to the free pool once a vehicle exits and pays."""
        heapq.heappush(self._free_heap, slot_id)

    def rebuild_from(self, free_slot_ids) -> None:
        """Used on startup to reconstruct heap state from the database."""
        self._free_heap = list(free_slot_ids)
        heapq.heapify(self._free_heap)


class WaitingQueue:
    """FIFO queue for vehicles that arrive while the lot is full."""

    def __init__(self):
        self._queue = deque()

    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def enqueue(self, plate: str) -> int:
        """Add a plate to the back of the line; return its 1-based position."""
        self._queue.append(plate)
        return len(self._queue)

    def dequeue(self):
        """Remove and return the plate that has waited longest, or None."""
        if not self._queue:
            return None
        return self._queue.popleft()

    def contains(self, plate: str) -> bool:
        return plate in self._queue

    def remove(self, plate: str) -> bool:
        """Allow a waiting driver to leave the queue (e.g. gives up waiting)."""
        try:
            self._queue.remove(plate)
            return True
        except ValueError:
            return False

    def as_list(self):
        return list(self._queue)

    def __len__(self):
        return len(self._queue)
