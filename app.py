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
    """
    Fallback skin scores.
    75 means generally healthy/default state.
    This prevents the demo from failing if Claude Vision fails.
    """
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
    0 = no concern, 100 = severe concern

    Your recommendation engine expects skin health:
    0 = poor, 100 = good

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
    """
    Fallback recommendation if Claude recommendation generation fails.
    This keeps the demo usable and gives the interviewer confidence that
    you thought about failure modes.
    """

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
        "rules_applied": [
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


def is_valid_recommendation(recommendation):
    """
    Basic guardrail validation for Claude recommendation output.
    This prevents broken or incomplete responses from reaching the frontend.

    It checks that:
    - response is a dictionary
    - morning and night routines exist
    - at least one product exists
    - every product has a name, SKU, and rule_id
    """

    if not isinstance(recommendation, dict):
        return False

    morning = recommendation.get("morning")
    night = recommendation.get("night")

    if not isinstance(morning, list):
        return False

    if not isinstance(night, list):
        return False

    if len(morning) == 0 and len(night) == 0:
        return False

    all_products = morning + night

    for product in all_products:
        if not isinstance(product, dict):
            return False

        product_name = product.get("product_name") or product.get("name")
        sku = product.get("sku")
        rule_id = product.get("rule_id")

        if not product_name:
            return False

        if not sku:
            return False

        if not rule_id:
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

    cached_recommendation = get_cache(recommendation_cache_key)
    if cached_recommendation is not None:
        print(f"[CACHE HIT] /recommend returned in {time.time() - start_time:.2f}s")
        return jsonify(cached_recommendation)

    try:
        recommendation = get_recommendation(skin_scores, market)

        if not is_valid_recommendation(recommendation):
            print("[VALIDATION FAILED] Claude recommendation was incomplete. Using fallback.")
            recommendation = build_fallback_recommendation(skin_scores, market)

        set_cache(recommendation_cache_key, recommendation)

        print(f"[CACHE MISS] /recommend completed in {time.time() - start_time:.2f}s")

        return jsonify(recommendation)

    except Exception as e:
        print(f"[FALLBACK] /recommend failed after {time.time() - start_time:.2f}s: {e}")

        fallback_recommendation = build_fallback_recommendation(skin_scores, market)

        set_cache(recommendation_cache_key, fallback_recommendation)

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