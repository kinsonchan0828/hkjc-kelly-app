import streamlit as st
import pandas as pd

# ==============================================================================
# Page Configuration
# ==============================================================================
st.set_page_config(page_title="HKJC Win-Only Quantitative Betting Engine", layout="wide")

# ==============================================================================
# Sidebar: Bankroll & Risk Management
# ==============================================================================
st.sidebar.header("💰 Bankroll & Risk Control")

if 'bankroll' not in st.session_state:
    st.session_state.bankroll = 10000.0

bankroll = st.sidebar.number_input(
    "Current Total Bankroll ($)",
    min_value=100.0,
    value=float(st.session_state.bankroll),
    step=500.0,
    key="bankroll_input"
)
st.session_state.bankroll = bankroll

# Calculate strict 5% bankroll cap
max_race_stake = bankroll * 0.05

st.sidebar.metric(
    label="Max Race Stake (5% Cap)",
    value=f"${max_race_stake:.2f}"
)

st.sidebar.markdown("""
---
**Risk Rules Enabled:**
* 🎯 **Win-Only Mode:** Exotic pools disabled.
* 🛡️ **Hard Cap:** Total stake capped at 5% of bankroll.
* 🛑 **Price Floor:** Auto-reject bets below Minimum Odds (+5% EV).
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

tab_sheet, tab_manual = st.tabs(["📊 Import from Google Sheet / CSV", "✏️ Manual Input"])

data_df = None

with tab_sheet:
    sheet_url = st.text_input("Google Sheet Public CSV URL or File Upload", placeholder="https://docs.google.com/spreadsheets/d/.../export?format=csv")
    uploaded_file = st.file_uploader("Or upload CSV file", type=["csv"])
    
    if uploaded_file is not None:
        try:
            data_df = pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading uploaded file: {e}")
    elif sheet_url.strip():
        try:
            data_df = pd.read_csv(sheet_url.strip())
        except Exception as e:
            st.error(f"Error loading Google Sheet URL. Ensure the sheet is shared as 'Anyone with link can view': {e}")

with tab_manual:
    if data_df is None:
        default_data = pd.DataFrame({
            'Horse No': [1, 2, 3, 4, 5, 6],
            'Horse Name': ['Romantic Warrior', 'California Spangle', 'Golden Sixty', 'Voyage Bubble', 'Beauty Eternal', 'Straight Arron'],
            'Model Win %': [35.0, 25.0, 18.0, 12.0, 7.0, 3.0]
        })
        data_df = st.data_editor(default_data, num_rows="dynamic")

if data_df is not None and not data_df.empty:
    # Ensure standard column naming
    required_cols = ['Horse No', 'Horse Name', 'Model Win %']
    if not all(col in data_df.columns for col in required_cols):
        st.error(f"Data must contain the following columns: {required_cols}")
    else:
        # Calculate Fair Odds and Minimum Acceptable Odds (+5% EV)
        df_calc = data_df.copy()
        df_calc['Win Prob (Dec)'] = df_calc['Model Win %'] / 100.0
        df_calc['Fair Odds'] = df_calc['Win Prob (Dec)'].apply(lambda p: round(1.0 / p, 2) if p > 0 else 999.0)
        
        # Minimum Odds for +5% EV: Required Odds = 1.05 / Win_Probability
        df_calc['Min Odds (+5% EV)'] = df_calc['Win Prob (Dec)'].apply(lambda p: round(1.05 / p, 2) if p > 0 else 999.0)

        st.subheader("Price Floor & Trainer Audit Table")
        st.write("Use the **Keep** column to uncheck/remove 'absurd' bets or horses that fail your trainer intent audit.")

        # Add interactive selection column
        if 'Keep' not in df_calc.columns:
            df_calc.insert(0, 'Keep', True)

        edited_df = st.data_editor(
            df_calc[['Keep', 'Horse No', 'Horse Name', 'Model Win %', 'Fair Odds', 'Min Odds (+5% EV)']],
            disabled=['Horse No', 'Horse Name', 'Model Win %', 'Fair Odds', 'Min Odds (+5% EV)'],
            hide_index=True,
            use_container_width=True
        )

        # Filtered contenders
        contenders = edited_df[edited_df['Keep'] == True].copy()
        
        st.info(f"Active Contenders Remaining: **{len(contenders)} / {len(edited_df)}**")

# ==============================================================================
# PART 3: Dutching Calculator & Execution
# ==============================================================================
        st.divider()
        st.header("2. Live Odds & Dutching Calculator")

        if contenders.empty:
            st.warning("No horses selected. Keep at least one horse checked in the audit table above.")
        else:
            st.write("Enter the **Live Market Odds** for your shortlisted horses to generate Dutching ratios.")

            # Form to enter live market odds
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
                
                custom_stake = st.number_input(
                    "Total Race Stake ($)",
                    min_value=10.0,
                    max_value=float(max_race_stake),
                    value=float(max_race_stake),
                    step=50.0,
                    help="Defaults to your 5% bankroll cap. You can lower this amount, but cannot exceed 5%."
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
                    
                    # Inverse odds sum calculation for Dutching
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

                # Dutching Allocation Logic
                dutch_df['Bet Ratio (%)'] = (dutch_df['Inv Odds'] / inv_odds_sum) * 100.0
                dutch_df['Suggested Stake ($)'] = (dutch_df['Bet Ratio (%)'] / 100.0) * custom_stake
                dutch_df['Suggested Stake ($)'] = dutch_df['Suggested Stake ($)'].round(1)

                # Projected Returns
                projected_payout = (custom_stake / inv_odds_sum) if inv_odds_sum > 0 else 0
                projected_profit = projected_payout - custom_stake
                roi_pct = (projected_profit / custom_stake) * 100.0 if custom_stake > 0 else 0

                st.subheader("🎯 Execution Summary")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Investment", f"${custom_stake:.2f}")
                m2.metric("Projected Payout", f"${projected_payout:.2f}")
                m3.metric("Net Profit", f"${projected_profit:.2f}", delta=f"{roi_pct:.1f}% ROI")
                m4.metric("Dutch Book Overround", f"{(inv_odds_sum * 100.0):.1f}%", delta="Profit Guaranteed" if inv_odds_sum < 1.0 else "High Market Takeout", delta_color="normal" if inv_odds_sum < 1.0 else "inverse")

                st.dataframe(
                    dutch_df[['Horse No', 'Horse Name', 'Live Odds', 'Min Odds (+5% EV)', 'Value Check', 'Bet Ratio (%)', 'Suggested Stake ($)']],
                    hide_index=True,
                    use_container_width=True
                )

                if any(dutch_df['Live Odds'] < dutch_df['Min Odds (+5% EV)']):
                    st.warning("⚠️ One or more selected horses are currently below your Minimum Acceptable Odds (+5% EV). Consider unchecking overvalued runners in the audit table.")
