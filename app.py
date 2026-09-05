import streamlit as st
import pandas as pd

# --- FULL HKJC TRACK STRATEGY MATRIX ---

TRACK_STRATEGY_MAP = {
    # Sha Tin A Course
    "SH A 1000": "Quin", "SH A 1200": "Quin", "SH A 1400": "Quin", "SH A 2000": "Quin",
    "SH A 1600": "Standard",
    "SH A 1800": "Win only",
    
    # Sha Tin A+3 Course
    "SH A+3 1000": "Quin", "SH A+3 1200": "Quin", "SH A+3 1400": "Quin", "SH A+3 1600": "Quin",
    "SH A+3 1800": "Win only", "SH A+3 2000": "Win only",
    
    # Sha Tin B Course
    "SH B 1000": "Standard", "SH B 1600": "Standard",
    "SH B 1200": "Quin",
    "SH B 1400": "Win only", "SH B 1800": "Win only", "SH B 2000": "Win only",
    
    # Sha Tin B+2 Course
    "SH B+2 1000": "Win only", "SH B+2 1600": "Win only", "SH B+2 1800": "Win only",
    "SH B+2 1200": "Quin", "SH B+2 1400": "Quin", "SH B+2 2000": "Quin",
    
    # Sha Tin C Course
    "SH C 1000": "Win only", "SH C 1200": "Win only", "SH C 1800": "Win only",
    "SH C 1400": "Standard",
    "SH C 1600": "Quin",
    
    # Sha Tin C+3 Course
    "SH C+3 1000": "Standard", "SH C+3 1400": "Standard", "SH C+3 1600": "Standard",
    "SH C+3 1200": "Quin",
    "SH C+3 1800": "Win only",
    
    # Happy Valley A Course
    "HV A 1000": "Quin",
    "HV A 1200": "Win only",
    "HV A 1650": "Standard", "HV A 1800": "Standard", "HV A 2200": "Standard",
    
    # Happy Valley B Course
    "HV B 1000": "Standard",
    "HV B 1200": "Win only", "HV B 1650": "Win only", "HV B 1800": "Win only",
    "HV B 2200": "Quin",
    
    # Happy Valley C Course
    "HV C 1000": "Win only", "HV C 1650": "Win only",
    "HV C 1200": "Standard", "HV C 1800": "Standard",
    "HV C 2200": "Quin",
    
    # Happy Valley C+3 Course
    "HV C+3 1000": "Win only", "HV C+3 1200": "Win only", "HV C+3 1650": "Win only",
    "HV C+3 1800": "Win only", "HV C+3 2200": "Win only",
    
    # All-Weather Dirt (Mud)
    "Mud 1200": "Standard", "Mud 1800": "Standard",
    "Mud 1650": "Win only",
}

# --- MATHEMATICAL ENGINES ---

def calculate_harville_quinella(p_a, p_b):
    """Calculates joint top-2 Quinella probability using Harville formula."""
    p_a_then_b = p_a * (p_b / (1.0 - p_a))
    p_b_then_a = p_b * (p_a / (1.0 - p_b))
    return p_a_then_b + p_b_then_a

def calculate_quarter_kelly(p, odds, bankroll, min_ev=0.05, kelly_frac=0.25):
    """Calculates 1/4 Kelly stake in HKD with minimum +5% EV filter."""
    ev = (p * odds) - 1.0
    if ev < min_ev:
        return 0.0, ev
    raw_kelly = ev / (odds - 1.0)
    stake = bankroll * kelly_frac * raw_kelly
    return stake, ev

# --- STRATEGY DECISION ENGINE ---

