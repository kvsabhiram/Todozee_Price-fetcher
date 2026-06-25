"""
India Gold & Silver Live Tracker — Production API
====================================================
Runs forever. Fetches 2x/day. Spike >5% → extra fetch.
Production WSGI server (Waitress) on port 5006.

pip install requests beautifulsoup4 flask waitress
python safe_price_fetcher.py
"""

import requests
from bs4 import BeautifulSoup
import json, time, random, re, os, threading
from collections import deque
from datetime import datetime
from flask import Flask, jsonify, request

# ─── SETTINGS ────────────────────────────────────
MORNING   = "09:30"
EVENING   = "18:30"
SPIKE_PCT = 5.0
CHECK_GAP = 3600
RATES_FILE = "rates.json"
API_PORT  = 5006
LOG_MAX   = 500          # max log lines kept in memory for /api/logs

# In-memory ring buffer of recent log lines (served by GET /api/logs)
LOG_BUFFER = deque(maxlen=LOG_MAX)

UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ─── HELPERS ─────────────────────────────────────
def load_rates():
    if os.path.exists(RATES_FILE):
        with open(RATES_FILE) as f: return json.load(f)
    return {"latest": {}, "history": []}

def save_rates(rates):
    with open(RATES_FILE, "w") as f:
        json.dump(rates, f, indent=2, ensure_ascii=False)

def http_get(url, timeout=15):
    time.sleep(random.uniform(2, 5))
    return requests.get(url, headers={
        "User-Agent": random.choice(UA),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Referer": "https://www.google.co.in/",
    }, timeout=timeout)

def chg(old, new):
    return round(((new - old) / old) * 100, 2) if old and old > 0 and new else 0

def now(): return datetime.now()
def ts():  return now().strftime("%Y-%m-%d %H:%M:%S")
def hm():  return now().strftime("%H:%M")
def td():  return now().strftime("%Y-%m-%d")
def log(msg):
    line = f"[{ts()}] {msg}"
    LOG_BUFFER.append(line)
    print(f"  [{now().strftime('%H:%M:%S')}] {msg}")


# ─── PARSERS ─────────────────────────────────────
def parse_gold(html_text):
    full_text = BeautifulSoup(html_text, "html.parser").get_text()
    gold_24k = gold_22k = None
    m = re.search(r'₹\s*([\d,]+)\s*per\s*gram\s*(?:for|of)\s*24\s*(?:karat|carat|K)', full_text, re.I)
    if m: gold_24k = float(m.group(1).replace(",", ""))
    m = re.search(r'₹\s*([\d,]+)\s*per\s*gram\s*(?:for|of)\s*22\s*(?:karat|carat|K)', full_text, re.I)
    if m: gold_22k = float(m.group(1).replace(",", ""))
    if not gold_24k:
        m = re.search(r'24\s*(?:karat|carat|K)\s*gold.*?₹\s*([\d,]+)', full_text, re.I)
        if m:
            v = float(m.group(1).replace(",", ""))
            if 4000 < v < 25000: gold_24k = v
    if not gold_22k:
        m = re.search(r'22\s*(?:karat|carat|K)\s*gold.*?₹\s*([\d,]+)', full_text, re.I)
        if m:
            v = float(m.group(1).replace(",", ""))
            if 4000 < v < 25000: gold_22k = v
    return {"gold_24k": gold_24k, "gold_22k": gold_22k}

def parse_silver(html_text):
    full_text = BeautifulSoup(html_text, "html.parser").get_text()
    m = re.search(r'₹\s*([\d,]+)\s*per\s*(?:gram|gm)', full_text, re.I)
    if m:
        v = float(m.group(1).replace(",", ""))
        if 30 < v < 1000: return {"silver": v}
    m = re.search(r'₹\s*([\d,]+)\s*per\s*(?:kg|kilo)', full_text, re.I)
    if m:
        v = float(m.group(1).replace(",", ""))
        if 50000 < v < 500000: return {"silver": round(v / 1000, 2)}
    return {}


