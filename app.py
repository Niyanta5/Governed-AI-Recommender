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
    data       = request.get_json()
    image_b64  = data.get("image")
    media_type = data.get("media_type", "image/jpeg")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-opus-4-5",
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
                        "Return ONLY raw JSON, no markdown, no explanation:\n"
                        '{"acne":0,"redness":0,"oiliness":0,'
                        '"moisture":0,"radiance":0,"age_spots":0,'
                        '"texture":0,"wrinkles":0,"dark_circles":0,'
                        '"firmness":0}'
                    )
                }
            ]
        }]
    )

    text  = message.content[0].text.strip()
    match = re.search(r'\{[\s\S]*\}', text)
    raw   = json.loads(match.group()) if match else {}

    # Flip scores: vision returns low=good concern, but recommendation
    # engine expects high=good skin health. So 100 - concern = health score.
    flipped = {k: round(100 - float(v)) for k, v in raw.items()}
    return jsonify(flipped)


@app.route("/recommend", methods=["POST"])
def recommend():
    data   = request.get_json() or {}
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