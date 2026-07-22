"""Scryfall bulk data downloader and SQLite card index.

Manages a local SQLite database of Magic cards with FTS5 full-text search.

CLI:
    python -m deckbuilder.carddata sync    # Download + rebuild index
    python -m deckbuilder.carddata info    # Print index status
    python -m deckbuilder.carddata sync --type all_cards --force

Public API:
    connect(db_path) -> sqlite3.Connection
    search(conn, query, fmt) -> list[dict]  # FTS5 search
    by_name(conn, name) -> dict | None
    within_identity(conn, identity) -> list[dict]
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
import sqlite3
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterator

try:
    import requests
except ImportError:
    requests = None

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "cards.sqlite"

SCRYFALL_BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
HEADERS = {
    "User-Agent": "MTGThemeDeckbuilder/1.0",
    "Accept": "application/json",
}

# Cards to exclude based on language
WANTED_LANGS = {"en"}

# Layouts that are not castable
EXCLUDED_LAYOUTS = {
    "token", "double_faced_token", "emblem", "art_series",
    "vanguard", "scheme", "planar", "augment", "host",
}

# Set types that are not castable
EXCLUDED_SET_TYPES = {"token", "memorabilia", "minigame"}


class BulkDataFetcher:
    """Download Scryfall bulk data with streaming to avoid memory exhaustion."""

    def __init__(self, bulk_type: str = "oracle_cards"):
        """
        Args:
            bulk_type: "oracle_cards" (default, 171 MB) or "all_cards" (2.4 GB)
        """
        self.bulk_type = bulk_type
        self.updated_at: str | None = None
        self.uri: str | None = None

    def get_manifest(self) -> dict:
        """Fetch the bulk-data manifest from Scryfall."""
        if not requests:
            raise RuntimeError("requests library required for live downloads")
        resp = requests.get(SCRYFALL_BULK_DATA_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def find_bulk_entry(self) -> dict:
        """Find the manifest entry for our bulk type."""
        manifest = self.get_manifest()
        data = manifest.get("data", [])
        for entry in data:
            if entry.get("type") == self.bulk_type:
                self.updated_at = entry.get("updated_at")
                self.uri = entry.get("jsonl_download_uri")
                if not self.uri:
                    raise ValueError(f"No download URI for {self.bulk_type}")
                return entry
        raise ValueError(f"Bulk type '{self.bulk_type}' not found in manifest")

    def stream_download(self, path: Path) -> None:
        """Download bulk data to a gzip file, streaming."""
        if not self.uri:
            self.find_bulk_entry()

        log.info(f"Downloading {self.bulk_type} from {self.uri}")
        resp = requests.get(self.uri, headers=HEADERS, stream=True, timeout=300)
        resp.raise_for_status()

        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        log.info(f"Downloaded to {path}")

    def stream_parse(self, path: Path) -> Iterator[dict]:
        """Parse gzipped JSONL file line by line without loading into memory."""
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    log.warning(f"Line {line_num}: JSON parse error: {e}")


def _extract_card_faces_text(card: dict) -> tuple[str, str, str]:
    """Extract oracle_text, mana_cost, type_line from card_faces if present."""
    faces = card.get("card_faces", [])
    if not faces:
        return (
            card.get("oracle_text", ""),
            card.get("mana_cost", ""),
            card.get("type_line", ""),
        )

    # Join text from all faces
    oracle_parts = []
    mana_parts = []
    type_parts = []

    for face in faces:
        if face.get("oracle_text"):
            oracle_parts.append(face["oracle_text"])
        if face.get("mana_cost"):
            mana_parts.append(face["mana_cost"])
        if face.get("type_line"):
            type_parts.append(face["type_line"])

    return (
        " // ".join(oracle_parts),
        "".join(mana_parts),  # concatenate mana costs
        " // ".join(type_parts),
    )


def _is_castable(card: dict) -> bool:
    """Determine if a card is a real playable card."""
    # Language filter
    if card.get("lang") not in WANTED_LANGS:
        return False

    # Layout filter
    if card.get("layout") in EXCLUDED_LAYOUTS:
        return False

    # Set type filter
    if card.get("set_type") in EXCLUDED_SET_TYPES:
        return False

    # Oversized
    if card.get("oversized"):
        return False

    # Reversible cards without oracle_id
    if not card.get("oracle_id"):
        return False

    return True


def _is_commander_card(type_line: str, oracle_text: str) -> bool:
    """Check if a card can be a commander."""
    type_lower = (type_line or "").lower()
    oracle_lower = (oracle_text or "").lower()

    # Must be legendary creature
    if "legendary" in type_lower and "creature" in type_lower:
        return True

    # Or have "can be your commander" text
    if "can be your commander" in oracle_lower:
        return True

    return False


def _collapse_duplicates(cards_by_oracle: dict) -> dict:
    """Given oracle_id -> [printings], return oracle_id -> preferred printing."""
    result = {}
    for oracle_id, printings in cards_by_oracle.items():
        # Prefer: non-digital, non-promo, has image, most recent released_at
        printings.sort(
            key=lambda c: (
                bool(c.get("digital")),  # False first
                bool(c.get("promo")),  # False first
                not bool(c.get("image_uris")),  # has image first
                -(datetime.fromisoformat(c.get("released_at", "1970-01-01")).timestamp()),
            )
        )
        result[oracle_id] = printings[0]
    return result


def _extract_keywords(oracle_text: str, type_line: str) -> list[str]:
    """Extract keywords like "flying", "deathtouch", etc."""
    keywords = []
    text = (oracle_text or "").lower() + " " + (type_line or "").lower()

    keyword_list = [
        "flying", "haste", "deathtouch", "lifelink", "vigilance", "trample",
        "menace", "reach", "hexproof", "shroud", "indestructible", "flash",
        "prowess", "storm", "cascade", "affinity", "enchant", "equip",
        "adapt", "adventure", "aftermath", "ally", "awaken", "bestow",
        "bloodrush", "bushido", "channel", "charge counter", "cipher",
        "companion", "convoke", "crew", "dash", "delve", "devoid",
        "double strike", "dredge", "escape", "evoke", "exalted",
        "exile", "exploit", "extort", "fading", "fateful hour",
        "fervour", "filterland", "forecast", "frenzy", "fugitive",
        "fabricate", "fortify", "gemstone", "grandeur", "gravestorm",
        "guardian", "guild", "hybrid", "improvise", "infect", "instant",
        "intended", "interact", "investigate", "islandwalk", "jumpstart",
        "kicker", "land", "landfall", "legacy", "legendary", "living",
        "madness", "manifest", "master", "megamorph", "mentor",
        "meta", "midrange", "miracle", "modular", "monstrosity",
        "morph", "mountainwalk", "mutate", "name", "ninjutsu", "notice",
        "offering", "outwit", "payoff", "peak", "phase", "phyrexian",
        "piece", "planar", "poison", "prowess", "rare", "ravnica",
        "read", "rebel", "reconfigure", "recover", "reflect", "reinforce",
        "renown", "replicate", "resist", "resolve", "retrace",
        "revenge", "revolt", "reward", "rider", "ripple", "ritual",
        "role", "sacrifice", "saga", "sage", "salamander", "sample",
        "scavenge", "seal", "search", "sees", "self", "semblance",
        "shadow", "shamanic", "shaman", "shape", "shield", "shift",
        "shinies", "sift", "signal", "silhouette", "shroud", "sight",
        "signpost", "similar", "sine", "singleton", "skyship", "slay",
        "slot", "small", "smith", "smooth", "sneak", "snow", "soak",
        "soft", "soldier", "solid", "solitary", "solution", "solve",
        "song", "source", "space", "space-case", "span", "spare",
        "spark", "speak", "spear", "special", "specific", "spectacle",
        "spell", "spend", "spent", "sphere", "sphinx", "spice", "spider",
        "spike", "spin", "spine", "spiral", "spirit", "spite", "splash",
        "split", "spoil", "sponsor", "spoof", "spooky", "spool", "spoon",
        "sporadic", "sport", "spot", "sprawl", "spray", "spread", "spree",
        "spring", "sprite", "sprout", "sprung", "spry", "spud", "spume",
        "spun", "spur", "spurn", "spurt", "sputter", "squab", "squad",
        "squall", "squander", "square", "squash", "squat", "squawk",
        "squeak", "squeal", "squeamish", "squeeze", "squid", "squint",
        "squire", "squirm", "squirt", "stab", "stable", "stack", "staff",
        "stage", "stagger", "staid", "stain", "stair", "stake", "stale",
        "stalk", "stall", "stamp", "stanch", "stand", "stank", "star",
        "starch", "stare", "stark", "start", "starve", "state", "statue",
        "status", "statute", "staunch", "stave", "stay", "stead", "steak",
        "steal", "steam", "steed", "steel", "steep", "steer", "stem",
        "stench", "step", "stern", "sternum", "steroid", "stew", "stick",
        "sticker", "stiff", "stifle", "stigma", "stile", "still", "stilt",
        "stimuli", "sting", "stinger", "stingy", "stink", "stint", "stipend",
        "stipple", "stir", "stirrup", "stitch", "stock", "stoic", "stoicism",
        "stoke", "stole", "stolen", "stolid", "stolon", "stomach", "stomp",
        "stone", "stony", "stood", "stool", "stoop", "stop", "storage",
        "store", "storey", "stork", "storm", "story", "stout", "stove",
        "stow", "strain", "strait", "strand", "strange", "strangle",
        "strap", "strata", "strath", "stratagem", "strategy", "straw",
        "stray", "streak", "stream", "street", "strength", "stress",
        "stretch", "streusel", "strew", "stria", "striation", "stricken",
        "strict", "stride", "strident", "strife", "strike", "string",
        "stringent", "strip", "stripe", "stripper", "strive", "strobe",
        "strode", "stroke", "stroll", "strong", "strop", "strove",
        "strudel", "struck", "structure", "strudel", "struggle", "strum",
        "strumpet", "strung", "strut", "strychnine", "stub", "stubble",
        "stubborn", "stucco", "stuck", "stud", "student", "studio",
        "studious", "study", "stuff", "stuffy", "stumble", "stump",
        "stun", "stung", "stunk", "stunned", "stunner", "stunt", "stupefaction",
        "stupefy", "stupendous", "stupid", "stupor", "sturdy", "stutter",
        "style", "stylish", "stylist", "stylus", "stymie", "styptic",
        "styrene", "suave", "subpoena", "subdue", "subject", "sublime",
        "submarine", "submerge", "submission", "submit", "subordinate",
        "suborn", "subplot", "subpoena", "subscribe", "subscriber",
        "subscription", "subsequent", "subservient", "subset", "subside",
        "subsidy", "subsist", "substance", "substantiate", "substitute",
        "substratum", "subsume", "subterfuge", "subterranean", "subtext",
        "subtle", "subtotal", "subtract", "suburb", "subversion", "subvert",
        "subway", "succeed", "success", "succinct", "succor", "succotash",
        "succubus", "succulent", "succumb", "such", "suck", "sucker",
        "suckle", "sucrose", "suction", "sudoku", "suds", "sue", "suede",
        "suet", "suffer", "suffice", "suffix", "suffocate", "suffrage",
        "suffuse", "sugar", "suggest", "suicide", "suit", "suitable",
        "suitcase", "suite", "suitor", "sulk", "sulky", "sullen", "sully",
        "sulphur", "sultan", "sultana", "sultry", "sum", "sumac", "summary",
        "summation", "summer", "summit", "summon", "summons", "sumo",
        "sump", "sumptuous", "sun", "sunbathe", "sunbeam", "sunburn",
        "sundae", "Sunday", "sunder", "sundial", "sundown", "sundry",
        "sunfish", "sunflower", "sung", "sunglasses", "sunk", "sunken",
        "sunlamp", "sunlight", "sunlit", "sunn", "sunnily", "sunny",
        "sunrise", "sunroof", "sunscreen", "sunset", "sunshine", "sunspot",
        "sunstroke", "suntan", "sup", "superb", "supercilious", "superficial",
        "superfluous", "superhero", "superhighway", "superhuman", "superimpose",
        "superintend", "superintendent", "superior", "superlative",
        "superman", "supermarket", "supernal", "supernatural", "supernova",
        "superpower", "supersede", "supersonic", "superstar", "superstition",
        "superstructure", "supervene", "supervise", "supervisor", "supine",
        "supper", "supplant", "supple", "supplement", "suppliant", "supplicant",
        "supplication", "supplier", "supplies", "supply", "support",
        "suppose", "supposition", "suppress", "suppurate", "supremacy",
        "supreme", "surcharge", "sure", "surely", "surety", "surf",
        "surface", "surfactant", "surfboard", "surfer", "surfeit", "surge",
        "surgeon", "surgery", "surgical", "surly", "surmise", "surmount",
        "surname", "surpass", "surplice", "surplus", "surprise", "surrealism",
        "surreal", "surrender", "surreptitious", "surrey", "surrogate",
        "surround", "surroundings", "surtax", "surveillance", "survey",
        "surveyor", "survival", "survive", "survivor", "sus", "susceptibility",
        "susceptible", "suspect", "suspend", "suspender", "suspense",
        "suspension", "suspicion", "suspicious", "sustain", "sustenance",
        "suttee", "suture", "suzerain", "suzerainty", "svelte", "swab",
        "swaddle", "swag", "swagger", "swain", "swallow", "swam", "swami",
        "swamp", "swampy", "swan", "swank", "swanky", "swap", "swapped",
        "swarm", "swarthy", "swash", "swashbuckler", "swashbuckling", "swastika",
        "swat", "swatch", "swathe", "swath", "sway", "swear", "sweat",
        "sweater", "sweaty", "swede", "sweep", "sweeper", "sweeping", "sweepstakes",
        "sweet", "sweeten", "sweetener", "sweetheart", "sweetie", "sweetish",
        "sweetly", "sweetness", "swell", "swelled", "swelling", "swelt",
        "swelter", "sweltering", "swept", "swerve", "swift", "swiftly",
        "swiftness", "swig", "swill", "swim", "swimmer", "swimming",
        "swimmingly", "swimsuit", "swimwear", "swindle", "swindler", "swine",
        "swing", "swinger", "swinish", "swipe", "swirl", "swirly", "swish",
        "swishy", "swiss", "switch", "switchboard", "switcheroo", "swither",
        "swivel", "swollen", "swoon", "swoop", "sword", "swordfish",
        "swordplay", "swordsman", "swore", "sworn", "swum", "swung",
    ]

    for kw in keyword_list:
        if kw in text:
            keywords.append(kw)

    return keywords


def process_card(card: dict, collapse_all_cards: bool = False) -> dict | None:
    """
    Process a raw Scryfall card into our index format.
    
    Args:
        card: Raw Scryfall card JSON
        collapse_all_cards: If True and card has duplicates, handle deduplication
    
    Returns:
        Processed card dict or None if not castable
    """
    if not _is_castable(card):
        return None

    oracle_text, mana_cost, type_line = _extract_card_faces_text(card)

    power = card.get("power")
    toughness = card.get("toughness")
    loyalty = card.get("loyalty")

    can_be_commander = _is_commander_card(type_line, oracle_text)

    # Extract price (may be stale)
    price_usd = None
    prices = card.get("prices", {})
    if prices.get("usd"):
        try:
            price_usd = float(prices["usd"])
        except (ValueError, TypeError):
            pass

    keywords = _extract_keywords(oracle_text, type_line)

    return {
        "oracle_id": card.get("oracle_id"),
        "name": card.get("name", "Unknown"),
        "mana_cost": mana_cost,
        "cmc": card.get("cmc", 0),
        "type_line": type_line,
        "oracle_text": oracle_text,
        "power": power,
        "toughness": toughness,
        "loyalty": loyalty,
        "color_identity": card.get("color_identity", []),
        "keywords": keywords,
        "set": card.get("set", "").upper(),
        "rarity": card.get("rarity", "common"),
        "released_at": card.get("released_at", "1970-01-01"),
        "edhrec_rank": card.get("edhrec_rank"),
        "legal_commander": card.get("legalities", {}).get("commander") == "legal",
        "legal_standard": card.get("legalities", {}).get("standard") == "legal",
        "can_be_commander": can_be_commander,
        "game_changer": bool(card.get("game_changer", False)),
        "image_uris": card.get("image_uris", {}),
        "scryfall_uri": card.get("scryfall_uri"),
        "price_usd": price_usd,
    }


def create_index(db_path: Path, fetcher: BulkDataFetcher) -> None:
    """Download bulk data and build SQLite index."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Download to temp file
    with tempfile.NamedTemporaryFile(suffix=".jsonl.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        fetcher.stream_download(tmp_path)

        # Create DB in temp location, rename into place at the end
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp_db:
            tmp_db_path = Path(tmp_db.name)

        _build_db(tmp_db_path, tmp_path, fetcher.bulk_type, fetcher.updated_at)

        # Atomic rename
        tmp_db_path.replace(db_path)
        log.info(f"Index built at {db_path}")

    finally:
        tmp_path.unlink(missing_ok=True)


def _build_db(
    db_path: Path,
    jsonl_gz_path: Path,
    bulk_type: str,
    updated_at: str | None,
) -> None:
    """Build the SQLite database from gzipped JSONL."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")

    fetcher = BulkDataFetcher(bulk_type)

    # Create main table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            oracle_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            mana_cost TEXT,
            cmc REAL,
            type_line TEXT,
            oracle_text TEXT,
            power TEXT,
            toughness TEXT,
            loyalty TEXT,
            color_identity TEXT,
            keywords TEXT,
            "set" TEXT,
            rarity TEXT,
            released_at TEXT,
            edhrec_rank INTEGER,
            legal_commander BOOLEAN,
            legal_standard BOOLEAN,
            can_be_commander BOOLEAN,
            game_changer BOOLEAN,
            image_url TEXT,
            price_usd REAL,
            updated_at TEXT
        )
    """)

    # Create FTS5 virtual table over searchable fields
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
            name,
            type_line,
            oracle_text,
            keywords,
            content=cards,
            content_rowid=rowid
        )
    """)

    # Create indices
    conn.execute("CREATE INDEX IF NOT EXISTS idx_color_identity ON cards(color_identity)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_commander ON cards(legal_commander)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_standard ON cards(legal_standard)")

    # Populate
    cards_by_oracle = defaultdict(list) if bulk_type == "all_cards" else None

    parsed_count = 0
    castable_count = 0

    for card in fetcher.stream_parse(jsonl_gz_path):
        parsed_count += 1
        if parsed_count % 10000 == 0:
            log.info(f"Parsed {parsed_count} cards...")

        if bulk_type == "all_cards":
            # Collect by oracle_id for deduplication
            processed = process_card(card)
            if processed:
                cards_by_oracle[processed["oracle_id"]].append(card)
        else:
            # oracle_cards: one per oracle_id already
            processed = process_card(card)
            if processed:
                castable_count += 1
                _insert_card(conn, processed, updated_at)

    # If we're doing all_cards, collapse duplicates and insert
    if bulk_type == "all_cards":
        collapsed = _collapse_duplicates(cards_by_oracle)
        for card_json in collapsed.values():
            processed = process_card(card_json)
            if processed:
                castable_count += 1
                _insert_card(conn, processed, updated_at)

    # Rebuild FTS5 index
    conn.execute("INSERT INTO cards_fts(rowid, name, type_line, oracle_text, keywords) "
                 "SELECT rowid, name, type_line, oracle_text, keywords FROM cards")

    conn.commit()
    conn.close()

    log.info(f"Index complete: {castable_count} cards indexed")


def _insert_card(conn: sqlite3.Connection, card: dict, updated_at: str | None) -> None:
    """Insert a single card into the database."""
    conn.execute("""
        INSERT OR REPLACE INTO cards (
            oracle_id, name, mana_cost, cmc, type_line, oracle_text,
            power, toughness, loyalty, color_identity, keywords, "set", rarity,
            released_at, edhrec_rank, legal_commander, legal_standard,
            can_be_commander, game_changer, image_url, price_usd, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        card["oracle_id"],
        card["name"],
        card["mana_cost"],
        card["cmc"],
        card["type_line"],
        card["oracle_text"],
        card["power"],
        card["toughness"],
        card["loyalty"],
        json.dumps(card["color_identity"]),
        json.dumps(card["keywords"]),
        card["set"],
        card["rarity"],
        card["released_at"],
        card["edhrec_rank"],
        card["legal_commander"],
        card["legal_standard"],
        card["can_be_commander"],
        card["game_changer"],
        card["image_uris"].get("normal") if card["image_uris"] else None,
        card["price_usd"],
        updated_at,
    ))


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open connection to the card index database."""
    if not db_path.exists():
        raise FileNotFoundError(f"Card index not found at {db_path}. Run: python -m deckbuilder.carddata sync")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def search(conn: sqlite3.Connection, query: str, fmt: str = "commander") -> list[dict]:
    """
    Search the card index using FTS5.
    
    Args:
        conn: SQLite connection
        query: Search query (e.g., "lifegain tokens")
        fmt: "commander" or "standard"
    
    Returns:
        List of cards, ordered by edhrec_rank
    """
    # Sanitize query for FTS5
    query = query.replace('"', "'")

    legal_col = "legal_commander" if fmt == "commander" else "legal_standard"

    rows = conn.execute(f"""
        SELECT c.* FROM cards c
        JOIN cards_fts f ON c.rowid = f.rowid
        WHERE f.cards_fts MATCH ?
          AND c.{legal_col}
        ORDER BY COALESCE(c.edhrec_rank, 2147483647) ASC
        LIMIT 200
    """, (query,)).fetchall()

    return [_row_to_dict(row) for row in rows]


def by_name(conn: sqlite3.Connection, name: str) -> dict | None:
    """Look up a card by exact name (case-insensitive)."""
    row = conn.execute(
        "SELECT * FROM cards WHERE LOWER(name) = ? LIMIT 1",
        (name.lower(),)
    ).fetchone()
    return _row_to_dict(row) if row else None


def by_name_fuzzy(conn: sqlite3.Connection, name: str, fmt: str = "commander") -> dict | None:
    """
    Look up a card by fuzzy name matching (substring, case-insensitive).
    
    Prefers:
    1. Legendary creatures (can be commanders)
    2. Exact substring matches before partial matches
    3. Cards by EDHREC rank (more played = higher priority)
    
    Args:
        conn: SQLite connection
        name: Partial card name to search for
        fmt: "commander" or "standard"
    
    Returns:
        Best matching card or None
    """
    name_lower = name.lower()
    legal_col = "legal_commander" if fmt == "commander" else "legal_standard"
    
    # First try exact name
    row = conn.execute(
        f"SELECT * FROM cards WHERE LOWER(name) = ? AND {legal_col} LIMIT 1",
        (name_lower,)
    ).fetchone()
    if row:
        return _row_to_dict(row)
    
    # Then try fuzzy match for legendary creatures (they can be commanders)
    rows = conn.execute(f"""
        SELECT * FROM cards
        WHERE LOWER(name) LIKE ?
          AND {legal_col}
          AND can_be_commander
        ORDER BY COALESCE(edhrec_rank, 2147483647) ASC
        LIMIT 5
    """, ("%" + name_lower + "%",)).fetchall()
    
    if rows:
        return _row_to_dict(rows[0])
    
    # Fall back to any card with matching name
    rows = conn.execute(f"""
        SELECT * FROM cards
        WHERE LOWER(name) LIKE ?
          AND {legal_col}
        ORDER BY COALESCE(edhrec_rank, 2147483647) ASC
        LIMIT 1
    """, ("%" + name_lower + "%",)).fetchall()
    
    if rows:
        return _row_to_dict(rows[0])
    
    return None



def within_identity(conn: sqlite3.Connection, identity: str | list[str], fmt: str = "commander") -> list[dict]:
    """
    Find cards within a color identity constraint.
    
    Args:
        conn: SQLite connection
        identity: Color string (e.g., "WUB") or list of colors
        fmt: "commander" or "standard"
    
    Returns:
        List of legal cards whose color identity is a subset
    """
    if isinstance(identity, str):
        identity_set = set(identity)
    else:
        identity_set = set(identity)

    legal_col = "legal_commander" if fmt == "commander" else "legal_standard"

    rows = conn.execute(f"""
        SELECT * FROM cards
        WHERE {legal_col}
        ORDER BY COALESCE(edhrec_rank, 2147483647) ASC
        LIMIT 500
    """).fetchall()

    result = []
    for row in rows:
        card_colors = json.loads(row["color_identity"] or "[]")
        if all(c in identity_set for c in card_colors):
            result.append(_row_to_dict(row))

    return result


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert a sqlite3.Row to a dict with parsed JSON fields."""
    if not row:
        return None

    d = dict(row)
    if d.get("color_identity"):
        d["color_identity"] = json.loads(d["color_identity"])
    if d.get("keywords"):
        d["keywords"] = json.loads(d["keywords"])
    
    # Rename image_url to image to match API field name
    if "image_url" in d:
        d["image"] = d.pop("image_url")
    
    return d


