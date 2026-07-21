"""Flask web app for the MTG Theme Deckbuilder.

Run:
    pip install -r requirements.txt
    python -m deckbuilder.carddata sync    # Download the card index first
    python app.py
    # open http://127.0.0.1:5000

Endpoints:
    GET  /               -> the web interface
    POST /api/build      -> {description, format, offline} -> deck JSON
    GET  /api/health     -> liveness + whether an LLM key is configured
"""

from __future__ import annotations

import logging
import os
import traceback

from flask import Flask, jsonify, render_template, request

from deckbuilder.engine import build_deck
from deckbuilder import carddata
from deckbuilder.scryfall import ScryfallUnavailable

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    index_status = carddata.get_index_status()
    return jsonify({
        "status": "ok",
        "llm_enabled": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "card_index": {
            "exists": index_status["exists"],
            "card_count": index_status["card_count"],
            "updated_at": index_status["updated_at"],
        }
    })


@app.route("/api/build", methods=["POST"])
def build():
    data = request.get_json(force=True, silent=True) or {}
    description = (data.get("description") or "").strip()
    fmt = data.get("format", "commander")
    deck_type_hint = (data.get("deck_type_hint") or data.get("deck_type") or "").strip()
    # Support both 'offline' (deprecated) and 'no_network' parameter
    no_network = bool(data.get("no_network", False)) or bool(data.get("offline", False))
    references = data.get("references") or data.get("reference_cards") or []
    
    if not description:
        return jsonify({"error": "Please enter a theme or description."}), 400
    if fmt not in ("commander", "standard"):
        fmt = "commander"
    
    # Check if card index is available when not in no_network mode
    if not no_network:
        index_status = carddata.get_index_status()
        if not index_status["exists"]:
            return jsonify({
                "error": "Card index not initialized. Run: python -m deckbuilder.carddata sync"
            }), 503
    
    try:
        deck = build_deck(description, fmt=fmt, no_network=no_network, use_llm=True,
                          deck_type_hint=deck_type_hint, references=references)
        return jsonify(deck)
    except ScryfallUnavailable as exc:
        # Network error after retries -> 503 Service Unavailable
        logger.warning(f"Scryfall API unavailable: {exc}")
        return jsonify({
            "error": f"Scryfall API temporarily unavailable. Please try again in a moment.",
            "detail": str(exc)
        }), 503
    except Exception as exc:  # never crash the UI; report the problem
        traceback.print_exc()
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=True)
