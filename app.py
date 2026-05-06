from cache import get_cache, set_cache, hash_text

import os
import re
import json
import time
import anthropic

from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv

from claude_client import get_recommendation
from airtable_client import get_market_config

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")


EXPECTED_SKIN_KEYS = [
    "acne",
    "redness",
    "oiliness",
    "moisture",
    "radiance",
    "age_spots",
    "texture",
    "wrinkles",
    "dark_circles",
    "firmness",
]


def get_default_skin_scores():
    return {
        "acne": 75,
        "redness": 75,
        "oiliness": 75,
        "moisture": 75,
        "radiance": 75,
        "age_spots": 75,
        "texture": 75,
        "wrinkles": 75,
        "dark_circles": 75,
        "firmness": 75,
    }


def normalize_skin_scores(raw):
    """
    Claude returns concern severity:
    0 = no concern, 100 = severe concern.

    Recommendation engine expects health score:
    0 = poor, 100 = good.

    So we flip:
    health_score = 100 - concern_score
    """
    flipped = {}

    for key in EXPECTED_SKIN_KEYS:
        value = raw.get(key, 25)

        try:
            score = round(100 - float(value))
            score = max(0, min(100, score))
            flipped[key] = score
        except (TypeError, ValueError):
            flipped[key] = 75

    return flipped


def build_fallback_recommendation(skin_scores, market):
    sorted_concerns = sorted(skin_scores.items(), key=lambda item: item[1])
    weakest_concerns = [name for name, score in sorted_concerns[:3]]

    return {
        "market": market,
        "fallback": True,
        "message": (
            "We generated a fallback regimen because the AI recommendation "
            "service was temporarily unavailable."
        ),
        "top_concerns": weakest_concerns,
        "morning": [
            {
                "slot": "Cleanser",
                "product_name": "Gentle Cleanser",
                "sku": "FALLBACK-CLEANSER",
                "reason": "A gentle cleanser is a safe baseline step for most routines.",
                "rule_id": "fallback_rule_001",
            },
            {
                "slot": "Moisturizer",
                "product_name": "Daily Moisturizer",
                "sku": "FALLBACK-MOISTURIZER",
                "reason": "Moisturizer supports the skin barrier and hydration.",
                "rule_id": "fallback_rule_002",
            },
            {
                "slot": "SPF",
                "product_name": "Broad Spectrum SPF",
                "sku": "FALLBACK-SPF",
                "reason": "SPF is a standard daytime protection step.",
                "rule_id": "fallback_rule_003",
            },
        ],
        "night": [
            {
                "slot": "Cleanser",
                "product_name": "Gentle Cleanser",
                "sku": "FALLBACK-CLEANSER",
                "reason": "A gentle cleanser helps remove buildup from the day.",
                "rule_id": "fallback_rule_001",
            },
            {
                "slot": "Moisturizer",
                "product_name": "Night Moisturizer",
                "sku": "FALLBACK-NIGHT-MOISTURIZER",
                "reason": "A basic night moisturizer is used as a safe fallback routine.",
                "rule_id": "fallback_rule_004",
            },
        ],
        # Keep this empty so the UI does not imply Airtable rules were applied.
        "rules_applied": [],
        "fallback_rules_applied": [
            "fallback_rule_001",
            "fallback_rule_002",
            "fallback_rule_003",
            "fallback_rule_004",
        ],
        "reasoning": (
            "This fallback routine uses a conservative cleanser, moisturizer, and SPF structure. "
            "In production, this fallback would use approved market-specific baseline products "
            "from the product catalog."
        ),
    }


