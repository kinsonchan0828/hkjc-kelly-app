import streamlit as st
import pandas as pd
import itertools
import re

# ==============================================================================
# Page Configuration
# ==============================================================================
st.set_page_config(page_title="HKJC Win & Henery-Quinella Decision Engine", layout="wide")

# ==============================================================================
# Helper Functions: Track Detection, Sheet Parser, & Henery Engine
# ==============================================================================
def detect_track_theta(race_info_text: str):
    """
    Analyzes Race Info string (e.g. 'HV A 1200', 'ST AWT 1650', 'SH A 1400', 'MUD 1200')
    and returns (theta_value, track_label).
    Literature-backed parameters for HKJC:
    - Sha Tin Turf: 0.83 (Fair, long straight)
    - Happy Valley Turf: 0.79 (Tight turns, short straight, position bias)
    - All-Weather / Dirt / Mud: 0.76 (High variance, kickback, severe bias)
    """
    text_upper = race_info_text.upper()
    
    # Check for Dirt / Mud / All Weather Track
    if any(k in text_upper for k in ['AWT', 'DIRT', 'MUD', 'ALL WEATHER', 'WET', 'YIELDING']):
        return 0.76, "Sha Tin Dirt / Mud (AWT) [High Variance]"
    # Check for Happy Valley
    elif any(k in text_upper for k in ['HV', 'HAPPY', 'VALLEY']):
        return 0.79, "Happy Valley Turf [Position Bias]"
    # Default to Sha Tin Turf
    else:
        return 0.83, "Sha Tin Turf [Standard Class]"


def parse_custom_sheet(df_raw):
    """
    Parses multi-race Google Sheets with format:
    Col A: 'R1' (Race) or Horse No (1-14)
    Col B: Race details (e.g., 'ST A 1200', 'HV C+3 1650') or Horse Name
    Col C: Win% header or Decimal/Percentage Win Probability
    """
    race_data = []
    current_race_id = "R1"
    current_race_details = "Sha Tin Turf"
    
    if df_raw.shape[1] < 3:
        return None, "Sheet must have at least 3 columns (Col A, Col B, Col C)."

    for idx, row in df_raw.iterrows():
        col_a = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        col_b = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        col_c = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""

        if not col_a and not col_b and not col_c:
            continue

        # Detect Race Header row (e.g., Col A = 'R1', Col B = 'HV A 1200')
        if col_a.upper().startswith('R') and not col_a.isdigit():
            current_race_id = col_a.upper()
            current_race_details = col_b if col_b and col_b.lower() != 'nan' else "ST Turf"
            continue

        try:
            horse_no = int(float(col_a))
            if 1 <= horse_no <= 14:
                horse_name = col_b if col_b and col_b.lower() != 'nan' else f"Horse {horse_no}"
                
                try:
                    clean_c = col_c.replace('%', '').strip()
                    win_val = float(clean_c)
                    win_pct = round(win_val * 100.0, 2) if 0 < win_val <= 1.0 else round(win_val, 2)
                except ValueError:
                    continue

                full_race_label = f"{current_race_id} ({current_race_details})"
                race_data.append({
                    'Race Label': full_race_label,
                    'Race Code': current_race_id,
                    'Race Details': current_race_details,
                    'Horse No': horse_no,
                    'Horse Name': horse_name,
                    'Model Win %': win_pct
                })
        except ValueError:
            continue

    if not race_data:
        return None, "No valid horse data found. Check sheet columns and formatting."
        
    return pd.DataFrame(race_data), None


def compute_henery_quinella(df_full, theta=0.82):
    """
    Computes Henery's Power Discount Quinella probabilities for all pairs 
    based on normalized field Win probabilities and auto-detected track theta.
    """
    df = df_full.copy()
    total_win_pct = df['Model Win %'].sum()
    if total_win_pct <= 0:
        return {}
    
    # Normalize win probabilities across full field
    p = {row['Horse No']: (row['Model Win %'] / total_win_pct) for _, row in df.iterrows()}
    horses = list(p.keys())
    
    q_probs = {}
    for h1, h2 in itertools.combinations(horses, 2):
        # Direction 1: h1 wins (1st), h2 comes second (2nd)
        denom_1 = sum(p[k]**theta for k in horses if k != h1)
        p_h2_given_h1 = (p[h2]**theta / denom_1) if denom_1 > 0 else 0.0
        
        # Direction 2: h2 wins (1st), h1 comes second (2nd)
        denom_2 = sum(p[k]**theta for k in horses if k != h2)
        p_h1_given_h2 = (p[h1]**theta / denom_2) if denom_2 > 0 else 0.0
        
        # Combined Henery Quinella Probability
        prob_q = (p[h1] * p_h2_given_h1) + (p[h2] * p_h1_given_h2)
        q_probs[f"{min(h1, h2)}-{max(h1, h2)}"] = prob_q
        
    return q_probs

