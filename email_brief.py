"""
email_brief.py - render the daily brief from docs/state.json and email it.

Sends a polished, responsive HTML email (with a plain-text fallback). The HTML
is built with inline styles + table layout for email-client compatibility
(Gmail / Outlook / Apple Mail). No AI, no extra cost - it renders the same
verified numbers the dashboard uses.

SMTP via env secrets: SMTP_HOST, SMTP_PORT(465), SMTP_USER, SMTP_PASS, EMAIL_TO.
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

UP, DOWN, MUT = "#1a7f37", "#b42318", "#6b7280"


def load_state():
    with open(os.path.join(ROOT, "docs", "state.json")) as f:
        return json.load(f)


def fmt(x):
    return "-" if x is None else f"{x:,.2f}"


def plus(x):
    return ("+" if x > 0 else "") + str(x)


# ----------------------------------------------------------- plain text -------
def render_text(state):
    m = state["meta"]
    out = [f"SIGNAL - {m['session']} brief - {m.get('as_of_date','')}  [{m['data_mode']}]", ""]
    out.append("BACKDROP: " + " | ".join(
        f"{b['name']} {b['value']} ({b['change']:+}) {b['note']}" for b in state["backdrop"]))
    out += ["", "FED & DATA:"]
    for e in state["fed_econ"]:
        a = e["actual"] if e["actual"] else f"cons {e['consensus']}"
        out.append(f"  {e['date']} {e['time']} [{e['impact']}] {e['event']} - prior {e['prior']}, {a}")
    out.append("")
    for i in state["instruments"]:
        if not i.get("verified"):
            out += [f"{i['symbol']}: {i.get('read','withheld')}", ""]
            continue
        out.append(f"{i['symbol']} ({i['name']}) {i['ohlc']['close']} ({i['change_pct']:+}%) - {i['structure']}")
        out.append(f"  {i['read']}")
        if i.get("changed"):
            out.append(f"  changed: {', '.join(i['changed'])}")
        out.append("")
    out.append(m["disclaimer"])
    return "\n".join(out)


# ----------------------------------------------------------------- html -------
def market_one_liner(state):
    vix = next((b for b in state["backdrop"] if b["name"] == "VIX"), None)
    regime = "Normal"
    if vix:
        regime = "Calm" if vix["value"] < 15 else ("Elevated" if vix["value"] > 20 else "Normal")
    ins = [i for i in state["instruments"] if i.get("verified")]
    up = sum(1 for i in ins if i.get("structure") == "uptrend")
    dn = sum(1 for i in ins if i.get("structure") == "downtrend")
    rg = sum(1 for i in ins if i.get("structure") == "range")
    parts = []
    if vix:
        parts.append(f"{regime} tape (VIX {vix['value']}).")
    parts.append(f"{up} up / {dn} down / {rg} ranging across {len(ins)} names.")
    hi = [e for e in state.get("fed_econ", []) if e.get("impact") == "high" and not e.get("actual")]
    if hi:
        parts.append(f"Next catalyst: {hi[0]['event']} {hi[0]['time']}.")
    return " ".join(parts)


def structure_tag(s):
    colors = {"uptrend": ("#166534", "#dcfce7"), "downtrend": ("#991b1b", "#fee2e2"),
              "range": ("#6b7280", "#f3f4f6")}
    fg, bg = colors.get(s, ("#6b7280", "#f3f4f6"))
    return (f'<span style="background:{bg};color:{fg};font-size:10px;padding:2px 8px;'
            f'border-radius:5px;text-transform:uppercase;letter-spacing:1px;">{s}</span>')


def level_row(z):
    sc = f' <span style="color:#7c3aed;">x{z["score"]}</span>' if z.get("score", 0) >= 2 else ""
    ev = ", ".join(z.get("evidence", [])[:2])
    return (f'<tr><td style="padding:1px 0;"><b>{fmt(z["price"])}</b>{sc} '
            f'<span style="color:#9aa4b2;">{ev}</span></td></tr>')


def instrument_card(i):
    if not i.get("verified"):
        return (f'<tr><td style="background:#fff;border-left:1px solid #e5e7eb;'
                f'border-right:1px solid #e5e7eb;padding:10px 20px;">'
                f'<b>{i["symbol"]}</b> <span style="color:#b45309;font-size:12px;">'
                f'unverified - withheld (fail-closed)</span></td></tr>')
    chg = i["change_pct"]
    col = UP if chg > 0 else (DOWN if chg < 0 else MUT)
    above = "".join(level_row(z) for z in i.get("levels_above", [])[:3]) or '<tr><td style="color:#9aa4b2;">-</td></tr>'
    below = "".join(level_row(z) for z in i.get("levels_below", [])[:3]) or '<tr><td style="color:#9aa4b2;">-</td></tr>'
    changed = " &middot; ".join(i.get("changed", []))
    changed_html = f'<div style="margin-top:7px;font-size:11px;color:#2563eb;">&#8635; {changed}</div>' if changed else ""
    return f"""<tr><td style="background:#fff;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;padding:6px 16px;">
  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eef0f2;border-radius:8px;border-collapse:separate;">
    <tr><td style="padding:11px 13px;">
      <span style="font-size:16px;font-weight:700;color:#1f2329;">{i['symbol']}</span>
      <span style="color:#9aa4b2;font-size:11px;"> {i['name']}</span>
      <span style="float:right;font-size:15px;font-weight:600;color:#1f2329;">{fmt(i['ohlc']['close'])} <span style="color:{col};font-size:12px;">{plus(chg)}%</span></span>
      <div style="margin-top:6px;">{structure_tag(i['structure'])}</div>
      <div style="font-size:12px;color:#3f4651;margin:9px 0;line-height:1.55;">{i['read']}</div>
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td width="50%" valign="top" style="padding-right:8px;">
          <div style="color:#9aa4b2;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px;">Resistance / above</div>
          <table cellpadding="0" cellspacing="0" style="font-family:monospace;font-size:11px;color:#1f2329;">{above}</table></td>
        <td width="50%" valign="top" style="padding-left:8px;border-left:1px solid #eef0f2;">
          <div style="color:#9aa4b2;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px;">Support / below</div>
          <table cellpadding="0" cellspacing="0" style="font-family:monospace;font-size:11px;color:#1f2329;">{below}</table></td>
      </tr></table>
      <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:9px;"><tr>
        <td width="50%" style="padding-right:4px;"><div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:6px 8px;font-size:11px;color:#166534;"><b>Bull</b> {i['bull_trigger']}</div></td>
        <td width="50%" style="padding-left:4px;"><div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:6px 8px;font-size:11px;color:#991b1b;"><b>Bear</b> {i['bear_trigger']}</div></td>
      </tr></table>
      {changed_html}
    </td></tr>
  </table>