# ─── FETCH FUNCTIONS ─────────────────────────────
def fetch_goodreturns():
    r = http_get("https://www.goodreturns.in/gold-rates/")
    r.raise_for_status()
    gold = parse_gold(r.text)
    time.sleep(random.uniform(5, 10))
    r = http_get("https://www.goodreturns.in/silver-rates/")
    r.raise_for_status()
    silver = parse_silver(r.text)
    if gold.get("gold_24k") or silver.get("silver"):
        return {"src": "goodreturns.in", **gold, **silver}
    raise Exception("No prices found")

def fetch_goldpriceindia():
    r = http_get("https://www.goldpriceindia.com/")
    r.raise_for_status()
    txt = BeautifulSoup(r.text, "html.parser").get_text()
    out = {}
    for k, key in [("24","gold_24k"),("22","gold_22k")]:
        m = re.search(rf'{k}\s*(?:karat|carat|K).*?₹\s*([\d,]+)', txt, re.I)
        if m:
            v = float(m.group(1).replace(",",""))
            out[key] = v if 4000<v<25000 else round(v/10,2) if 50000<v<200000 else None
    if out.get("gold_24k"): return {"src": "goldpriceindia.com", **out}
    raise Exception("No prices")

def fetch_bankbazaar():
    r = http_get("https://www.bankbazaar.com/gold-rate-india.html")
    r.raise_for_status()
    txt = BeautifulSoup(r.text, "html.parser").get_text()
    out = {}
    for k, key in [("24","gold_24k"),("22","gold_22k")]:
        m = re.search(rf'₹\s*([\d,]+)\s*per\s*gram\s*for\s*{k}', txt, re.I)
        if m: out[key] = float(m.group(1).replace(",",""))
    if out.get("gold_24k"): return {"src": "bankbazaar.com", **out}
    raise Exception("No prices")

def fetch_goldpricez():
    r = requests.get("https://goldpricez.com/api/rates/currency/inr/measure/gram", timeout=10)
    r.raise_for_status()
    d = r.json()
    g = d.get("gold",{}).get("price"); s = d.get("silver",{}).get("price")
    if g: return {"src": "goldpricez.com", "gold_24k": round(g,2), "gold_22k": round(g*.9167,2),
                  "silver": round(s,2) if s else None}
    raise Exception("No price")

BACKUPS = [
    ("goldpriceindia.com", fetch_goldpriceindia),
    ("bankbazaar.com",     fetch_bankbazaar),
    ("goldpricez.com API", fetch_goldpricez),
]

def fetch():
    try:
        log("Fetching goodreturns.in (India)...")
        return fetch_goodreturns()
    except Exception as e:
        log(f"goodreturns.in failed: {e}")
    for name, fn in BACKUPS:
        try:
            log(f"Trying: {name}...")
            r = fn()
            if r and r.get("gold_24k"):
                log(f"Got from {name}"); return r
        except Exception as e:
            log(f"{name} failed: {e}")
            time.sleep(random.uniform(2, 4))
    log("ALL sources failed!")
    return None


# ─── DISPLAY ─────────────────────────────────────
def show(d):
    g24 = d.get("gold_24k") or 0
    g22 = d.get("gold_22k") or 0
    sv  = d.get("silver") or 0
    print(f"\n  ╔══════════════════════════════════════════╗")
    print(f"  ║  💰 INDIA GOLD & SILVER                 ║")
    print(f"  ║  {d.get('time',''):39s} ║")
    print(f"  ║  {d.get('src','?'):39s} ║")
    print(f"  ╠══════════════════════════════════════════╣")
    print(f"  ║  24K Gold:  ₹ {g24:>10,.2f} /gram        ║")
    if g22:
        print(f"  ║  22K Gold:  ₹ {g22:>10,.2f} /gram        ║")
    print(f"  ║  Silver:    ₹ {sv*1000:>10,.2f} /kg         ║")
    print(f"  ╚══════════════════════════════════════════╝\n")


# ─── FETCH + SAVE ────────────────────────────────
def do_fetch(reason):
    data = fetch()
    if not data: return None
    record = {
        "time":     ts(),
        "reason":   reason,
        "src":      data.get("src"),
        "gold_24k": data.get("gold_24k"),
        "gold_22k": data.get("gold_22k"),
        "silver":   data.get("silver"),
    }
    rates = load_rates()
    rates["latest"] = record
    rates["history"].append(record)
    if len(rates["history"]) > 500:
        rates["history"] = rates["history"][-500:]
    save_rates(rates)
    show(record)
    log(f"Saved to {RATES_FILE} ({len(rates['history'])} records)")
    return record