def normalize_recommendation_schema(recommendation):
    """
    Converts Claude's flexible output into the frontend schema:

    {
      "morning": [
        {
          "slot": "...",
          "product_name": "...",
          "sku": "...",
          "reason": "...",
          "rule_id": "..."
        }
      ],
      "night": [...],
      "reasoning": "...",
      "rules_applied": [...]
    }
    """

    if not isinstance(recommendation, dict):
        return recommendation

    container = recommendation

    for key in ["routine", "regimen", "recommendation", "recommendations"]:
        if isinstance(recommendation.get(key), dict):
            container = recommendation[key]
            break

    morning_raw = (
        container.get("morning")
        or container.get("Morning")
        or container.get("am")
        or container.get("AM")
        or container.get("day")
        or []
    )

    night_raw = (
        container.get("night")
        or container.get("Night")
        or container.get("pm")
        or container.get("PM")
        or container.get("evening")
        or []
    )

    def normalize_product(product):
        if not isinstance(product, dict):
            return None

        product_name = (
            product.get("product_name")
            or product.get("name")
            or product.get("product")
            or product.get("productName")
            or product.get("Product Name")
            or product.get("Product")
        )

        sku = (
            product.get("sku")
            or product.get("SKU")
            or product.get("sku_id")
            or product.get("product_sku")
            or product.get("productSku")
            or product.get("Product SKU")
        )

        rule_id = (
            product.get("rule_id")
            or product.get("rule")
            or product.get("ruleId")
            or product.get("rule_id_applied")
            or product.get("applied_rule")
            or product.get("appliedRule")
        )

        rule_ids = (
            product.get("rule_ids")
            or product.get("rules")
            or product.get("rules_applied")
        )

        if not rule_id and isinstance(rule_ids, list) and len(rule_ids) > 0:
            rule_id = rule_ids[0]

        reason = (
            product.get("reason")
            or product.get("reasoning")
            or product.get("rationale")
            or product.get("why")
            or product.get("explanation")
            or ""
        )

        slot = (
            product.get("slot")
            or product.get("step")
            or product.get("category")
            or product.get("product_type")
            or product.get("type")
            or "Product"
        )

        return {
            "slot": str(slot),
            "product_name": str(product_name) if product_name else "",
            "sku": str(sku) if sku else "",
            "reason": str(reason),
            "rule_id": str(rule_id) if rule_id else "",
        }

    morning = []
    for item in morning_raw:
        normalized = normalize_product(item)
        if normalized:
            morning.append(normalized)

    night = []
    for item in night_raw:
        normalized = normalize_product(item)
        if normalized:
            night.append(normalized)

    reasoning = (
        recommendation.get("reasoning")
        or recommendation.get("rationale")
        or recommendation.get("why_these_products")
        or recommendation.get("why")
        or recommendation.get("explanation")
        or container.get("reasoning")
        or container.get("rationale")
        or ""
    )

    rules_applied = (
        recommendation.get("rules_applied")
        or recommendation.get("rule_ids")
        or recommendation.get("rules")
        or container.get("rules_applied")
        or container.get("rule_ids")
        or []
    )

    if not isinstance(rules_applied, list):
        rules_applied = [rules_applied]

    for product in morning + night:
        rule_id = product.get("rule_id")
        if rule_id and rule_id not in rules_applied:
            rules_applied.append(rule_id)

    return {
        **recommendation,
        "morning": morning,
        "night": night,
        "reasoning": reasoning,
        "rules_applied": rules_applied,
    }


def is_valid_recommendation(recommendation):
    if not isinstance(recommendation, dict):
        print("[VALIDATION] Recommendation is not a dict")
        return False

    morning = recommendation.get("morning")
    night = recommendation.get("night")

    if not isinstance(morning, list):
        print("[VALIDATION] morning is missing or not a list")
        return False

    if not isinstance(night, list):
        print("[VALIDATION] night is missing or not a list")
        return False

    if len(morning) == 0 and len(night) == 0:
        print("[VALIDATION] both morning and night are empty")
        return False

    all_products = morning + night

    for index, product in enumerate(all_products):
        if not isinstance(product, dict):
            print(f"[VALIDATION] product {index} is not a dict")
            return False

        if not product.get("product_name"):
            print(f"[VALIDATION] product {index} missing product_name: {product}")
            return False

        if not product.get("sku"):
            print(f"[VALIDATION] product {index} missing sku: {product}")
            return False

        if not product.get("rule_id"):
            print(f"[VALIDATION] product {index} missing rule_id: {product}")
            return False

    return True


@app.route("/")
def index():
    start_time = time.time()

    try:
        markets = get_market_config()
        print(f"[OK] / loaded markets in {time.time() - start_time:.2f}s")
        return render_template("index.html", markets=markets)

    except Exception as e:
        print(f"[ERROR] / failed loading markets after {time.time() - start_time:.2f}s: {e}")

        fallback_markets = [
            {
                "Market": "US",
                "Name": "United States",
            }
        ]

        return render_template("index.html", markets=fallback_markets)


@app.route("/analyse-skin", methods=["POST"])
def analyse_skin():
    start_time = time.time()

    data = request.get_json() or {}

    image_b64 = data.get("image")
    media_type = data.get("media_type", "image/jpeg")

    if not image_b64:
        return jsonify({"error": "Missing image"}), 400

    image_cache_key = f"skin_analysis:{hash_text(image_b64)}"

    cached_result = get_cache(image_cache_key)
    if cached_result is not None:
        print(f"[CACHE HIT] /analyse-skin returned in {time.time() - start_time:.2f}s")
        return jsonify(cached_result)

    client = anthropic.Anthropic()

    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "You are a skincare analyst. Score each skin concern "
                                "0-100 where 0 = no concern at all, 100 = severe concern. "
                                "Return ONLY raw JSON, no markdown, no explanation:\n"
                                '{"acne":0,"redness":0,"oiliness":0,'
                                '"moisture":0,"radiance":0,"age_spots":0,'
                                '"texture":0,"wrinkles":0,"dark_circles":0,'
                                '"firmness":0}'
                            ),
                        },
                    ],
                }
            ],
        )

        text = message.content[0].text.strip()
        match = re.search(r"\{[\s\S]*\}", text)

        if not match:
            raise ValueError("Could not parse Claude response as JSON")

        raw = json.loads(match.group())
        flipped = normalize_skin_scores(raw)

        set_cache(image_cache_key, flipped)

        print(f"[CACHE MISS] /analyse-skin Claude call completed in {time.time() - start_time:.2f}s")

        return jsonify(flipped)

    except Exception as e:
        print(f"[FALLBACK] /analyse-skin failed after {time.time() - start_time:.2f}s: {e}")

        fallback_scores = get_default_skin_scores()

        set_cache(image_cache_key, fallback_scores)

        return jsonify(
            {
                **fallback_scores,
                "fallback": True,
                "message": "Skin analysis fallback used because AI vision analysis failed.",
            }
        )


