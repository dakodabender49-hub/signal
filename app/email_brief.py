"""
email_brief.py - render the daily brief from docs/state.json and email it.

Runs in the GitHub Action after build.py. SMTP via env secrets:
  SMTP_HOST, SMTP_PORT (465), SMTP_USER, SMTP_PASS, EMAIL_TO
(Gmail: smtp.gmail.com / 465 / your address / an App Password.)
If SMTP isn't configured it just prints the brief.
"""
from __future__ import annotations
import json
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_state():
    with open(os.path.join(ROOT, "docs", "state.json")) as f:
        return json.load(f)


def render_text(state):
    m = state["meta"]
    out = [f"SIGNAL - {m['session']} brief - {m.get('as_of_date','')}  [{m['data_mode']}]", ""]
    out.append("BACKDROP: " + " | ".join(
        f"{b['name']} {b['value']} ({b['change']:+}) {b['note']}" for b in state["backdrop"]))
    out += ["", "FED & DATA (today/upcoming):"]
    for e in state["fed_econ"]:
        a = e["actual"] if e["actual"] else f"cons {e['consensus']}"
        out.append(f"  {e['date']} {e['time']} [{e['impact']}] {e['event']} - prior {e['prior']}, {a}")
    out.append("")
    for i in state["instruments"]:
        if not i.get("verified"):
            out += [f"{i['symbol']}: {i.get('read','withheld')}", ""]
            continue
        out.append(f"{i['symbol']} ({i['name']}) {i['ohlc']['close']} "
                   f"({i['change_pct']:+}%) - {i['structure']}")
        out.append(f"  {i['read']}")
        if i.get("changed"):
            out.append(f"  changed: {', '.join(i['changed'])}")
        out.append("")
    out.append(m["disclaimer"])
    return "\n".join(out)


def send(subject, text):
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER")
    pw = os.environ.get("SMTP_PASS")
    to = os.environ.get("EMAIL_TO")
    if not to:
        try:
            to = json.load(open(os.path.join(ROOT, "config", "watchlist.json")))["email_to"]
        except Exception:
            to = user
    if not (host and user and pw and to):
        print("SMTP not configured - printing brief instead:\n")
        print(text)
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(text, "plain"))
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())
    print("Email sent to", to)


if __name__ == "__main__":
    st = load_state()
    send(f"SIGNAL {st['meta']['session']} brief {st['meta'].get('as_of_date','')}",
         render_text(st))
