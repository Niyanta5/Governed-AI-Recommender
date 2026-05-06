import json
import os
from airtable_client import (
    get_products,
    get_rules,
    get_concern_priority,
    get_market_config
)

TOOLS = [
    {
        "name": "get_products",
        "description": "Fetch active products from the LumiSkin catalog for a specific market. Returns product names, SKUs, categories and skin concern tags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "Market code: US, UK, CA, AU, FR, DE, JP, BR, MX, SG, IN, AE"
                }
            },
            "required": ["market"]
        }
    },
    {
        "name": "get_rules",
        "description": "Fetch active business rules from Airtable for a specific market. Returns base regimen rules and focused treatment override rules with rule IDs for audit trail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "Market code: US, UK, CA, AU, FR, DE, JP, BR, MX, SG, IN, AE"
                }
            },
            "required": ["market"]
        }
    },
    {
        "name": "get_concern_priority",
        "description": "Fetch concern priority rankings for a market. Used to determine which skin concern takes precedence when multiple concerns need attention.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "Market code: US, UK, CA, AU, FR, DE, JP, BR, MX, SG, IN, AE"
                }
            },
            "required": ["market"]
        }
    },
    {
        "name": "get_market_config",
        "description": "Fetch all active markets and their configurations including currency.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

def execute_tool(tool_name, tool_input):
    if tool_name == "get_products":
        market = tool_input.get("market")
        data = get_products(market=market)
        return json.dumps(data)

    elif tool_name == "get_rules":
        market = tool_input.get("market")
        data = get_rules(market=market)
        return json.dumps(data)

    elif tool_name == "get_concern_priority":
        market = tool_input.get("market")
        data = get_concern_priority(market=market)
        return json.dumps(data)

    elif tool_name == "get_market_config":
        data = get_market_config()
        return json.dumps(data)

    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})