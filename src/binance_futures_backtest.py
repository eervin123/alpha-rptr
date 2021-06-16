# coding: UTF-8

import os, tempfile
import time
from datetime import timedelta, datetime, timezone
import dateutil.parser

import pandas as pd

from src import logger, allowed_range, retry, delta, load_data, resample
from src.binance_futures_stub import BinanceFuturesStub

OHLC_DIRNAME = os.path.join(os.path.dirname(__file__), "../ohlc/{}/{}")
OHLC_FILENAME = os.path.join(os.path.dirname(__file__), "../ohlc/{}/{}/data.csv")

class BinanceFuturesBackTest(BinanceFuturesStub):
     # Pair
    pair = 'BTCUSDT'
    # Market price
    market_price = 0
    # Update Data before Backtest
    update_data = True
    # Check candles
    check_candles_flag = True
    # OHLCV
    df_ohlcv = None
    # Current time axis
    index = None
    # Current time
    time = None
    # Order count
    order_count = 0
    # Buy signal history
    buy_signals = []
    # Sell signal history
    sell_signals = []
    # EXIT history
    close_signals = []
    # Balance history
    balance_history = []
    # Start balance
    start_balance = 0
    # Drawdown history
    draw_down_history = []
    # Plot data
    plot_data = {}
    # Resample data
    resample_data = {}

    def __init__(self, account, pair):
        """
        constructor
        :account:
        :pair:
        :param periods:
        """
        self.pair = pair
        BinanceFuturesStub.__init__(self, account, pair=self.pair, threading=False)
        self.enable_trade_log = False
        self.start_balance = self.get_balance()

    def get_market_price(self):
        """
        get market price
        :return:
        """
        return self.market_price

    def now_time(self):
        """
        current time
        :return:
        """
        return self.time    
    
    def entry(self, id, long, qty, limit=0, stop=0, post_only=False, when=True):
        """
        places an entry order, works equivalent to tradingview pine script implementation
        https://jp.tradingview.com/study-script-reference/#fun_strategy{dot}entry
        :param id: Order id
        :param long: Long or Short
        :param qty: Quantity
        :param limit: Limit price
        :param stop: Stop limit
        :param post_only: Post only        
        :param when: Do you want to execute the order or not - True for live trading
        :return:
        """
        BinanceFuturesStub.entry(self, id, long, qty, limit, stop, post_only, when)

    def commit(self, id, long, qty, price, need_commission=False):
        """
        Commit
        :param id: order
        :param long: long or short
        :param qty: quantity
        :param price: price
        :param need_commission: use commision or not?
        """
        BinanceFuturesStub.commit(self, id, long, qty, price, need_commission)

        if long:
            self.buy_signals.append(self.index)
        else:
            self.sell_signals.append(self.index)

    def close_all(self):
        """
        Close all positions
        """
        if self.get_position_size() == 0:
            return 
        BinanceFuturesStub.close_all(self)
        self.close_signals.append(self.index)
    
    def close_all_at_price(self, price):
        """
        close the current position at price, for backtesting purposes its important to have a function that closes at given price
        :param price: price
        """
        if self.get_position_size() == 0:
            return 
        BinanceFuturesStub.close_all_at_price(self, price)
        self.close_signals.append(self.index)        

    def __crawler_run(self):
        """
        Get the data and execute the strategy.
        """
        start = time.time()

        for i in range(self.ohlcv_len):
            self.balance_history.append((self.get_balance() - self.start_balance))#/100000000*self.get_market_price())
            self.draw_down_history.append(self. max_draw_down_session_perc)

        for i in range(len(self.df_ohlcv) - self.ohlcv_len):
            self.data = self.df_ohlcv.iloc[i:i + self.ohlcv_len, :]
            index = self.data.iloc[-1].name
            self.timestamp = self.data.iloc[-1][0]
            close = self.data['close'].values
            open = self.data['open'].values
            high = self.data['high'].values
            low = self.data['low'].values
            volume = self.data['volume'].values

            if self.get_position_size() > 0 and low[-1] > self.get_trail_price():
                self.set_trail_price(low[-1])
            if self.get_position_size() < 0 and high[-1] < self.get_trail_price():
                self.set_trail_price(high[-1])

            self.market_price = close[-1]
            self.OHLC = {
                        'open': open,
                        'high': high,
                        'low': low,
                        'close': close
                        }
            # self.time = timestamp.tz_convert('Asia/Tokyo')
            self.index = index
            #self.eval_sltp()
            self.strategy(open, close, high, low, volume)

            self.balance_history.append((self.get_balance() - self.start_balance)) #/ 100000000 * self.get_market_price())
            #self.eval_exit()
            #self.eval_sltp()

        self.close_all()
        logger.info(f"Back test time : {time.time() - start}")    

    def on_update(self, bin_size, strategy):
        """
        Register the strategy function.
        :param strategy:
        """
        self.__load_ohlcv(bin_size)

        BinanceFuturesStub.on_update(self, bin_size, strategy)
        self.__crawler_run()

    def security(self, bin_size):
        """
        Recalculate and obtain different time frame data
        """
        if bin_size not in self.resample_data:
            self.resample_data[bin_size] = resample(self.df_ohlcv, bin_size)
        return self.resample_data[bin_size][:self.data.iloc[-1].name].iloc[-1 * self.ohlcv_len:, :]

    def check_candles(self, df):

        logger.info("-------")
        logger.info(f"Checking Candles:")
        logger.info("-------")

        logger.info(f"Start: {df.iloc[0][0]}")
        logger.info(f"End: {df.iloc[-1][0]}")

        logger.info("-------")

        diff = (dateutil.parser.isoparse(df.iloc[1][0])-dateutil.parser.isoparse(df.iloc[0][0])).total_seconds()

        logger.info(f"Interval: {diff}s")

        logger.info("-------")

        count = 0
        rows = df.shape[0]
        prev_current_date = None

        for index in range(0, rows-1):

            current_date = dateutil.parser.isoparse(df.iloc[index][0])
            next_date = dateutil.parser.isoparse(df.iloc[index+1][0])

            diff2 = (next_date-current_date).total_seconds()               

            if diff2 != diff:

                count += abs((diff2-diff)/diff)
                
                # logger.info(current_date)
                # logger.info(next_date)
                # logger.info(f"Missing Candles: {(diff2-diff)/diff} Total: {count}")

                # if(prev_current_date != None):
                #     logger.info(f"Last Missing Candle Interval: {current_date-prev_current_date}")

                # logger.info("------------")

                prev_current_date = current_date  

            elif diff2 <= 0:
                logger.info(f"Duplicate Candle: {current_date}")

        logger.info(f"Total Missing Candles = {count}")
        logger.info("-------")

    
    def save_csv(self, data, file):

        if not os.path.exists(os.path.dirname(file)):
            os.makedirs(os.path.dirname(file))

        data.to_csv(file, index_label="time")
    
    def download_data(self, bin_size, start_time, end_time):
        """
        download or get the data
        """       

        data = pd.DataFrame()
        left_time = None
        source = None
        is_last_fetch = False

        while True:
            if left_time is None:
                left_time = start_time
                right_time = left_time + delta(allowed_range[bin_size][0]) * 99
            else:
                left_time = source.iloc[-1].name + delta(allowed_range[bin_size][0]) * allowed_range[bin_size][2]
                right_time = left_time + delta(allowed_range[bin_size][0]) * 99

            if right_time > end_time:
                right_time = end_time
                is_last_fetch = True

            source = self.fetch_ohlcv(bin_size=bin_size, start_time=left_time, end_time=right_time)       
            
            # if(data.shape[0]):
            #     logger.info(f"Last: {data.iloc[-1].name} Left: {left_time} Start: {source.iloc[0].name} Right: {right_time} End: {source.iloc[-1].name}")         
     
            data = pd.concat([data, source])   


            if is_last_fetch:
                return data

            time.sleep(0.25)

    def __load_ohlcv(self, bin_size):
        """
        Read the data.
        :return:
        """
        start_time = datetime.now(timezone.utc) - 1 * timedelta(days=121)
        end_time = datetime.now(timezone.utc)
        file = OHLC_FILENAME.format(self.pair, bin_size)

        self.bin_size = bin_size

        if os.path.exists(file):
            self.df_ohlcv = load_data(file)
            self.df_ohlcv.set_index(self.df_ohlcv.columns[0], inplace=True)

            if(self.update_data):
                data = self.download_data( bin_size, dateutil.parser.isoparse(self.df_ohlcv.iloc[-1].name), end_time)
                self.df_ohlcv = pd.concat([self.df_ohlcv, data])
                self.save_csv(self.df_ohlcv, file) 
                
            # self.df_ohlcv.reset_index(inplace=True)
            self.df_ohlcv = load_data(file)   

        else:
            data = self.download_data(bin_size, start_time, end_time)
            self.save_csv(data, file)
            self.df_ohlcv = load_data(file)

        if self.check_candles_flag:
            self.check_candles(self.df_ohlcv)

    # https://stackoverflow.com/questions/8299386/modifying-a-symlink-in-python/55742015#55742015
    def symlink(self, target, link_name, overwrite=False):
        
        '''
        Create a symbolic link named link_name pointing to target.
        If link_name exists then FileExistsError is raised, unless overwrite=True.
        When trying to overwrite a directory, IsADirectoryError is raised.
        '''

        if not overwrite:
            os.symlink(target, link_name)
            return

        # os.replace() may fail if files are on different filesystems
        link_dir = os.path.dirname(link_name)

        # Create link to target with temporary filename
        while True:
            temp_link_name = tempfile.mktemp(dir=link_dir)

            # os.* functions mimic as closely as possible system functions
            # The POSIX symlink() returns EEXIST if link_name already exists
            # https://pubs.opengroup.org/onlinepubs/9699919799/functions/symlink.html
            try:
                os.symlink(target, temp_link_name)
                break
            except FileExistsError:
                pass

        # Replace link_name with temp_link_name
        try:
            # Pre-empt os.replace on a directory with a nicer message
            if not os.path.islink(link_name) and os.path.isdir(link_name):
                raise IsADirectoryError(f"Cannot symlink over existing directory: '{link_name}'")
            os.replace(temp_link_name, link_name)
        except:
            if os.path.islink(temp_link_name):
                os.remove(temp_link_name)
            raise
    
    def show_result(self):

        DATA_FILENAME = OHLC_FILENAME.format(self.pair, self.bin_size)
        self.symlink(DATA_FILENAME, 'html/data/data.csv', overwrite=True)
        ORDERS_FILENAME = os.path.join(os.path.dirname(__file__), "../orders.csv")
        self.symlink(ORDERS_FILENAME, 'html/data/orders.csv', overwrite=True)

        """
        Display results
        """
        logger.info(f"============== Result ================")
        logger.info(f"TRADE COUNT         : {self.order_count}")
        logger.info(f"BALANCE             : {self.get_balance()}")
        logger.info(f"PROFIT RATE         : {self.get_balance()/self.start_balance*100} %")
        logger.info(f"WIN RATE            : {0 if self.order_count == 0 else self.win_count/(self.win_count + self.lose_count)*100} %")
        logger.info(f"PROFIT FACTOR       : {self.win_profit if self.lose_loss == 0 else self.win_profit/self.lose_loss}")
        logger.info(f"MAX DRAW DOWN TOTAL : {round(self.max_draw_down_session, 4)} or {round(self.max_draw_down_session_perc, 2)}%")
        logger.info(f"======================================")

        import matplotlib.pyplot as plt

        plt_num = len([k for k, v in self.plot_data.items() if not v['overlay']]) + 2
        i = 1

        plt.figure(figsize=(12,8))

        plt.subplot(plt_num,1,i)
        plt.plot(self.df_ohlcv.index, self.df_ohlcv["high"])
        plt.plot(self.df_ohlcv.index, self.df_ohlcv["low"])
        for k, v in self.plot_data.items():
            if v['overlay']:
                color = v['color']
                plt.plot(self.df_ohlcv.index, self.df_ohlcv[k], color)
        plt.ylabel("Price(USD)")
        ymin = min(self.df_ohlcv["low"]) - 200
        ymax = max(self.df_ohlcv["high"]) + 200
        plt.vlines(self.buy_signals, ymin, ymax, "blue", linestyles='dashed', linewidth=1)
        plt.vlines(self.sell_signals, ymin, ymax, "red", linestyles='dashed', linewidth=1)
        plt.vlines(self.close_signals, ymin, ymax, "green", linestyles='dashed', linewidth=1)

        i = i + 1

        for k, v in self.plot_data.items():
            if not v['overlay']:
                plt.subplot(plt_num,1,i)
                color = v['color']
                plt.plot(self.df_ohlcv.index, self.df_ohlcv[k], color)
                plt.ylabel(f"{k}")
                i = i + 1

        plt.subplot(plt_num,1,i)
        plt.plot(self.df_ohlcv.index, self.balance_history)
        plt.hlines(y=0, xmin=self.df_ohlcv.index[0],
                   xmax=self.df_ohlcv.index[-1], colors='k', linestyles='dashed')
        plt.ylabel("PL(USD)")        
        plt.show()

    def plot(self, name, value, color, overlay=True):
        """
        Draw the graph
        """
        self.df_ohlcv.at[self.index, name] = value
        if name not in self.plot_data:
            self.plot_data[name] = {'color': color, 'overlay': overlay}

