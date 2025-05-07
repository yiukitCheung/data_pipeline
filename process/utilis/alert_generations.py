import numpy as np
from collections import deque
from pyspark.sql.window import Window
from pyspark.sql.functions import when, col, lit, sum, lag, max, min, greatest, least
import logging
import traceback

# =============================================== #
# ===============  EMA Trend Alert  ============= #
# =============================================== #

class AddTrendAlert:
    """
    This class adds the trend alerts to the stock data.
    """
    def __init__(self, spark, df, interval):
        """
        This function initializes the AddTrendAlert class.
        """
        self.df = df
        self.spark = spark
        self.window = 30
        self.interval = interval
        self.rolling_window = 50

    # =============================================== #
    # ===== Acceleration Deceleration Alert  ======== #
    # =============================================== #
    def velocity_accel_decel_alert(self, interval_df, base_window=28, interval=1):
        """
        This function calculates the velocity acceleration and deceleration alerts.
        """
        # Define window specifications
        window_spec = Window.partitionBy("symbol").orderBy("date")
        window_dict = {
            1: base_window,      
            3: base_window - 8,   
            5: base_window - 8,   
            8: base_window - 14,   
            13: base_window - 14   
        }
        
        obs_window = window_dict.get(interval, base_window//4)
        
        # Calculate velocity status counts in observation window
        df = interval_df.withColumn(
            "velocity_status",
            when(
                (col("close") > col("open")) & 
                (col("close") > greatest(col("EMA-13"), col("EMA-8"))) & 
                (col("close") > greatest(col("EMA-169"), col("EMA-144"))),
                lit("velocity_maintained")
            ).when(
                (col("close") < col("EMA-13")) & 
                (col("close") > col("EMA-169")),
                lit("velocity_weak")
            ).when(
                (col("close") < col("EMA-13")) & 
                (col("close") < col("EMA-169")),
                lit("velocity_loss")
            ).otherwise(lit("velocity_negotiating"))
        )
        
        # Create window for counting previous alerts
        count_window = Window.partitionBy("symbol").orderBy("date").rowsBetween(-obs_window, -1)
        
        # Calculate counts of different velocity statuses
        df = df.withColumn(
            "count_velocity_loss",
            sum(when(col("velocity_status").isin(["velocity_loss", "velocity_weak", "velocity_negotiating"]), 1).otherwise(0))
            .over(count_window)
        ).withColumn(
            "count_velocity_maintained",
            sum(when(col("velocity_status") == "velocity_maintained", 1).otherwise(0))
            .over(count_window)
        )
        
        # Calculate short and long term bounds
        df = df.withColumn(
            "short_term_max",
            greatest(col("EMA-8"), col("EMA-13"))
            ).withColumn(
                "short_term_min",
                least(col("EMA-8"), col("EMA-13"))
            ).withColumn(
                "lng_term_max",
                greatest(col("EMA-169"), col("EMA-144"))
            ).withColumn(
                "lng_term_min",
                least(col("EMA-169"), col("EMA-144"))
        )
        
        # Handle NaN cases for EMAs
        df = df.withColumn(
            "lng_term_max",
            when(col("EMA-144").isNull(), col("EMA-13")).otherwise(col("lng_term_max"))
            ).withColumn(
                "lng_term_min",
                when(col("EMA-144").isNull(), col("EMA-13")).otherwise(col("lng_term_min"))
            ).withColumn(
                "short_term_max",
                when(col("EMA-144").isNull(), col("EMA-8")).otherwise(col("short_term_max"))
            ).withColumn(
                "short_term_min",
                when(col("EMA-144").isNull(), col("EMA-8")).otherwise(col("short_term_min"))
            )
        
        # Calculate acceleration/deceleration with all conditions
        df = df.withColumn(
            "signal",
            when(
                (col("lng_term_max") <= col("short_term_max")) & 
                (col("short_term_max") < col("open")) & 
                (col("open") < col("close")) & 
                (col("count_velocity_loss") > col("count_velocity_maintained")),
                lit("accelerated")
            ).when(
                (col("close") < col("short_term_min")) & 
                (col("short_term_min") <= col("lng_term_min")) & 
                (col("count_velocity_maintained") < col("count_velocity_loss")),
                lit("decelerated")
            ).otherwise(lit(None))
        )
        
        # Add Alert Type to the dataframe
        df = df.withColumn("alert_type", lit("velocity_status"))
        
        # Filter out rows where signal is None
        df = df.filter(col("signal").isNotNull())
        
        # Select final columns
        df = df.select(
            "symbol",
            "date",
            "interval",
            col("alert_type"),
            col("signal")
        )
        
        return df
    
    # =============================================== #
    # ===============  EMA Touch Alert  ============= #
    # =============================================== #
    def add_169ema_touch_alert(self, interval_df, interval=1):
        """
        This function calculates the EMA touch alerts.
        """
        
        tolerance_dict = {
            1: 0.002,
            3: 0.02,
            5: 0.05,
            8: 0.07,
            13: 0.1
        }
        
        tolerance = tolerance_dict.get(interval, 0.02)
        
        # Calculate bounds based on available EMAs
        df = interval_df.withColumn(
            "lower_bound",
            when(
                (col("EMA-144").isNotNull() & col("EMA-169").isNotNull()),
                least(col("EMA-144"), col("EMA-169")) * (1 - tolerance)
            ).when(
                col("EMA-144").isNotNull(),
                col("EMA-144") * (1 - tolerance)
            ).when(
                (col("EMA-13").isNotNull() & col("EMA-8").isNotNull()),
                least(col("EMA-13"), col("EMA-8")) * (1 - tolerance)
            ).when(
                col("EMA-8").isNotNull(),
                col("EMA-8") * (1 - tolerance)
            )
        ).withColumn(
            "upper_bound",
            when(
                (col("EMA-144").isNotNull() & col("EMA-169").isNotNull()),
                greatest(col("EMA-144"), col("EMA-169")) * (1 + tolerance)
            ).when(
                col("EMA-144").isNotNull(),
                col("EMA-144") * (1 + tolerance)
            ).when(
                (col("EMA-13").isNotNull() & col("EMA-8").isNotNull()),
                greatest(col("EMA-13"), col("EMA-8")) * (1 + tolerance)
            ).when(
                col("EMA-8").isNotNull(),
                col("EMA-8") * (1 + tolerance)
            )
        )
        
        # Calculate tunnel values
        df = df.withColumn(
            "lng_term_tunnel_max",
            when(
                (col("EMA-169").isNull() & col("EMA-144").isNull()),
                greatest(col("EMA-13"), col("EMA-8"))
            ).otherwise(greatest(col("EMA-169"), col("EMA-144")))
        ).withColumn(
            "lng_term_tunnel_min",
            when(
                (col("EMA-169").isNull() & col("EMA-144").isNull()),
                least(col("EMA-13"), col("EMA-8"))
            ).otherwise(least(col("EMA-169"), col("EMA-144")))
        ).withColumn(
            "short_term_tunnel_max",
            greatest(col("EMA-13"), col("EMA-8"))
        ).withColumn(
            "short_term_tunnel_min",
            least(col("EMA-13"), col("EMA-8"))
        ).withColumn(
            "candle_min",
            least(col("close"), col("open"))
        ).withColumn(
            "candle_max",
            greatest(col("close"), col("open"))
        )
        
        # Add Alert Type to the dataframe
        df = df.withColumn("alert_type", lit("accumulation"))
        
        # Calculate touch alerts with all conditions
        df = df.withColumn(
            "signal",
            when(
                ((col("lower_bound") <= col("low")) & (col("low") <= col("upper_bound"))) |
                ((col("lower_bound") <= col("EMA-13")) & (col("EMA-13") <= col("upper_bound"))) |
                ((col("lower_bound") <= col("EMA-8")) & (col("EMA-8") <= col("upper_bound"))),
                when(
                    (col("short_term_tunnel_min") > col("lng_term_tunnel_max")) & 
                    (col("candle_min") > col("lng_term_tunnel_min")),
                    lit("support")
                ).when(
                    (col("short_term_tunnel_max") < col("lng_term_tunnel_max")) & 
                    (col("close") < col("lng_term_tunnel_max")),
                    lit("resistance")
                ).otherwise(lit(None))
            ).otherwise(lit(None))
        )
        
        # Filter out rows where signal is None
        df = df.filter(col("signal").isNotNull())
        
        # Select final columns
        df = df.select(
            "symbol",
            "date",
            "interval",
            col("alert_type"),
            col("signal")
        )
        return df
    
    # =============================================== #
    # ===============  Apply Alerts  ================ #
    # =============================================== #
    def apply(self):
        try:
            # Initialize empty list to store all alert dataframes
            alert_dfs = []
            
            # Process each interval
            for interval in self.interval:
                df = self.df.filter(col("interval") == interval)
                
                # Apply velocity acceleration/deceleration alerts
                df_accel_decel = self.velocity_accel_decel_alert(df, interval)
                
                # Apply EMA touch alerts
                df_touch = self.add_169ema_touch_alert(df, interval)
                
                # Add both dataframes to the list
                alert_dfs.extend([df_accel_decel, df_touch])
            
            # Union all dataframes together
            if alert_dfs:
                all_dfs = alert_dfs[0]
                for df in alert_dfs[1:]:
                    all_dfs = all_dfs.union(df)
                return all_dfs
            else:
                return self.spark.createDataFrame([])
            
        except Exception as e:
            logging.error(f"Error in AddTrendAlert.apply: {e}")
            traceback.print_exc()
            return self.df

# =============================================== #
# ===============  Structural Area  ============= #
# =============================================== #

class AddStructuralArea:
    def __init__(self, df_dict, interval=1):
        self.df_dict = [entry for entry in df_dict if entry['interval'] == interval]
        self.window = 30

    def _ensure_structural_area(self, entry):
        if 'structural_area' not in entry:
            entry['structural_area'] = {}

    def _get_window_data(self, i):
        window = self.df_dict[i-self.window:i]
        return {
            'close': [entry['close'] for entry in window],
            'high': max(entry['high'] for entry in window),
            'low': min(entry['low'] for entry in window)
        }

    def kernel_density_estimation(self):
        """
        This function calculates the kernel density estimation.
        """
        for i, entry in enumerate(self.df_dict):
            if i < self.window:
                continue
                
            self._ensure_structural_area(entry)
            window_data = self._get_window_data(i)
            close_prices = np.array(window_data['close'])

            # Calculate histogram
            hist_counts, bin_edges = np.histogram(close_prices, bins=20)
            max_bin_idx = np.argmax(hist_counts)
            
            # Find second highest peak
            remaining_hist = hist_counts[max_bin_idx+1:]
            sec_bin_idx = max_bin_idx + 1 + np.argmax(remaining_hist) if len(remaining_hist) > 0 else max_bin_idx

            # Get bin ranges
            main_bin = (bin_edges[max_bin_idx], bin_edges[max_bin_idx + 1])
            second_bin = (bin_edges[sec_bin_idx], bin_edges[sec_bin_idx + 1])

            entry['structural_area']['kernel_density_estimation'] = {
                "date": entry['date'],
                "top": main_bin[0],
                "bottom": main_bin[1], 
                "second_top": second_bin[0],
                "second_bottom": second_bin[1],
                "details": f"Most frequent price bin between {main_bin[0]} and {main_bin[1]}.\nSecond most frequent price bin between {second_bin[0]} and {second_bin[1]}."
            }

    def fibonacci_retracement(self):
        """
        This function calculates the fibonacci retracement levels.
        """
        for i, entry in enumerate(self.df_dict):
            if i < self.window:
                continue
                
            self._ensure_structural_area(entry)
            window_data = self._get_window_data(i)
            
            # Calculate fibonacci levels
            diff = window_data['high'] - window_data['low']
            fibs = {
                'fib_236': 0.236,
                'fib_382': 0.382,
                'fib_500': 0.500,
                'fib_618': 0.618,
                'fib_786': 0.,
                'fib_1236': 1.236,
                'fib_1382': 1.382
            }
            
            levels = {key: window_data['low'] + (diff * ratio) 
                    for key, ratio in fibs.items()}
            
            entry['structural_area']['fibonacci_retracement'] = {
                "date": entry['date'],
                **levels,
                "details": f"Fibonacci retracement levels: " + 
                        ", ".join(f"{ratio*100}%: {level}" 
                                for ratio, level in zip(fibs.values(), levels.values()))
            }

    def apply(self):
        self.kernel_density_estimation()
        self.fibonacci_retracement()
        return self.df_dict

# =============================================== #
# ===============  Best fitting EMA  ============ #
# =============================================== #

class BestFittingEMA:
    def __init__(self, data):
        self.data = data

    def support_loss(self, closing_prices, ema_13):
        """
        Custom loss function to find intervals where the 13 EMA acts as support.
        Penalizes any instance where the closing price falls below the 13 EMA.
        """
        differences = closing_prices - ema_13
        penalties = np.where(differences < 0, np.abs(differences), 0)
        return np.sum(penalties)

    def find_best_interval(self):
        """
        Find the interval with the lowest time-weighted 'price velocity', 
        i.e., the one where the closing price fits the 13 EMA line the best, for the last 60 days.
        """
        intervals = self.data['interval'].unique()

        min_loss = float('inf')
        best_interval = None

        # Loop through each interval to find the best fitting one
        for interval in intervals:
            interval_data = self.data[self.data['interval'] == interval].tail(60)
            if not interval_data.empty:
                closing_prices = interval_data['close'].values
                ema_13 = interval_data['13ema'].values
                loss = self.support_loss(closing_prices, ema_13)

                if loss < min_loss:
                    min_loss = loss
                    best_interval = interval

        # Find the date range of 60 candles in the best interval
        interval_date_start = self.data[self.data['interval'] == best_interval]['date'].values[-60]
        interval_date_end = self.data[self.data['interval'] == best_interval]['date'].values[-1]

        # Attach the best interval as the best_velocity for the rows with dates between interval_date_start and interval_date_end
        self.data.loc[
            (self.data['date'] >= interval_date_start) & 
            (self.data['date'] <= interval_date_end),
            'best_velocity'
        ] = best_interval

    def run(self):
        self.find_best_interval()
        
        for interval in self.data['interval'].unique():
            self.data.loc[self.data['interval'] == interval] = self.data.loc[self.data['interval'] == interval].ffill()
        return self.data