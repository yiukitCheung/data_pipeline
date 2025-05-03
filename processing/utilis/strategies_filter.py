import pandas as pd
import numpy as np
from pymongo import MongoClient

class DailyTradingStrategy:
    def __init__(self, mongo_config, start_date=None, sandbox_mode=False, initial_capital=10000, aggressive_split=1.0):
        self.protected = None
        self.peak_profit_pct = None
        self.peak_profit = None
        self.trades = []
        self.current_trade = {"conservative": {}, "aggressive": {}}
        self.start_date = start_date if sandbox_mode else '2024-01-01'

        self.aggressive_capital = initial_capital * aggressive_split
        self.conservative_capital = initial_capital * (1.0 - aggressive_split)
        self.capital_split = aggressive_split
        self.mongo_config = mongo_config
        self.dynamic_protection = False

        # Initialize MongoDB client and collections
        self.client = MongoClient(self.mongo_config['url'])
        self.db = self.client[self.mongo_config['db_name']]
        self.data_collection = self.db[self.mongo_config['process_collection_name']]
        self.alert_collection = self.db[self.mongo_config['alert_collection_name']['long_term']]
        self.stock_candidates = pd.DataFrame(list(self.db[self.mongo_config['candidates_collection_name']['long_term']] \
                                                .find({'date': {'$gte': pd.to_datetime(self.start_date)}},
                                                        {'_id': 0})))
        # Load data and alerts
        self.df = pd.DataFrame(list(self.data_collection. \
                                    find({'date': {'$gte': pd.to_datetime(self.start_date)},
                                        'instrument': 'equity',
                                        'interval': 1},
                                        {'_id': 0}))) \
            .sort_values(by=['symbol', 'date'])

        self.alert_df = self.get_alert_dataframe()

    def get_alert_dataframe(self):
        data_dict = list(self.alert_collection.find({'date': {'$gte': pd.to_datetime(self.start_date)},
                                                    'instrument': 'equity'}, {'_id': 0}))
        for row in data_dict:
            if 'alerts' in row and 'momentum_alert' in row['alerts']:
                row['momentum_alert'] = row['alerts']['momentum_alert']['alert_type']
            if 'alerts' in row and 'velocity_alert' in row['alerts']:
                row['velocity_alert'] = row['alerts']['velocity_alert']['alert_type']
            if 'alerts' in row and '169ema_touched' in row['alerts']:
                row['touch_type'] = row['alerts']['169ema_touched']['type']
                row['count'] = row['alerts']['169ema_touched']['count']
            elif 'alerts' in row and '13ema_touched' in row['alerts']:
                row['touch_type'] = row['alerts']['13ema_touched']['type']
                row['count'] = row['alerts']['13ema_touched']['count']
            else:
                row['touch_type'] = np.nan
        return pd.DataFrame(data_dict).drop(columns=['alerts'])

    # Execute both types of trades
    def execute_critical_trades(self):

        for idx, date in enumerate(self.df['date'].unique()):
            # Handle aggressive trades
            if self.aggressive_capital >= 0:
                self.manage_trade("aggressive", date, idx)

    def manage_trade(self, trade_type, date, idx):
        if len(self.current_trade[trade_type]) != 0:
            # Step 1: Get the alert data and processed data for the ongoing trade
            stock = self.current_trade[trade_type]["symbol"]

            tracked_processed_stock = self.df[(self.df['symbol'] == stock) & (self.df['date'] == date)]
            tracked_alert_stock = self.alert_df[(self.alert_df['symbol'] == stock) &
                                                (self.alert_df['date'] == date) &
                                                (self.alert_df['interval'] == 1)]

            if tracked_alert_stock.empty:
                return

            # Step 2 : Aggressive selling rule: Sell if the stock fails to maintain velocity or inverse hammer
            if trade_type == "aggressive":
                self.protected = False

                # Initial protection flag and profit tracking
                if not self.dynamic_protection:
                    # Track current profit or loss for the stock
                    tracked_profit_loss = self.track_profit_loss(trade_type, tracked_processed_stock, sell=False)
                    tracked_profit_pct = (tracked_profit_loss - self.aggressive_capital) / self.aggressive_capital
                    # Activate dynamic protection if profit reaches or exceeds 10%
                    if tracked_profit_pct >= 0.3:
                        print(
                            f"{stock} in {tracked_processed_stock['date'].iloc[0]} needs attention in profit protection | current profit rate: {tracked_profit_pct}")
                        self.dynamic_protection = True
                        self.peak_profit = tracked_profit_loss  # Set the initial peak profit
                        self.peak_profit_pct = tracked_profit_pct
                    else:
                        self.dynamic_protection = False

                # Dynamic protection logic if the flag is activated
                elif self.dynamic_protection:
                    # Track updated profit or loss
                    tracked_profit_loss = self.track_profit_loss(trade_type, tracked_alert_stock, sell=False)
                    tracked_profit_pct = (tracked_profit_loss - self.aggressive_capital) / self.aggressive_capital

                    print(
                        f"{tracked_processed_stock['symbol'].iloc[0]}| {tracked_processed_stock['date'].iloc[0]}: current profit: {tracked_profit_loss} | current profit rate: {tracked_profit_pct}")

                    # Update the peak profit if the profit is increasing
                    if tracked_profit_loss > self.peak_profit:
                        self.peak_profit = tracked_profit_loss
                        self.peak_profit_pct = tracked_profit_pct
                        print(
                            f"New peak profit updated: {tracked_processed_stock['symbol'].iloc[0]} earns {self.peak_profit}")

                    # Sell if the profit has declined by 50% from the peak profit
                    if self.peak_profit_pct - tracked_profit_pct >= self.peak_profit_pct * 0.5:
                        print(
                            f"{stock} Profit declined by 50% from the peak. Initiating sell.| Peak profit rate: {self.peak_profit_pct} vs. Current profit rate: {tracked_profit_pct}")
                        self.track_profit_loss(trade_type, tracked_alert_stock, sell=True)
                        self.dynamic_protection = False  # Reset dynamic protection after selling
                        self.protected = True

                if not self.protected:
                    # Sell if bearish signals
                    if tracked_alert_stock['velocity_alert'].iloc[0] == 'velocity_loss':
                        self.track_profit_loss(trade_type, tracked_processed_stock, sell=True)

                    # Sell if testing duration ends
                    if idx == len(self.df['date'].unique()) - 1:
                        self.track_profit_loss(trade_type, tracked_alert_stock, sell=True)
                else:
                    return

        elif len(self.current_trade[trade_type]) == 0:
            # Step 1: Get the stock candidate for the day
            cur_stock_pick = self.stock_candidates.iloc[idx]
            # Step 2: Find the stock based on the desired alert
            stock = self.find_alert(trade_type, cur_stock_pick, desired_alerts=['accelerating'])
            # Step 3: Buy the stock if found
            if not stock:
                return
            # Step 3.1: Aggressive trade: Test buy with 10% of aggressive capital (Conservative trade will buy full)
            # if trade_type == "aggressive":
            #     self.current_trade[trade_type]["testing_buy"] = True  # Flag for testing buy
            #     self.current_trade[trade_type]["testing_capital"] = self.aggressive_capital * 0.1  # 10% of aggressive capital
            #     self.aggressive_capital *= 0.9  # Hold back 90% for potential all-in later

            # Step 4: Update the current trade
            entry_date = self.df['date'].iloc[idx + 1]
            self.current_trade[trade_type]["entry_price"] = \
            self.df[(self.df['symbol'] == stock) & (self.df['date'] == entry_date)]['open'].iloc[0]
            self.current_trade[trade_type]["entry_date"] = \
            self.df[(self.df['symbol'] == stock) & (self.df['date'] == entry_date)]['date'].iloc[0]
            self.current_trade[trade_type]["symbol"] = stock

    # Separate method to handle selling a stock
    def track_profit_loss(self, trade_type, tracked_processed_stock, sell=False):
        # Step 1: Calculate profit/loss rate
        exit_price = tracked_processed_stock['close'].iloc[0]
        entry_price = self.current_trade[trade_type]['entry_price']
        profit_rate = (exit_price / entry_price) - 1
        if sell:
            # Step 2: Update the capital based on the profit rate and trade type
            if trade_type == "aggressive":
                # # Check if it's a testing buy
                # if self.current_trade[trade_type]['testing_buy'] == True:
                #     # Apply profit rate only to testing buy capital if testing buy
                #     testing_capital = self.current_trade[trade_type]["testing_capital"]
                #     self.aggressive_capital += (testing_capital * (profit_rate + 1))
                # else:
                # Apply profit to full aggressive capital if it's fully invested
                self.aggressive_capital += self.aggressive_capital * profit_rate

            # Save the trade
            self.trades.append({
                "type": trade_type,
                "symbol": self.current_trade[trade_type]["symbol"],
                "Entry_price": entry_price,
                "Entry_date": self.current_trade[trade_type]["entry_date"],
                "Exit_price": exit_price,
                "Exit_date": tracked_processed_stock['date'].iloc[0],
                "profit/loss": f"{profit_rate * 100 :.2f}%",
                "total_conser_asset": self.conservative_capital,
                "total_aggr_asset": self.aggressive_capital,
                "total_asset": self.conservative_capital + self.aggressive_capital
            })

            # Reset current trade
            self.current_trade[trade_type] = {}
        else:
            if trade_type == "conservative":
                return self.conservative_capital + self.conservative_capital * profit_rate
            elif trade_type == "aggressive":
                return self.aggressive_capital + self.aggressive_capital * profit_rate

    def find_alert(self, trade_type, stock_data, desired_alerts: list):
        if trade_type == "aggressive":
            for alert in desired_alerts:
                cur_alert_data = stock_data.loc[alert]
                # Ensure that cur_stock_pick is non-empty and the alert column exists
                if len(cur_alert_data) != 0:
                    return stock_data[alert][0]

    def run_trading_strategy(self):
        self.execute_critical_trades()

    def get_trades(self):
        return pd.DataFrame(self.trades)

    def get_total_return(self):
        total_capital = self.conservative_capital + self.aggressive_capital
        return total_capital