# ─── SPIKE CHECK ─────────────────────────────────
def check_spike():
    old = load_rates().get("latest", {})
    if not old.get("gold_24k"): return False
    log("Spike check...")
    cur = fetch()
    if not cur: return False
    spike = False
    if cur.get("gold_24k") and old.get("gold_24k"):
        c = abs(chg(old["gold_24k"], cur["gold_24k"]))
        if c >= SPIKE_PCT:
            d = "UP" if cur["gold_24k"] > old["gold_24k"] else "DOWN"
            log(f"⚡ GOLD {d} {c:.1f}%!  ₹{old['gold_24k']:,.0f} → ₹{cur['gold_24k']:,.0f}")
            spike = True
        else:
            log(f"Gold {c:.1f}% — ok")
    if cur.get("silver") and old.get("silver"):
        c = abs(chg(old["silver"], cur["silver"]))
        if c >= SPIKE_PCT:
            d = "UP" if cur["silver"] > old["silver"] else "DOWN"
            log(f"⚡ SILVER {d} {c:.1f}%!  ₹{old['silver']:,.0f} → ₹{cur['silver']:,.0f}")
            spike = True
        else:
            log(f"Silver {c:.1f}% — ok")
    return spike


# ══════════════════════════════════════════════════
#  FLASK API — Production Ready
# ══════════════════════════════════════════════════

app = Flask(__name__)


# ─── ROOT — API info ─────────────────────────────
@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "service": "India Gold & Silver Rate API",
        "version": "1.0.0",
        "endpoints": {
            "GET /api/rates":         "Latest gold & silver rates",
            "GET /api/rates/gold":    "Gold rates only",
            "GET /api/rates/silver":  "Silver rate only",
            "GET /api/rates/history": "Last 30 fetched records",
            "GET /api/logs":          "Recent log lines (?limit=N)",
            "GET /api/health":        "Health check",
        }
    })


# ─── GET /api/rates — all latest rates ──────────
@app.route("/api/rates", methods=["GET"])
def get_rates():
    latest = load_rates().get("latest", {})
    if not latest.get("gold_24k"):
        return jsonify({"status": "error", "message": "No rates fetched yet. Please wait."}), 503

    silver_per_gram = latest.get("silver") or 0

    return jsonify({
        "status": "ok",
        "data": {
            "gold_24k": {
                "price": latest.get("gold_24k"),
                "unit":  "1 Gram"
            },
            "gold_22k": {
                "price": latest.get("gold_22k"),
                "unit":  "1 Gram"
            },
            "silver": {
                "price": round(silver_per_gram * 1000, 2),
                "unit":  "1 KG"
            },
            "last_updated": latest.get("time"),
            "source":       latest.get("src"),
        }
    })


# ─── GET /api/rates/gold ────────────────────────
@app.route("/api/rates/gold", methods=["GET"])
def get_gold():
    latest = load_rates().get("latest", {})
    if not latest.get("gold_24k"):
        return jsonify({"status": "error", "message": "No rates fetched yet."}), 503

    return jsonify({
        "status": "ok",
        "data": {
            "gold_24k": {
                "price": latest.get("gold_24k"),
                "unit":  "1 Gram"
            },
            "gold_22k": {
                "price": latest.get("gold_22k"),
                "unit":  "1 Gram"
            },
            "last_updated": latest.get("time"),
            "source":       latest.get("src"),
        }
    })


# ─── GET /api/rates/silver ──────────────────────
@app.route("/api/rates/silver", methods=["GET"])
def get_silver():
    latest = load_rates().get("latest", {})
    if not latest.get("silver"):
        return jsonify({"status": "error", "message": "No rates fetched yet."}), 503

    silver_per_gram = latest.get("silver") or 0

    return jsonify({
        "status": "ok",
        "data": {
            "silver": {
                "price": round(silver_per_gram * 1000, 2),
                "unit":  "1 KG"
            },
            "last_updated": latest.get("time"),
            "source":       latest.get("src"),
        }
    })


