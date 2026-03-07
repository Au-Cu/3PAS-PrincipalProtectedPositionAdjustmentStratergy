import tushare as ts
import pandas as pd
import matplotlib.pyplot as plt
import time
from tqdm import tqdm
import numpy as np

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# 参数设置
total_0 = 50000                                     # 初始总本金
tolerance = [0.1, 0.15, 0.2, 0.3, 0.4]                  # 相对亏损容忍度
protected = 40000                                   # 保护本金
enviornments = {'熊市':('20230408', '20240918'),
                '牛市':('20240918', '20260227'),
                '熊转牛':('20230408', '20260227')}  # 市场环境

# Tushare 初始化
ts.set_token("cc3de208455a2a97b7cd257e2e0ddc16cfd4b94cf9e46819d6becc68")
pro = ts.pro_api()

# 回测指标汇总表格初始化
summary = []


# 读取指数成分股代码函数
def load_index_codes(index):

    df = pd.read_excel(index, header=None)
    codes = df.iloc[1:, 4].dropna().astype(str)

    result = []

    for code in codes:

        code = code.zfill(6)            # 补全excel读入时丢失的0

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

# 核密度图数据容器初始化
kde_metrics={'年化收益':{trend:{index_name:[] for index_name in targets} for trend in enviornments},
             '最大回撤':{trend:{index_name:[] for index_name in targets} for trend in enviornments},
             '年化波动率':{trend:{index_name:[] for index_name in targets} for trend in enviornments}}

# 单只股票回测函数
def backtest_stock(code, start, end, tol):

    try:

        df = pro.daily(ts_code=code, start_date=start, end_date=end)
        
        time.sleep(1.2)

        if df is None:
            print('标的数据获取出现问题')
            raise ValueError

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


# 年化收益计算函数
def annual_return(series):
    days = len(series)
    if days == 0:
        return None
    total_ret = series.iloc[-1] / series.iloc[0] - 1
    return (1 + total_ret) ** (252 / days) - 1


# 最大回撤计算函数
def max_drawdown(series):
    cummax = series.cummax()
    drawdown = (series - cummax) / cummax
    return drawdown.min()


# 年化波动率计算函数
def annual_volatility(series):
    ret = series.pct_change().dropna()
    return ret.std() * np.sqrt(252)


# 胜率计算函数
def win_rate(series):
    ret = series.pct_change().dropna()
    return (ret > 0).sum() / len(ret)


