import os
import requests
from dotenv import load_dotenv
from cache import get_cache, set_cache

load_dotenv()

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
HEADERS = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}

def fetch_table(table_name):
    url = f"{BASE_URL}/{table_name}"
    records = []
    params = {}
    while True:
        response = requests.get(url, headers=HEADERS, params=params)
        data = response.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset
    return records  # Return raw records — let callers extract fields

def get_products(market=None):
    cache_key = f"products:{market}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached
    records = fetch_table("Products")
    products = []
    for record in records:
        fields = record.get("fields", {})
        if fields.get("Status") != "Active":
            continue
        if fields.get("Market") not in [market, "ALL"]:
            continue
        products.append(fields)
    set_cache(cache_key, products)
    return products

def get_rules(market=None):
    cache_key = f"rules:{market}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached
    records = fetch_table("Business_Rules")
    rules = []
    for record in records:
        fields = record.get("fields", {})
        if fields.get("Active") is not True:
            continue
        if fields.get("Market") not in [market, "ALL"]:
            continue
        rules.append(fields)
    set_cache(cache_key, rules)
    return rules

def get_concern_priority(market=None):
    cache_key = f"concern_priority:{market}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached
    records = fetch_table("Concern_Priority")
    priorities = []
    for record in records:
        fields = record.get("fields", {})
        if fields.get("Market") not in [market, "ALL"]:
            continue
        priorities.append(fields)
    set_cache(cache_key, priorities)
    return priorities

def get_market_config():
    cache_key = "market_config"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached
    records = fetch_table("Market_Config")
    markets = [r.get("fields", {}) for r in records if r.get("fields", {}).get("is_active") == True]
    set_cache(cache_key, markets)
    return markets