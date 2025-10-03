import requests
import logging

logger = logging.getLogger(__name__)

class FMPClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/stable"

    def fetch_profile(self, symbol: str):
        try:
            url = f"{self.base_url}/profile?symbol={symbol}&apikey={self.api_key}"
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"FMP API returned status {response.status_code} for {symbol}")
                return {}
            
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            else:
                logger.warning(f"FMP API returned empty or invalid data for {symbol}")
                return {}
        except Exception as e:
            logger.error(f"Error fetching FMP profile for {symbol}: {e}")
            return {}
if __name__ == "__main__":
    fmp_client = FMPClient(api_key="nsxezOY5RgF6NTyx6n8UWsBoi9WH0cMq")
    print(fmp_client.fetch_profile("AAPL").get("marketCap"))
    
    
    