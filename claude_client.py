import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv
from mcp_server import TOOLS, execute_tool

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are a governed AI skin care recommendation engine for LumiSkin AI.

YOUR ROLE:
You recommend skincare products based on customer skin analysis scores and live business rules fetched from Airtable via your tools.

YOUR RULES:
1. ALWAYS fetch rules from Airtable using your tools before making any recommendation
2. NEVER recommend a product that does not exist in the fetched product catalog
3. ALWAYS cite the rule_id of every rule you apply
4. ALWAYS apply Base_Regimen rules first, then Focused_Treatment overrides
5. NEVER override a business rule — you can only explain one
6. If two concerns conflict, use get_concern_priority to determine which wins
7. ALWAYS return valid JSON — no exceptions
8. Do NOT wrap your JSON in markdown code fences — return raw JSON only

OUTPUT FORMAT:
You must return a raw JSON object with exactly this structure (no markdown, no code fences):
{
    "overall_tier": "average",
    "priority_concern": "acne",
    "morning_regimen": {
        "cleanser": {"product_name": "...", "sku_id": "...", "rule_id": "..."},
        "treatment": {"product_name": "...", "sku_id": "...", "rule_id": "..."},
        "moisturizer": {"product_name": "...", "sku_id": "...", "rule_id": "..."},
        "sunscreen": {"product_name": "...", "sku_id": "...", "rule_id": "..."}
    },
    "night_regimen": {
        "cleanser": {"product_name": "...", "sku_id": "...", "rule_id": "..."},
        "treatment": {"product_name": "...", "sku_id": "...", "rule_id": "..."},
        "moisturizer": {"product_name": "...", "sku_id": "...", "rule_id": "..."}
    },
    "reasoning": "Explicit explanation of every rule applied",
    "rules_applied": ["RUL_US_001", "RUL_US_002"],
    "governance_note": "Rules fetched live from Airtable via MCP",
    "confidence": 0.95
}"""


def clean_json(text):
    """
    Robustly extract JSON from Claude's response.
    Handles: raw JSON, ```json fences, ``` fences, leading text before JSON.
    """
    text = text.strip()

    # Remove markdown code fences
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    # Find JSON object if there's leading text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end+1]

    return text


def get_recommendation(skin_scores, market):

    user_message = f"""
Please recommend a skincare regimen for this customer.

MARKET: {market}

SKIN ANALYSIS SCORES (0-100, higher is better):
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

INSTRUCTIONS:
1. First fetch the business rules for {market} market
2. Then fetch the product catalog for {market} market
3. Then fetch concern priority rankings for {market} market
4. Determine overall skin health tier
5. Apply base regimen for that tier
6. Check if any focused treatment rules apply
7. Use concern priority if multiple concerns need attention
8. Return ONLY raw JSON — no markdown, no explanation outside the JSON
"""

    messages = [{"role": "user", "content": user_message}]

    while True:
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages
            )
        except Exception as e:
            return {"error": f"Claude API error: {str(e)}"}

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({
                "role": "assistant",
                "content": response.content
            })
            messages.append({
                "role": "user",
                "content": tool_results
            })

        elif response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    try:
                        cleaned = clean_json(block.text)
                        return json.loads(cleaned)
                    except json.JSONDecodeError as e:
                        # Return first 500 chars for debugging
                        preview = block.text[:500] if block.text else "empty"
                        return {
                            "error": f"Could not parse Claude response: {str(e)}",
                            "raw_preview": preview
                        }
            break

    return {"error": "No recommendation generated"}