# ==============================================================================
# Sidebar: Bankroll & Risk Management
# ==============================================================================
st.sidebar.header("💰 Bankroll & Risk Control")

if 'bankroll' not in st.session_state:
    st.session_state.bankroll = 5000.0

bankroll = st.sidebar.number_input(
    "Current Total Bankroll ($)",
    min_value=100.0,
    value=float(st.session_state.bankroll),
    step=500.0,
    key="bankroll_input"
)
st.session_state.bankroll = bankroll

max_race_stake = float(bankroll * 0.05)

st.sidebar.metric(
    label="Max Allowed Stake (5% Cap)",
    value=f"${max_race_stake:.2f}"
)

st.sidebar.markdown("""
---
**Active Engine Settings:**
* 🧠 **Quinella Engine:** Henery Power Discount (Auto-Track $\\theta$).
* 🎯 **Supported Pools:** Win & Quinella (Q).
* 🛡️ **Hard Cap Ceiling:** Dynamic 5% bankroll limit per race.
* 💵 **HKJC Unit Rule:** Individual bets rounded to nearest HK$10.
""")

# ==============================================================================
# Main App Header
# ==============================================================================
st.title("🏇 HKJC Win & Henery-Quinella Decision Engine")
st.caption("Hybrid System: Auto Track-Specific Henery Model + Trainer Audit + Multi-Pool Dutching")

# ==============================================================================
# STEP 1: Model Input & Individual Horse Pruning
# ==============================================================================
st.header("1. Field Input & Horse Audit")

tab_sheet, tab_manual = st.tabs(["📊 Import Google Sheet / CSV", "✏️ Manual Input"])
data_df = None
selected_race_details = "ST Turf"

with tab_sheet:
    sheet_url = st.text_input(
        "Google Sheet Public CSV URL or File Upload",
        placeholder="https://docs.google.com/spreadsheets/d/.../export?format=csv"
    )
    uploaded_file = st.file_uploader("Or upload CSV file", type=["csv"])
    
    raw_df = None
    if uploaded_file is not None:
        try:
            raw_df = pd.read_csv(uploaded_file, header=None)
        except Exception as e:
            st.error(f"Error reading uploaded file: {e}")
    elif sheet_url.strip():
        try:
            raw_df = pd.read_csv(sheet_url.strip(), header=None)
        except Exception as e:
            st.error(f"Error loading Google Sheet URL: {e}")

    if raw_df is not None:
        parsed_df, err = parse_custom_sheet(raw_df)
        if err:
            st.error(err)
        else:
            races_available = parsed_df['Race Label'].unique()
            selected_race_label = st.selectbox("🎯 Select Race to Analyze:", races_available)
            
            race_subset = parsed_df[parsed_df['Race Label'] == selected_race_label]
            selected_race_details = race_subset['Race Details'].iloc[0]
            data_df = race_subset[['Horse No', 'Horse Name', 'Model Win %']].reset_index(drop=True)

with tab_manual:
    if data_df is None:
        default_data = pd.DataFrame({
            'Horse No': [1, 2, 3, 4, 5, 6],
            'Horse Name': ['Romantic Warrior', 'California Spangle', 'Golden Sixty', 'Voyage Bubble', 'Beauty Eternal', 'Straight Arron'],
            'Model Win %': [35.0, 25.0, 18.0, 12.0, 7.0, 3.0]
        })
        data_df = st.data_editor(default_data, num_rows="dynamic", key="manual_editor")
        selected_race_details = st.text_input("Manual Race Details / Track:", value="HV A 1200")

