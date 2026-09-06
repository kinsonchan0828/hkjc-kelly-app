import io
import re
import csv
import requests
import numpy as np
import pandas as pd
import streamlit as st

# ==========================================
# 1. PAGE CONFIGURATION & TRACK STRATEGY MAP
# ==========================================
st.set_page_config(
    page_title="HKJC Kelly & Quinella Terminal",
    page_icon="🏇",
    layout="wide"
)

TRACK_STRATEGY_MAP = {
    # Sha Tin Course A
    "SH A 1000": "Quin", "SH A 1200": "Quin", "SH A 1400": "Quin", "SH A 2000": "Quin",
    "SH A 1600": "Standard", "SH A 1800": "Win only",
    # Sha Tin Course A+3
    "SH A+3 1000": "Quin", "SH A+3 1200": "Quin", "SH A+3 1400": "Quin", "SH A+3 1600": "Quin",
    "SH A+3 1800": "Win only", "SH A+3 2000": "Win only",
    # Sha Tin Course B
    "SH B 1000": "Standard", "SH B 1600": "Standard", "SH B 1200": "Quin",
    "SH B 1400": "Win only", "SH B 1800": "Win only", "SH B 2000": "Win only",
    # Sha Tin Course B+2
    "SH B+2 1000": "Win only", "SH B+2 1600": "Win only", "SH B+2 1800": "Win only",
    "SH B+2 1200": "Quin", "SH B+2 1400": "Quin", "SH B+2 2000": "Quin",
    # Sha Tin Course C
    "SH C 1000": "Win only", "SH C 1200": "Win only", "SH C 1800": "Win only",
    "SH C 1400": "Standard", "SH C 1600": "Quin",
    # Sha Tin Course C+3
    "SH C+3 1000": "Standard", "SH C+3 1400": "Standard", "SH C+3 1600": "Standard",
    "SH C+3 1200": "Quin", "SH C+3 1800": "Win only",
    # Happy Valley Course A
    "HV A 1000": "Quin", "HV A 1200": "Win only",
    "HV A 1650": "Standard", "HV A 1800": "Standard", "HV A 2200": "Standard",
    # Happy Valley Course B
    "HV B 1000": "Standard", "HV B 1200": "Win only", "HV B 1650": "Win only",
    "HV B 1800": "Win only", "HV B 2200": "Quin",
    # Happy Valley Course C
    "HV C 1000": "Win only", "HV C 1650": "Win only",
    "HV C 1200": "Standard", "HV C 1800": "Standard", "HV C 2200": "Quin",
    # Happy Valley Course C+3
    "HV C+3 1000": "Win only", "HV C+3 1200": "Win only", "HV C+3 1650": "Win only",
    "HV C+3 1800": "Win only", "HV C+3 2200": "Win only",
    # All Weather / Dirt / Mud
    "Mud 1200": "Standard", "Mud 1800": "Standard", "Mud 1650": "Win only"
}

# ==========================================
# 2. GOOGLE SHEET / CSV MULTI-RACE PARSER
# ==========================================
def parse_multi_race_sheet(df_raw):
    """Parses multi-race data stacked vertically in a 3-column CSV/Sheet format."""
    races = []
    current_race = None

    for _, row in df_raw.iterrows():
        col0 = str(row[0]).strip() if pd.notna(row[0]) else ""
        col1 = str(row[1]).strip() if pd.notna(row[1]) else ""
        col2 = str(row[2]).strip() if pd.notna(row[2]) else ""

        if not col0 and not col1:
            continue

        try:
            horse_no = int(float(col0))
            if current_race is not None and col1:
                def clean_prob(val):
                    s = str(val).replace('%', '').strip()
                    try:
                        num = float(s)
                        return num / 100.0 if num > 1.0 else num
                    except ValueError:
                        return 0.0

                current_race['horses'].append({
                    'no': horse_no,
                    'name': col1,
                    'win_prob': clean_prob(col2)
                })
        except ValueError:
            # Row is a race header (e.g. "R1", "SH A 1200", "Win %")
            if col1 and not col0.lower().startswith("horse"):
                current_race = {
                    'title': col0 if col0 else f"Race {len(races)+1}",
                    'track': col1,
                    'horses': []
                }
                races.append(current_race)

    return [r for r in races if len(r['horses']) > 0]