# ─── GET /api/rates/history ─────────────────────
@app.route("/api/rates/history", methods=["GET"])
def get_history():
    history = load_rates().get("history", [])
    return jsonify({
        "status": "ok",
        "count":  len(history),
        "data": [
            {
                "gold_24k":     {"price": r.get("gold_24k"), "unit": "1 Gram"},
                "gold_22k":     {"price": r.get("gold_22k"), "unit": "1 Gram"},
                "silver":       {"price": round((r.get("silver") or 0) * 1000, 2), "unit": "1 KG"},
                "time":         r.get("time"),
                "source":       r.get("src"),
                "reason":       r.get("reason"),
            }
            for r in history[-30:]
        ]
    })


# ─── GET /api/logs ──────────────────────────────
@app.route("/api/logs", methods=["GET"])
def get_logs():
    # ?limit=N to cap how many recent lines are returned (default: all kept)
    try:
        limit = int(request.args.get("limit", LOG_MAX))
    except (TypeError, ValueError):
        limit = LOG_MAX
    limit = max(1, min(limit, LOG_MAX))

    lines = list(LOG_BUFFER)[-limit:]
    return jsonify({
        "status": "ok",
        "count":  len(lines),
        "logs":   lines,
    })


# ─── GET /api/health ────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    latest = load_rates().get("latest", {})
    return jsonify({
        "status":       "ok",
        "service":      "gold-silver-tracker",
        "last_updated": latest.get("time"),
        "records":      len(load_rates().get("history", [])),
        "port":         API_PORT,
    })


# ─── 404 handler ─────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "status": "error",
        "message": "Endpoint not found",
        "available": {
            "GET /":                  "API info",
            "GET /api/rates":         "All rates",
            "GET /api/rates/gold":    "Gold only",
            "GET /api/rates/silver":  "Silver only",
            "GET /api/rates/history": "History",
            "GET /api/logs":          "Recent logs",
            "GET /api/health":        "Health",
        }
    }), 404


# ─── CORS — allow any frontend/backend to call ──
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ─── START PRODUCTION SERVER ─────────────────────
def start_api():
    try:
        from waitress import serve
        log(f"Production server (Waitress) on port {API_PORT}")
        serve(app, host="0.0.0.0", port=API_PORT, threads=4, _quiet=True)
    except ImportError:
        log(f"Waitress not found, using Flask dev server on port {API_PORT}")
        log(f"For production: pip install waitress")
        app.run(host="0.0.0.0", port=API_PORT, debug=False, use_reloader=False)


# ─── MAIN LOOP ───────────────────────────────────
def main():
    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │  🏅 INDIA GOLD & SILVER — PRODUCTION API    │")
    print("  │                                             │")
    print("  │  Fetches: 9:30 AM + 6:30 PM daily           │")
    print("  │  Spike >5% → extra fetch                    │")
    print("  │                                             │")
    print(f"  │  API: http://0.0.0.0:{API_PORT}                    │")
    print("  │                                             │")
    print("  │  GET /api/rates          → all rates        │")
    print("  │  GET /api/rates/gold     → gold only        │")
    print("  │  GET /api/rates/silver   → silver only      │")
    print("  │  GET /api/rates/history  → last 30 records  │")
    print("  │  GET /api/logs           → recent logs      │")
    print("  │  GET /api/health         → health check     │")
    print("  │                                             │")
    print("  │  Ctrl+C to stop                             │")
    print("  └─────────────────────────────────────────────┘")
    print()

    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    time.sleep(1)

    log("Starting up...")
    do_fetch("startup")

    done_m = done_e = None
    last_spike = now()

    try:
        while True:
            today, current = td(), hm()

            if current >= MORNING and current < "10:00" and done_m != today:
                log("⏰ Morning fetch")
                do_fetch("morning")
                done_m = today

            if current >= EVENING and current < "19:00" and done_e != today:
                log("⏰ Evening fetch")
                do_fetch("evening")
                done_e = today

            if (now() - last_spike).total_seconds() >= CHECK_GAP:
                if check_spike():
                    log("⚡ Spike! Updating...")
                    do_fetch("spike")
                last_spike = now()

            time.sleep(30)

    except KeyboardInterrupt:
        r = load_rates()
        print(f"\n\n  🛑 Stopped. {len(r.get('history',[]))} records in {RATES_FILE}\n")


if __name__ == "__main__":
    main()
