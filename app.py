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

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
except ImportError:
    def load_dotenv() -> None:  # noqa: F811
        pass

from flask import Flask, jsonify, render_template, request  # type: ignore[import-not-found]

# Load .env file before anything reads os.environ
load_dotenv()

from deckbuilder.engine import build_deck
from deckbuilder import carddata
from deckbuilder.scryfall import ScryfallUnavailable

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)
app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    index_status = carddata.get_index_status()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    llm_available = bool(api_key)
    
    return jsonify({
        "status": "ok",
        "llm": {
            "available": llm_available,
            "configured": llm_available,
            "api_key_set": llm_available,
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
        },
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
    bracket = data.get("bracket")  # 1-5, optional
    enforce_ban_list = data.get("enforce_ban_list", True)  # default True
    # Part 2: LLM Re-ranking parameters
    use_llm_reranking = data.get("use_llm_reranking", True)  # default enabled
    llm_model = data.get("llm_model")  # optional specific model
    
    if not description:
        return jsonify({"error": "Please enter a theme or description."}), 400
    if fmt not in ("commander", "standard"):
        fmt = "commander"
    
    # Validate bracket if provided
    if bracket is not None:
        try:
            bracket = int(bracket)
            if bracket not in (1, 2, 3, 4, 5):
                return jsonify({"error": "Bracket must be 1-5."}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Bracket must be an integer 1-5."}), 400
    
    # Check if card index is available when not in no_network mode
    if not no_network:
        index_status = carddata.get_index_status()
        if not index_status["exists"]:
            return jsonify({
                "error": "Card index not initialized. Run: python -m deckbuilder.carddata sync"
            }), 503
    
    try:
        deck = build_deck(description, fmt=fmt, no_network=no_network, use_llm=True,
                          deck_type_hint=deck_type_hint, references=references,
                          bracket=bracket, enforce_ban_list=enforce_ban_list,
                          use_llm_reranking=use_llm_reranking, llm_model=llm_model)
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