# ==========================================
# 3. LIVE HKJC ODDS FETCHER (SESSION ENABLED)
# ==========================================
def fetch_hkjc_live_odds(race_no_str):
    """Fetches real-time HKJC Win tote odds using session cookies and browser headers."""
    race_digit = ''.join(filter(str.isdigit, str(race_no_str))) or "1"
    
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://bet.hkjc.com/racing/pages/odds_wp.aspx?lang=en",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    try:
        # Establish session cookies with HKJC
        session.get("https://bet.hkjc.com/racing/pages/odds_wp.aspx?lang=en", headers=headers, timeout=5)
        
        # Fetch live odds JSON
        url = f"https://bet.hkjc.com/racing/script/json/win_odds.aspx?lang=en&date=latest&raceno={race_digit}"
        res = session.get(url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            odds_dict = {}
            if "out" in data and "odds" in data["out"]:
                for item in data["out"]["odds"]:
                    h_num = int(item.get("no", 0))
                    h_win = float(item.get("win", 0.0))
                    if h_num > 0 and h_win > 0:
                        odds_dict[h_num] = h_win
                return odds_dict
    except Exception:
        pass
    return {}

# ==========================================
# 4. MATH ENGINE & BET CALCULATOR
# ==========================================
def calculate_harville_quinella(p_a, p_b):
    """Calculates Harville joint Quinella probability for horses A and B."""
    p_a_then_b = p_a * (p_b / max(1.0 - p_a, 1e-6))
    p_b_then_a = p_b * (p_a / max(1.0 - p_b, 1e-6))
    return p_a_then_b + p_b_then_a

def calculate_quarter_kelly(p, odds, bankroll, min_ev=0.05, kelly_frac=0.25):
    """Calculates Quarter-Kelly stake with a minimum EV filter (+5%)."""
    ev = (p * odds) - 1.0
    if ev < min_ev or odds <= 1.0:
        return 0.0, ev
    raw_kelly = ev / (odds - 1.0)
    stake = bankroll * kelly_frac * raw_kelly
    return stake, ev

def round_to_hkd_10(amount):
    """Rounds stakes to nearest HK$10 unit."""
    return int(round(amount / 10.0) * 10)

def evaluate_bets(horses, track_code, bankroll, manual_quin_odds=None):
    """Applies strategy matrix, Harville formula, Kelly sizing, and bankroll capping."""
    strategy = TRACK_STRATEGY_MAP.get(track_code.strip(), "Standard")
    
    # Track Cap: 5% max outlay per race
    race_bankroll_cap = bankroll * 0.05
    raw_bets = []

    # Process Win Bets
    win_bets = []
    for h in horses:
        p = h['win_prob']
        o = h['live_odds']
        stake, ev = calculate_quarter_kelly(p, o, bankroll)
        if stake > 0:
            win_bets.append({
                'type': 'WIN',
                'selection': f"#{h['no']} {h['name']}",
                'horse_nos': {h['no']},
                'prob': p,
                'odds': o,
                'ev': ev,
                'raw_stake': stake
            })

    # Process Quinella Bets
    quin_bets = []
    if strategy in ["Quin", "Standard"]:
        n = len(horses)
        for i in range(n):
            for j in range(i + 1, n):
                h1, h2 = horses[i], horses[j]
                p_q = calculate_harville_quinella(h1['win_prob'], h2['win_prob'])
                
                # Use manually supplied Quinella odds or fallback estimation
                q_pair_key = tuple(sorted([h1['no'], h2['no']]))
                if manual_quin_odds and q_pair_key in manual_quin_odds:
                    o_q = manual_quin_odds[q_pair_key]
                else:
                    o_q = (h1['live_odds'] * h2['live_odds']) * 0.42

                stake_q, ev_q = calculate_quarter_kelly(p_q, o_q, bankroll)
                if stake_q > 0:
                    quin_bets.append({
                        'type': 'QUINELLA',
                        'selection': f"#{h1['no']} & #{h2['no']} ({h1['name']} / {h2['name']})",
                        'horse_nos': {h1['no'], h2['no']},
                        'prob': p_q,
                        'odds': o_q,
                        'ev': ev_q,
                        'raw_stake': stake_q
                    })

    # Execute Strategy Allocation Rules
    if strategy == "Quin":
        if quin_bets:
            raw_bets.extend(quin_bets)
            # Uncovered Win Bets fallback for +EV horses not in Quinella pairs
            quin_horses = set().union(*[q['horse_nos'] for q in quin_bets])
            for w in win_bets:
                if not w['horse_nos'].issubset(quin_horses):
                    raw_bets.append(w)
        else:
            # Fallback to Win bets if no Quinella meets +5% EV
            raw_bets.extend(win_bets)

    elif strategy == "Standard":
        raw_bets.extend(quin_bets)
        raw_bets.extend(win_bets)

    elif strategy == "Win only":
        raw_bets.extend(win_bets)

    # Scale stakes down if exceeding single-race 5% bankroll cap
    total_raw_stake = sum(b['raw_stake'] for b in raw_bets)
    scale_factor = min(1.0, race_bankroll_cap / total_raw_stake) if total_raw_stake > 0 else 1.0

    final_bets = []
    for b in raw_bets:
        scaled_stake = b['raw_stake'] * scale_factor
        rounded_stake = round_to_hkd_10(scaled_stake)
        if rounded_stake >= 10:
            b['final_stake'] = rounded_stake
            final_bets.append(b)

    return strategy, final_bets, race_bankroll_cap

# ==========================================
# 5. STREAMLIT INTERFACE & WORKFLOW
# ==========================================
st.title("🏇 HKJC Kelly & Quinella Terminal")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Settings")
    bankroll = st.number_input("Total Bankroll (HKD)", min_value=1000, value=100000, step=1000)
    st.info(f"Race Cap (5%): **HK${bankroll * 0.05:,.0f}**")
    
    uploaded_file = st.file_uploader("Upload Google Sheet CSV (`data.csv`)", type=["csv"])

# Main Application Logic
if uploaded_file is not None:
    try:
        # Load CSV using python engine to handle quotes/commas safely
        df_raw = pd.read_csv(uploaded_file, header=None, engine='python', on_bad_lines='skip')
        parsed_races = parse_multi_race_sheet(df_raw)

        if not parsed_races:
            st.error("No valid race data parsed. Please verify CSV formatting.")
            st.stop()

        # Race Selection Tabs
        race_titles = [f"{r['title']} ({r['track']})" for r in parsed_races]
        selected_race_idx = st.selectbox("Select Race", range(len(race_titles)), format_func=lambda i: race_titles[i])
        race_data = parsed_races[selected_race_idx]

        st.subheader(f"📍 {race_data['title']} — Track Code: {race_data['track']}")

        # Header bar for Live Odds Retrieval
        col_hdr1, col_hdr2 = st.columns([3, 1])
        with col_hdr1:
            st.write("Adjust Win odds or pull real-time prices directly from HKJC:")
        with col_hdr2:
            if st.button("🔄 Pull HKJC Live Odds", use_container_width=True):
                live_odds = fetch_hkjc_live_odds(race_data['title'])
                if live_odds:
                    st.session_state[f"live_odds_{selected_race_idx}"] = live_odds
                    st.success("HKJC Odds Updated!")
                else:
                    st.warning("Could not reach HKJC live API. Using preset odds.")

        cached_live_odds = st.session_state.get(f"live_odds_{selected_race_idx}", {})

        # Odds Adjustment Inputs Grid
        st.markdown("### 1. Horse Inputs & Win Odds")
        cols = st.columns(4)
        updated_horses = []

        for idx, h in enumerate(race_data['horses']):
            col = cols[idx % 4]
            fetched_odds = cached_live_odds.get(h['no'], float(4.0 + (idx * 0.5)))
            
            with col:
                st.markdown(f"**#{h['no']} {h['name']}**")
                st.caption(f"Model Win %: {h['win_prob']*100:.2f}%")
                live_odds_val = st.number_input(
                    f"Win Odds (#{h['no']})",
                    min_value=1.01,
                    value=float(fetched_odds),
                    step=0.1,
                    key=f"win_odds_{selected_race_idx}_{h['no']}"
                )
                updated_horses.append({
                    'no': h['no'],
                    'name': h['name'],
                    'win_prob': h['win_prob'],
                    'live_odds': live_odds_val
                })

        # Calculate Bets
        strategy, recommended_bets, race_cap = evaluate_bets(updated_horses, race_data['track'], bankroll)

        st.divider()
        st.markdown("### 2. Strategy Analysis & Bet Recommendations")

        # Strategy Indicator Cards
        c1, c2, c3 = st.columns(3)
        c1.metric("Track Bias Strategy", strategy)
        c2.metric("Race Outlay Cap (5%)", f"HK${race_cap:,.0f}")
        total_outlay = sum(b['final_stake'] for b in recommended_bets)
        c3.metric("Total Recommended Stake", f"HK${total_outlay:,.0f}")

        # Display Bet Table
        if recommended_bets:
            bets_df = pd.DataFrame([
                {
                    "Bet Type": b['type'],
                    "Selection": b['selection'],
                    "Model Win / Joint Prob": f"{b['prob']*100:.2f}%",
                    "Odds": f"{b['odds']:.2f}",
                    "Expected Value (EV)": f"+{b['ev']*100:.1f}%",
                    "Recommended Stake": f"HK${b['final_stake']:,}"
                }
                for b in recommended_bets
            ])
            st.dataframe(bets_df, use_container_width=True)
        else:
            st.info("No selections met the +5% Expected Value (+EV) threshold for this race.")

    except Exception as e:
        st.error(f"Error parsing uploaded CSV file: {e}")
else:
    st.info("👈 Please upload your `data.csv` file in the sidebar menu to begin.")
