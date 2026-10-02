import streamlit as st
import pandas as pd
import itertools
import re

# ==============================================================================
# Page Configuration
# ==============================================================================
st.set_page_config(page_title="HKJC Win & Henery-Quinella Decision Engine", layout="wide")

# ==============================================================================
# Helper Functions: Track Detection, Tier Engine, & Henery Model
# ==============================================================================
def detect_track_theta(race_info_text: str):
    """
    Analyzes Race Info string and returns (theta_value, track_label).
    Literature-backed parameters for HKJC:
    - Sha Tin Turf: 0.83 (Fair, long straight)
    - Happy Valley Turf: 0.79 (Tight turns, short straight, position bias)
    - All-Weather / Dirt / Mud: 0.76 (High variance, kickback, severe bias)
    """
    text_upper = race_info_text.upper()
    
    if any(k in text_upper for k in ['AWT', 'DIRT', 'MUD', 'ALL WEATHER', 'WET', 'YIELDING']):
        return 0.76, "Sha Tin Dirt / Mud (AWT) [High Variance]"
    elif any(k in text_upper for k in ['HV', 'HAPPY', 'VALLEY']):
        return 0.79, "Happy Valley Turf [Position Bias]"
    else:
        return 0.83, "Sha Tin Turf [Standard Class]"


def classify_race_tier(race_details_text: str, df: pd.DataFrame):
    """
    Classifies race into Tiers 1-4 based on Class, Probability Concentration,
    and Dominance Gap between runners, with Class 5 Standout Override.
    Returns: (tier_num, tier_title, recommended_max_stake_pct, ev_multiplier, badge_color)
    """
    text_upper = race_details_text.upper()
    
    # Extract top win percentages for gap analysis
    top_win_pcts = df['Model Win %'].nlargest(4).tolist()
    p1 = top_win_pcts[0] if len(top_win_pcts) > 0 else 0.0
    p2 = top_win_pcts[1] if len(top_win_pcts) > 1 else 0.0
    p3 = top_win_pcts[2] if len(top_win_pcts) > 2 else 0.0
    p4 = top_win_pcts[3] if len(top_win_pcts) > 3 else 0.0
    
    top_2_sum = p1 + p2
    top_3_sum = p1 + p2 + p3
    
    gap_2_3 = p2 - p3
    gap_3_4 = p3 - p4

    # Check for Class 5 / Griffin / Maiden
    is_class_5_or_griffin = any(k in text_upper for k in [
        'C5', 'CLASS 5', 'CLASS5', 'GRIFFIN', 'MAIDEN', 'RATING 40-0', 'RESTRICTED'
    ])
    
    # Class 5 Standout Overrides
    if is_class_5_or_griffin:
        if p1 >= 50.0:
            return (
                1, 
                "🥇 Tier 1: Class 5 Standout (Top Pick ≥ 50% — High Confidence)", 
                0.05,   # 5.0% max stake cap
                1.05,   # +5% EV floor
                "green"
            )
        elif top_2_sum >= 55.0:
            return (
                2, 
                "🥈 Tier 2: Class 5 Dominant Pair (Top 2 ≥ 55% — Moderate Confidence)", 
                0.04,   # 4.0% max stake cap
                1.05,   # +5% EV floor
                "blue"
            )
        else:
            return (
                4, 
                "🚨 Tier 4: Class 5 / Griffin (High Noise — Recommended AUTO-PASS)", 
                0.015,  # 1.5% max stake cap
                1.15,   # +15% EV floor required
                "red"
            )

    # Standard Class 4 or Above Tier Logic
    # Tier 1: Dominant 2-Horse Core
    if (top_2_sum >= 45.0) or (p1 >= 28.0) or (top_2_sum >= 42.0 and gap_2_3 >= 7.0):
        return (
            1, 
            "🥇 Tier 1: Prime Dominant Core (Top 2 Win % ≥ 45% or Clear Gap — High Confidence)", 
            0.05,   # 5.0% max stake cap
            1.05,   # +5% EV floor
            "green"
        )
    # Tier 2: Solid 3-Horse Core
    elif (top_3_sum >= 48.0) or (top_3_sum >= 44.0 and gap_3_4 >= 5.0):
        return (
            2, 
            "🥈 Tier 2: Solid 3-Horse Core (Top 3 Win % ≥ 48% or Clear Gap — Moderate Confidence)", 
            0.04,   # 4.0% max stake cap
            1.05,   # +5% EV floor
            "blue"
        )
    # Tier 3: Wide-Open / Fragmented
    else:
        return (
            3, 
            "🥉 Tier 3: Wide-Open / Fragmented (Top 3 Win % < 44% — High Variance)", 
            0.025,  # 2.5% max stake cap
            1.10,   # +10% EV floor required
            "orange"
        )


