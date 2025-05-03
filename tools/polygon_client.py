import requests
import logging
import pandas as pd
from polygon import RESTClient
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================== #
# ===============  PolygonIO Tools  ============= #
# =============================================== #
class PolygonTools:
    def __init__(self, api_key):
        self.api_key = api_key
        self.client = RESTClient(api_key=self.api_key)
        
    def fetch_all_tickers(self):
        """
        Get all tickers from Polygon.
        Used in: extractor.py
        """
        # Get all tickers - using list comprehension for better performance
        ticker_list = []
        market_type = "stocks"  # can be stocks, crypto, fx

        # Fetch all tickers without pagination since next_token parameter is not supported
        try:
            tickers_response = self.client.list_tickers(
                market=market_type,
                active=True,
                limit=1000  # max limit per request
            )
            
            # Filter and extract only common stocks (CS) and exchange in XNYS, XNAS, XAMS 
            ticker_list.extend([{
                'symbol': ticker.ticker,
                'name': ticker.name,
                'market': ticker.market,
                'type': ticker.type,
                'active': ticker.active,
                'primary_exchange': ticker.primary_exchange,
                'currency_name': ticker.currency_name,
            } for ticker in tickers_response if ticker.type in ['CS', 'ADRC'] and ticker.primary_exchange in ['XNYS', 'XNAS', 'XAMS']])
            
            # Create DataFrame directly from the filtered list
            df = pd.DataFrame(ticker_list)
            print(f"PolygonTools: Retrieved {len(ticker_list)} common stocks")
            return df['symbol']
            
        except Exception as e:
            print(f"PolygonTools: Error fetching tickers: {e}")
            
            # Fallback to get_tickers method if available
            try:
                tickers = self.client.get_tickers(market=market_type, active=True, limit=1000)
                ticker_list = [{
                    'symbol': ticker.ticker,
                    'name': ticker.name,
                    'market': ticker.market,
                    'type': ticker.type,
                    'active': ticker.active,
                    'primary_exchange': ticker.primary_exchange,
                    'currency_name': ticker.currency_name,
                } for ticker in tickers if ticker.type == 'CS']
                df = pd.DataFrame(ticker_list)
                print(f"PolygonTools: Retrieved {len(ticker_list)} common stocks using fallback method")
                return df['symbol']
            except Exception as e2:
                print(f"PolygonTools: Fallback method also failed: {e2}")
    
    def fetch_meta(self, ticker: str):
        """
        Fetch meta data for a given ticker.
        Used in: extractor.py
        """
        # API parameters
        params = {
            'ticker': ticker,
            'apiKey': self.api_key,
        }

        # Make API request
        url = "https://api.polygon.io/v3/reference/tickers/"
        response = requests.get(url, params=params)

        # Check response status
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}")

        try:
            response_json = response.json()
            return response_json['results'][0]
        except requests.exceptions.JSONDecodeError as e:
            raise Exception(f"Failed to decode JSON response: {str(e)}")
        
    def fetch_ticker_ohlcv(self, ticker: str, start_date: str, end_date: str):
        """
        Fetch OHLCV data for a given ticker.
        Used in: extractor.py
        """
        try:
            params = {
                'multiplier': 1,
                'timespan': 'day',
                'adjusted': False,
                'sort': 'asc',
                'apiKey': self.api_key
            }
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"
            response = requests.get(url, params=params)
            response_json = response.json()
            
            return response_json['results']
        
        except Exception as e:
            logging.error(f"PolygonTools: Error fetching OHLCV data for {ticker}: {e}")
            return None

if __name__ == "__main__":
    polygon_client = PolygonTools(api_key=os.getenv('POLYGON_API_KEY'))
    # print(polygon_client.fetch_all_tickers())
    print(polygon_client.fetch_ticker_ohlcv('AAPL', '2025-03-28', '2025-03-28'))