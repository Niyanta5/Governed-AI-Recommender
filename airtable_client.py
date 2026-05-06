import os
import requests
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}"
}

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

  return [r["fields"] for r in records]

def get_products(market=None):
  products = fetch_table("Products")
  if market:
      products = [p for p in products 
                 if p.get("market") == market 
                 or p.get("market") == "ALL"]
  return [p for p in products 
          if p.get("status") == "Active"]


def get_rules(market=None):
  rules = fetch_table("Business_Rules")
  if market:
      rules = [r for r in rules 
              if r.get("market") == market 
              or r.get("market") == "ALL"]
  return [r for r in rules 
          if r.get("is_active") == True]


def get_concern_priority(market=None):
  priority = fetch_table("Concern_Priority")
  if market:
      priority = [p for p in priority 
                 if p.get("market") == market 
                 or p.get("market") == "ALL"]
  return priority


def get_market_config():
  markets = fetch_table("Market_Config")
  return [m for m in markets 
          if m.get("is_active") == True]