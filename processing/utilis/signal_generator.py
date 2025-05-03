import pandas as pd
from datetime import datetime
import logging
from pyspark.sql.functions import col, when, lit, sum, count, max
from pyspark.sql.window import Window
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set the logging level to INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Set the logging format
    handlers=[logging.StreamHandler()]  # Add a stream handler to print to console
)

class VegasChannelSignalGenerator:
    """A class to generate trading signals based on alerts and indicators.
    
    Attributes:
        spark (SparkSession): The Spark session
        df (DataFrame): Input DataFrame containing alerts and indicators
        intervals (list): List of intervals to process
        strategy (str): Name of the trading strategy
    """

    def __init__(self, df, intervals):
        self.df = df
        self.intervals = intervals

        self.interval_weights = {interval: idx + 1 if interval != '1' else 1 for idx, interval in enumerate(intervals)}

    def _calculate_weighted_alerts(self, df, interval_condition):
        """Helper method to calculate weighted alerts"""
        df = df.withColumn(
            "interval_weight",
            when(interval_condition, col("interval").cast("int")).otherwise(0)
        )
        
        # Calculate momentum alerts
        df = df.withColumn(
            "weighted_momentum_alert_accelerated",
            when((col("alert_type") == "velocity_status") & (col("signal") == "accelerated"), 
                col("interval_weight")).otherwise(0)
        ).withColumn(
            "weighted_momentum_alert_decelerated",
            when((col("alert_type") == "velocity_status") & (col("signal") == "decelerated"), 
                col("interval_weight")).otherwise(0)
        )
        
        return df

    def _calculate_accumulation_alerts(self, df, interval_condition):
        """Helper method to calculate accumulation alerts"""
        df = df.withColumn(
            "interval_weight",
            when(interval_condition, col("interval").cast("int")).otherwise(0)
        )
        
        df = df.withColumn(
            "weighted_touch_type_resistance",
            when((col("alert_type") == "accumulation") & (col("signal") == "resistance"), 
                col("interval_weight")).otherwise(0)
        ).withColumn(
            "weighted_touch_type_support",
            when((col("alert_type") == "accumulation") & (col("signal") == "support"), 
                col("interval_weight")).otherwise(0)
        )
        
        return df

    def _calculate_velocity_alerts(self, df, interval_condition):
        """Helper method to calculate velocity maintenance alerts"""
        df = df.withColumn(
            "interval_weight",
            when(interval_condition, col("interval").cast("int")).otherwise(0)
        )
        
        df = df.withColumn(
            "weighted_velocity_maintained",
            when((col("alert_type") == "velocity_status") & (col("signal") == "velocity_maintained"), 
                col("interval_weight")).otherwise(0)
        ).withColumn(
            "weighted_velocity_weak",
            when((col("alert_type") == "velocity_status") & (col("signal") == "velocity_weak"), 
                col("interval_weight")).otherwise(0)
        ).withColumn(
            "weighted_velocity_loss",
            when((col("alert_type") == "velocity_status") & (col("signal") == "velocity_loss"), 
                col("interval_weight")).otherwise(0)
        )
        
        return df

    def short_term_trend_signal(self, df):
        """Generate short-term trend signals based on acceleration/deceleration"""
        df = self._calculate_weighted_alerts(df, col("interval") <= 3)
        
        results = df.groupBy("symbol", "interval").agg(
            sum("weighted_momentum_alert_accelerated").alias("weighted_momentum_alert_accelerated"),
            sum("weighted_momentum_alert_decelerated").alias("weighted_momentum_alert_decelerated"),
            max("date").alias("date")
        )
        
        return results.filter(
            ((col("weighted_momentum_alert_accelerated") > 1)) &
            ((col("weighted_momentum_alert_decelerated") < 1)) &
            (col("interval") <= 3)
        ).select(
            "date",
            "symbol",
            lit(1).alias("decision")
        ).withColumn("strategy", lit("short_term_trend"))

    def long_term_trend_signal(self, df):
        """Generate long-term trend signals based on acceleration/deceleration"""
        df = self._calculate_weighted_alerts(df, col("interval") == 5)
        
        results = df.groupBy("symbol", "interval").agg(
            sum("weighted_momentum_alert_accelerated").alias("weighted_momentum_alert_accelerated"),
            sum("weighted_momentum_alert_decelerated").alias("weighted_momentum_alert_decelerated"),
            max("date").alias("date")
        )
        
        return results.filter(
            ((col("weighted_momentum_alert_accelerated") > 1)) &
            ((col("weighted_momentum_alert_decelerated") < 1)) &
            (col("interval") == 5)
        ).select(
            "date",
            "symbol",
            lit(1).alias("decision")
        ).withColumn("strategy", lit("long_term_trend"))

    def short_term_accumulation_signal(self, df):
        """Generate short-term accumulation signals"""
        df = self._calculate_accumulation_alerts(df, col("interval") <= 3)
        
        results = df.groupBy("symbol", "interval").agg(
            sum("weighted_touch_type_resistance").alias("weighted_touch_type_resistance"),
            sum("weighted_touch_type_support").alias("weighted_touch_type_support"),
            count("*").alias("count"),
            max("date").alias("date")
        )
        
        return results.filter(
            ((col("weighted_touch_type_support") > 1)) &
            ((col("weighted_touch_type_resistance") < 1)) &
            ((col("count") >= 2)) &
            ((col("interval") <= 3))
        ).select(
            "date",
            "symbol",
            lit(1).alias("decision")
        ).withColumn("strategy", lit("short_term_accumulation"))

    def long_term_accumulation_signal(self, df):
        """Generate long-term accumulation signals"""
        df = self._calculate_accumulation_alerts(df, col("interval") == 5)
        
        results = df.groupBy("symbol", "interval").agg(
            sum("weighted_touch_type_resistance").alias("weighted_touch_type_resistance"),
            sum("weighted_touch_type_support").alias("weighted_touch_type_support"),
            count("*").alias("count"),
            max("date").alias("date")
        )
        
        return results.filter(
            ((col("weighted_touch_type_support") > 1)) &
            ((col("weighted_touch_type_resistance") < 1)) &
            ((col("count") >= 1)) &
            ((col("interval") == 5))
        ).select(
            "date",
            "symbol",
            lit(1).alias("decision")
        ).withColumn("strategy", lit("long_term_accumulation"))

    def long_term_maintain_signal(self, df):
        """Generate long-term maintain signals based on velocity maintenance"""
        df = self._calculate_velocity_alerts(df, col("interval") >= 8)
        
        results = df.groupBy("symbol", "interval").agg(
            sum("weighted_velocity_maintained").alias("weighted_velocity_maintained"),
            sum("weighted_velocity_weak").alias("weighted_velocity_weak"),
            sum("weighted_velocity_loss").alias("weighted_velocity_loss"),
            max("date").alias("date")
        )
        
        return results.filter(
            ((col("weighted_velocity_maintained") > 0)) &
            ((col("weighted_velocity_weak") == 0)) &
            ((col("weighted_velocity_loss") == 0)) &
            ((col("interval") >= 8))
        ).select(
            "date",
            "symbol",
            lit(1).alias("decision")
        ).withColumn("strategy", lit("long_term_maintain"))

    def apply(self):
        """Generate all signals"""
        try:
            results = []
            
            for interval in self.intervals:
                # Convert interval to string since it's stored as string in the database
                interval_str = str(interval)
                interval_df = self.df.filter(col("interval") == interval_str)
                
                if interval <= 3:
                    short_term_trend = self.short_term_trend_signal(interval_df)
                    if short_term_trend.count() > 0:  # Only add if there are results
                        results.append(short_term_trend)
                        
                    short_term_accum = self.short_term_accumulation_signal(interval_df)
                    if short_term_accum.count() > 0:  # Only add if there are results
                        results.append(short_term_accum)
                        
                elif interval == 5:
                    long_term_trend = self.long_term_trend_signal(interval_df)
                    if long_term_trend.count() > 0:  # Only add if there are results
                        results.append(long_term_trend)
                        
                    long_term_accum = self.long_term_accumulation_signal(interval_df)
                    if long_term_accum.count() > 0:  # Only add if there are results
                        results.append(long_term_accum)
                
            if results:
                final_df = results[0]
                for df in results[1:]:
                    final_df = final_df.union(df)
                
                # Create the final DataFrame with the required schema
                final_df = final_df.select(
                    col("date"),
                    col("symbol"),
                    col("decision"),
                    col("strategy")
                ).distinct()  # Remove any duplicates
                
                return final_df
            else:
                # Create empty DataFrame with the correct schema
                return self.spark.createDataFrame(
                    [], 
                    ["date", "symbol", "decision", "strategy"]
                )
            
        except Exception as e:
            logging.error(f"Error in VegasChannelSignalGenerator.apply: {e}")
            traceback.print_exc()
            # Create empty DataFrame with the correct schema on error
            return self.spark.createDataFrame(
                [], 
                ["date", "symbol", "decision", "strategy"]
            )

