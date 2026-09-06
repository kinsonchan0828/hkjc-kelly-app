import json
import requests
from typing import Dict, Any, Optional, List
from playwright.sync_api import sync_playwright

# ==============================================================================
# METHOD 1: Direct API Fetcher (Lightweight & Fast)
# ==============================================================================

class HKJCApiClient:
    """
    Direct API client with custom headers, query splitting, and optional proxy support.
    """
    def __init__(self, proxy_url: Optional[str] = None):
        """
        :param proxy_url: Optional Hong Kong proxy (e.g. 'http://user:pass@hk-proxy.com:8080')
                          to bypass HKJC geo-blocking restrictions.
        """
        self.session = requests.Session()
        
        # Emulate browser headers to pass basic WAF filtering
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
        """
        Fetches odds for specified types. Capped at 2-3 types per request 
        to avoid HKJC DOWNSTREAM_SERVICE_ERROR.
        """
        url = "https://bet.hkjc.com/racing/api/getOdds"
        
        params = {
            'date': date_str,                 # Format: YYYY-MM-DD
            'venue': venue,                   # 'ST' (Shatin) or 'HV' (Happy Valley)
            'raceNo': race_no,                # Race number (e.g. 1)
            'types': ','.join(odds_types)     # Maximum ~2-3 types per query
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[API Error] Failed fetching {odds_types}: {e}")
            return None

    def get_full_race_odds(self, date_str: str, venue: str, race_no: int) -> Dict[str, Any]:
        """
        Splits queries for Win/Place and Quinella markets into separate requests 
        and merges the payloads.
        """
        # Batch 1: Win (WIN) & Place (PLA)
        wp_data = self.fetch_odds_batch(date_str, venue, race_no, ['WIN', 'PLA'])
        
        # Batch 2: Quinella (QIN) & Quinella Place (QPL)
        wpq_data = self.fetch_odds_batch(date_str, venue, race_no, ['QIN', 'QPL'])
        
        return {
            'win_place': wp_data,
            'quinella_place': wpq_data
        }


# ==============================================================================
# METHOD 2: Playwright Network Interceptor (Robust Fallback for SPA/Anti-Bot)
# ==============================================================================

def intercept_hkjc_web_odds(target_urls: List[str], proxy_config: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Launches a headless browser to open HKJC web pages and captures the background 
    JSON/GraphQL network responses emitted by the client application.
    """
    captured_payloads = []

    with sync_playwright() as p:
        browser_args = {
            'headless': True,
            'args': ['--no-sandbox', '--disable-setuid-sandbox']
        }
        if proxy_config:
            browser_args['proxy'] = proxy_config

        browser = p.chromium.launch(**browser_args)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="zh-HK"
        )
        page = context.new_page()

        # Intercept network responses dynamically
        def on_response(response):
            content_type = response.headers.get("content-type", "")
            # Intercept background API responses (GraphQL or JSON)
            if "application/json" in content_type or "graphql" in response.url:
                try:
                    data = response.json()
                    captured_payloads.append({
                        "source_url": response.url,
                        "data": data
                    })
                    print(f"[Intercepted] JSON payload from: {response.url[:80]}...")
                except Exception:
                    pass

        page.on("response", on_response)

        for url in target_urls:
            print(f"Opening page: {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)  # Wait for background polling to register

        browser.close()

    return captured_payloads


# ==============================================================================
# Usage Example
# ==============================================================================

if __name__ == "__main__":
    RACE_DATE = "2026-09-06"
    VENUE_CODE = "ST"
    RACE_NUM = 1

    # Option A: Direct API fetch with query splitting
    print("--- Method 1: Direct API Call ---")
    # Replace None with 'http://proxy-ip:port' if running from outside Hong Kong
    api_client = HKJCApiClient(proxy_url=None) 
    race_odds = api_client.get_full_race_odds(RACE_DATE, VENUE_CODE, RACE_NUM)
    print("Fetched API Data Keys:", list(race_odds.keys()))

    # Option B: Playwright web page interception fallback
    print("\n--- Method 2: Headless Network Interception ---")
    urls_to_scrape = [
        f"https://bet.hkjc.com/ch/racing/wp/{RACE_DATE}/{VENUE_CODE}/{RACE_NUM}",
        f"https://bet.hkjc.com/ch/racing/wpq/{RACE_DATE}/{VENUE_CODE}/{RACE_NUM}"
    ]
    
    # Pass proxy dict if running outside HK: {'server': 'http://hk-proxy-ip:port'}
    payloads = intercept_hkjc_web_odds(urls_to_scrape, proxy_config=None)
    print(f"Total network JSON responses captured: {len(payloads)}")
