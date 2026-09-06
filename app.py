import os
import subprocess
import json
import requests
import pandas as pd
import streamlit as st
from typing import Dict, Any, Optional, List
from playwright.sync_api import sync_playwright

# ==============================================================================
# 1. Automatic Playwright Browser Installation for Streamlit Cloud
# ==============================================================================
@st.cache_resource
def install_playwright_browser():
    """Installs the headless Chromium browser binary on Streamlit Cloud startup."""
    try:
        subprocess.run(["playwright", "install", "chromium"], check=True)
    except Exception as e:
        st.error(f"Playwright browser installation failed: {e}")

# Run browser installation check on app load
install_playwright_browser()

# ==============================================================================
# 2. Method 1: Direct API Client (Fast & Lightweight)
# ==============================================================================
class HKJCApiClient:
    """
    Direct API client with custom browser headers, query splitting,
    and proxy support to prevent DOWNSTREAM_SERVICE_ERROR.
    """
    def __init__(self, proxy_url: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': 'https://bet.hkjc.com/ch/racing/',
            'Origin': 'https://bet.hkjc.com',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        })
        if proxy_url:
            self.session.proxies = {'http': proxy_url, 'https': proxy_url}

    def fetch_odds_batch(self, date_str: str, venue: str, race_no: int, odds_types: List[str]) -> Optional[Dict[str, Any]]:
        url = "https://bet.hkjc.com/racing/api/getOdds"
        params = {
            'date': date_str,
            'venue': venue,
            'raceNo': race_no,
            'types': ','.join(odds_types)
        }
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.warning(f"API Error fetching {odds_types}: {e}")
            return None

    def get_full_race_odds(self, date_str: str, venue: str, race_no: int) -> Dict[str, Any]:
        wp_data = self.fetch_odds_batch(date_str, venue, race_no, ['WIN', 'PLA'])
        wpq_data = self.fetch_odds_batch(date_str, venue, race_no, ['QIN', 'QPL'])
        return {
            'win_place': wp_data,
            'quinella_place': wpq_data
        }

# ==============================================================================
# 3. Method 2: Headless Network Interceptor (Container-Safe Playwright)
# ==============================================================================
def intercept_hkjc_web_odds(target_urls: List[str], proxy_config: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Launches Playwright with container-safe memory flags to capture background network responses.
    """
    captured_payloads = []

    with sync_playwright() as p:
        browser_args = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',  # Prevents Streamlit Cloud shared memory crashes
                '--disable-gpu',
                '--single-process'          # Lowers RAM footprint under Streamlit Cloud 1GB limit
            ]
        }
        if proxy_config:
            browser_args['proxy'] = proxy_config

        browser = p.chromium.launch(**browser_args)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="zh-HK"
        )
        page = context.new_page()

        def on_response(response):
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type or "graphql" in response.url:
                try:
                    data = response.json()
                    captured_payloads.append({
                        "source_url": response.url,
                        "data": data
                    })
                except Exception:
                    pass

        page.on("response", on_response)

        for url in target_urls:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(3000)  # Wait for background AJAX/GraphQL calls
            except Exception as e:
                st.write(f"Warning while loading {url}: {e}")

        browser.close()

    return captured_payloads

# ==============================================================================
# 4. Streamlit User Interface
# ==============================================================================
st.set_page_config(page_title="HKJC Live Odds Fetcher", layout="wide")
st.title("🏇 HKJC Live Odds Fetcher")

# Input controls
col1, col2, col3 = st.columns(3)
with col1:
    race_date = st.date_input("Race Date").strftime("%Y-%m-%d")
with col2:
    venue = st.selectbox("Venue", options=["ST", "HV"], format_func=lambda x: "Sha Tin (ST)" if x == "ST" else "Happy Valley (HV)")
with col3:
    race_num = st.number_input("Race Number", min_value=1, max_value=14, value=1)

proxy_input = st.text_input("Proxy URL (Optional, for HK geo-blocking bypass)", value="", placeholder="http://user:pass@hk-proxy.com:8080")
proxy_url = proxy_input.strip() if proxy_input.strip() else None

st.divider()

# Action buttons
col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button("Fetch via Direct API (Method 1)", use_container_width=True):
        with st.spinner("Fetching odds via HKJC Direct API..."):
            client = HKJCApiClient(proxy_url=proxy_url)
            results = client.get_full_race_odds(race_date, venue, race_num)
            st.subheader("API Data Results")
            st.json(results)

with col_btn2:
    if st.button("Fetch via Headless Interceptor (Method 2)", use_container_width=True):
        with st.spinner("Launching headless browser to intercept odds payloads..."):
            urls = [
                f"https://bet.hkjc.com/ch/racing/wp/{race_date}/{venue}/{race_num}",
                f"https://bet.hkjc.com/ch/racing/wpq/{race_date}/{venue}/{race_num}"
            ]
            proxy_cfg = {'server': proxy_url} if proxy_url else None
            payloads = intercept_hkjc_web_odds(urls, proxy_config=proxy_cfg)
            st.subheader(f"Intercepted Payloads ({len(payloads)} items captured)")
            for i, item in enumerate(payloads):
                with st.expander(f"Payload #{i+1}: {item['source_url'][:70]}..."):
                    st.json(item['data'])
