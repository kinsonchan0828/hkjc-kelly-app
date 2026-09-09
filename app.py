import streamlit as st
import pandas as pd

# ==============================================================================
# Page Configuration
# ==============================================================================
st.set_page_config(page_title="HKJC Win-Only Quantitative Betting Engine", layout="wide")

# ==============================================================================
# Helper Function: Parse Custom HKJC Google Sheet Structure
# ==============================================================================
def parse_custom_sheet(df_raw):
    """
    Parses a multi-race sheet with structure:
    Col A: 'R1' (Race) or Horse No (1-14)
    Col B: Race details (e.g. 'HV A 1200') or Horse Name
    Col C: 'Win%' header or Win Probability (0.15 or 15)
    """
    race_data = []
    current_race = "Race 1"
    
    if df_raw.shape[1] < 3:
        return None, "Sheet must have at least 3 columns (Col A, Col B, Col C)."

    for idx, row in df_raw.iterrows():
        col_a = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        col_b = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        col_c = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""

        if not col_a and not col_b and not col_c:
            continue

        if col_a.upper().startswith('R') and not col_a.isdigit():
            race_info = f"{col_a}"
            if col_b and col_b.lower() != 'nan':
                race_info += f" - {col_b}"
            current_race = race_info
            continue

        try:
            horse_no = int(float(col_a))
            if 1 <= horse_no <= 14:
                horse_name = col_b if col_b and col_b.lower() != 'nan' else f"Horse {horse_no}"
                
                try:
                    clean_c = col_c.replace('%', '').strip()
                    win_val = float(clean_c)
                    
                    if 0 < win_val <= 1.0:
                        win_pct = round(win_val * 100.0, 2)
                    else:
                        win_pct = round(win_val, 2)
                except ValueError:
                    continue

                race_data.append({
                    'Race': current_race,
                    'Horse No': horse_no,
                    'Horse Name': horse_name,
                    'Model Win %': win_pct
                })
        except ValueError:
            continue

    if not race_data:
        return None, "No valid horse data found. Check sheet columns and formatting."
        
    return pd.DataFrame(race_data), None

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

# Hard 5% bankroll cap ceiling
max_race_stake = float(bankroll * 0.05)

st.sidebar.metric(
    label="Max Allowed Stake (5% Cap)",
    value=f"${max_race_stake:.2f}"
)

st.sidebar.markdown("""
---
**Active Risk Rules:**
* 🎯 **Win-Only Mode:** Exotic pools disabled.
* 🛡️ **Hard Cap Limit:** Maximum 5% bankroll per race.
* 🛑 **Price Floor:** Auto-reject bets below Minimum Odds (+5% EV).
* 💵 **HKJC Rule:** Stakes rounded to nearest HK$10.
""")

# ==============================================================================
# Main App Header
# ==============================================================================
st.title("🏇 HKJC Win-Only Decision Support Engine")
st.caption("Hybrid System: Math Model Price Floor + Human Trainer Audit + Constrained Dutching")

# ==============================================================================
# PART 1 & 2: Data Input, Minimum Acceptable Odds, & Trainer Pruning
# ==============================================================================
st.header("1. Model Input & Trainer Audit")

tab_sheet, tab_manual = st.tabs(["📊 Import Google Sheet / CSV", "✏️ Manual Input"])

data_df = None

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
            st.error(f"Error loading Google Sheet URL. Ensure sheet is published/shared publicly as CSV: {e}")

    if raw_df is not None:
        parsed_df, err = parse_custom_sheet(raw_df)
        if err:
            st.error(err)
        else:
            races_available = parsed_df['Race'].unique()
            selected_race = st.selectbox("🎯 Select Race to Analyze:", races_available)
            data_df = parsed_df[parsed_df['Race'] == selected_race][['Horse No', 'Horse Name', 'Model Win %']].reset_index(drop=True)

with tab_manual:
    if data_df is None:
        default_data = pd.DataFrame({
            'Horse No': [1, 2, 3, 4, 5, 6],
            'Horse Name': ['Romantic Warrior', 'California Spangle', 'Golden Sixty', 'Voyage Bubble', 'Beauty Eternal', 'Straight Arron'],
            'Model Win %': [35.0, 25.0, 18.0, 12.0, 7.0, 3.0]
        })
        data_df = st.data_editor(default_data, num_rows="dynamic", key="manual_editor")

