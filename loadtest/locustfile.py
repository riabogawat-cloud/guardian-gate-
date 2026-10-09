"""Load test. Run the stack with RATE_LIMIT_ENABLED=false so you measure caching, not 429s.

Compare two runs:  CACHE_ENABLED=true   vs   CACHE_ENABLED=false
Then read median and p95 latency for GET /invoices/[id] in the Locust results.
"""
import random

from locust import HttpUser, between, task


class InvoiceUser(HttpUser):
    wait_time = between(0.1, 0.5)
    ids = []

    def on_start(self):
        # seed a few invoices once per simulated user
        for _ in range(3):
            num = f"LT-{random.randint(1, 10**9)}"
            r = self.client.post("/invoices", json={"invoice_number": num, "customer_name": "Load", "amount": "100.00"})
            if r.status_code == 201:
                InvoiceUser.ids.append(r.json()["id"])

    @task(8)
    def read_one(self):
        if InvoiceUser.ids:
            self.client.get(f"/invoices/{random.choice(InvoiceUser.ids)}", name="/invoices/[id]")

    @task(2)
    def read_list(self):
        self.client.get("/invoices?limit=10", name="/invoices")
