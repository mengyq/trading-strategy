#!/usr/bin/env python3
"""v7 - Stricter entry: full multi-TF alignment + volume confirmation + fundamentals"""
import pandas as pd
import numpy as np
import csv
import matplotlib; matplotlib.use("Agg")
import csv
import matplotlib.pyplot as plt
import os, time, warnings, json
warnings.filterwarnings("ignore")

OUTDIR = r"C:\Users\myq28\Documents\Codex\2026-07-23\ma5-ma10-ma20-ma60-macd-1\outputs_v7"
FC = r"C:\Users\myq28\Documents\Codex\2026-07-23\ma5-ma10-ma20-ma60-macd-1\outputs\factors_cache"
FUND_DIR = r"C:\Users\myq28\Documents\Codex\2026-07-23\ma5-ma10-ma20-ma60-macd-1\outputs\fundamental_cache"
IC = 1000000
SD = "20210701"
ED = "20260723"
MP = 5; MPP = 0.20; MPB = 3; MHD = 30
PDD_LIMIT = 0.20; PF_STOP = 0.15
PRICE_MIN = 3.0; PRICE_MAX = 50.0; MIN_DAYS = 120  # 4 months IPO age

W = {"W_TREND": 0.30, "W_MACD": 0.15, "W_VOL": 0.15, "W_RSI": 0.15, "W_MOM": 0.15, "W_LIQ": 0.10}

# (SL, trail, trend_threshold, cost_desc, desc)
PARAM_GRID = [
    # 2 stocks, 50% each
    (0.06, 0.15, 0.35, "zero", "z_p2_sl6_tr15"),
    (0.07, 0.10, 0.35, "zero", "z_p2_sl7_tr10"),
    (0.07, 0.12, 0.35, "zero", "z_p2_sl7_tr12"),
    (0.06, 0.15, 0.35, "real", "p2_sl6_tr15"),
    (0.07, 0.10, 0.35, "real", "p2_sl7_tr10"),
    (0.07, 0.12, 0.35, "real", "p2_sl7_tr12"),
    (0.05, 0.15, 0.35, "real", "p2_sl5_tr15"),
    (0.08, 0.08, 0.35, "real", "p2_sl8_tr08"),
    (0.07, 0.10, 0.40, "real", "p2_sl7_tr10_t40"),
    # 3 stocks, 33% each
    (0.06, 0.15, 0.35, "real", "p3_sl6_tr15"),
    (0.07, 0.10, 0.35, "real", "p3_sl7_tr10"),
    (0.07, 0.12, 0.35, "real", "p3_sl7_tr12"),
    # 1 stock, 100% all-in
    (0.07, 0.10, 0.35, "real", "p1_sl7_tr10"),
]
def load_factors():
    print("Loading factors..."); t0 = time.time()
    data = {}; fd = {}
    for f in os.listdir(FC):
        if not f.endswith(".csv"): continue
        code = f.replace(".csv","")
        df = pd.read_csv(os.path.join(FC, f))
        df["D"] = pd.to_datetime(df["D"])
        data[code] = df
        fd[code] = df["D"].iloc[0]
    print(f"  {len(data)} stocks, {time.time()-t0:.0f}s")
    return data, fd

def load_fundamentals(codes):
    """Load cached fundamental data (PE/PB/ROE) if exists."""
    if not os.path.exists(FUND_DIR):
        print("  No fundamental cache")
        return {}
    fund = {}
    for f in os.listdir(FUND_DIR):
        if not f.endswith(".json"): continue
        code = f.replace(".json","")
        if code not in codes: continue
        try:
            with open(os.path.join(FUND_DIR, f), "r") as fh:
                fund[code] = json.load(fh)
        except: pass
    if fund:
        print(f"  Loaded {len(fund)} fundamental records")
    return fund

