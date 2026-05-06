import os
import json
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


@app.route("/recommend", methods=["POST"])
def recommend():
    market = request.form.get("market", "US")

    skin_scores = {
        "acne":         float(request.form.get("acne", 75)),
        "redness":      float(request.form.get("redness", 75)),
        "oiliness":     float(request.form.get("oiliness", 75)),
        "moisture":     float(request.form.get("moisture", 75)),
        "radiance":     float(request.form.get("radiance", 75)),
        "age_spots":    float(request.form.get("age_spots", 75)),
        "texture":      float(request.form.get("texture", 75)),
        "wrinkles":     float(request.form.get("wrinkles", 75)),
        "dark_circles": float(request.form.get("dark_circles", 75)),
        "firmness":     float(request.form.get("firmness", 75))
    }

    recommendation = get_recommendation(skin_scores, market)

    return render_template(
        "results.html",
        recommendation=recommendation,
        market=market,
        skin_scores=skin_scores
    )


@app.route("/admin")
def admin():
    markets = get_market_config()
    return render_template("admin.html", markets=markets)


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "1.0.0",
        "mcp": "enabled",
        "markets": len(get_market_config())
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)