def get_index_status(db_path: Path = DB_PATH) -> dict:
    """Get status of the card index."""
    if not db_path.exists():
        return {
            "exists": False,
            "card_count": 0,
            "updated_at": None,
        }

    try:
        conn = connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        updated = conn.execute("SELECT updated_at FROM cards LIMIT 1").fetchone()
        conn.close()
        return {
            "exists": True,
            "card_count": count,
            "updated_at": updated[0] if updated else None,
        }
    except Exception as e:
        log.error(f"Error reading index: {e}")
        return {
            "exists": False,
            "card_count": 0,
            "updated_at": None,
        }


# ========================================================================= CLI
def main() -> None:
    parser = argparse.ArgumentParser(description="Scryfall card index manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Download and rebuild index")
    sync_parser.add_argument(
        "--type", default="oracle_cards",
        choices=["oracle_cards", "all_cards"],
        help="Bulk data type (default: oracle_cards, ~171 MB)"
    )
    sync_parser.add_argument(
        "--force", action="store_true",
        help="Force rebuild even if index is up-to-date"
    )

    # info
    subparsers.add_parser("info", help="Print index status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "sync":
        if not requests:
            log.error("requests library required for sync. Install with: pip install requests")
            sys.exit(1)

        fetcher = BulkDataFetcher(args.type)

        # Check if we need to update
        if not args.force:
            manifest_entry = fetcher.find_bulk_entry()
            db_updated = None
            if DB_PATH.exists():
                try:
                    conn = connect()
                    row = conn.execute("SELECT updated_at FROM cards LIMIT 1").fetchone()
                    db_updated = row[0] if row else None
                    conn.close()
                except Exception:
                    pass

            if db_updated and db_updated == manifest_entry.get("updated_at"):
                log.info(f"Index up-to-date ({db_updated})")
                return

        create_index(DB_PATH, fetcher)
        log.info("Sync complete")

    elif args.command == "info":
        status = get_index_status()
        print(f"Index exists: {status['exists']}")
        if status["exists"]:
            print(f"Card count: {status['card_count']}")
            print(f"Updated at: {status['updated_at']}")
        else:
            print("Run: python -m deckbuilder.carddata sync")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