def evaluate_bets(track_code, horses_data, bankroll):
    strategy_mode = TRACK_STRATEGY_MAP.get(track_code.strip(), "Standard")
    
    win_bets = []
    quinella_bets = []

    # 1. Evaluate Win Bets
    for h in horses_data:
        stake, ev = calculate_quarter_kelly(h['win_prob'], h['live_odds'], bankroll)
        if stake > 0:
            win_bets.append({
                'type': 'WIN',
                'selection': f"#{h['no']} {h['name']}",
                'stake': stake,
                'ev': ev,
                'odds': h['live_odds']
            })

    # 2. Evaluate Quinella Bets (Skipped completely if mode is "Win only")
    if strategy_mode in ["Quin", "Standard"]:
        n = len(horses_data)
        for i in range(n):
            for j in range(i + 1, n):
                h1, h2 = horses_data[i], horses_data[j]
                p_quin = calculate_harville_quinella(h1['win_prob'], h2['win_prob'])
                
                # Fetch custom Q odds or auto-estimate from Win odds
                q_odds = st.session_state.get(f"q_odds_{h1['no']}_{h2['no']}", round(h1['live_odds'] * h2['live_odds'] * 0.40, 1))
                stake, ev = calculate_quarter_kelly(p_quin, q_odds, bankroll)
                
                if stake > 0:
                    quinella_bets.append({
                        'type': 'QUINELLA',
                        'selection': f"Q #{h1['no']} & #{h2['no']} ({h1['name']} / {h2['name']})",
                        'stake': stake,
                        'ev': ev,
                        'odds': q_odds
                    })

    # 3. Apply Track Strategy Filter
    if strategy_mode == "Win only":
        recommended_bets = win_bets
        strategy_reason = f"Track Profile [{track_code}] is set to WIN ONLY. Quinellas are disabled."
    elif strategy_mode == "Quin":
        recommended_bets = quinella_bets if quinella_bets else win_bets
        strategy_reason = f"Track Profile [{track_code}] prioritizes QUINELLA. Showing +EV Quinella pairs."
    else:  # Standard
        recommended_bets = win_bets + quinella_bets
        strategy_reason = f"Track Profile [{track_code}] uses STANDARD mode. Showing all +EV Win and Quinella opportunities."

    # 4. Enforce 5% Single-Race Bankroll Cap & Round Stakes to Nearest HK$10
    max_cap = bankroll * 0.05
    total_raw_stake = sum(b['stake'] for b in recommended_bets)

    if total_raw_stake > max_cap and total_raw_stake > 0:
        scale_factor = max_cap / total_raw_stake
        for b in recommended_bets:
            b['stake'] = int(round((b['stake'] * scale_factor) / 10.0) * 10)
        strategy_reason += f" Stakes scaled down proportionally to fit HK${max_cap:.0f} cap."
    else:
        for b in recommended_bets:
            b['stake'] = int(round(b['stake'] / 10.0) * 10)

    # Filter out bets that round down below the HK$10 minimum unit
    recommended_bets = [b for b in recommended_bets if b['stake'] >= 10]

    return recommended_bets, strategy_reason, strategy_mode

# --- MULTI-RACE GOOGLE SHEET PARSER ---

def parse_multi_race_sheet(df_raw):
    """Parses a Google Sheet containing up to 10 races stacked vertically."""
    races = []
    current_race = None

    for _, row in df_raw.iterrows():
        col0 = str(row[0]).strip() if pd.notna(row[0]) else ""
        col1 = str(row[1]).strip() if pd.notna(row[1]) else ""
        col2 = str(row[2]).strip() if pd.notna(row[2]) else ""

        if not col0:
            continue

        # Try parsing col0 as a horse number (e.g., 1, 2, 3...)
        try:
            horse_no = int(float(col0))
            if current_race is not None and col1:
                def clean_probability(val):
                    s = str(val).replace('%', '').strip()
                    try:
                        num = float(s)
                        return num / 100.0 if num > 1.0 else num
                    except ValueError:
                        return 0.0

                current_race['horses'].append({
                    'no': horse_no,
                    'name': col1,
                    'win_prob': clean_probability(col2)
                })
        except ValueError:
            # col0 is non-numeric (e.g., "R1", "R2", "Race 10")
            if col1 and not col0.lower().startswith("horse"):
                current_race = {
                    'title': col0,
                    'track': col1,
                    'horses': []
                }
                races.append(current_race)

    # Return only valid races that contain horses
    return [r for r in races if len(r['horses']) > 0]

# --- STREAMLIT USER INTERFACE ---

st.set_page_config(page_title="HKJC Kelly Execution Terminal", layout="centered")
st.title("🏇 HKJC Execution Terminal")

# Sidebar - Bankroll Settings
bankroll = st.sidebar.number_input("Current Bankroll (HK$)", value=5000, step=500)
st.sidebar.write(f"Single-Race 5% Cap: **HK${bankroll * 0.05:.0f}**")