class LongTermTradingStrategy:
    def __init__(self, mongo_config, instrument, start_date=None, sandbox_mode=False, initial_capital=10000, verbose=False, stock_candidates_df=None):
        # Initialize trade tracking state
        self._init_trade_state(instrument)
        
        # Initialize configuration parameters
        self._init_config(mongo_config, instrument, start_date, sandbox_mode, initial_capital, verbose)
        
        # Initialize MongoDB connections and load data
        self._init_mongo_connections(sandbox_mode, stock_candidates_df)
        
    def _init_trade_state(self, instrument):
        """Initialize trade tracking variables"""
        self.protected = False
        self.peak_profit_pct = None  
        self.peak_profit = None 
        self.trades = []
        self.current_trade = {}
        self.dynamic_protection = False
        self.buy_fee = 0.0025 if instrument == 'crypto' else 0.002
        self.sell_fee = 0.0075 if instrument == 'crypto' else 0.002
        self.dynamic_asset_control = True
        
    def _init_config(self, mongo_config, instrument, start_date, sandbox_mode, initial_capital, verbose):
        """Initialize configuration parameters"""
        self.start_date = start_date if sandbox_mode else '2020-01-01'
        self.instrument = instrument
        self.capital = initial_capital
        self.mongo_config = mongo_config
        self.verbose = verbose
        
    def _init_mongo_connections(self, sandbox_mode, stock_candidates_df):
        """Initialize MongoDB client and database connections"""
        self.client = MongoClient(self.mongo_config['connection_string'])
        self.db = self.client[self.mongo_config['db']]
        self.data_collection = self.db[self.mongo_config['processed_collection_name']]
        self.alert_collection = self.db[self.mongo_config['alert_collection_name']['long_term']]
        self.trades_collection = self.db[self.mongo_config['trades_collection_name']['long_term']]
        self.results_collection = self.db[self.mongo_config['sandbox_results']] if sandbox_mode else self.db[self.mongo_config['trades_collection_name']['long_term']]
        # Load stock candidates data
        self.stock_candidates = DatabaseTools.fetch_stock_candidates(self.db, 
                                                                    self.mongo_config['candidates_collection_name']['long_term'], 
                                                                    self.instrument, 
                                                                    self.start_date, 
                                                                    df=True).set_index('date') if not sandbox_mode else stock_candidates_df

        # Load historical price data
        self.processed_df = DatabaseTools.fetch_processed_data(self.db, 
                                                                self.mongo_config['processed_collection_name'], 
                                                                self.instrument, 
                                                                self.start_date, 
                                                                interval=1, 
                                                                df=True).sort_values(by=['symbol', 'date'])
        # Load alert data
        self.alert_df = DatabaseTools.fetch_alerts(self.db, 
                                                    self.mongo_config['alert_collection_name']['long_term'], 
                                                    self.instrument, 
                                                    self.start_date, 
                                                    df=True)
        
    def excute_trades(self):
        """Execute trades for each date in stock candidates"""
        for idx, date in enumerate(self.stock_candidates.index.unique()):
            self.manage_trade(pd.to_datetime(date), idx)

    def manage_trade(self, date, idx):
        """Manage existing trades and look for new opportunities"""
        if self.current_trade:
            self._manage_existing_trade(date, idx)
        else:
            self._look_for_new_trade(date, idx)
            
    def _manage_existing_trade(self, date, idx):
        """Handle management of current open position"""
        stock = self.current_trade["symbol"]
        
        # Skip sell check if the same day as purchase
        if self.current_trade["entry_date"] == date:
            self._log(f"Skipping sell check - same day as purchase for {stock}")
            return
        
        # Get tracked data
        tracked_data = self._get_tracked_data(stock, date)
        if tracked_data['alert'].empty:
            self._log(f"No alert data found for {stock} on {date}")
            return
        
        # Apply trading rules if there is an alert
        self._apply_trading_rules(tracked_data, idx)

    def _get_tracked_data(self, stock, date):
        """Get relevant price and alert data for a stock"""
        next_day_data = self.processed_df[(self.processed_df['symbol'] == stock) & (self.processed_df['date'] > date)].sort_values('date')
        current_day_data = self.processed_df[(self.processed_df['symbol'] == stock) & (self.processed_df['date'] == date)]
        previous_day_data = self.processed_df[(self.processed_df['symbol'] == stock) & (self.processed_df['date'] < date)].sort_values('date')
        # Condition 1: Today is out of available trading days
        if len(current_day_data) == 0:
            return {
                'price': previous_day_data.iloc[-1],
                'price_next_day': previous_day_data.iloc[-1],
                'alert': self.alert_df[(self.alert_df['symbol'] == stock) & 
                                    (self.alert_df['date'] == date) & 
                                    (self.alert_df['interval'] == 1)]
            }
        # Condition 2: No next day data
        if len(next_day_data) == 0:
            return {
                'price': current_day_data.iloc[0],
                'price_next_day': current_day_data.iloc[0],
                'alert': self.alert_df[(self.alert_df['symbol'] == stock) & 
                                    (self.alert_df['date'] == date) & 
                                    (self.alert_df['interval'] == 1)]}
        # Condition 3: Next day data exists
        else:
            return {
                'price': current_day_data.iloc[0],
                'price_next_day': next_day_data.iloc[0],
                'alert': self.alert_df[(self.alert_df['symbol'] == stock) & 
                                (self.alert_df['date'] == date) & 
                                (self.alert_df['interval'] == 1)]}
    
    def _apply_trading_rules(self, tracked_data, idx):
        """Apply trading rules to determine if position should be closed"""
        self._log("Applying trading rules")
        if not self.dynamic_protection:
            self._check_profit_protection(tracked_data)
        elif self.dynamic_protection:
            if self.verbose:
                print(f"Processing date: {tracked_data['price']['date']}")
            self._manage_dynamic_protection(tracked_data)

        if not self.protected and not self.dynamic_protection:
            self._check_exit_signals(tracked_data, idx)

    def _check_exit_signals(self, tracked_data, idx):
        """Check if exit signals are triggered"""
        # Check for sell signals in alert data
        alert_data = tracked_data['alert']
        
        for signal in self.sell_signals:
            if signal in alert_data.values:
                self._log(f"Sell signal detected, closing position for {self.current_trade['symbol']} at {tracked_data['price']['date']}")
                self.track_profit_loss(tracked_data['price_next_day'], signal, sell=True)
                return

    def _check_profit_protection(self, tracked_data):
        """Check if profit protection should be activated"""
        tracked_profit_loss = self.track_profit_loss(tracked_data['price'], sell=False)
        tracked_profit_pct = tracked_profit_loss / self.current_trade['cost']
        self._log(f"Symbol: {self.current_trade['symbol']} | Date: {tracked_data['price']['date']} | Tracked profit loss: {tracked_profit_loss} | Tracked profit pct: {tracked_profit_pct}")
        if tracked_profit_pct >= 0.3:
            self._activate_profit_protection(tracked_profit_loss, tracked_profit_pct)
            self._log("Profit protection activated")
        else:
            self._log("Profit protection not required")
            
    def _activate_profit_protection(self, profit, profit_pct):
        """Activate profit protection mechanism"""
        self.dynamic_protection = True
        self.peak_profit = profit
        self.peak_profit_pct = profit_pct

    def _manage_dynamic_protection(self, tracked_data):
        """Manage dynamic profit protection"""
        self._log("Dynamic protection activated")
        # Track profit loss
        current_profit = self.track_profit_loss(tracked_data['price'], sell=False)
        current_profit_pct = (current_profit - self.capital + self.current_trade['cost']) / (self.capital + self.current_trade['cost'])
        self._log(f"Current profit: {current_profit} | Current profit pct: {current_profit_pct} in date: {tracked_data['price']['date']}")
        
        # Update peak profits
        self._update_peak_profits(current_profit, current_profit_pct)
        self._log(f"Peak profit: {self.peak_profit} | Peak profit pct: {self.peak_profit_pct} in date: {tracked_data['price']['date']}")
        
        # Check if profits have declined
        if self._check_profit_decline(tracked_data, current_profit_pct):
            self._log(f"Profit decline detected, closing position in date: {tracked_data['price']['date']}")
            return
        
        # Check if velocity signals are triggered
        if self._check_velocity_signals(tracked_data):
            self._log(f"Velocity signal detected, closing position in date: {tracked_data['price']['date']}")
            return


    def _update_peak_profits(self, current_profit, current_profit_pct):
        """Update peak profit values if current profits are higher"""
        if current_profit > self.peak_profit:
            self.peak_profit = current_profit
            self.peak_profit_pct = current_profit_pct

    def _check_profit_decline(self, tracked_data, current_profit_pct):
        """Check if profits have declined significantly from peak"""
        if self.peak_profit_pct - current_profit_pct >= 0.5:
            self.track_profit_loss(tracked_data['price_next_day'],  exit_reason='profit_protection', sell=True)
            self.protected = False
            return True
        return False

    def _check_velocity_signals(self, tracked_data):
        """Check velocity signals for additional protection"""
        alert_data = tracked_data['alert']
        for signal in self.sell_signals:
            if signal in alert_data.values:
                self.track_profit_loss(tracked_data['price_next_day'], signal, sell=True)
                
                # Reset the peak profit and profit protection
                self.protected = False
                self.peak_profit = 0
                self.peak_profit_pct = 0
                
                return True
        return False

    def _look_for_new_trade(self, date, idx):
        """Look for new trading opportunities"""
        cur_stock_pick = self.stock_candidates.iloc[idx]
        stock, alert = self.find_alert(cur_stock_pick, desired_alerts=self.buy_signals)
        if stock != None:
            self._log(f"Looking for new trade for {stock} on {date}")
            
        else:
            return
        
        self._open_new_position(stock, date, alert)
        
    def _open_new_position(self, stock, date, alert):
        """Open a new trading position"""
        
        # Step 1: Open a new position in the next candle open
        next_day_data = self.processed_df[(self.processed_df['symbol'] == stock) & (self.processed_df['date'] == date + pd.Timedelta(days=1))]
        if next_day_data.empty:
            return
        avg_cost = next_day_data['open'].iloc[0]
        
        # Step 2: Calculate fees and available capital
        portion = self.dynamic_portion(self.capital) if self.dynamic_asset_control else 1
        trading_capital = self.capital * portion
        fees = trading_capital * self.buy_fee
        post_fees_capital = trading_capital - fees
        
        # Step 3: Calculate position size
        position_size = post_fees_capital / avg_cost
        position_size = position_size if position_size < 0 else int(position_size)
        
        # Step 4: Calculate actual cost
        total_cost = avg_cost * position_size
        
        # Step 5: Verify we have enough capital
        if total_cost > post_fees_capital:
            self._log(f"Insufficient capital for trade in {stock}")
            return
        # Step 6: Caculate Remaining Capital    
        remaining_capital = self.capital - total_cost
        
        self._log(f"Next day data for {stock} on {next_day_data['date'].iloc[0]}")
        self._log(f"Position size: {position_size:.8f} shares at ${avg_cost:.2f}")
        self._log(f"Cost: ${total_cost:.8f}")
        self._log(f"Fees: ${fees:.8f}")
        self._log(f"Remaining capital: ${remaining_capital:.8f}")
        
        self.current_trade = {
            "entry_date": next_day_data['date'].iloc[0],
            "symbol": stock,
            "entry_price": avg_cost,
            "position_size": position_size,
            "fees": fees,
            "cost": total_cost,
            "remaining_capital": remaining_capital,
            "entry_reason": alert
        }
        
        # Deduct cost from available capital
        self.capital = post_fees_capital - total_cost
        
        self._log(f"Opened new position for {stock} on {next_day_data['date'].iloc[0]}")
        self._log(f"Remaining capital: ${self.capital:.2f}")
        
    def dynamic_portion(self, available_capital):
        """Calculate the dynamic portion of the available capital"""
        # All in if available capital is less than 10000
        if available_capital <= 10000:
            return 1
        # 50% if available capital is less than 100000
        elif (available_capital <= 100000) and (available_capital > 10000):
            return 0.5
        # 25% if available capital is less than 1000000
        elif (available_capital <= 1000000) and (available_capital >= 100000):
            return 0.25
        # 10% if available capital is less than 10000000
        else:
            return 0.1
    def track_profit_loss(self, tracked_data, exit_reason=None, sell=False):
        """Track and calculate profit/loss for a position"""
        exit_price = tracked_data['close']
        entry_price = self.current_trade['entry_price']
        cost = self.current_trade['cost']
        profit_loss = (exit_price - entry_price) * self.current_trade['position_size']
        profit_rate = profit_loss / cost
                
        if sell:
            self._close_position(tracked_data, exit_price, profit_loss, exit_reason)
            return None
        
        return profit_loss
    
    def _close_position(self, tracked_data, exit_price, profit_loss, exit_reason):
        """Close out an existing position and record the trade"""
        
        # Step 1. Get the amount of capital after sold
        gain_loss_after_sold = profit_loss + self.current_trade["cost"] # Reamining captial + profit or loss + the total cost
        
        # Step 2. Compute the actual final captial after fees
        self.capital = (self.current_trade['remaining_capital'] + gain_loss_after_sold) - (gain_loss_after_sold * self.sell_fee)
        
        # Step 3. Compute the profit rate
        # Potential divide by zero if self.current_trade["cost"] is 0
        if self.current_trade["cost"] == 0:
            profit_rate = 0
        else:
            profit_rate = profit_loss / self.current_trade["cost"]
        
        self.trades.append({
            "symbol": self.current_trade["symbol"],
            "Entry_price": self.current_trade["entry_price"],
            "Entry_date": self.current_trade["entry_date"],
            "Exit_price": exit_price,
            "Exit_date": tracked_data['date'],
            "Position_size": self.current_trade["position_size"],
            "cost": f"{self.current_trade['cost']:.2f}",
            "profit/loss%": f"{profit_rate * 100:.2f}%",
            "profit/loss": f"{profit_loss:.2f}",
            "remaining_capital": f"{self.current_trade['remaining_capital']:.2f}",
            "total_captial": f"{self.capital:.2f}",
            "entry_reason": self.current_trade["entry_reason"],
            "exit_reason": exit_reason,
            
        })
        
        self.current_trade = {}

    def find_alert(self, stock_data, desired_alerts):
        """Find matching alerts in stock data"""
        for alert in desired_alerts:
            cur_alert_data = stock_data.loc[alert]
            if len(cur_alert_data) != 0:
                return stock_data[alert][0], alert
        return None, None

    def run(self, buy_signals, sell_signals):
        """Run the trading strategy"""
        self.buy_signals = buy_signals
        self.sell_signals = sell_signals
        
        # Start Backtesting
        self.excute_trades()
        
        results_df = pd.DataFrame(self.trades)
        results_df['instrument'] = self.instrument
        
        # Store the trades into the MongoDB collection
        
        self.store_trades(results_df)
        
    def store_trades(self, results_df):
        """Store the trades into the MongoDB collection"""
        keep_duration = 157788000 # 5 years
        DatabaseTools.create_timeseries_collection(self.db, [], keep_duration=keep_duration)
        
        latest_record = self.trades_collection.find_one({'instrument': self.instrument}, sort=[("date", -1)])
        latest_date = latest_record['date'] if latest_record else None
        
        # Convert DataFrame to dict and ensure proper date formatting
        results_dict = results_df.to_dict('records')
        for trade in results_dict:
            # Add required 'date' field and ensure dates are datetime objects
            trade['date'] = pd.to_datetime(trade['Exit_date']).to_pydatetime()
            trade['Entry_date'] = pd.to_datetime(trade['Entry_date']).to_pydatetime()
            trade['Exit_date'] = pd.to_datetime(trade['Exit_date']).to_pydatetime()
        
        if latest_date is None:
            self.trades_collection.insert_many(results_dict)
            logging.info(f"StockCandidatesAnalysis: Trades stored for {self.instrument}")
        else:
            for trade in results_dict:
                if trade['Entry_date'] > latest_date:
                    self.trades_collection.insert_one(trade)
                    logging.info(f"StockCandidatesAnalysis: New trade stored for {self.instrument} on {trade['Entry_date']}")
        
    def get_trades(self):
        """Get DataFrame of completed trades"""
        return pd.DataFrame(self.trades)

    def _log(self, message):
        """Log debug messages if verbose mode is enabled"""
        if self.verbose:
            print(message)

