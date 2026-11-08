"""Mock Oracle ERP adapter (Order Management + Shipping Execution).

Everything here is simulated. The adapter keeps an integration log of the
messages a real Oracle interface would exchange (pick release in, ship
confirm out) so the demo can show the integration contract. Replacing this
module with a real Oracle REST/SOAP client is the production path.
"""
from __future__ import annotations

import random
from datetime import datetime

PRODUCTS = [
    {"code": "AP-60402", "name": "Window frame profile 60x40", "alloy": "6063", "temper": "T5",
     "finish": "Anodized Silver", "wrap": "film", "outdoor": False},
    {"code": "AP-12050", "name": "Curtain wall mullion 120x50", "alloy": "6063", "temper": "T6",
     "finish": "Powder coated RAL 9016", "wrap": "paper", "outdoor": False},
    {"code": "AP-40400", "name": "Square tube 40x40x2", "alloy": "6063", "temper": "T5",
     "finish": "Mill finish", "wrap": "bare", "outdoor": True},
    {"code": "AP-80800", "name": "Structural T-slot 80x80", "alloy": "6082", "temper": "T6",
     "finish": "Mill finish", "wrap": "bare", "outdoor": True},
    {"code": "AP-25015", "name": "Solar mounting rail 25x15", "alloy": "6005A", "temper": "T6",
     "finish": "Mill finish", "wrap": "bare", "outdoor": True},
    {"code": "AP-15060", "name": "Trailer side rail 150x60", "alloy": "6061", "temper": "T6",
     "finish": "Mill finish", "wrap": "bare", "outdoor": True},
    {"code": "AP-10030", "name": "Door leaf profile 100x30", "alloy": "6063", "temper": "T5",
     "finish": "Anodized Bronze", "wrap": "film", "outdoor": False},
    {"code": "AP-50025", "name": "Interior trim profile 50x25", "alloy": "6063", "temper": "T6",
     "finish": "Powder coated RAL 7016", "wrap": "kraft", "outdoor": False},
]
PRODUCT_BY_CODE = {p["code"]: p for p in PRODUCTS}

# Fictional customers for the demonstration.
CUSTOMERS = [
    {"id": "C1001", "name": "Gulf Facade Systems", "ship_to": "Jebel Ali, Dubai"},
    {"id": "C1002", "name": "Northline Windows", "ship_to": "Pune, Maharashtra"},
    {"id": "C1003", "name": "Apex Solar Structures", "ship_to": "Jodhpur, Rajasthan"},
    {"id": "C1004", "name": "Metro Rail Interiors", "ship_to": "Chennai, Tamil Nadu"},
    {"id": "C1005", "name": "Coastal Curtain Wall Co.", "ship_to": "Kochi, Kerala"},
    {"id": "C1006", "name": "TransLogix Trailers", "ship_to": "Hosur, Tamil Nadu"},
    {"id": "C1007", "name": "Skyline Doors & Partitions", "ship_to": "Gurugram, Haryana"},
]
CARRIERS = ["BlueLine Logistics", "Sundaram Freight", "Atlas Road Carriers", "Vega Transport"]


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


class MockOracle:
    """In-memory stand-in for Oracle Order Management."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.next_so = 45890
        self.log: list[dict] = []
        self._seq = 0

    def new_order_number(self) -> str:
        n = f"SO-{self.next_so}"
        self.next_so += 1
        return n

    def book_order(self, product: dict, qty: int, booked_at: datetime, customer: dict | None = None) -> dict:
        cust = customer or self.rng.choice(CUSTOMERS)
        return {
            "order_number": self.new_order_number(),
            "customer_id": cust["id"],
            "customer": cust["name"],
            "ship_to": cust["ship_to"],
            "carrier": self.rng.choice(CARRIERS),
            "status": "BOOKED",
            "priority": self.rng.choice(["STANDARD", "STANDARD", "EXPRESS"]),
            "booked_at": iso(booked_at),
            "lines": [{"line": 1, "product": product["code"], "description": product["name"],
                       "alloy": f"{product['alloy']}-{product['temper']}", "finish": product["finish"],
                       "qty_bundles": qty}],
            "bundles": [],
            "oracle_header_id": 880000 + self.rng.randint(1000, 9999),
        }

    def record(self, t: datetime, direction: str, interface: str, ref: str, payload: dict) -> dict:
        self._seq += 1
        msg = {"id": self._seq, "ts": iso(t), "direction": direction, "interface": interface, "ref": ref,
               "payload": payload, "status": "PROCESSED"}
        self.log.append(msg)
        self.log = self.log[-300:]
        return msg

    def pick_release_message(self, order: dict, t: datetime) -> dict:
        return self.record(t, "INBOUND", "OE_ORDER_PUB → Pick Release", order["order_number"], {
            "header_id": order["oracle_header_id"], "order_number": order["order_number"].split("-")[1],
            "sold_to": order["customer"], "ship_to": order["ship_to"], "carrier": order["carrier"],
            "release_status": "R", "lines": order["lines"],
        })

    def move_order_message(self, order: dict, bundle: dict, t: datetime, src: str, dst: str) -> dict:
        return self.record(t, "OUTBOUND", "INV Move Order Transaction", order["order_number"], {
            "lpn": bundle["barcode"], "epc": bundle["epc"], "from_locator": src, "to_locator": dst,
            "transaction_type": "Pick Confirm",
        })

    def ship_confirm_message(self, order: dict, manifest: dict, t: datetime) -> dict:
        return self.record(t, "OUTBOUND", "WSH Ship Confirm", order["order_number"], {
            "delivery_id": manifest["delivery_id"], "truck": manifest["truck_plate"], "carrier": order["carrier"],
            "lpns": manifest["expected_barcodes"], "rfid_validated": True, "gate": "GATE-01",
        })

    def exception_message(self, order: dict, manifest: dict, result: dict, t: datetime) -> dict:
        return self.record(t, "OUTBOUND", "WSH Delivery Hold", order["order_number"], {
            "delivery_id": manifest["delivery_id"], "hold_reason": "RFID_MISMATCH",
            "missing": result["missing"], "unexpected": result["unexpected"],
        })
