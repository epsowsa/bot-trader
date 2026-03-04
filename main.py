import asyncio
import requests
import csv
from telegram import Bot
from datetime import datetime

# CONFIG

TELEGRAM_TOKEN = "8710147086:AAFYsYJ0K9ibKC57_WpIzGi7jR6EaYkhV18"
CHAT_ID = "6621233312"

API_FOOTBALL_KEY = "b4f5533d0331652750f2e7bc2a14d359"
ODDS_API_KEY = "efb6634f3177d56bb50599c1a7ba3e75"


BANKROLL = 100
RISK_PERCENT = 10

BOT_ATIVO = True
LAST_UPDATE_ID = None

bot = Bot(token=TELEGRAM_TOKEN)

active_trades = {}
alerted_games = set()

# ==========================

def calculate_stake():
    return BANKROLL * (RISK_PERCENT / 100)

def calculate_score(shots, shots_on_target, dangerous_attacks):
    raw = (shots * 2) + (shots_on_target * 4) + (dangerous_attacks * 1.5)
    return round(min(raw / 5, 100), 2)

def calculate_ev(prob_model, odd):
    return round((prob_model * odd) - 1, 3)

# ==========================
# TELEGRAM COMMANDS
# ==========================

async def check_commands():

    global BOT_ATIVO
    global LAST_UPDATE_ID

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"

    data = requests.get(url).json()

    if not data["result"]:
        return

    update = data["result"][-1]

    update_id = update["update_id"]

    if LAST_UPDATE_ID == update_id:
        return

    LAST_UPDATE_ID = update_id

    if "message" not in update:
        return

    message = update["message"].get("text","")

    if message == "/stopbot":

        BOT_ATIVO = False

        await bot.send_message(
            chat_id=CHAT_ID,
            text="⛔ BOT DESATIVADO"
        )

    elif message == "/startbot":

        BOT_ATIVO = True

        await bot.send_message(
            chat_id=CHAT_ID,
            text="✅ BOT ATIVADO"
        )

    elif message == "/status":

        status = "ATIVO 🟢" if BOT_ATIVO else "PARADO 🔴"

        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"📊 STATUS DO BOT\n\nBot está: {status}"
        )

# ==========================
# API
# ==========================

def get_live_games():

    url = "https://v3.football.api-sports.io/fixtures?live=all"

    headers = {"x-apisports-key": API_FOOTBALL_KEY}

    try:
        data = requests.get(url, headers=headers, timeout=10).json()
        return data.get("response", [])
    except:
        return []

def get_statistics(fixture_id):

    url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"

    headers = {"x-apisports-key": API_FOOTBALL_KEY}

    try:
        data = requests.get(url, headers=headers, timeout=10).json().get("response", [])
    except:
        return None

    if not data:
        return None

    stats_home = data[0]["statistics"]
    stats_away = data[1]["statistics"]

    def get_stat(stats, name):

        for item in stats:

            if item["type"] == name:
                return item["value"] if item["value"] else 0

        return 0

    shots = get_stat(stats_home,"Total Shots") + get_stat(stats_away,"Total Shots")
    shots_on_target = get_stat(stats_home,"Shots on Goal") + get_stat(stats_away,"Shots on Goal")
    dangerous_attacks = get_stat(stats_home,"Dangerous Attacks") + get_stat(stats_away,"Dangerous Attacks")

    return shots, shots_on_target, dangerous_attacks

# ==========================

def get_over_odds():

    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=eu&markets=totals&apiKey={ODDS_API_KEY}"

    try:
        data = requests.get(url, timeout=10).json()
    except:
        return {}

    odds_dict = {}

    for event in data:

        home = event["home_team"]
        away = event["away_team"]

        for bookmaker in event["bookmakers"]:

            if bookmaker["key"] == "bet365":

                for market in bookmaker["markets"]:

                    if market["key"] == "totals":

                        for outcome in market["outcomes"]:

                            if outcome["name"] == "Over" and outcome["point"] == 1.5:

                                odds_dict[f"{home} vs {away}"] = outcome["price"]

    return odds_dict

# ==========================

async def main_loop():

    await bot.send_message(chat_id=CHAT_ID,text="🚀 BOT EPSTRADER ONLINE")

    while True:

        await check_commands()

        if not BOT_ATIVO:

            print("Bot pausado...")
            await asyncio.sleep(30)
            continue

        print("Analisando jogos...")

        games = get_live_games()
        odds_market = get_over_odds()

        for game in games:

            fixture_id = game["fixture"]["id"]
            minute = game["fixture"]["status"]["elapsed"]

            home = game["teams"]["home"]["name"]
            away = game["teams"]["away"]["name"]

            if not minute or fixture_id in alerted_games:
                continue

            stats = get_statistics(fixture_id)

            if not stats:
                continue

            shots,shots_on_target,dangerous_attacks = stats

            score = calculate_score(shots,shots_on_target,dangerous_attacks)

            match_key = f"{home} vs {away}"

            if match_key not in odds_market:
                continue

            odd = odds_market[match_key]

            prob_model = score / 100

            ev = calculate_ev(prob_model,odd)

            if score >= 65 and ev > 0.05:

                alerted_games.add(fixture_id)

                stake = calculate_stake()

                message = f"""
🔥 ENTRADA EV+ 🔥
{home} x {away}

Minuto: {minute}

Score: {score}
Odd: {odd}
EV+: {ev}

Stake: R${stake}
"""

                await bot.send_message(chat_id=CHAT_ID,text=message)

        await asyncio.sleep(180)

# ==========================

asyncio.run(main_loop())