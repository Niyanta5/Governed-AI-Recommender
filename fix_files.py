"""
Run this once from your workspace root:
    python fix_files.py

It will overwrite app.py, airtable_client.py, and claude_client.py
with the correct versions, then print instructions to push.
"""

import os

# ── 1. app.py ────────────────────────────────────────────────────────────────

APP = '''\
import os
import re
import json
import anthropic
from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv
from claude_client import get_recommendation
from airtable_client import get_market_config

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")


@app.route("/")
def index():
    markets = get_market_config()
    return render_template("index.html", markets=markets)


@app.route("/analyse-skin", methods=["POST"])
def analyse_skin():
    data = request.get_json()
    image_b64 = data.get("image")
    media_type = data.get("media_type", "image/jpeg")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_b64,
                    }
                },
                {
                    "type": "text",
                    "text": (
                        "You are a skincare analyst. Score each skin concern "
                        "0-100 where 0 = no concern at all, 100 = severe concern. "
                        "Return ONLY raw JSON, no markdown, no explanation:\\n"
                        \'{"acne":0,"redness":0,"oiliness":0,\'
                        \'"moisture":0,"radiance":0,"age_spots":0,\'
                        \'"texture":0,"wrinkles":0,"dark_circles":0,\'
                        \'"firmness":0}\'
                    )
                }
            ]
        }]
    )

    text = message.content[0].text.strip()
    match = re.search(r\'\\{[\\s\\S]*\\}\', text)
    raw = json.loads(match.group()) if match else {}
    flipped = {k: round(100 - float(v)) for k, v in raw.items()}
    return jsonify(flipped)


@app.route("/recommend", methods=["POST"])
def recommend():
    data = request.get_json() or {}
    market = data.get("market", request.form.get("market", "US"))

    skin_scores = {
        "acne":         float(data.get("acne",         request.form.get("acne", 75))),
        "redness":      float(data.get("redness",      request.form.get("redness", 75))),
        "oiliness":     float(data.get("oiliness",     request.form.get("oiliness", 75))),
        "moisture":     float(data.get("moisture",     request.form.get("moisture", 75))),
        "radiance":     float(data.get("radiance",     request.form.get("radiance", 75))),
        "age_spots":    float(data.get("age_spots",    request.form.get("age_spots", 75))),
        "texture":      float(data.get("texture",      request.form.get("texture", 75))),
        "wrinkles":     float(data.get("wrinkles",     request.form.get("wrinkles", 75))),
        "dark_circles": float(data.get("dark_circles", request.form.get("dark_circles", 75))),
        "firmness":     float(data.get("firmness",     request.form.get("firmness", 75))),
    }

    recommendation = get_recommendation(skin_scores, market)
    return jsonify(recommendation)


@app.route("/admin")
def admin():
    markets = get_market_config()
    return render_template("admin.html", markets=markets)


@app.route("/health")
def health():
    return jsonify({
        "status":  "ok",
        "version": "1.0.0",
        "mcp":     "enabled",
        "markets": len(get_market_config())
    })


@app.route("/debug")
def debug():
    from airtable_client import get_rules, get_products
    rules    = get_rules(market="US")
    products = get_products(market="US")
    return jsonify({
        "rules_count":    len(rules),
        "products_count": len(products),
        "sample_rule":    rules[0] if rules else None,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
'''

# ── 2. airtable_client.py ────────────────────────────────────────────────────

AIRTABLE = '''\
import os
import requests
from dotenv import load_dotenv
from cache import get_cache, set_cache

load_dotenv()

AIRTABLE_TOKEN   = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
HEADERS  = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}


def fetch_table(table_name):
    url     = f"{BASE_URL}/{table_name}"
    records = []
    params  = {}
    while True:
        response = requests.get(url, headers=HEADERS, params=params)
        data     = response.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset
    return records


def get_products(market=None):
    cache_key = f"products:{market}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached
    records  = fetch_table("Products")
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
    rules   = []
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
    records    = fetch_table("Concern_Priority")
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
    markets = [
        r.get("fields", {}) for r in records
        if r.get("fields", {}).get("is_active") is True
    ]
    set_cache(cache_key, markets)
    return markets
'''

# ── 3. claude_client.py ──────────────────────────────────────────────────────