if data_df is not None and not data_df.empty:
    # Auto-detect Track & Surface Theta behind the scenes
    active_theta, track_label = detect_track_theta(selected_race_details)
    
    st.success(f"⚙️ **Behind-the-Scenes Calibration:** Detected `{selected_race_details}` $\\rightarrow$ Applied **{track_label}** (Henery $\\theta = {active_theta}$)")

    # Compute underlying Henery Quinella probabilities with active_theta
    full_q_probs = compute_henery_quinella(data_df, theta=active_theta)
    
    df_calc = data_df.copy()
    df_calc['Win Prob (Dec)'] = df_calc['Model Win %'] / 100.0
    df_calc['Win Fair Odds'] = df_calc['Win Prob (Dec)'].apply(lambda p: round(1.0 / p, 2) if p > 0 else 999.0)
    df_calc['Win Min Odds (+5% EV)'] = df_calc['Win Prob (Dec)'].apply(lambda p: round(1.05 / p, 2) if p > 0 else 999.0)

    st.subheader("Individual Horse Audit Table")
    st.write("Uncheck **Keep** to eliminate horses from consideration. (Henery Quinella probabilities update automatically in the background).")

    if 'Keep' not in df_calc.columns:
        df_calc.insert(0, 'Keep', True)

    edited_df = st.data_editor(
        df_calc[['Keep', 'Horse No', 'Horse Name', 'Model Win %', 'Win Fair Odds', 'Win Min Odds (+5% EV)']],
        disabled=['Horse No', 'Horse Name', 'Model Win %', 'Win Fair Odds', 'Win Min Odds (+5% EV)'],
        hide_index=True,
        use_container_width=True
    )

    contenders = edited_df[edited_df['Keep'] == True].copy()
    st.info(f"Active Contenders Remaining: **{len(contenders)} / {len(edited_df)}** (Horses: {', '.join(map(str, contenders['Horse No'].tolist()))})")

# ==============================================================================
# STEP 2: Portfolio Builder (Win & Henery Quinella Custom Combo Selection)
# ==============================================================================
    st.divider()
    st.header("2. Bet Selection & Value Floor Table")

    if len(contenders) < 1:
        st.warning("Select at least one horse to build a betting portfolio.")
    else:
        st.write("Construct your portfolio by selecting individual **Win** bets and/or **Henery Quinella** combinations among remaining contenders:")

        col_win_sec, col_q_sec = st.columns([1, 1.2])

        # --- Sub-Section A: Win Bets ---
        selected_win_bets = []
        with col_win_sec:
            st.subheader("🎯 Win Bets")
            win_selection_data = []
            for _, row in contenders.iterrows():
                win_selection_data.append({
                    'Select': False,
                    'Horse No': int(row['Horse No']),
                    'Horse Name': row['Horse Name'],
                    'Model Win %': row['Model Win %'],
                    'Min Odds (+5% EV)': row['Win Min Odds (+5% EV)']
                })
            win_sel_df = pd.DataFrame(win_selection_data)
            
            edited_win_sel = st.data_editor(
                win_sel_df,
                disabled=['Horse No', 'Horse Name', 'Model Win %', 'Min Odds (+5% EV)'],
                hide_index=True,
                key="win_bet_selector",
                use_container_width=True
            )
            
            for _, row in edited_win_sel[edited_win_sel['Select'] == True].iterrows():
                selected_win_bets.append({
                    'Bet Code': f"WIN #{row['Horse No']}",
                    'Bet Type': 'Win',
                    'Label': f"#{row['Horse No']} {row['Horse Name']}",
                    'Model %': row['Model Win %'],
                    'Min Odds (+5% EV)': row['Min Odds (+5% EV)']
                })

        # --- Sub-Section B: Henery Quinella Combinations ---
        selected_q_bets = []
        with col_q_sec:
            st.subheader(f"🔄 Henery Quinella Combinations (\\theta = {active_theta})")
            contender_nos = sorted(contenders['Horse No'].tolist())
            
            if len(contender_nos) < 2:
                st.info("Keep at least 2 horses checked in the Audit table above to enable Quinella combinations.")
            else:
                q_selection_data = []
                for h1, h2 in itertools.combinations(contender_nos, 2):
                    q_key = f"{min(h1, h2)}-{max(h1, h2)}"
                    prob_q = full_q_probs.get(q_key, 0.0)
                    
                    fair_q_odds = round(1.0 / prob_q, 2) if prob_q > 0 else 999.0
                    min_q_odds = round(1.05 / prob_q, 2) if prob_q > 0 else 999.0
                    
                    q_selection_data.append({
                        'Select': False,
                        'Combo': f"Q {q_key}",
                        'Henery Q %': round(prob_q * 100.0, 2),
                        'Fair Odds': fair_q_odds,
                        'Min Odds (+5% EV)': min_q_odds
                    })
                
                q_sel_df = pd.DataFrame(q_selection_data)
                
                edited_q_sel = st.data_editor(
                    q_sel_df,
                    disabled=['Combo', 'Henery Q %', 'Fair Odds', 'Min Odds (+5% EV)'],
                    hide_index=True,
                    key="q_bet_selector",
                    use_container_width=True
                )
                
                for _, row in edited_q_sel[edited_q_sel['Select'] == True].iterrows():
                    selected_q_bets.append({
                        'Bet Code': row['Combo'],
                        'Bet Type': 'Quinella',
                        'Label': row['Combo'],
                        'Model %': row['Henery Q %'],
                        'Min Odds (+5% EV)': row['Min Odds (+5% EV)']
                    })

        active_portfolio = selected_win_bets + selected_q_bets

