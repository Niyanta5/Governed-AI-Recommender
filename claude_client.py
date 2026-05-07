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
- Acne/Blemishes:  {skin_scores.get('acne', 75)}
- Redness:         {skin_scores.get('redness', 75)}
- Oiliness:        {skin_scores.get('oiliness', 75)}
- Moisture:        {skin_scores.get('moisture', 75)}
- Radiance:        {skin_scores.get('radiance', 75)}
- Age Spots:       {skin_scores.get('age_spots', 75)}
- Texture:         {skin_scores.get('texture', 75)}
- Wrinkles:        {skin_scores.get('wrinkles', 75)}
- Dark Circles:    {skin_scores.get('dark_circles', 75)}
- Firmness:        {skin_scores.get('firmness', 75)}

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