@app.route("/recommend", methods=["POST"])
def recommend():
    start_time = time.time()

    data = request.get_json() or {}
    market = data.get("market", request.form.get("market", "US"))

    skin_scores = {
        "acne": float(data.get("acne", request.form.get("acne", 75))),
        "redness": float(data.get("redness", request.form.get("redness", 75))),
        "oiliness": float(data.get("oiliness", request.form.get("oiliness", 75))),
        "moisture": float(data.get("moisture", request.form.get("moisture", 75))),
        "radiance": float(data.get("radiance", request.form.get("radiance", 75))),
        "age_spots": float(data.get("age_spots", request.form.get("age_spots", 75))),
        "texture": float(data.get("texture", request.form.get("texture", 75))),
        "wrinkles": float(data.get("wrinkles", request.form.get("wrinkles", 75))),
        "dark_circles": float(data.get("dark_circles", request.form.get("dark_circles", 75))),
        "firmness": float(data.get("firmness", request.form.get("firmness", 75))),
    }

    recommendation_input = json.dumps(
        {
            "market": market,
            "skin_scores": skin_scores,
        },
        sort_keys=True,
    )

    recommendation_cache_key = f"recommendation:{hash_text(recommendation_input)}"

    # IMPORTANT:
    # Recommendation cache is temporarily disabled while debugging.
    # Otherwise, old fallback responses may keep appearing.
    #
    # cached_recommendation = get_cache(recommendation_cache_key)
    # if cached_recommendation is not None:
    #     print(f"[CACHE HIT] /recommend returned in {time.time() - start_time:.2f}s")
    #     return jsonify(cached_recommendation)

    try:
        recommendation = get_recommendation(skin_scores, market)

        print("[DEBUG] Raw recommendation from Claude:")
        print(json.dumps(recommendation, indent=2))

        recommendation = normalize_recommendation_schema(recommendation)

        print("[DEBUG] Normalized recommendation:")
        print(json.dumps(recommendation, indent=2))

        if not is_valid_recommendation(recommendation):
            print("[VALIDATION FAILED] Normalized recommendation was incomplete. Using fallback.")

            fallback_recommendation = build_fallback_recommendation(skin_scores, market)
            fallback_recommendation["debug_error"] = "Validation failed after schema normalization."

            # Do not cache fallback while debugging.
            return jsonify(fallback_recommendation)

        # Cache only valid real recommendations.
        set_cache(recommendation_cache_key, recommendation)

        print(f"[CACHE MISS] /recommend completed in {time.time() - start_time:.2f}s")

        return jsonify(recommendation)

    except Exception as e:
        print(f"[FALLBACK] /recommend failed after {time.time() - start_time:.2f}s: {e}")

        fallback_recommendation = build_fallback_recommendation(skin_scores, market)
        fallback_recommendation["debug_error"] = str(e)

        # Do not cache fallback while debugging.
        return jsonify(fallback_recommendation)


@app.route("/admin")
def admin():
    start_time = time.time()

    try:
        markets = get_market_config()
        print(f"[OK] /admin loaded in {time.time() - start_time:.2f}s")
        return render_template("admin.html", markets=markets)

    except Exception as e:
        print(f"[ERROR] /admin failed after {time.time() - start_time:.2f}s: {e}")

        fallback_markets = [
            {
                "Market": "US",
                "Name": "United States",
            }
        ]

        return render_template("admin.html", markets=fallback_markets)


@app.route("/health")
def health():
    start_time = time.time()

    try:
        markets = get_market_config()

        print(f"[OK] /health completed in {time.time() - start_time:.2f}s")

        return jsonify(
            {
                "status": "ok",
                "version": "1.0.0",
                "mcp": "enabled",
                "markets": len(markets),
            }
        )

    except Exception as e:
        print(f"[ERROR] /health failed after {time.time() - start_time:.2f}s: {e}")

        return jsonify(
            {
                "status": "degraded",
                "version": "1.0.0",
                "mcp": "enabled",
                "markets": 0,
                "error": str(e),
            }
        ), 200


@app.route("/debug")
def debug():
    start_time = time.time()

    try:
        from airtable_client import get_rules, get_products

        rules = get_rules(market="US")
        products = get_products(market="US")

        print(f"[OK] /debug completed in {time.time() - start_time:.2f}s")

        return jsonify(
            {
                "rules_count": len(rules),
                "products_count": len(products),
                "sample_rule": rules[0] if rules else None,
            }
        )

    except Exception as e:
        print(f"[ERROR] /debug failed after {time.time() - start_time:.2f}s: {e}")

        return jsonify(
            {
                "error": "Debug check failed",
                "details": str(e),
            }
        ), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)