# ==============================================================================
# STEP 3: Multi-Pool Dutching Engine
# ==============================================================================
        st.divider()
        st.header("3. Live Odds & Multi-Pool Dutching Execution")

        if not active_portfolio:
            st.info("👈 Check boxes in Section 2 to add Win or Henery Quinella bets to your execution portfolio.")
        else:
            st.write(f"Enter **Live Market Odds** for your **{len(active_portfolio)}** chosen bets:")

            with st.form("dutching_form"):
                live_odds_inputs = {}
                cols = st.columns(min(len(active_portfolio), 4))
                
                for idx, bet in enumerate(active_portfolio):
                    col = cols[idx % 4]
                    bet_code = bet['Bet Code']
                    min_odds = float(bet['Min Odds (+5% EV)'])
                    
                    live_odds_inputs[bet_code] = col.number_input(
                        f"{bet_code} (Min: {min_odds})",
                        min_value=1.01,
                        value=min_odds,
                        step=0.1,
                        key=f"live_odds_{bet_code}"
                    )

                custom_stake = st.number_input(
                    f"Target Total Race Stake ($) — Max Allowed: ${max_race_stake:.2f}",
                    min_value=10.0,
                    max_value=max_race_stake,
                    value=max_race_stake,
                    step=10.0,
                    help=f"Defaults to 5% bankroll ceiling (${max_race_stake:.2f}). You can manually reduce this stake amount."
                )

                calculate_btn = st.form_submit_button("Calculate Portfolio Dutching")

            if calculate_btn:
                dutch_rows = []
                inv_odds_sum = 0.0

                for bet in active_portfolio:
                    code = bet['Bet Code']
                    curr_odds = live_odds_inputs[code]
                    min_odds = bet['Min Odds (+5% EV)']
                    
                    inv_odds = 1.0 / curr_odds
                    inv_odds_sum += inv_odds
                    
                    dutch_rows.append({
                        'Bet Code': code,
                        'Type': bet['Bet Type'],
                        'Model %': bet['Model %'],
                        'Min Odds (+5% EV)': min_odds,
                        'Live Odds': curr_odds,
                        'Value Check': "✅ Value" if curr_odds >= min_odds else "❌ Overvalued",
                        'Inv Odds': inv_odds
                    })

                dutch_df = pd.DataFrame(dutch_rows)
                
                dutch_df['Bet Ratio (%)'] = (dutch_df['Inv Odds'] / inv_odds_sum) * 100.0
                raw_stakes = (dutch_df['Bet Ratio (%)'] / 100.0) * custom_stake
                
                # HKJC Rounding to nearest HK$10
                dutch_df['Suggested Stake ($)'] = raw_stakes.apply(
                    lambda s: max(10, int(round(s / 10.0) * 10)) if s >= 5 else 0
                )

                actual_total_stake = int(dutch_df['Suggested Stake ($)'].sum())
                dutch_df['Est Payout ($)'] = (dutch_df['Suggested Stake ($)'] * dutch_df['Live Odds']).round(1)
                
                min_payout = dutch_df[dutch_df['Suggested Stake ($)'] > 0]['Est Payout ($)'].min() if actual_total_stake > 0 else 0
                net_profit = min_payout - actual_total_stake
                roi_pct = (net_profit / actual_total_stake * 100.0) if actual_total_stake > 0 else 0

                st.subheader("🎯 Execution Summary (HK$10 Units)")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Actual Total Bet", f"${actual_total_stake}")
                m2.metric("Min Floor Payout", f"${min_payout:.1f}")
                m3.metric("Est. Floor Net Profit", f"${net_profit:.1f}", delta=f"{roi_pct:.1f}% ROI")
                m4.metric("Dutch Book Overround", f"{(inv_odds_sum * 100.0):.1f}%")

                st.dataframe(
                    dutch_df[['Bet Code', 'Type', 'Live Odds', 'Min Odds (+5% EV)', 'Value Check', 'Bet Ratio (%)', 'Suggested Stake ($)', 'Est Payout ($)']],
                    hide_index=True,
                    use_container_width=True
                )

                if any(dutch_df['Live Odds'] < dutch_df['Min Odds (+5% EV)']):
                    st.warning("⚠️ One or more selected bets are below your Minimum Acceptable Odds (+5% EV). Consider unchecking overvalued legs in Section 2.")
