"""Run ONLY against the disposable HP Docker fixture on 127.0.0.1:18092.

Creates test accounts/transactions. Never point this at a real deployment.
Start compose with project smartspend-hp-test and HTTPS origin smartspend.test.
"""

import json
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = "http://127.0.0.1:18092"
ORIGIN = "https://smartspend.test"
PASSWORD = "Isolated-Test-Password-12345"


class Client:
    def __init__(self):
        self.cookie = ""
        self.user_id = ""

    def request(self, path, method="GET", payload=None, host="smartspend.test"):
        headers = {"Host": host, "Origin": ORIGIN}
        if self.cookie:
            headers["Cookie"] = self.cookie
        if self.user_id:
            headers["X-SmartSpend-User"] = self.user_id
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        request = Request(BASE + path, data=data, method=method, headers=headers)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            cookies = response.headers.get_all("Set-Cookie") or []
            if cookies:
                self.cookie = cookies[-1].split(";", 1)[0]
                assert "secure" in cookies[-1].lower()
            raw = response.read()
            body = (
                json.loads(raw)
                if "application/json" in response.headers.get("Content-Type", "")
                else raw
            )
            return response.status, body

    def login(self, username, register=False):
        action = "register" if register else "login"
        status, _ = self.request(
            "/api/auth/" + action,
            "POST",
            {"username": username, "password": PASSWORD},
        )
        assert status == 200, status
        status, body = self.request("/api/auth/status")
        assert status == 200
        self.user_id = body["user"]["id"]


def main():
    guest = Client()
    assert guest.request("/healthz")[0] == 200
    assert guest.request("/api/finance/categories")[0] == 401
    assert guest.request("/", host="wrong.test")[0] == 400
    assert guest.request("/")[0] == 200
    owner = Client()
    owner.login("chuso")
    alice, bob = Client(), Client()
    alice.login("alice_" + uuid4().hex[:10], register=True)
    bob.login("bob_" + uuid4().hex[:10], register=True)
    status, categories = alice.request("/api/finance/categories")
    assert status == 200
    payload = {
        "client_id": str(uuid4()),
        "title": "HP isolated smoke test",
        "amount": 35000,
        "spent_on": date.today().isoformat(),
        "category_id": categories[0]["id"],
    }
    status, transaction = alice.request("/api/finance/transactions", "POST", payload)
    assert status == 200, (status, transaction)
    path = "/api/finance/transactions/" + str(transaction["id"])
    assert alice.request(path)[0] == 200
    assert bob.request(path)[0] == 404
    assert bob.request(path, "DELETE")[0] == 404
    print(
        "Container smoke OK: health, Host, guest auth, secure cookie, owner login, private ledgers and cross-user write rejection."
    )


if __name__ == "__main__":
    main()
