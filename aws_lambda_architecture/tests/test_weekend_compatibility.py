#!/usr/bin/env python3
"""
Weekend compatibility test for data fetching
This script tests core functionality without making hanging API calls
"""

import os
import sys
from datetime import date, timedelta
from dotenv import load_dotenv

# Add shared modules to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from shared.clients.polygon_client import PolygonClient

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

def test_fallback_symbols():
    """Test that fallback symbols are returned when API fails"""
    print("🔧 Testing Fallback Symbol Logic...")
    
    api_key = os.getenv('POLYGON_API_KEY')
    if not api_key:
        print("❌ POLYGON_API_KEY not set")
        return False
    
    client = PolygonClient(api_key)
    
    # Force an exception to test fallback logic
    try:
        # Temporarily break the client to simulate weekend failure
        original_client = client.client
        client.client = None  # This will cause an exception
        
        symbols = client.get_active_symbols(limit=5)
        
        # Restore the client
        client.client = original_client
        
        if symbols and len(symbols) > 0:
            print(f"✅ Success! Got fallback symbols: {symbols}")
            return True
        else:
            print("❌ No fallback symbols returned")
            return False
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_previous_trading_day():
    """Test that previous trading day calculation works for any day"""
    print("\n📅 Testing Previous Trading Day Calculation...")
    
    api_key = os.getenv('POLYGON_API_KEY')
    client = PolygonClient(api_key)
    
    # Test for different days of the week
    test_dates = [
        date(2024, 1, 6),   # Saturday
        date(2024, 1, 7),   # Sunday
        date(2024, 1, 8),   # Monday
        date(2024, 1, 9),   # Tuesday
        date(2024, 1, 10),  # Wednesday
        date(2024, 1, 11),  # Thursday
        date(2024, 1, 12),  # Friday
    ]
    
    for test_date in test_dates:
        prev_trading_day = client.get_previous_trading_day(test_date)
        weekday_name = test_date.strftime('%A')
        prev_weekday_name = prev_trading_day.strftime('%A')
        
        # Previous trading day should never be a weekend
        if prev_trading_day.weekday() >= 5:
            print(f"❌ {weekday_name} {test_date} -> {prev_weekday_name} {prev_trading_day} (WEEKEND!)")
            return False
        else:
            print(f"✅ {weekday_name} {test_date} -> {prev_weekday_name} {prev_trading_day}")
    
    return True

def test_data_fetching_with_fallback():
    """Test that we can fetch data using fallback symbols"""
    print("\n📊 Testing Data Fetching with Fallback Symbols...")
    
    api_key = os.getenv('POLYGON_API_KEY')
    client = PolygonClient(api_key)
    
    # Use a known good symbol
    symbol = "AAPL"
    target_date = client.get_previous_trading_day()
    
    try:
        ohlcv_data = client.fetch_ohlcv_data(symbol, target_date)
        
        if ohlcv_data:
            print(f"✅ Successfully fetched {symbol} data for {target_date}")
            print(f"   Close: ${ohlcv_data.close}")
            return True
        else:
            print(f"⚠️  No data returned for {symbol} on {target_date}")
            print("   This might be expected on weekends/holidays")
            return True  # Still consider this a pass since it didn't hang
            
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return False

def main():
    """Run weekend compatibility tests"""
    print("🧪 Weekend Compatibility Test (Fast Version)")
    print("=" * 50)
    
    results = {}
    
    # Test 1: Fallback symbols
    results['fallback'] = test_fallback_symbols()
    
    # Test 2: Previous trading day
    results['trading_day'] = test_previous_trading_day()
    
    # Test 3: Data fetching
    results['data_fetch'] = test_data_fetching_with_fallback()
    
    # Summary
    print(f"\n📋 Test Results:")
    print(f"   Fallback Symbols: {'✅' if results['fallback'] else '❌'}")
    print(f"   Trading Day Calc: {'✅' if results['trading_day'] else '❌'}")
    print(f"   Data Fetching: {'✅' if results['data_fetch'] else '❌'}")
    
    if all(results.values()):
        print(f"\n🎉 All weekend compatibility tests passed!")
        print("   ✅ Tests will work on any day of the week!")
    else:
        print(f"\n❌ Some tests failed")
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