def build_daily(data, fund, fd):
    t0 = time.time()
    di = {}; breadth = {}
    for code, df in data.items():
        for _, row in df.iterrows():
            d = row["D"]
            if d not in di: di[d] = {}
            di[d][code] = row
            if d not in breadth: breadth[d] = {"t": 0, "a": 0}
            breadth[d]["t"] += 1
            if row["C"] > row.get("M60", np.inf): breadth[d]["a"] += 1
    for d in breadth: breadth[d] = breadth[d]["a"] / max(breadth[d]["t"], 1)
    print(f"  {len(di)} days, {time.time()-t0:.0f}s")
    return di, breadth
def strict_buy(r):
    """Strict multi-timeframe entry condition."""
    if not r.get("buy", False): return False
    if pd.isna(r.get("M200", np.nan)) or r["C"] <= r.get("M200", np.inf): return False
    if r.get("M60", 0) <= r.get("M200", np.inf): return False
    if r.get("F_VOL", 0) < 80: return False  # vol > 1.5x
    if r.get("F_MOM", 0) < 60: return False  # positive momentum
    return True

def score_stock(r, fund_info=None):
    s = (W["W_TREND"]*r.get("F_TREND",0) + W["W_MACD"]*r.get("F_MACD",0) +
         W["W_VOL"]*r.get("F_VOL",0) + W["W_RSI"]*r.get("F_RSI",0) +
         W["W_MOM"]*r.get("F_MOM",0) + W["W_LIQ"]*r.get("F_LIQ",0))
    if fund_info:
        if fund_info.get("roe", 0) >= 10: s = s * 1.1
        if 0 < fund_info.get("pe", 999) <= 30: s = s * 1.05
        if 0 < fund_info.get("pb", 999) <= 5: s = s * 1.05
    return s