# 指数全成分股回测函数
def batch_backtest(index, index_name, start, end, tolerance, trend):

    ## 数组元素为面板数据
    strat_total = []    # 本策略总资产
    strat_market = []   # 本策略市值
    strat_position = [] # 本策略仓位

    ## 数组元素为时间序列
    cons_total = []    # 保守基准总资产面板
    cons_market = []   # 保守基准市值面板
    cons_position = [] # 保守基准仓位面板

    aggr_total = []    # 激进基准总资产面板
    aggr_market = []   # 激进基准市值面板
    aggr_position = [] # 激进基准仓位面板

    # 数组元素为四元组
    strat_metrics = [] # 策略表现统计指标
    bench_metrics = [] # 基准表现统计指标

    if index == kc50:
        tols = tolerance[2:] # 科创50成分股涨跌停幅度为20%，取tolerance为20%，30%，40%
    else:
        tols = tolerance[:3] # 上证50、沪深300成分股涨跌停幅度多为10%，取tolerance为10%，15%，20%

    ## 对不同的相对亏损容忍度参数分别进行回测
    for i, tol in enumerate(tols):

        strat_total.append([])    # 单个相对亏损容忍度下本策略总资产面板数据，数组元素为时间序列
        strat_market.append([])   # 单个相对亏损容忍度下本策略市值面板数据，数组元素为时间序列
        strat_position.append([]) # 单个相对亏损容忍度下本策略仓位面板数据，数组元素为时间序列
        
        ### 对所有的成分股分别进行回测
        for stock in tqdm(index, desc=index_name):

            df, total, market = backtest_stock(stock, start, end, tol)
            
            if df is None:
                continue

            strat_total[i].append(total)
            strat_market[i].append(market)

            #### 保守基准策略：只投容忍亏损本金
            c_total, c_market = benchmark(df, total_0 - protected, protected)
            cons_total.append(c_total)
            cons_market.append(c_market)

            #### 激进基准策略：本金all in
            a_total, a_market = benchmark(df, total_0, 0)
            aggr_total.append(a_total)
            aggr_market.append(a_market)
        
            #### 取中间的tolerance值，计算各统计指标
            if i == 1:

                ar = annual_return(total)
                md = max_drawdown(total)
                av = annual_volatility(total)
                wr = win_rate(total)

                kde_metrics['年化收益'][trend][index_name].append(ar)
                kde_metrics['最大回撤'][trend][index_name].append(md)
                kde_metrics['年化波动率'][trend][index_name].append(av)

                strat_metrics.append([ar, md, av, wr])

                bench_metrics.append([annual_return(a_total),
                                      max_drawdown(a_total),
                                      annual_volatility(a_total),
                                      win_rate(a_total)])
                
    ## 按时间对齐后取均值
        try:

            strat_total[i] = pd.concat(strat_total[i], axis=1).mean(axis=1)
            strat_market[i] = pd.concat(strat_market[i], axis=1).mean(axis=1)

        except ValueError:
            print('调用API接口频率过高，请等待一分钟后重试，或尝试切换网络')
            raise

        strat_position[i] = np.array(strat_market[i]) / np.array(strat_total[i])
    
    try:
        
        cons_total = pd.concat(cons_total, axis=1).mean(axis=1)
        cons_market = pd.concat(cons_market, axis=1).mean(axis=1)

        aggr_total = pd.concat(aggr_total, axis=1).mean(axis=1)
        aggr_market = pd.concat(aggr_market, axis=1).mean(axis=1)

    except ValueError:
        print('调用API接口频率过高，请等待一分钟后重试，或尝试切换网络')
        raise

    ## 计算基准仓位
    cons_position = np.array(cons_market) / np.array(cons_total)
    aggr_position = np.array(aggr_market) / np.array(aggr_total)

    strat_metrics = np.array(strat_metrics)
    bench_metrics = np.array(bench_metrics)

    # 统计指标汇总
    summary.append([trend,
                    index_name,
                    np.nanmean(strat_metrics[:,0]),
                    np.nanmean(bench_metrics[:,1]),
                    np.nanmean(strat_metrics[:,1]),
                    np.nanmean(bench_metrics[:,2]),
                    np.nanmean(strat_metrics[:,2])])

    ## 总资产变化可视化
    plt.figure(figsize=(12,6))
    for i, lst in enumerate(strat_total):
        plt.plot(lst, label=f"本策略(tolerance={tols[i]}%)", alpha=0.5)
    plt.plot(cons_total, label="保守基准")
    plt.plot(aggr_total, label="激进基准")
    plt.title(f"{index_name} {start}——{end} 总资产")
    plt.legend()
    plt.grid()
    plt.show()

    ## 仓位可视化
    plt.figure(figsize=(12,6))
    for i, array in enumerate(strat_position):
        plt.plot(array, label=f"本策略(tolerance={tols[i]}%)", alpha=0.5)
    plt.plot(cons_position, label="保守基准")
    plt.plot(aggr_position, label="激进基准")
    plt.title(f"{index_name} {start}——{end} 仓位")
    plt.legend()
    plt.grid()
    plt.show()

    print(f"{index_name} {start}——{end} 回测完成")


# 主函数
for trend, interval in enviornments.items():

    start = interval[0]
    end = interval[1]

    for index_name, index in targets.items():

        batch_backtest(index, index_name, start, end, tolerance, trend)

# 绘制策略统计指标核密度图
for metric in kde_metrics:

    for env in enviornments:

        plt.figure(figsize=(8,5))

        for index in targets:

            data = pd.Series(kde_metrics[metric][env][index]).dropna()

            if len(data) > 1:
                data.plot.kde(label=index)

        plt.title(f"{metric} KDE分布 | {env}")
        plt.legend()
        plt.grid()
        plt.show()

# 输出回测指标汇总表
table = pd.DataFrame(summary, columns=['市场环境',
                                       '指数风格',
                                       '年化收益（策略平均）',
                                       '最大回撤(基准)',
                                       '最大回撤(策略平均)',
                                       '年化波动率(基准)',
                                       '年化波动率(策略平均)'])
print("\n策略表现统计汇总表\n")
print(summary)