</td></tr>
<tr><td style="background:#fff;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;height:6px;line-height:6px;font-size:6px;">&nbsp;</td></tr>"""


def render_html(state):
    m = state["meta"]
    live = m["data_mode"] == "LIVE"
    badge_bg = "#1a7f37" if live else "#b45309"
    chips = ""
    for b in state["backdrop"]:
        c = UP if b["change"] > 0 else (DOWN if b["change"] < 0 else MUT)
        chips += (f'<td style="padding:5px 9px;border:1px solid #e5e7eb;border-radius:6px;'
                  f'background:#fff;font-family:monospace;font-size:12px;color:#1f2329;white-space:nowrap;">'
                  f'<span style="color:#9aa4b2;">{b["name"]}</span> {b["value"]} '
                  f'<span style="color:{c};">{plus(b["change"])}</span></td><td style="width:6px;font-size:1px;">&nbsp;</td>')
    feds = ""
    for e in state["fed_econ"]:
        val = ("actual " + e["actual"]) if e["actual"] else ("cons " + e["consensus"])
        dot = "#b45309" if e["impact"] == "high" else "#9aa4b2"
        feds += (f'<tr><td style="padding:3px 0;font-size:11px;color:#3f4651;border-left:2px solid {dot};padding-left:8px;">'
                 f'<b>{e["date"]} {e["time"]}</b> &middot; {e["event"]} '
                 f'<span style="color:#9aa4b2;">- prior {e["prior"]}, {val}</span></td></tr>')
    cards = "".join(instrument_card(i) for i in state["instruments"])
    side = "border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;"
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f5f7;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:16px 0;"><tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:94%;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <tr><td style="background:#0d1117;border-radius:12px 12px 0 0;padding:16px 20px;">
    <span style="color:#fff;font-size:20px;font-weight:700;letter-spacing:2px;">SIG<span style="color:#3fb950;">N</span>AL</span>
    <span style="float:right;background:{badge_bg};color:#fff;font-size:11px;padding:3px 9px;border-radius:5px;letter-spacing:1px;">{m['data_mode']}</span>
    <div style="color:#9aa4b2;font-size:12px;margin-top:5px;">{m['session']} &middot; as of {m.get('as_of_date','')}</div>
  </td></tr>
  <tr><td style="background:#fff;{side}padding:14px 20px 4px;">
    <div style="font-size:14px;color:#1f2329;line-height:1.55;font-weight:600;">{market_one_liner(state)}</div></td></tr>
  <tr><td style="background:#fff;{side}padding:10px 18px 6px;">
    <div style="color:#9aa4b2;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:2px 2px 6px;">Intermarket backdrop</div>
    <table cellpadding="0" cellspacing="0"><tr>{chips}</tr></table></td></tr>
  <tr><td style="background:#fff;{side}padding:8px 20px 6px;">
    <div style="color:#9aa4b2;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:4px 0 4px;">Fed &amp; economic data</div>
    <table cellpadding="0" cellspacing="0" width="100%">{feds}</table></td></tr>
  <tr><td style="background:#fff;{side}padding:10px 20px 2px;">
    <div style="color:#9aa4b2;font-size:10px;text-transform:uppercase;letter-spacing:1px;">Instruments</div></td></tr>
  {cards}
  <tr><td style="background:#fff;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;border-top:none;padding:14px 20px;color:#9aa4b2;font-size:11px;line-height:1.5;">
    {m['disclaimer']}<br>SIGNAL &middot; structural reads, not financial advice.</td></tr>
</table></td></tr></table></body></html>"""


# ---------------------------------------------------------------- send --------
def send(subject, text, html=None):
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
        print("SMTP not configured - printing text brief instead:\n")
        print(text)
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(text, "plain"))
    if html:
        msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())
    print("Email sent to", to)


if __name__ == "__main__":
    st = load_state()
    subj = f"SIGNAL {st['meta']['session']} brief {st['meta'].get('as_of_date','')}"
    send(subj, render_text(st), render_html(st))
