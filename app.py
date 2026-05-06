from cache import get_cache, set_cache, hash_text
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
    data = request.get_json() or {}

    image_b64 = data.get("image")
    media_type = data.get("media_type", "image/jpeg")

    if not image_b64:
        return jsonify({"error": "Missing image"}), 400

    # Cache key based on uploaded image content
    image_cache_key = f"skin_analysis:{hash_text(image_b64)}"

    # Return cached result if same image was analyzed recently
    cached_result = get_cache(image_cache_key)
    if cached_result is not None:
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
            return jsonify({"error": "Could not parse Claude response"}), 500

        raw = json.loads(match.group())

        # Claude returns concern severity:
        # 0 = no concern, 100 = severe concern
        #
        # Your recommendation engine expects skin health:
        # 0 = poor, 100 = good
        #
        # So we flip: health_score = 100 - concern_score
        flipped = {}

        for key, value in raw.items():
            try:
                score = round(100 - float(value))
                score = max(0, min(100, score))
                flipped[key] = score
            except (TypeError, ValueError):
                flipped[key] = 75

        # Ensure all 10 expected concerns exist
        expected_keys = [
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

        for key in expected_keys:
            flipped.setdefault(key, 75)

        # Save result in cache so same image does not call Claude again
        set_cache(image_cache_key, flipped)

        return jsonify(flipped)

    except Exception as e:
        return jsonify(
            {
                "error": "Skin analysis failed",
                "details": str(e),
            }
        ), 500


@app.route("/recommend", methods=["POST"])
def recommend():
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

    # Stable cache key based on market + skin scores
    recommendation_input = json.dumps(
        {
            "market": market,
            "skin_scores": skin_scores,
        },
        sort_keys=True,
    )

    recommendation_cache_key = f"recommendation:{hash_text(recommendation_input)}"

    # Return cached recommendation if same market + same scores were used recently
    cached_recommendation = get_cache(recommendation_cache_key)
    if cached_recommendation is not None:
        return jsonify(cached_recommendation)

    recommendation = get_recommendation(skin_scores, market)

    # Save recommendation so repeated tests do not call Claude again
    set_cache(recommendation_cache_key, recommendation)

    return jsonify(recommendation)


@app.route("/admin")
def admin():
    markets = get_market_config()
    return render_template("admin.html", markets=markets)


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "version": "1.0.0",
            "mcp": "enabled",
            "markets": len(get_market_config()),
        }
    )


@app.route("/debug")
def debug():
    from airtable_client import get_rules, get_products

    rules = get_rules(market="US")
    products = get_products(market="US")

    return jsonify(
        {
            "rules_count": len(rules),
            "products_count": len(products),
            "sample_rule": rules[0] if rules else None,
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)