if data_df is not None and not data_df.empty:
    df_calc = data_df.copy()
    df_calc['Win Prob (Dec)'] = df_calc['Model Win %'] / 100.0
    df_calc['Fair Odds'] = df_calc['Win Prob (Dec)'].apply(lambda p: round(1.0 / p, 2) if p > 0 else 999.0)
    df_calc['Min Odds (+5% EV)'] = df_calc['Win Prob (Dec)'].apply(lambda p: round(1.05 / p, 2) if p > 0 else 999.0)

    st.subheader("Price Floor & Trainer Audit Table")
    st.write("Uncheck **Keep** to eliminate horses that fail your trainer audit or expert judgment.")

    if 'Keep' not in df_calc.columns:
        df_calc.insert(0, 'Keep', True)

    edited_df = st.data_editor(
        df_calc[['Keep', 'Horse No', 'Horse Name', 'Model Win %', 'Fair Odds', 'Min Odds (+5% EV)']],
        disabled=['Horse No', 'Horse Name', 'Model Win %', 'Fair Odds', 'Min Odds (+5% EV)'],
        hide_index=True,
        use_container_width=True
    )

    contenders = edited_df[edited_df['Keep'] == True].copy()
    st.info(f"Active Contenders Remaining: **{len(contenders)} / {len(edited_df)}**")

# ==============================================================================
# PART 3: Dutching Calculator & HKJC Execution
# ==============================================================================
    st.divider()
    st.header("2. Live Odds & Dutching Calculator")

    if contenders.empty:
        st.warning("No horses selected. Keep at least one horse checked in the audit table above.")
    else:
        st.write("Enter the **Live Market Odds** for your shortlisted horses:")

        with st.form("dutching_form"):
            live_odds_input = {}
            cols = st.columns(min(len(contenders), 4))
            
            for idx, (_, row) in enumerate(contenders.iterrows()):
                col = cols[idx % 4]
                horse_key = f"horse_{row['Horse No']}"
                default_min = float(row['Min Odds (+5% EV)'])
                
                live_odds_input[row['Horse No']] = col.number_input(
                    f"#{row['Horse No']} {row['Horse Name']} (Min: {default_min})",
                    min_value=1.01,
                    value=default_min,
                    step=0.1,
                    key=horse_key
                )
            
            # Allows user manual entry up to 5% bankroll limit
            custom_stake = st.number_input(
                f"Target Total Race Stake ($) — Max Allowed: ${max_race_stake:.2f}",
                min_value=10.0,
                max_value=max_race_stake,
                value=max_race_stake,
                step=10.0,
                help=f"Defaults to 5% bankroll cap (${max_race_stake:.2f}). You can reduce this amount (e.g. $200), but cannot exceed the maximum cap."
            )

            calculate_btn = st.form_submit_button("Calculate Dutching Execution")

        if calculate_btn:
            dutch_data = []
            inv_odds_sum = 0.0

            for _, row in contenders.iterrows():
                h_no = row['Horse No']
                h_name = row['Horse Name']
                min_odds = row['Min Odds (+5% EV)']
                curr_odds = live_odds_input[h_no]
                
                inv_odds_sum += (1.0 / curr_odds)
                
                is_value = curr_odds >= min_odds
                dutch_data.append({
                    'Horse No': h_no,
                    'Horse Name': h_name,
                    'Model Win %': row['Model Win %'],
                    'Min Odds (+5% EV)': min_odds,
                    'Live Odds': curr_odds,
                    'Value Check': "✅ Value" if is_value else "❌ Overvalued",
                    'Inv Odds': 1.0 / curr_odds
                })

            dutch_df = pd.DataFrame(dutch_data)

            dutch_df['Bet Ratio (%)'] = (dutch_df['Inv Odds'] / inv_odds_sum) * 100.0
            raw_stake = (dutch_df['Bet Ratio (%)'] / 100.0) * custom_stake

            # Round stakes to nearest HK$10
            dutch_df['Suggested Stake ($)'] = raw_stake.apply(lambda s: max(10, int(round(s / 10.0) * 10)) if s >= 5 else 0)

            actual_total_stake = int(dutch_df['Suggested Stake ($)'].sum())
            dutch_df['Est Payout ($)'] = (dutch_df['Suggested Stake ($)'] * dutch_df['Live Odds']).round(1)
            
            min_payout = dutch_df[dutch_df['Suggested Stake ($)'] > 0]['Est Payout ($)'].min() if actual_total_stake > 0 else 0
            net_profit = min_payout - actual_total_stake
            roi_pct = (net_profit / actual_total_stake * 100.0) if actual_total_stake > 0 else 0

            st.subheader("🎯 Execution Summary (HK$10 Units)")
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Actual Total Bet", f"${actual_total_stake}")
            m2.metric("Min Est. Payout", f"${min_payout:.1f}")
            m3.metric("Est. Net Profit", f"${net_profit:.1f}", delta=f"{roi_pct:.1f}% ROI")
            m4.metric("Dutch Book Overround", f"{(inv_odds_sum * 100.0):.1f}%")

            st.dataframe(
                dutch_df[['Horse No', 'Horse Name', 'Live Odds', 'Min Odds (+5% EV)', 'Value Check', 'Bet Ratio (%)', 'Suggested Stake ($)', 'Est Payout ($)']],
                hide_index=True,
                use_container_width=True
            )

            if any(dutch_df['Live Odds'] < dutch_df['Min Odds (+5% EV)']):
                st.warning("⚠️ One or more selected horses are currently below your Minimum Acceptable Odds (+5% EV). Uncheck overvalued runners in the audit table if you want to exclude them.")
