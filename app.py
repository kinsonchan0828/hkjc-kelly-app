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

    # 4. Enforce 5% Single-Race Bankroll Cap (HK$250 on HK$5000)
    max_cap = bankroll * 0.05
    total_raw_stake = sum(b['stake'] for b in recommended_bets)

    if total_raw_stake > max_cap and total_raw_stake > 0:
        scale_factor = max_cap / total_raw_stake
        for b in recommended_bets:
            b['stake'] = round(b['stake'] * scale_factor, 0)
        strategy_reason += f" Stakes scaled down proportionally to fit HK${max_cap:.0f} cap."
    else:
        for b in recommended_bets:
            b['stake'] = round(b['stake'], 0)

    return recommended_bets, strategy_reason, strategy_mode

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

def parse_sheet_data(df_raw):
    race_title = str(df_raw.iloc[0, 0]).strip()
    track_code = str(df_raw.iloc[0, 1]).strip()
    
    data = df_raw.iloc[1:].copy()
    data.columns = ['Horse_No', 'Horse_Name', 'Win_Prob']
    
    data['Horse_No'] = pd.to_numeric(data['Horse_No'], errors='coerce')
    data = data.dropna(subset=['Horse_No'])
    data['Horse_No'] = data['Horse_No'].astype(int)
    
    def clean_probability(val):
        s = str(val).replace('%', '').strip()
        num = float(s)
        return num / 100.0 if num > 1.0 else num

    data['Win_Prob'] = data['Win_Prob'].apply(clean_probability)
    return race_title, track_code, data

# Fallback default data matching user layout if no URL provided
if not sheet_url:
    mock_df = pd.DataFrame([
        ["Race 1", "SH A 1000", "Final Win %"],
        [1, "浪漫勇士", 0.28],
        [2, "金槍六十", 0.24],
        [3, "加州星球", 0.18],
        [4, "遨遊氣泡", 0.14],
    ])
    race_title, track_code, horse_df = parse_sheet_data(mock_df)
else:
    try:
        raw_df = pd.read_csv(sheet_url, header=None)
        race_title, track_code, horse_df = parse_sheet_data(raw_df)
    except Exception as e:
        st.error(f"Error loading Google Sheet CSV: {e}")
        st.stop()

# Track Rule Lookup Display
rule_type = TRACK_STRATEGY_MAP.get(track_code, "Standard")
st.info(f"**Loaded:** {race_title} | **Track:** {track_code} | **Strategy Rule:** {rule_type}")

# Live Odds Input Area
st.subheader("2. Input Real-Time Tote Odds (T-3 min)")

horses_input = []
cols = st.columns(min(len(horse_df), 4))

for idx, (_, row) in enumerate(horse_df.iterrows()):
    col_idx = idx % 4
    with cols[col_idx]:
        st.caption(f"#{row['Horse_No']} {row['Horse_Name']}")
        st.text(f"Win%: {row['Win_Prob']*100:.1f}%")
        live_odds = st.number_input(
            f"Odds #{row['Horse_No']}",
            min_value=1.0,
            value=float(4.0 + idx),
            step=0.1,
            key=f"odds_{row['Horse_No']}"
        )
        horses_input.append({
            'no': row['Horse_No'],
            'name': row['Horse_Name'],
            'win_prob': row['Win_Prob'],
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
                    key=f"q_odds_{h1['no']}_{h2['no']}"
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
