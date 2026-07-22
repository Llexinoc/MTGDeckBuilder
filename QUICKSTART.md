# 🚀 Quick Start - ManaForge Deckbuilder

## The Fastest Way to Start

### **Option 1: Windows - Double-Click (Easiest)**
1. Open the `mtg-theme-deckbuilder` folder
2. **Double-click `START_APP.bat`**
3. A window will open and start the server
4. **Open your browser to: http://127.0.0.1:5000**
5. Done! The app is running

### **Option 2: Python Script**
1. Open a terminal in the `mtg-theme-deckbuilder` folder
2. Run: `python start_app.py`
3. **Open your browser to: http://127.0.0.1:5000**

### **Option 3: Manual Setup (if scripts don't work)**

#### First Time Only:
```bash
# Install dependencies
pip install -r requirements.txt

# Download the card database (this takes ~1-2 minutes)
python -m deckbuilder.carddata sync
```

#### Every Time You Want to Run:
```bash
# Start the server
python app.py
```

Then open: **http://127.0.0.1:5000**

---

## What Happens When You Run It

The startup script will:
1. ✓ Check if Python is installed
2. ✓ Install Flask, requests, and python-dotenv if needed
3. ✓ Download and sync the Magic card database (34,182 cards)
4. ✓ Start the Flask development server
5. ✓ Print the URL to visit

**Look for:**
```
Running on http://127.0.0.1:5000
```

Then open that URL in your browser.

---

## Troubleshooting

### "Python not found"
- Install Python 3.9+ from https://www.python.org/
- Make sure to check "Add Python to PATH" during installation

### "ModuleNotFoundError: No module named 'flask'"
Run: `pip install -r requirements.txt`

### "Card index not initialized"
Run: `python -m deckbuilder.carddata sync`
(This downloads the Scryfall database)

### Server won't start
1. Check if port 5000 is already in use
2. Try: `python app.py` manually to see the error

### App loads but says "Card index not found"
The database sync didn't complete. Run:
```bash
python -m deckbuilder.carddata sync
```

---

## What You Can Do in the App

Once it's running:

1. **Build a deck** - Type a theme like "Blue control" and click Build
2. **Choose format** - Commander (100 cards) or Standard (60 cards)
3. **Add reference cards** - Include cards you want in the deck
4. **See the reasoning** - Understand why each card was chosen
5. **Compare versions** - Build the same theme with different settings

---

## Environment Variables (Optional)

If you have an Anthropic API key, create a `.env` file in the root directory:

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-haiku-20241022
```

The app will still work without this — it just won't use LLM re-ranking.

---

## Stopping the Server

Press **Ctrl+C** in the terminal window to stop the server.

---

**That's it! Enjoy building themed decks! 🎉**
