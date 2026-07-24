#!/usr/bin/env python3
"""通知推送模块 - PushPlus + Email"""
import json, os, sys
from datetime import datetime, timedelta

def load_config():
    path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def send_pushplus(title, content, token=None):
    """通过PushPlus发送微信消息"""
    if not token:
        config = load_config()
        token = config.get("pushplus", {}).get("token", "")
    if not token:
        return False
    import urllib.request
    data = json.dumps({"token": token, "title": title, "content": content, "template": "txt"}).encode()
    req = urllib.request.Request("https://www.pushplus.plus/send", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())["code"] == 200
    except:
        return False

def send_email(title, content, config=None):
    """发送邮件(需要SMTP授权码)"""
    if not config:
        config = load_config().get("email", {})
    password = config.get("password", "")
    if not password or password == "请输入163邮箱授权码":
        return False, "请先在config.json中配置邮箱授权码"
    import smtplib
    from email.mime.text import MIMEText
    try:
        msg = MIMEText(content, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = config["sender"]
        msg["To"] = config["receiver"]
        s = smtplib.SMTP_SSL(config["smtp_server"], config.get("smtp_port", 465))
        s.login(config["sender"], password)
        s.send_message(msg)
        s.quit()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def send_all(title, content):
    """同时发送PushPlus和邮件"""
    ok = send_pushplus(title, content)
    email_ok, email_msg = send_email(title, content)
    return ok and email_ok

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    if mode == "test":
        r = send_pushplus("策略测试", "推送系统配置完成!")
        print("PushPlus结果:", "成功" if r else "失败")
