import tushare as ts
import pandas as pd
import matplotlib.pyplot as plt
import time
from tqdm import tqdm

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# Tushare 初始化
ts.set_token("cc3de208455a2a97b7cd257e2e0ddc16cfd4b94cf9e46819d6becc68")
pro = ts.pro_api()

# 参数设置
total_0 = 50000                                     # 初始总本金
tolerance = [0.05, 0.1, 0.15, 0.2]                  # 相对亏损容忍度
protected = 40000                                   # 保护本金
enviornments = {'熊市':('20230408', '20240918'),
                '牛市':('20240918', '20260227'),
                '牛转熊':('20230408', '20260227')}  # 市场环境


# 读取指数成分股代码函数
def load_index_codes(index):
    df = pd.read_excel(index, header=None)
    codes = df.iloc[1:, 4].dropna().astype(str)

    result = []
    for code in codes:
        code = code.zfill(6)
        if code.startswith(("6", "9")): # 上交所标的
            result.append(code + ".SH")
        else:                           # 深交所标的
            result.append(code + ".SZ")

    return list(set(result))


# 读取三个指数成分股
sz50 = load_index_codes("000016cons.xls")
hs300 = load_index_codes("000300cons.xls")
kc50 = load_index_codes("000688cons.xls")

targets = {'上证50':sz50,
           '沪深300':hs300,
           '科创50':kc50}


# 单只股票回测函数
def backtest_stock(code, start, end, tol):
    try:
        df = pro.daily(ts_code=code, start_date=start, end_date=end)
        time.sleep(1.2)

        if df is None:
            return None, None, None

        df = df.sort_values("trade_date")
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date")

        total = []                                              # 总资产时间序列
        market = []                                             # 个股市值时间序列
        total_prev = total_0                                    # 上一日总资产
        market_prev = min((total_0 - protected) / tol, total_0) # 上一日市值

        total.append(total_prev)
        market.append(market_prev)

        for i in range(1, len(df)):
            ## 计算上一日涨跌幅并更新上一日总资产
            change = (df["close"].iloc[i-1] - df["open"].iloc[i-1]) / df["open"].iloc[i-1]
            total_n = total_prev + market_prev * change
            total_n = max(total_n, protected)

            market_n = min((total_n - protected) / tol, total_n) # 调仓目标市值

            total.append(total_n)
            market.append(market_n)

            total_prev = total_n
            market_prev = market_n

        total = pd.Series(total, index=df.index)
        market = pd.Series(market, index=df.index)

        return df, total, market

    except:
        return None, None, None


# 基准策略总资产和市值计算函数
def benchmark(df, invest, empty):
    initial = df["open"].iloc[0]
    shares = invest / initial

    market = shares * df["close"]
    total = market + empty

    return total, market


# 指数全成分股回测函数
def batch_backtest(index, index_name, start, end, tolerance):

    ## 数组元素为面板数据
    s_total = []  # 本策略总资产
    s_market = [] # 本策略市值

    ## 数组元素为时间序列
    cons_total = []   # 保守基准总资产面板
    conmarket = []    # 保守基准市值面板
    aggr_total = []   # 激进基准总资产面板
    aggr_market = []  # 激进基准市值面板

    # 对不同的相对亏损容忍度参数分别进行回测
    for i, tol in enumerate(tolerance):
        s_total.append([])  # 单个相对亏损容忍度下本策略总资产面板数据，数组元素为时间序列
        s_market.append([]) # 单个相对亏损容忍度下本策略市值面板数据，数组元素为时间序列
        for stock in tqdm(index, desc=index_name):
            df, total, market = backtest_stock(stock, start, end, tol)
            if df is None:
                continue
            
            s_total[i].append(total)
            s_market[i].append(market)

            # 保守基准策略：只投容忍亏损本金
            c_total, c_market = benchmark(df, total_0 - protected, protected)
            cons_total.append(c_total)
            conmarket.append(c_market)

            # 激进基准策略：本金all in
            a_total, a_market = benchmark(df, total_0, 0)
            aggr_total.append(a_total)
            aggr_market.append(a_market)

 
    ## 按时间对齐后取均值
        s_total[i] = pd.concat(s_total[i], axis=1).mean(axis=1)
        s_market[i] = pd.concat(s_market[i], axis=1).mean(axis=1)

    cons_total = pd.concat(cons_total, axis=1).mean(axis=1)
    conmarket = pd.concat(conmarket, axis=1).mean(axis=1)

    aggr_total = pd.concat(aggr_total, axis=1).mean(axis=1)
    aggr_market = pd.concat(aggr_market, axis=1).mean(axis=1)
    '''
    # ============
    # 收益率
    # ============
    strat_ret = (s_total / total_0 - 1) * 100
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
    ## 总资产变化可视化
    plt.figure(figsize=(12,6))
    for i, lst in enumerate(s_total):
        plt.plot(lst, label=f"本策略(tolerance={tolerance[i]}%)", alpha=0.5)
    plt.plot(cons_total, label="保守基准")
    plt.plot(aggr_total, label="激进基准")
    plt.title(f"{index_name} {start}——{end} 总资产")
    plt.legend()
    plt.grid()
    plt.show()

    ## 持仓市值可视化
    plt.figure(figsize=(12,6))
    for i, lst in enumerate(s_market):
        plt.plot(lst, label=f"本策略(tolerance={tolerance[i]}%)", alpha=0.5)
    plt.plot(conmarket, label="保守基准")
    plt.plot(aggr_market, label="激进基准")
    plt.title(f"{index_name} {start}——{end} 持仓市值")
    plt.legend()
    plt.grid()
    plt.show()

    print(f"{index_name} {start}——{end} 回测完成")


# 主函数
for trend, interval in enviornments.items():
    start = interval[0]
    end = interval[1]
    for index_name, index in targets.items():
        batch_backtest(index, index_name, start, end, tolerance)