def parse_custom_sheet(df_raw):
    """
    Parses multi-race Google Sheets with format:
    Col A: 'R1' (Race) or Horse No (1-14)
    Col B: Race details (e.g., 'ST C4 1200', 'HV C5 1650') or Horse Name
    Col C: Win% header or Decimal/Percentage Win Probability
    """
    race_data = []
    current_race_id = "R1"
    current_race_details = "ST C4 1200"
    
    if df_raw.shape[1] < 3:
        return None, "Sheet must have at least 3 columns (Col A, Col B, Col C)."

    for idx, row in df_raw.iterrows():
        col_a = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        col_b = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        col_c = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""

        if not col_a and not col_b and not col_c:
            continue

        if col_a.upper().startswith('R') and not col_a.isdigit():
            current_race_id = col_a.upper()
            current_race_details = col_b if col_b and col_b.lower() != 'nan' else "ST C4 1200"
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
    
    p = {row['Horse No']: (row['Model Win %'] / total_win_pct) for _, row in df.iterrows()}
    horses = list(p.keys())
    
    q_probs = {}
    for h1, h2 in itertools.combinations(horses, 2):
        denom_1 = sum(p[k]**theta for k in horses if k != h1)
        p_h2_given_h1 = (p[h2]**theta / denom_1) if denom_1 > 0 else 0.0
        
        denom_2 = sum(p[k]**theta for k in horses if k != h2)
        p_h1_given_h2 = (p[h1]**theta / denom_2) if denom_2 > 0 else 0.0
        
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

st.sidebar.markdown("""
---
**Active Engine Rules:**
* 🏷️ **Tier Classification:** Gap-Adjusted Tiers 1–4 Engine.
* ⚡ **Class 5 Override:** Active (P1 ≥ 50% → Tier 1 Override).
* 🧠 **Quinella Engine:** Henery Power Discount (Auto-Track $\\theta$).
* 🛡️ **Dynamic Stake Cap:** Scaled by Tier Confidence (1.5% to 5.0%).
* 💵 **HKJC Unit Rule:** Stakes rounded to nearest HK$10.
""")

# ==============================================================================
# Main App Header
# ==============================================================================
st.title("🏇 HKJC Win & Henery-Quinella Decision Engine")
st.caption("Hybrid System: Auto Tier Identification + Track-Specific Henery Model + Multi-Pool Dutching")

# ==============================================================================
# STEP 1: Model Input, Tier Identification & Horse Audit
# ==============================================================================
st.header("1. Field Input, Tier Identification & Audit")

tab_sheet, tab_manual = st.tabs(["📊 Import Google Sheet / CSV", "✏️ Manual Input"])
data_df = None
selected_race_details = "ST C4 1200"

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
        selected_race_details = st.text_input("Manual Race Details / Track:", value="ST C4 1200")

