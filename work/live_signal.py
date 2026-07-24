#!/usr/bin/env python3
"""
v7_6 策略 · 实时交易信号系统
============================
策略: p2_sl7_tr10（2只持仓, 止损7%, 移动止盈10%）
本金: 5,000 RMB（每只2,500 RMB）
数据: 使用缓存的因子数据（outputs/factors_cache/）
============================================================

使用方法:
  1. 先运行 python work/update_cache.py   # 更新因子缓存（每日执行）
  2. 运行 python work/live_signal.py        # 查看今日买卖信号
  3. 运行 python work/report.py             # 查看周报/月报
"""

import pandas as pd
import numpy as np
import os, sys, json, time
from datetime import datetime, date

# ========== 配置 ==========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FC = os.path.join(BASE_DIR, "outputs", "factors_cache")
FUND_DIR = os.path.join(BASE_DIR, "outputs", "fundamental_cache")
PORTFOLIO_FILE = os.path.join(BASE_DIR, "work", "portfolio.json")

CAPITAL = 5000          # 初始本金
MAX_POS = 2             # 最大持仓数
POS_PCT = 0.50          # 单只仓位比例
STOP_LOSS = 0.07        # 止损 7%
TRAIL_STOP = 0.10       # 移动止盈 10%
MAX_HOLD = 30           # 最大持仓天数
PRICE_MIN = 3.0         # 最低股价
PRICE_MAX = 25.0        # 最高股价（5,000元/2只/100股）
MIN_DAYS = 120          # 上市最少天数

# 买入条件参数
RSI_MIN = 50
RSI_MAX = 78
VOL_MIN = 70            # F_VOL >= 70（成交量 > 1.2倍均量）
MOM_MIN = 0             # 5日动量 > 0

# ========== 策略逻辑 ==========

