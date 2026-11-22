"""
Small client for talking to Odoo through its JSON-2 API.
Used by the sync script to find or create customers and to create orders.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ["ODOO_URL"]
HEADERS = {
    "Authorization": f"bearer {os.environ['ODOO_API_KEY']}",
    "X-Odoo-Database": os.environ["ODOO_DB"],
    "Content-Type": "application/json",
}


class OdooError(Exception):
    def __init__(self, status, payload):
        super().__init__(f"HTTP {status}: {payload}")
        self.status = status
        self.payload = payload


def call(model, method, **body):
    # Every Odoo request is a POST with a JSON body.
    response = requests.post(
        f"{BASE_URL}/json/2/{model}/{method}",
        json=body,
        headers=HEADERS,
        timeout=10,
    )
    if not response.ok:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        raise OdooError(response.status_code, payload)
    return response.json()


def find_or_create_partner(name):
    # Reuse the customer if one with this name already exists.
    found = call("res.partner", "search_read",
                 domain=[["name", "=", name]], fields=["id"], limit=1)
    if found:
        return found[0]["id"]
    return call("res.partner", "create", vals_list=[{"name": name}])[0]


def map_skus(skus):
    # Match our product codes to Odoo product ids.
    rows = call("product.product", "search_read",
                domain=[["default_code", "in", skus]],
                fields=["id", "default_code"])
    mapping = {row["default_code"]: row["id"] for row in rows}
    missing = [s for s in skus if s not in mapping]
    if missing:
        raise ValueError(f"Unknown product code: {missing}")
    return mapping


def create_order(order):
    """
    Returns the Odoo order id and whether we created it just now.
    If an order with the same external number is already in Odoo, we return
    that one instead of making a second copy.
    """
    existing = call("sale.order", "search_read",
                    domain=[["client_order_ref", "=", order["external_order_id"]]],
                    fields=["id"], limit=1)
    if existing:
        return existing[0]["id"], False

    partner_id = find_or_create_partner(order["customer_name"])
    mapping = map_skus([item["sku"] for item in order["items"]])
    lines = [
        [0, 0, {"product_id": mapping[item["sku"]],
                "product_uom_qty": item["quantity"]}]
        for item in order["items"]
    ]
    order_id = call("sale.order", "create", vals_list=[{
        "partner_id": partner_id,
        "client_order_ref": order["external_order_id"],
        "order_line": lines,
    }])[0]
    return order_id, True