if data_df is not None and not data_df.empty:
    # Auto-detect Track & Surface Theta behind the scenes
    active_theta, track_label = detect_track_theta(selected_race_details)
    
    # Tier Classification Engine
    tier_num, tier_title, tier_max_stake_pct, ev_multiplier, badge_color = classify_race_tier(selected_race_details, data_df)
    suggested_tier_stake_cap = float(bankroll * tier_max_stake_pct)

    # Status Banners
    st.markdown(f"### {tier_title}")
    
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    col_stat1.metric("Track Calibration", f"\\theta = {active_theta}", help=track_label)
    col_stat2.metric("Suggested Stake Cap", f"${suggested_tier_stake_cap:.2f} ({tier_max_stake_pct*100:.1f}%)")
    col_stat3.metric("Required EV Price Floor", f"+{(ev_multiplier - 1.0)*100:.0f}% EV")

    if tier_num == 4:
        st.error("⚠️ **HIGH NOISE WARNING:** Class 5 / Griffin races carry high statistical variance. Passing this race is strongly recommended to preserve capital.")

    # Compute Henery Quinella probabilities
    full_q_probs = compute_henery_quinella(data_df, theta=active_theta)
    
    df_calc = data_df.copy()
    df_calc['Win Prob (Dec)'] = df_calc['Model Win %'] / 100.0
    df_calc['Win Fair Odds'] = df_calc['Win Prob (Dec)'].apply(lambda p: round(1.0 / p, 2) if p > 0 else 999.0)
    
    # Apply Tier-Specific EV Multiplier
    df_calc['Win Min Odds (EV Floor)'] = df_calc['Win Prob (Dec)'].apply(
        lambda p: round(ev_multiplier / p, 2) if p > 0 else 999.0
    )

    st.subheader("Price Floor & Trainer Audit Table")
    
    col_audit_desc, col_highlight_ctrl = st.columns([2.2, 1])
    with col_audit_desc:
        st.write("Uncheck **Keep** to eliminate horses from consideration. (Henery Quinella probabilities update automatically).")
    with col_highlight_ctrl:
        top_n_val = st.number_input(
            "💡 Highlight Top N Win % Horses:",
            min_value=1,
            max_value=max(1, len(df_calc)),
            value=min(3, len(df_calc)),
            step=1,
            help="Highlights the horses with the highest Model Win % in bright yellow."
        )

    top_n_cutoffs = df_calc['Model Win %'].nlargest(top_n_val).tolist()
    cutoff_val = top_n_cutoffs[-1] if top_n_cutoffs else 0.0

    def highlight_top_n(row):
        if row['Model Win %'] >= cutoff_val and row['Model Win %'] > 0:
            return ['background-color: #FFFF99; color: #000000; font-weight: bold;'] * len(row)
        return [''] * len(row)

    if 'Keep' not in df_calc.columns:
        df_calc.insert(0, 'Keep', True)

    display_df = df_calc[['Keep', 'Horse No', 'Horse Name', 'Model Win %', 'Win Fair Odds', 'Win Min Odds (EV Floor)']]
    styled_df = display_df.style.apply(highlight_top_n, axis=1)

    edited_df = st.data_editor(
        styled_df,
        disabled=['Horse No', 'Horse Name', 'Model Win %', 'Win Fair Odds', 'Win Min Odds (EV Floor)'],
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
                    'Min Odds (EV Floor)': row['Win Min Odds (EV Floor)']
                })
            win_sel_df = pd.DataFrame(win_selection_data)
            
            edited_win_sel = st.data_editor(
                win_sel_df,
                disabled=['Horse No', 'Horse Name', 'Model Win %', 'Min Odds (EV Floor)'],
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
                    'Min Odds (EV Floor)': row['Min Odds (EV Floor)']
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
                    min_q_odds = round(ev_multiplier / prob_q, 2) if prob_q > 0 else 999.0
                    
                    q_selection_data.append({
                        'Select': False,
                        'Combo': f"Q {q_key}",
                        'Henery Q %': round(prob_q * 100.0, 2),
                        'Fair Odds': fair_q_odds,
                        'Min Odds (EV Floor)': min_q_odds
                    })
                
                q_sel_df = pd.DataFrame(q_selection_data)
                
                edited_q_sel = st.data_editor(
                    q_sel_df,
                    disabled=['Combo', 'Henery Q %', 'Fair Odds', 'Min Odds (EV Floor)'],
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
                        'Min Odds (EV Floor)': row['Min Odds (EV Floor)']
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
                    min_odds = float(bet['Min Odds (EV Floor)'])
                    
                    live_odds_inputs[bet_code] = col.number_input(
                        f"{bet_code} (Min: {min_odds})",
                        min_value=1.01,
                        value=min_odds,
                        step=0.1,
                        key=f"live_odds_{bet_code}"
                    )

                custom_stake = st.number_input(
                    f"Target Total Race Stake ($) — Tier Suggested Cap: ${suggested_tier_stake_cap:.2f}",
                    min_value=10.0,
                    max_value=float(suggested_tier_stake_cap),
                    value=float(suggested_tier_stake_cap),
                    step=10.0,
                    help=f"Auto-scaled to {tier_title} max stake cap (${suggested_tier_stake_cap:.2f})."
                )

                calculate_btn = st.form_submit_button("Calculate Portfolio Dutching")

            if calculate_btn:
                dutch_rows = []
                inv_odds_sum = 0.0

                for bet in active_portfolio:
                    code = bet['Bet Code']
                    curr_odds = live_odds_inputs[code]
                    min_odds = bet['Min Odds (EV Floor)']
                    
                    inv_odds = 1.0 / curr_odds
                    inv_odds_sum += inv_odds
                    
                    dutch_rows.append({
                        'Bet Code': code,
                        'Type': bet['Bet Type'],
                        'Model %': bet['Model %'],
                        'Min Odds (EV Floor)': min_odds,
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
                
                # Multi-Pool Scenario Evaluation
                all_horses_in_race = sorted(data_df['Horse No'].tolist())
                stake_lookup = dict(zip(dutch_df['Bet Code'], dutch_df['Suggested Stake ($)']))
                odds_lookup = dict(zip(dutch_df['Bet Code'], dutch_df['Live Odds']))

                scenario_profits = []
                for h1 in all_horses_in_race:
                    for h2 in all_horses_in_race:
                        if h1 == h2:
                            continue
                        
                        win_code = f"WIN #{h1}"
                        q_code = f"Q {min(h1, h2)}-{max(h1, h2)}"
                        
                        payout = 0.0
                        if win_code in stake_lookup and stake_lookup[win_code] > 0:
                            payout += stake_lookup[win_code] * odds_lookup[win_code]
                        if q_code in stake_lookup and stake_lookup[q_code] > 0:
                            payout += stake_lookup[q_code] * odds_lookup[q_code]
                        
                        if payout > 0:
                            profit = payout - actual_total_stake
                            scenario_profits.append(profit)

                if scenario_profits:
                    min_floor_profit = min(scenario_profits)
                    max_total_profit = max(scenario_profits)
                else:
                    min_floor_profit = 0.0
                    max_total_profit = 0.0

                min_payout = min_floor_profit + actual_total_stake
                min_roi_pct = (min_floor_profit / actual_total_stake * 100.0) if actual_total_stake > 0 else 0
                max_roi_pct = (max_total_profit / actual_total_stake * 100.0) if actual_total_stake > 0 else 0

                st.subheader("🎯 Execution Summary (HK$10 Units)")
                
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Actual Total Bet", f"${actual_total_stake}")
                m2.metric("Min Floor Payout", f"${min_payout:.1f}")
                m3.metric("Min Floor Profit", f"${min_floor_profit:.1f}", delta=f"{min_roi_pct:.1f}% Min ROI")
                m4.metric("Max Total Profit", f"${max_total_profit:.1f}", delta=f"{max_roi_pct:.1f}% Max ROI" if max_total_profit > min_floor_profit else None)
                m5.metric("Dutch Book Overround", f"{(inv_odds_sum * 100.0):.1f}%")

                st.dataframe(
                    dutch_df[['Bet Code', 'Type', 'Live Odds', 'Min Odds (EV Floor)', 'Value Check', 'Bet Ratio (%)', 'Suggested Stake ($)', 'Est Payout ($)']],
                    hide_index=True,
                    use_container_width=True
                )

                if any(dutch_df['Live Odds'] < dutch_df['Min Odds (EV Floor)']):
                    st.warning("⚠️ One or more selected bets are below your Minimum Acceptable Odds (EV Floor). Consider unchecking overvalued legs in Section 2.")