class Engine:
    def __init__(self, sl, trail, trend, cost_mode, desc, MP=3, MPP=0.33):
        self.SL = sl; self.TRAIL = trail; self.TREND = trend; self.MP = MP; self.MPP = MPP; self.DESC = desc
        if cost_mode == "zero":
            self.CR = 0; self.ST = 0; self.SP = 0
        else:
            self.CR = 0.00025; self.ST = 0.001; self.SP = 0.0003
        self.reset()
    def reset(self):
        self.c = IC; self.av = IC; self.pos = {}; self.tr = []; self.eq = []
        self.peak_eq = IC; self.buy_times = 0
    def tv(self):
        return self.av + sum(p["sv"] for p in self.pos.values())
    def run(self, di, dates, breed, fd, fund):
        for d in dates:
            day = di.get(d, {}); eq = self.tv()
            if eq > self.peak_eq: self.peak_eq = eq
            pdd = (self.peak_eq - eq) / self.peak_eq
            market_ok = breed.get(d, 0) >= self.TREND

            for code in list(self.pos.keys()):
                if code not in day: continue
                r = day[code]; p = self.pos[code]; close = r["C"]
                p["sv"] = p["sh"] * close; p["hd"] += 1
                if close > p["pk"]: p["pk"] = close
                pp = (close - p["ep"]) / p["ep"]
                reason = None
                if pp <= -self.SL: reason = f"SL_{pp*100:.0f}"
                elif p["pk"] > p["ep"] * 1.05:
                    dd = (p["pk"] - close) / p["pk"]
                    if dd >= self.TRAIL: reason = f"TRAIL_{dd*100:.0f}"
                elif p["hd"] >= MHD and pp <= 0: reason = f"TIME_{p['hd']}d"
                if not reason and pp >= 0.30: reason = f"TP_{pp*100:.0f}"
                if reason:
                    self.sell(code, d, close, reason)
                    self.pos.pop(code, None)

            if pdd >= PDD_LIMIT:
                for code in list(self.pos.keys()):
                    if code in day: self.sell(code, d, day[code]["C"], f"PDD_{pdd*100:.0f}")
                    self.pos.pop(code, None)
                self.eq.append({"d": d, "eq": eq, "np": 0}); continue

            if len(self.pos) < self.MP and pdd < PF_STOP and market_ok:
                cand = []
                for code, r in day.items():
                    if code in self.pos: continue
                    if not strict_buy(r): continue
                    close = r["C"]
                    if close < PRICE_MIN or close > PRICE_MAX: continue
                    fdate = fd.get(code)
                    if (d - fdate).days < MIN_DAYS if fdate else True: continue
                    fi = fund.get(code) if fund else None
                    s = score_stock(r, fi)
                    cand.append((code, r, close, s))
                cand.sort(key=lambda x: x[3], reverse=True)
                for code, r, close, s in cand[:MPB]:
                    if len(self.pos) >= self.MP: break
                    amt = min(self.av / max(1, self.MP - len(self.pos)) * 0.95, self.av * self.MPP)
                    sh = int(amt / (close * (1 + self.SP)) / 100) * 100
                    if sh <= 0: continue
                    cost = sh * close * (1 + self.SP) * (1 + self.CR)
                    if cost > self.av: continue
                    self.av -= cost
                    self.pos[code] = {"ep": close, "sh": sh, "pk": close, "hd": 1, "sv": sh * close}
                    self.buy_times += 1
            self.eq.append({"d": d, "eq": self.tv(), "np": len(self.pos)})
        return self.rpt()
    def sell(self, code, date, price, reason):
        p = self.pos[code]
        val = p["sh"] * price * (1 - self.SP)
        net = val - val * self.CR - val * self.ST
        cost = p["ep"] * p["sh"] * (1 + self.SP) * (1 + self.CR)
        pnl = net - cost
        self.av += net
        self.tr.append({"code": code, "ep": round(p["ep"],2), "xp": round(price,2),
                        "pnl": round(pnl,2), "pct": round(pnl/cost,4),
                        "hd": p["hd"], "exit": date.strftime("%Y%m%d"), "reason": reason})
    def rpt(self):
        eq = pd.DataFrame(self.eq); tr = pd.DataFrame(self.tr)
        if len(eq) == 0: return {"init": IC, "final": IC}, eq, tr
        total_ret = eq["eq"].iloc[-1] / IC - 1
        yrs = (pd.to_datetime(ED) - pd.to_datetime(SD)).days / 365
        ann = (1 + total_ret) ** (1 / max(yrs, 0.1)) - 1
        eq["cm"] = eq["eq"].cummax(); eq["dd"] = (eq["eq"]-eq["cm"])/eq["cm"]
        mdd = eq["dd"].min()
        dr = eq["eq"].pct_change().dropna()
        shp = np.sqrt(252)*(dr.mean()-0.03/252)/dr.std() if len(dr)>1 and dr.std()>0 else 0
        calmar = ann/abs(mdd) if mdd!=0 else 0
        hits = sum(1 for r in self.tr if r["pnl"] > 0)
        st = {"init": IC, "final": round(eq["eq"].iloc[-1],2), "ret%": round(total_ret*100,2),
              "ann%": round(ann*100,2), "mdd%": round(mdd*100,2), "sharpe": round(shp,2),
              "calmar": round(calmar,2), "trades": len(self.tr), "buy_times": self.buy_times, "desc": self.DESC}
        if len(self.tr) > 0:
            st["wr%"] = round(hits / len(self.tr) * 100, 2)
            w_p = [r["pct"] for r in self.tr if r["pnl"] > 0]
            l_p = [r["pct"] for r in self.tr if r["pnl"] < 0]
            st["aw%"] = round(np.mean(w_p)*100, 2) if w_p else 0
            st["al%"] = round(np.mean(l_p)*100, 2) if l_p else 0
            w_s = sum(r["pnl"] for r in self.tr if r["pnl"] > 0)
            l_s = sum(abs(r["pnl"]) for r in self.tr if r["pnl"] < 0)
            st["pf"] = round(w_s / l_s, 2) if l_s > 0 else "inf"
        return st, eq, tr

