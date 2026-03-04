import asyncio
import requests
import csv
from telegram import Bot
from datetime import datetime

# ==========================
# CONFIG
# ==========================

TELEGRAM_TOKEN = "8710147086:AAFYsYJ0K9ibKC57_WpIzGi7jR6EaYkhV18"
CHAT_ID = "6621233312"

API_FOOTBALL_KEY = "b4f5533d0331652750f2e7bc2a14d359"
ODDS_API_KEY = "efb6634f3177d56bb50599c1a7ba3e75"


BANKROLL = 100
RISK_PERCENT = 10

bot = Bot(token=TELEGRAM_TOKEN)

active_trades = {}
alerted_games = set()

# ==========================
# FUNÇÕES
# ==========================

def calculate_stake():
    return BANKROLL * (RISK_PERCENT / 100)

def calculate_score(shots, shots_on_target, dangerous_attacks):
    raw = (shots * 2) + (shots_on_target * 4) + (dangerous_attacks * 1.5)
    return round(min(raw / 5, 100), 2)

def calculate_ev(prob_model, odd):
    return round((prob_model * odd) - 1, 3)

def get_live_games():
    url = "https://v3.football.api-sports.io/fixtures?live=all"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    return requests.get(url, headers=headers).json().get("response", [])

def get_statistics(fixture_id):
    url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    data = requests.get(url, headers=headers).json().get("response", [])
    if not data:
        return None

    stats_home = data[0]["statistics"]
    stats_away = data[1]["statistics"]

    def get_stat(stats, name):
        for item in stats:
            if item["type"] == name:
                return item["value"] if item["value"] else 0
        return 0

    shots = get_stat(stats_home, "Total Shots") + get_stat(stats_away, "Total Shots")
    shots_on_target = get_stat(stats_home, "Shots on Goal") + get_stat(stats_away, "Shots on Goal")
    dangerous_attacks = get_stat(stats_home, "Dangerous Attacks") + get_stat(stats_away, "Dangerous Attacks")

    return shots, shots_on_target, dangerous_attacks

def get_over_odds():
    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?regions=eu&markets=totals&apiKey={ODDS_API_KEY}"
    data = requests.get(url).json()

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

def get_fixture_result(fixture_id):
    url = f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    data = requests.get(url, headers=headers).json().get("response", [])
    if not data:
        return None
    return data[0]["goals"]["home"], data[0]["goals"]["away"], data[0]["fixture"]["status"]["short"]

def save_result(row):
    with open("results_trader.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)

# ==========================

async def main_loop():
    while True:
        print("Analisando modelo completo...")

        games = get_live_games()
        odds_market = get_over_odds()

        for game in games:
            fixture_id = game["fixture"]["id"]
            minute = game["fixture"]["status"]["elapsed"]
            home = game["teams"]["home"]["name"]
            away = game["teams"]["away"]["name"]
            goals_home = game["goals"]["home"]
            goals_away = game["goals"]["away"]

            if not minute or fixture_id in alerted_games:
                continue

            stats = get_statistics(fixture_id)
            if not stats:
                continue

            shots, shots_on_target, dangerous_attacks = stats
            score = calculate_score(shots, shots_on_target, dangerous_attacks)

            match_key = f"{home} vs {away}"
            if match_key not in odds_market:
                continue

            odd = odds_market[match_key]
            prob_model = score / 100
            ev = calculate_ev(prob_model, odd)

            if score >= 65 and ev > 0.05:
                alerted_games.add(fixture_id)

                stake = calculate_stake()

                message = f"""
🔥 ENTRADA EV+ 🔥
{home} x {away}
Min: {minute}

Score: {score}
Odd: {odd}
EV: {ev}
Stake: R${stake}
"""
                await bot.send_message(chat_id=CHAT_ID, text=message)

                active_trades[fixture_id] = {
                    "home": home,
                    "away": away
                }

        # Verificar resultados finais
        for fixture_id in list(active_trades.keys()):
            result = get_fixture_result(fixture_id)
            if not result:
                continue

            goals_home, goals_away, status = result

            if status == "FT":
                total_goals = goals_home + goals_away
                outcome = "GREEN" if total_goals >= 2 else "RED"

                home = active_trades[fixture_id]["home"]
                away = active_trades[fixture_id]["away"]

                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=f"📊 RESULTADO\n{home} x {away}\n{outcome}"
                )

                save_result([
                    datetime.now(),
                    home,
                    away,
                    total_goals,
                    outcome
                ])

                del active_trades[fixture_id]

        await asyncio.sleep(180)

print("BOT MODELO COMPLETO ATIVO 🔥")
asyncio.run(main_loop())