# Data Loader / Input Source
st.subheader("1. Load Pre-Loaded Selections")

sheet_url = st.text_input(
    "Google Sheet Published CSV URL",
    value="",
    placeholder="Paste published CSV link here..."
)

# Mock fallback multi-race data for testing if no URL provided
mock_df = pd.DataFrame([
    ["R1", "SH A 1000", "Final Win %"],
    [1, "浪漫勇士", 0.28],
    [2, "金槍六十", 0.24],
    [3, "加州星球", 0.18],
    [4, "遨遊氣泡", 0.14],
    ["R2", "HV A 1200", "Final Win %"],
    [1, "超悅明駒", 0.30],
    [2, "快如疾風", 0.25],
    [3, "幸運有您", 0.20],
])

if not sheet_url:
    races = parse_multi_race_sheet(mock_df)
else:
    try:
        raw_df = pd.read_csv(sheet_url, header=None)
        races = parse_multi_race_sheet(raw_df)
    except Exception as e:
        st.error(f"Error loading Google Sheet CSV: {e}")
        st.stop()

if not races:
    st.error("No valid race data could be parsed from the provided Google Sheet.")
    st.stop()

# Race Selector Dropdown
race_options = [f"{r['title']} ({r['track']})" for r in races]
selected_race_idx = st.selectbox(
    "Select Race to Bet On",
    range(len(race_options)),
    format_func=lambda x: race_options[x]
)

# Active Race Data
selected_race = races[selected_race_idx]
race_title = selected_race['title']
track_code = selected_race['track']
horse_list = selected_race['horses']

# Track Rule Lookup Display
rule_type = TRACK_STRATEGY_MAP.get(track_code, "Standard")
st.info(f"**Selected:** {race_title} | **Track:** {track_code} | **Strategy Rule:** {rule_type}")

# Live Odds Input Area
st.subheader("2. Input Real-Time Tote Odds (T-3 min)")

horses_input = []
cols = st.columns(min(len(horse_list), 4))

for idx, h in enumerate(horse_list):
    col_idx = idx % 4
    with cols[col_idx]:
        st.caption(f"#{h['no']} {h['name']}")
        st.text(f"Win%: {h['win_prob']*100:.1f}%")
        live_odds = st.number_input(
            f"Odds #{h['no']}",
            min_value=1.0,
            value=float(4.0 + idx),
            step=0.1,
            key=f"odds_{race_title}_{h['no']}"
        )
        horses_input.append({
            'no': h['no'],
            'name': h['name'],
            'win_prob': h['win_prob'],
            'live_odds': live_odds
        })

# Manual Quinella Odds Input
if rule_type in ["Quin", "Standard"]:
    with st.expander("Adjust Quinella Tote Odds (Optional)"):
        for i in range(len(horses_input)):
            for j in range(i + 1, len(horses_input)):
                h1, h2 = horses_input[i], horses_input[j]
                default_q = round(h1['live_odds'] * h2['live_odds'] * 0.40, 1)
                st.number_input(
                    f"Q Odds #{h1['no']} & #{h2['no']}",
                    value=default_q,
                    step=0.5,
                    key=f"q_odds_{race_title}_{h1['no']}_{h2['no']}"
                )

# Calculate Decision
if st.button("🚀 Calculate Final Bet Decisions", type="primary"):
    bets, reason, mode = evaluate_bets(track_code, horses_input, bankroll)
    
    st.markdown("---")
    st.subheader("3. Execution Output")
    st.info(f"**Strategy Decision:** {reason}")
    
    if not bets:
        st.warning("⛔ PASS - No selections meet the minimum +5% EV threshold.")
    else:
        total_spend = sum(b['stake'] for b in bets)
        for b in bets:
            st.success(
                f"**{b['type']}** | **{b['selection']}** | Odds: **{b['odds']:.1f}** | "
                f"EV: **+{b['ev']*100:.1f}%** $\rightarrow$ **STAKE: HK${b['stake']:.0f}**"
            )
        st.metric(
            "Total Single-Race Outlay",
            f"HK${total_spend:.0f}",
            delta=f"{total_spend/bankroll*100:.1f}% of Bankroll"
        )