CLAUDE = '''\
import os
import json
import concurrent.futures
from anthropic import Anthropic
from dotenv import load_dotenv
from airtable_client import get_rules, get_products, get_concern_priority

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL  = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are a governed AI skin care recommendation engine for LumiSkin AI.

YOUR ROLE:
Recommend skincare products based on customer skin analysis scores and the business rules
provided to you in the user message. All Airtable data has already been fetched for you.

YOUR RULES:
1. NEVER recommend a product that does not exist in the provided product catalog
2. ALWAYS cite the rule_id of every rule you apply
3. ALWAYS apply Base_Regimen rules first, then Focused_Treatment overrides
4. NEVER override a business rule - you can only explain one
5. If two concerns conflict, use the concern priority table to determine which wins
6. ALWAYS return valid JSON - no exceptions
7. Do NOT wrap your JSON in markdown code fences - return raw JSON only

OUTPUT FORMAT:
Return a raw JSON object with exactly this structure (no markdown, no code fences):

{
  "overall_tier": "average",
  "priority_concern": "acne",
  "morning_regimen": {
    "cleanser":    {"product_name": "...", "sku_id": "...", "rule_id": "..."},
    "treatment":   {"product_name": "...", "sku_id": "...", "rule_id": "..."},
    "moisturizer": {"product_name": "...", "sku_id": "...", "rule_id": "..."},
    "sunscreen":   {"product_name": "...", "sku_id": "...", "rule_id": "..."}
  },
  "night_regimen": {
    "cleanser":    {"product_name": "...", "sku_id": "...", "rule_id": "..."},
    "treatment":   {"product_name": "...", "sku_id": "...", "rule_id": "..."},
    "moisturizer": {"product_name": "...", "sku_id": "...", "rule_id": "..."}
  },
  "reasoning": "Explicit explanation of every rule applied",
  "rules_applied": ["RUL_US_001", "RUL_US_002"],
  "governance_note": "Rules fetched live from Airtable",
  "confidence": 0.95
}"""


def fetch_all_airtable_data(market):
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_rules    = executor.submit(get_rules,            market)
        f_products = executor.submit(get_products,         market)
        f_priority = executor.submit(get_concern_priority, market)
        rules    = f_rules.result()
        products = f_products.result()
        priority = f_priority.result()
    return rules, products, priority


def clean_json(text):
    text = text.strip()
    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return text


def get_recommendation(skin_scores, market):
    rules, products, priority = fetch_all_airtable_data(market)

    user_message = f"""Please recommend a skincare regimen for this customer.

MARKET: {market}

SKIN ANALYSIS SCORES (0-100, higher = healthier):
- Acne/Blemishes:  {skin_scores.get(\'acne\', 75)}
- Redness:         {skin_scores.get(\'redness\', 75)}
- Oiliness:        {skin_scores.get(\'oiliness\', 75)}
- Moisture:        {skin_scores.get(\'moisture\', 75)}
- Radiance:        {skin_scores.get(\'radiance\', 75)}
- Age Spots:       {skin_scores.get(\'age_spots\', 75)}
- Texture:         {skin_scores.get(\'texture\', 75)}
- Wrinkles:        {skin_scores.get(\'wrinkles\', 75)}
- Dark Circles:    {skin_scores.get(\'dark_circles\', 75)}
- Firmness:        {skin_scores.get(\'firmness\', 75)}

BUSINESS RULES (fetched live from Airtable):
{json.dumps(rules, indent=2)}

PRODUCT CATALOG (fetched live from Airtable):
{json.dumps(products, indent=2)}

CONCERN PRIORITY TABLE (fetched live from Airtable):
{json.dumps(priority, indent=2)}

Return ONLY raw JSON - no markdown, no explanation outside the JSON.
"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
    except Exception as e:
        return {"error": f"Claude API error: {str(e)}"}

    for block in response.content:
        if hasattr(block, "text"):
            try:
                return json.loads(clean_json(block.text))
            except json.JSONDecodeError as e:
                return {"error": f"JSON parse error: {str(e)}", "raw": block.text[:500]}

    return {"error": "No response generated"}
'''

# ── Write all files ───────────────────────────────────────────────────────────

files = {
    "app.py":             APP,
    "airtable_client.py": AIRTABLE,
    "claude_client.py":   CLAUDE,
}

for filename, content in files.items():
    with open(filename, "w") as f:
        f.write(content)
    print(f"✓ wrote {filename}")

print("\nAll files written. Now run:")
print("  git add app.py airtable_client.py claude_client.py")
print('  git commit -m "fix: correct all three core files"')
print("  git push")