
import os, sys, json, subprocess
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.dirname(BASE)

def run_daily():
    from notify import send_pushplus
    result = subprocess.run([sys.executable, os.path.join(BASE, 'live_signal.py')],
                          capture_output=True, text=True, cwd=WORK_DIR)
    output = result.stdout + result.stderr
    log_path = os.path.join(BASE, 'trade_log.json')
    log = json.load(open(log_path, encoding='utf-8')) if os.path.exists(log_path) else []
    today = datetime.now().strftime('%Y-%m-%d')
    log.append({'date': today, 'output': output[:1000]})
    json.dump(log[-365:], open(log_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    has_buy = '买入' in output
    has_sell = ('卖出' in output) and ('无需卖出' not in output)
    if has_buy or has_sell:
        lines = [l.strip() for l in output.split(chr(10)) if any(k in l for k in ['买入','卖出','止损'])]
        content = chr(10).join(lines[:15]) if lines else output[:500]
        send_pushplus('交易信号 - ' + today, content)
        print('Notify sent')
    else:
        print('No signals today')

def run_weekly():
    from notify import send_pushplus
    log_path = os.path.join(BASE, 'trade_log.json')
    log = json.load(open(log_path, encoding='utf-8')) if os.path.exists(log_path) else []
    week = [r for r in log if r['date'] >= (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')]
    content = '周报: ' + str(datetime.now().strftime('%Y-W%V')) + chr(10)
    content += '本周交易日: ' + str(len(week)) + '天' + chr(10)
    content += '当前持仓: 请运行 python work/live_signal.py 查看'
    send_pushplus('周报', content)
    print('Weekly sent')

def run_monthly():
    from notify import send_pushplus
    log_path = os.path.join(BASE, 'trade_log.json')
    log = json.load(open(log_path, encoding='utf-8')) if os.path.exists(log_path) else []
    month = [r for r in log if r['date'] >= (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')]
    content = '月报: ' + str(datetime.now().strftime('%Y-%m')) + chr(10)
    content += '本月交易日: ' + str(len(month)) + '天' + chr(10)
    content += '累计运行: ' + str(len(log)) + '天'
    send_pushplus('月报', content)
    print('Monthly sent')

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'daily'
    {'daily': run_daily, 'weekly': run_weekly, 'monthly': run_monthly}.get(mode, run_daily)()