def load_factor(code):
    """加载单只股票的因子数据"""
    path = os.path.join(FC, code + ".csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df["D"] = pd.to_datetime(df["D"])
    return df

def check_buy(row):
    """检查买入条件（与回测一致）"""
    # MA多头排列
    if row.get("M5", 0) <= row.get("M10", 0): return False
    if row.get("M10", 0) <= row.get("M20", 0): return False
    if row.get("M20", 0) <= row.get("M60", 0): return False
    # C > MA200
    m200 = row.get("M200", None)
    if pd.isna(m200) or row["C"] <= m200: return False
    if row.get("M60", 0) <= m200: return False
    # MACD金叉
    if row.get("DIF", 0) <= row.get("DE", 0): return False
    # RSI区间
    rsi = row.get("R", 50)
    if pd.isna(rsi) or rsi < RSI_MIN or rsi > RSI_MAX: return False
    # 成交量放大
    if row.get("F_VOL", 0) < VOL_MIN: return False
    # 正动量
    if row.get("MOM", -99) <= MOM_MIN: return False
    # ATR正常波动（日波动 < 10%）
    atr_r = row.get("ATR", 0) / max(row["C"], 0.01)
    if pd.isna(atr_r) or atr_r > 0.10: return False
    return True

def check_sell(row, entry_price, peak_price, hold_days):
    """检查卖出条件"""
    close = row["C"]
    pp = (close - entry_price) / entry_price  # 盈亏比例
    reasons = []
    
    # 1.止损
    if pp <= -STOP_LOSS:
        reasons.append("止损(亏损{:.1f}%)".format(pp*100))
        return True, reasons
    
    # 2.移动止盈（从最高点回落）
    if peak_price > entry_price * 1.05:
        dd = (peak_price - close) / peak_price
        if dd >= TRAIL_STOP:
            reasons.append("移动止盈(从高点回落{:.1f}%)".format(dd*100))
            return True, reasons
    
    # 3.时间止损（持仓超过30天且亏损）
    if hold_days >= MAX_HOLD and pp <= 0:
        reasons.append("时间止损(持仓{:.0f}天)".format(hold_days))
        return True, reasons
    
    # 4.止盈（盈利30%以上）
    if pp >= 0.30:
        reasons.append("止盈(盈利{:.1f}%)".format(pp*100))
        return True, reasons
    
    return False, reasons

def load_portfolio():
    """加载当前持仓"""
    if not os.path.exists(PORTFOLIO_FILE):
        return []
    try:
        with open(PORTFOLIO_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_portfolio(portfolio):
    """保存当前持仓"""
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)

def calc_shares(price, budget):
    """计算可买股数（100股=1手）"""
    max_shares = int(budget / price / 100) * 100
    return max(0, max_shares)

# ========== 主程序 ==========

def main():
    print("=" * 65)
    print("  v7_6 交易信号系统")
    print("  策略: 2只持仓, 止损7%, 移动止盈10%, 本金{:.0f}元".format(CAPITAL))
    print("  数据截止: ", datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 65)
    
    # 1. 加载持仓
    portfolio = load_portfolio()
    stock_codes = set(p["code"] for p in portfolio)
    
    # 2. 加载全市场因子数据
    print("\n[1/3] 扫描全市场买入信号...")
    files = sorted([f.replace(".csv", "") for f in os.listdir(FC) if f.endswith(".csv")])
    buylist = []
    
    for code in files:
        if code in stock_codes:
            continue  # 已持仓的不扫描
        df = load_factor(code)
        if df is None or len(df) < 250:
            continue
        
        # 取最新一行
        latest = df.iloc[-1].to_dict()
        d = latest["D"]
        fd = df["D"].iloc[0]
        
        # 上市时间过滤
        if (d - fd).days < MIN_DAYS:
            continue
        
        # 价格过滤
        close = latest["C"]
        if close < PRICE_MIN or close > PRICE_MAX:
            continue
        
        # 买入条件检查
        if check_buy(latest):
            budget = CAPITAL * POS_PCT
            shares = calc_shares(close, budget)
            if shares >= 100:
                buylist.append({
                    "code": code,
                    "price": round(close, 2),
                    "shares": shares,
                    "cost": round(shares * close, 2),
                    "date": d.strftime("%Y-%m-%d")
                })
    
    # 按价格排序
    buylist.sort(key=lambda x: x["price"])
    
    # 3. 检查持仓卖出信号
    print("[2/3] 检查持仓卖出信号...")
    sell_signals = []
    hold_signals = []
    
    for p in portfolio:
        code = p["code"]
        df = load_factor(code)
        if df is None:
            continue
        latest = df.iloc[-1].to_dict()
        
        should_sell, reasons = check_sell(
            latest, p["entry_price"], p["peak_price"], p["hold_days"]
        )
        
        p["hold_days"] += 1
        if latest["C"] > p["peak_price"]:
            p["peak_price"] = latest["C"]
        p["current_price"] = round(latest["C"], 2)
        p["pnl_pct"] = round((latest["C"] - p["entry_price"]) / p["entry_price"] * 100, 2)
        p["pnl_amt"] = round((latest["C"] - p["entry_price"]) * p["shares"], 2)
        
        if should_sell:
            sell_signals.append(p)
        else:
            hold_signals.append(p)
    
    # 4. 输出报告
    print("[3/3] 生成信号报告...")
    print("\n" + "=" * 65)
    print("  【交易信号报告】- " + datetime.now().strftime("%Y-%m-%d"))
    print("=" * 65)
    
    # 卖出信号
    if sell_signals:
        print("\n  !!! 卖出信号 !!!")
        for s in sell_signals:
            print("    股票: {}, 买入价: {}, 现价: {}, 盈亏: {:.1f}%({:.0f}元), 持仓{}天".format(
                s["code"], s["entry_price"], s["current_price"],
                s["pnl_pct"], s["pnl_amt"], s["hold_days"]))
    else:
        print("\n  无需卖出 OK")
    
    # 持仓状态
    if hold_signals:
        print("\n  当前持仓:")
        for h in hold_signals:
            print("    股票: {}, 买入: {}, 现价: {}, 盈亏: {:.1f}%, 持仓{}天".format(
                h["code"], h["entry_price"], h["current_price"],
                h["pnl_pct"], h["hold_days"]))
    
    # 买入信号（最多2只）
    print("\n  当前持仓: {}/{}".format(len(portfolio), MAX_POS))
    empty_slots = MAX_POS - len(portfolio)
    
    if empty_slots > 0 and buylist:
        print("\n  买入信号 (推荐最多{}只):".format(empty_slots))
        for b in buylist[:empty_slots + 1]:
            lot_text = "1手({}股)".format(b["shares"]) if b["shares"] == 100 else "{:.0f}手({}股)".format(b["shares"]/100, b["shares"])
            print("    [买入] {} 价格{}元 {} 约{:.0f}元".format(
                b["code"], b["price"], lot_text, b["cost"]))
    elif not buylist:
        print("\n  无符合条件的买入信号（均线未多头排列或MACD未金叉）")
    else:
        print("\n  仓位已满，等待卖出信号释放仓位")
    
    # 策略说明
    print("\n" + "-" * 65)
    print("  策略说明:")
    print("  买入条件: MA5>MA10>MA20>MA60>MA200 + MACD金叉 + RSI 50-78 + 放量1.2倍 + 正动量")
    print("  卖出条件: 止损{}% | 移动止盈{}% | 持仓>30天亏损 | 止盈30%".format(
        int(STOP_LOSS*100), int(TRAIL_STOP*100)))
    print("  仓位管理: 最多{}只, 每只{}%, 本金{:.0f}元".format(MAX_POS, POS_PCT*100, CAPITAL))
    print("-" * 65)
    
    # 保存持仓
    if sell_signals or hold_signals:
        new_portfolio = [s for s in sell_signals] + hold_signals
        # Remove sold stocks
        new_portfolio = [p for p in new_portfolio if p["code"] not in [s["code"] for s in sell_signals]]
        save_portfolio(new_portfolio)
    elif not portfolio and not any(p["code"] in [s["code"] for s in sell_signals] for p in portfolio):
        pass  # Keep empty portfolio

if __name__ == "__main__":
    main()