def plot_curves(results, path):
    fig, axes = plt.subplots(2,1,figsize=(14,10),gridspec_kw={"height_ratios":[3,1]})
    colors = ["#2196F3","#FF5722","#4CAF50","#FF9800","#9C27B0","#00BCD4","#E91E63"]
    for idx,(desc,st,eq_df) in enumerate(results[:7]):
        if len(eq_df)==0: continue
        c = colors[idx%len(colors)]
        dates = pd.to_datetime(eq_df["d"]) if "d" in eq_df.columns else range(len(eq_df))
        axes[0].plot(dates, eq_df["eq"].values, label=f"{desc} ({st.get('ret%',0):.1f}% pf={st.get('pf','inf')})", color=c, lw=1.5)
        axes[1].fill_between(dates, (eq_df["eq"]-np.maximum.accumulate(eq_df["eq"]))/np.maximum.accumulate(eq_df["eq"])*100, 0, color=c, alpha=0.3)
    axes[0].set_ylabel("Equity"); axes[0].set_title("v7 Strict Entry"); axes[0].legend(fontsize=8)
    axes[0].axhline(y=IC,color="gray",ls="--",alpha=0.5); axes[0].grid(alpha=0.3)
    axes[1].set_ylabel("DD%"); axes[1].set_xlabel("Date"); axes[1].grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(path, dpi=150); plt.close()

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    print("="*70); print("  v7 - Full multi-TF alignment + Volume confirmation"); print("="*70)
    data, fd = load_factors()
    fund = load_fundamentals(set(data.keys()))
    di, breadth = build_daily(data, fund, fd)
    dates = sorted(d for d in di if SD <= d.strftime("%Y%m%d") <= ED)
    print(f"  {len(dates)} days")
    results = []; all_eq = []
    for sl, tra, tre, cm, desc in PARAM_GRID:
        mp = 3; mpp = 0.33
        if desc.startswith("p2_"): mp, mpp = 2, 0.50
        if desc.startswith("p3_"): mp, mpp = 3, 0.33
        if desc.startswith("p1_"): mp, mpp = 1, 1.00
        if desc.startswith("z_p2_"): mp, mpp = 2, 0.50
        eng = Engine(sl, tra, tre, cm, desc, MP=mp, MPP=mpp)
        st, eq_df, _ = eng.run(di, dates, breadth, fd, fund)
        pf_str = f"{st['pf']}" if isinstance(st['pf'],str) else f"{st['pf']:.2f}"
        print(f"  {desc:17s}  ret={st['ret%']:6.2f}%  ann={st['ann%']:5.2f}%  "
              f"mdd={st['mdd%']:5.2f}%  sharpe={st['sharpe']:.2f}  "
              f"wr={st.get('wr%',0):.0f}%  pf={pf_str}  trades={st['trades']}")
        results.append((desc,st)); all_eq.append((desc,st,eq_df))
    print("\n"+"="*70+"\n  SUMMARY (sorted by PF)\n"+"="*70)
    results.sort(key=lambda x: x[1].get("pf", 0) if isinstance(x[1].get("pf", 0),(int,float)) else 0, reverse=True)
    for desc,st in results:
        pf_str = f"{st['pf']}" if isinstance(st['pf'],str) else f"{st['pf']:.2f}"
        print(f"  {desc:17s}  ret={st['ret%']:6.2f}%  ann={st['ann%']:5.2f}%  "
              f"sharpe={st['sharpe']:.2f}  pf={pf_str}  wr={st.get('wr%',0):.0f}%  "
              f"aw={st.get('aw%',0):.1f}%  al={st.get('al%',0):.1f}%  trades={st['trades']}  mdd={st['mdd%']:5.2f}%")
    rpt = [{"desc":d,**{k:v for k,v in st.items() if k!="desc"}} for d,st in results]
    with open(os.path.join(OUTDIR,"report_v7.json"),"w",encoding="utf-8") as f:
        json.dump(rpt,f,ensure_ascii=False,indent=2,default=str)
    plot_curves(all_eq, os.path.join(OUTDIR,"chart_v7.png"))
    print(f"\nDone! Outputs in {OUTDIR}")

if __name__ == "__main__":
    main()
