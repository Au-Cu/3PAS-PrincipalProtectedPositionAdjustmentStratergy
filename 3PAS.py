import tushare as ts
import pandas as pd
import matplotlib.pyplot as plt
import time
from tqdm import tqdm

# ============
# 中文显示
# ============
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# ============
# Tushare 初始化
# ============
ts.set_token("cc3de208455a2a97b7cd257e2e0ddc16cfd4b94cf9e46819d6becc68")
pro = ts.pro_api()

# ============
# 参数
# ============
total_0 = 50000
tolerance = [0.05, 0.1, 0.15, 0.2]
protected = 40000
enviornments = {'熊市':('20230408', '20240918'),
                '牛市':('20240918', '20260227'),
                '牛转熊':('20230408', '20260227')}

# ============
# 读取Excel成分股
# ============
def load_index_codes(file_path):
    df = pd.read_excel(file_path, header=None)

    # E列 -> index 4，从第2行开始
    codes = df.iloc[1:, 4].dropna().astype(str)

    result = []
    for code in codes:
        code = code.zfill(6)
        if code.startswith(("6", "9")):
            result.append(code + ".SH")
        else:
            result.append(code + ".SZ")

    return list(set(result))


# ============
# 读取三个指数
# ============
sz50 = load_index_codes("000016cons.xls")
hs300 = load_index_codes("000300cons.xls")
kc50 = load_index_codes("000688cons.xls")

targets = {'上证50':sz50,
           '沪深300':hs300,
           '科创50':kc50}

# ============
# 回测单只股票
# ============
def backtest_stock(ts_code, start, end, tol):
    try:
        df = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
        #time.sleep(1.2)

        if df is None or len(df) < 30:
            return None, None, None

        df = df.sort_values("trade_date")
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date")

        total_list = []
        market_list = []

        total_prev = total_0
        market_prev = min((total_0 - protected) / tol, total_0)

        total_list.append(total_prev)
        market_list.append(market_prev)

        for i in range(1, len(df)):
            change = (df["close"].iloc[i-1] - df["open"].iloc[i-1]) / df["open"].iloc[i-1]

            total_n = total_prev + market_prev * change
            total_n = max(total_n, protected)

            market_n = min((total_n - protected) / tol, total_n)

            total_list.append(total_n)
            market_list.append(market_n)

            total_prev = total_n
            market_prev = market_n

        total_series = pd.Series(total_list, index=df.index)
        market_series = pd.Series(market_list, index=df.index)

        return df, total_series, market_series

    except:
        return None, None, None


# ============
# 基准策略
# ============
def benchmark(df, invest_amount, add_cash=0):
    first_open = df["open"].iloc[0]
    shares = invest_amount / first_open

    market = shares * df["close"]
    total = market + add_cash

    return total, market


# ============
# 批量回测
# ============
def batch_backtest(index, index_name, start, end, tolerance):

    strat_total = []
    strat_market = []

    cons_total = []
    cons_market = []

    aggr_total = []
    aggr_market = []

    for i, tol in enumerate(tolerance):
        strat_total.append([])
        strat_market.append([])
        for stock in tqdm(index, desc=index_name):
            df, s_total, s_market = backtest_stock(stock, start, end, tol)

            if df is None:
                continue
            
            strat_total[i].append(s_total)
            strat_market[i].append(s_market)

            # 保守（只投 total_0 - absol）
            c_total, c_market = benchmark(df, total_0 - protected, protected)
            cons_total.append(c_total)
            cons_market.append(c_market)

            # 激进（all in）
            a_total, a_market = benchmark(df, total_0, 0)
            aggr_total.append(a_total)
            aggr_market.append(a_market)

        # 聚合
        strat_total[i] = pd.concat(strat_total[i], axis=1).mean(axis=1)
        strat_market[i] = pd.concat(strat_market[i], axis=1).mean(axis=1)

    cons_total = pd.concat(cons_total, axis=1).mean(axis=1)
    cons_market = pd.concat(cons_market, axis=1).mean(axis=1)

    aggr_total = pd.concat(aggr_total, axis=1).mean(axis=1)
    aggr_market = pd.concat(aggr_market, axis=1).mean(axis=1)
    '''
    # ============
    # 收益率
    # ============
    strat_ret = (strat_total / total_0 - 1) * 100
    bench_ret = (aggr_total / total_0 - 1) * 100

    # ============
    # 图1 收益率
    # ============

    plt.figure(figsize=(12,6))
    plt.plot(strat_ret, label="策略收益率")
    plt.plot(bench_ret, label="基准收益率")
    plt.title(f"{index_name} {start}——{end} 收益率对比(tolerance={tol}%)")
    plt.legend()
    plt.grid()
    plt.show()
    '''
    # ============
    # 图2 总资产
    # ============
    plt.figure(figsize=(12,6))
    for i, lst in enumerate(strat_total):
        plt.plot(lst, label=f"本策略(tolerance={tolerance[i]}%)")
    plt.plot(cons_total, label="保守基准")
    plt.plot(aggr_total, label="激进基准")
    plt.title(f"{index_name} {start}——{end} 总资产")
    plt.legend()
    plt.grid()
    plt.show()

    # ============
    # 图3 持仓市值
    # ============
    plt.figure(figsize=(12,6))
    for i, lst in enumerate(start_market):
        plt.plot(lst, label=f"本策略(tolerance={tolerance[i]}%)")
    plt.plot(cons_market, label="保守基准")
    plt.plot(aggr_market, label="激进基准")
    plt.title(f"{index_name} {start}——{end} 持仓市值")
    plt.legend()
    plt.grid()
    plt.show()

    print(f"{index_name} {start}——{end} 回测完成")


# ============
# 执行
# ============
for trend, interval in enviornments.items():
    start = interval[0]
    end = interval[1]
    for index_name, index in targets.items():
        batch_backtest(index, index_name, start, end, tolerance)
