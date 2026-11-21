import os
import requests
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.environ["ODOO_URL"]
ODOO_DB = os.environ["ODOO_DB"]
API_KEY = os.environ["ODOO_API_KEY"]

endpoint = f"{ODOO_URL}/json/2/product.product/search_read"

headers = {
    "Authorization": f"bearer {API_KEY}",
    "X-Odoo-Database": ODOO_DB,
    "Content-Type": "application/json",
}

payload = {
    "domain": [],
    "fields": ["id", "name", "list_price"],
    "limit": 5,
}

response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
print("Status:", response.status_code)
print("Response:", response.json())
