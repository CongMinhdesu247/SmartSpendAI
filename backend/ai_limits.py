"""Bounded in-process AI admission control for the single-worker deployment."""

import threading
import time
from collections import OrderedDict, deque

from fastapi import HTTPException, Request


class AILimiter:
    def __init__(self, per_minute=10, concurrent=2):
        self.per_minute = per_minute
        self.slots = threading.BoundedSemaphore(concurrent)
        self.clients = OrderedDict()
        self.lock = threading.Lock()

    def acquire(self, user_id):
        now = time.monotonic()
        with self.lock:
            attempts = self.clients.setdefault(user_id, deque())
            self.clients.move_to_end(user_id)
            while attempts and now - attempts[0] >= 60:
                attempts.popleft()
            while len(self.clients) > 4096:
                self.clients.popitem(last=False)
            if len(attempts) >= self.per_minute:
                raise HTTPException(
                    429,
                    "Bạn đã gọi AI nhiều lần. Hãy đợi một phút rồi thử lại.",
                    headers={"Retry-After": "60"},
                )
            if not self.slots.acquire(blocking=False):
                raise HTTPException(
                    429, "AI đang bận. Hãy thử lại sau ít giây.", headers={"Retry-After": "5"}
                )
            attempts.append(now)


limiter = AILimiter()


def ai_slot(request: Request):
    user_id = getattr(request.state, "user", None)
    limiter.acquire(user_id["id"] if user_id else "legacy-owner")
    try:
        yield
    finally:
        limiter.slots.release()
