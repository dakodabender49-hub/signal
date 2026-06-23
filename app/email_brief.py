#!/usr/bin/env python3
"""SIGNAL email brief.

Reads docs/state.json (produced by build.py) and builds a rich, terminal-styled
HTML email: regime + breadth, intermarket backdrop, every watchlist name's read
with key levels and bull/bear triggers, the screener, and the next Fed catalyst.

Usage:
    python app/email_brief.py                 # send via SMTP_* env vars
    python app/email_brief.py --out FILE.html # write HTML to FILE, do not send (preview)

Sends only when SMTP_HOST/PORT/USER/PASS/EMAIL_TO are all set; otherwise it
prints a notice and exits 0 so scheduled runs never fail on a missing secret.
"""
from __future__ import annotations
import argparse
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = "https://dakodabender49-hub.github.io/signal/"

# terminal palette (inline styles only — email clients ignore <style>)
BG = "#05080d"; PANEL = "#0b121c"; PANEL2 = "#0e151f"; LINE = "#1f2b3a"
TEXT = "#d4dde8"; MUTED = "#8493a6"; DIM = "#5c6b80"
AMBER = "#ffb000"; GREEN = "#26e07b"; RED = "#ff4d6a"; CYAN = "#3cc9d6"; VIOLET = "#b08cff"
MONO = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,Courier,monospace"


def load_state():
    with open(os.path.join(ROOT, "docs", "state.json")) as f:
        return json.load(f)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def col(x):
    try:
        x = float(x)
    except Exception:
        return MUTED
    return GREEN if x > 0 else (RED if x < 0 else MUTED)


def sg(x):
    try:
        return ("+" if float(x) > 0 else "") + str(x)
    except Exception:
        return str(x)


def fnum(x):
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return "—"


def tag_style(structure):
    if structure == "uptrend":
        return f"color:{GREEN};border:1px solid #1c5e3c;background:rgba(38,224,123,.10)"
    if structure == "downtrend":
        return f"color:{RED};border:1px solid #6e2233;background:rgba(255,77,106,.10)"
    return f"color:{MUTED};border:1px solid {LINE}"


def lvl_str(zlist, n=2):
    out = []
    for z in (zlist or [])[:n]:
        ev = (z.get("evidence") or [""])[0]
        out.append(f"{fnum(z.get('price'))}" + (f" · {esc(ev)}" if ev else ""))
    return "  /  ".join(out) if out else "—"


def section(title, sub=""):
    s = (f'<span style="color:{DIM};font-weight:normal;letter-spacing:1px"> &nbsp;{esc(sub)}</span>'
         if sub else "")
    return (f'<tr><td style="padding:22px 0 8px 0">'
            f'<span style="display:inline-block;width:8px;height:8px;background:{AMBER};'
            f'vertical-align:middle"></span>'
            f'<span style="color:{AMBER};font-weight:bold;letter-spacing:2px;font-size:12px;'
            f'vertical-align:middle"> &nbsp;{esc(title.upper())}</span>{s}</td></tr>')


def instrument_card(i):
    sym = esc(i.get("symbol", "")); name = esc(i.get("name", ""))
    close = fnum(i.get("ohlc", {}).get("close"))
    chg = i.get("change_pct", 0)
    structure = i.get("structure", "range")
    read = esc(i.get("read", ""))
    above = lvl_str(i.get("levels_above"))
    below = lvl_str(i.get("levels_below"))
    bull = esc(i.get("bull_trigger", "")); bear = esc(i.get("bear_trigger", ""))
    return f"""
    <tr><td style="padding:5px 0">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:{PANEL};border:1px solid {LINE};border-radius:3px">
        <tr><td style="padding:11px 13px">
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation"><tr>
            <td style="font-family:{MONO}">
              <span style="color:{AMBER};font-weight:bold;font-size:15px;letter-spacing:1px">{sym}</span>
              <span style="color:{DIM};font-size:11px"> &nbsp;{name}</span>
            </td>
            <td align="right" style="font-family:{MONO};white-space:nowrap">
              <span style="color:{TEXT};font-weight:bold;font-size:15px">{close}</span>
              <span style="color:{col(chg)};font-weight:bold;font-size:13px"> &nbsp;{sg(chg)}%</span>
              <span style="font-size:9px;font-weight:bold;letter-spacing:1px;text-transform:uppercase;
                           padding:2px 6px;border-radius:2px;{tag_style(structure)}"> &nbsp;{esc(structure)} </span>
            </td>
          </tr></table>
          <div style="color:#aeb9c6;font-size:12px;line-height:1.55;font-family:{MONO};padding:9px 0 8px 0">{read}</div>
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                 style="font-family:{MONO};font-size:11px;line-height:1.5">
            <tr><td style="color:{RED};width:78px;vertical-align:top">▲ resistance</td>
                <td style="color:{MUTED};vertical-align:top">{above}</td></tr>
            <tr><td style="color:{GREEN};vertical-align:top">▼ support</td>
                <td style="color:{MUTED};vertical-align:top">{below}</td></tr>
          </table>
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                 style="font-family:{MONO};font-size:11px;line-height:1.4;padding-top:8px">
            <tr>
              <td width="50%" valign="top" style="padding-right:5px">
                <div style="background:rgba(38,224,123,.06);border:1px solid #1c5e3c;border-radius:2px;padding:6px 8px;color:#8fe6b4">
                  <span style="color:{GREEN};font-size:8.5px;letter-spacing:1px;text-transform:uppercase">Bull trigger</span><br>{bull}</div></td>
              <td width="50%" valign="top" style="padding-left:5px">
                <div style="background:rgba(255,77,106,.06);border:1px solid #6e2233;border-radius:2px;padding:6px 8px;color:#ffaeba">
                  <span style="color:{RED};font-size:8.5px;letter-spacing:1px;text-transform:uppercase">Bear trigger</span><br>{bear}</div></td>
            </tr>
          </table>
        </td></tr>
      </table>
    </td></tr>"""


def backdrop_row(backdrop):
    cells = []
    for b in backdrop or []:
        cells.append(
            f'<td align="center" style="padding:8px 6px;border-right:1px solid {LINE};font-family:{MONO}">'
            f'<div style="color:{CYAN};font-size:9px;letter-spacing:1px;text-transform:uppercase">{esc(b.get("name",""))}</div>'
            f'<div style="color:{TEXT};font-size:14px;font-weight:bold;padding-top:2px">{esc(b.get("value","—"))}</div>'
            f'<div style="color:{col(b.get("change",0))};font-size:10px">{sg(b.get("change",0))}</div></td>')
    if not cells:
        return ""
    return (f'<tr><td style="padding:4px 0"><table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
            f'style="background:{PANEL};border:1px solid {LINE};border-radius:3px"><tr>'
            + "".join(cells) + "</tr></table></td></tr>")


def pulse_line(S):
    backdrop = S.get("backdrop", [])
    vix = next((b for b in backdrop if b.get("name") == "VIX"), None)
    ins = [i for i in S.get("instruments", []) if i.get("verified")]
    up = sum(1 for i in ins if i.get("structure") == "uptrend")
    dn = sum(1 for i in ins if i.get("structure") == "downtrend")
    rg = len(ins) - up - dn
    reg = "—"
    if vix:
        try:
            v = float(vix["value"]); reg = "Calm" if v < 15 else ("Elevated" if v > 20 else "Normal")
        except Exception:
            pass
    fed = S.get("fed_econ", [])
    hi = next((e for e in fed if e.get("impact") == "high" and not e.get("actual")
               and "held" not in str(e.get("date", "")) and "target" not in str(e.get("event", "")).lower()), None)
    cat = ""
    if hi:
        when = " ".join([x for x in [hi.get("date"), hi.get("time")] if x])
        cat = f' &nbsp;·&nbsp; Next catalyst: <span style="color:{TEXT}">{esc(hi.get("event",""))}</span> {esc(when)}'
    vixtxt = f' &nbsp;·&nbsp; VIX {esc(vix["value"])}' if vix else ""
    return (f'<tr><td style="padding:6px 0"><table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
            f'style="background:{PANEL};border:1px solid {LINE};border-left:3px solid {CYAN};border-radius:3px">'
            f'<tr><td style="padding:11px 13px;font-family:{MONO};font-size:12px;color:{MUTED};line-height:1.5">'
            f'<span style="color:{TEXT};font-weight:bold">{reg} tape</span>{vixtxt} &nbsp;·&nbsp; '
            f'<span style="color:{GREEN};font-weight:bold">{up}</span> up / '
            f'<span style="color:{RED};font-weight:bold">{dn}</span> down / '
            f'<span style="font-weight:bold">{rg}</span> ranging across {len(ins)} names{cat}'
            f'</td></tr></table></td></tr>')


def breadth_bar(S):
    ins = [i for i in S.get("instruments", []) if i.get("verified")]
    if not ins:
        return ""
    up = sum(1 for i in ins if i.get("structure") == "uptrend")
    dn = sum(1 for i in ins if i.get("structure") == "downtrend")
    rg = len(ins) - up - dn
    n = max(len(ins), 1)
    def pct(x):
        return f"{x / n * 100:.1f}%"
    seg = (f'<td style="width:{pct(up)};background:{GREEN};font-size:0;line-height:8px">&nbsp;</td>'
           f'<td style="width:{pct(rg)};background:{MUTED};font-size:0;line-height:8px">&nbsp;</td>'
           f'<td style="width:{pct(dn)};background:{RED};font-size:0;line-height:8px">&nbsp;</td>')
    return (f'<tr><td style="padding:2px 0 6px 0">'
            f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
            f'style="border:1px solid {LINE};border-radius:2px;height:8px"><tr>{seg}</tr></table>'
            f'<div style="font-family:{MONO};font-size:10px;color:{DIM};letter-spacing:1px;'
            f'text-transform:uppercase;padding-top:5px">'
            f'<span style="color:{GREEN}">{up} uptrend</span> · '
            f'<span style="color:{MUTED}">{rg} range</span> · '
            f'<span style="color:{RED}">{dn} downtrend</span></div></td></tr>')


def screener_block(S):
    sc = S.get("screener", {}) or {}
    mv = sc.get("movers", []) or []
    su = sc.get("setups", []) or []
    if not mv and not su:
        return ""
    html = section("Screener", "movers & setups")
    body = ""
    if mv:
        cells = "".join(
            f'<span style="display:inline-block;font-family:{MONO};font-size:11px;background:{PANEL};'
            f'border:1px solid {LINE};border-radius:2px;padding:5px 9px;margin:0 6px 6px 0">'
            f'<span style="color:{AMBER};font-weight:bold">{esc(m.get("symbol",""))}</span> '
            f'<span style="color:{col(m.get("change_pct",0))};font-weight:bold">{sg(m.get("change_pct",0))}%</span> '
            f'<span style="color:{DIM}">RVOL {esc(m.get("rvol","—"))}x</span></span>'
            for m in mv)
        body += (f'<div style="font-family:{MONO};font-size:9px;color:{CYAN};letter-spacing:1px;'
                 f'text-transform:uppercase;padding:2px 0 6px 0">Unusual volume / movers</div>{cells}')
    if su:
        cells = "".join(
            f'<span style="display:inline-block;font-family:{MONO};font-size:11px;background:{PANEL};'
            f'border:1px solid {LINE};border-radius:2px;padding:5px 9px;margin:8px 6px 0 0">'
            f'<span style="color:{GREEN};font-size:9px;text-transform:uppercase;letter-spacing:.5px">{esc(s.get("setup",""))}</span> '
            f'<span style="color:{TEXT};font-weight:bold">{esc(s.get("symbol",""))}</span> '
            f'<span style="color:{DIM}">{esc(s.get("detail",""))}</span></span>'
            for s in su)
        body += (f'<div style="font-family:{MONO};font-size:9px;color:{CYAN};letter-spacing:1px;'
                 f'text-transform:uppercase;padding:12px 0 2px 0">Setups — screens, not signals</div>{cells}')
    return html + f'<tr><td style="padding:2px 0">{body}</td></tr>'


def fed_block(S):
    fed = S.get("fed_econ", []) or []
    if not fed:
        return ""
    rows = ""
    for e in fed:
        val = e.get("value") or (("actual " + str(e.get("actual"))) if e.get("actual")
                                  else (("cons " + str(e.get("consensus"))) if e.get("consensus") else ""))
        when = " ".join([x for x in [e.get("date"), e.get("time")] if x])
        bar = AMBER if e.get("impact") == "high" else DIM
        rows += (f'<tr><td style="padding:4px 0"><table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
                 f'style="background:{PANEL};border:1px solid {LINE};border-left:3px solid {bar};border-radius:2px">'
                 f'<tr><td style="padding:7px 11px;font-family:{MONO}">'
                 f'<span style="color:{TEXT};font-size:12px;font-weight:bold">{esc(e.get("event",""))}</span>'
                 f'<span style="color:{MUTED};font-size:11px"> &nbsp;{esc(when)}'
                 + (f' · {esc(val)}' if val else "") + '</span></td></tr></table></td></tr>')
    return section("Fed & economic data") + f'<tr><td><table width="100%" cellpadding="0" cellspacing="0" role="presentation">{rows}</table></td></tr>'


def onwatch_block(S):
    alerts = S.get("alerts", []) or []
    if not alerts:
        return (section("On watch", "what changed")
                + f'<tr><td style="font-family:{MONO};font-size:12px;color:{DIM};padding:2px 2px 0">'
                  f'Quiet \u2014 nothing tagged a key level or flipped a moving average this run.</td></tr>')
    cmap = {"move": AMBER, "tag": CYAN, "near": MUTED, "ma": "#5aa6ff", "hi": GREEN, "lo": RED}
    rows = ""
    for a in alerts:
        flags = " &nbsp;\u00b7&nbsp; ".join(
            f'<span style="color:{cmap.get(f.get("k"), MUTED)}">{esc(f.get("t",""))}</span>'
            for f in a.get("flags", []))
        rows += (f'<tr><td style="padding:4px 0"><table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
                 f'style="background:{PANEL};border:1px solid {LINE};border-left:3px solid {AMBER};border-radius:2px">'
                 f'<tr><td style="padding:7px 11px;font-family:{MONO};font-size:12px">'
                 f'<span style="color:{AMBER};font-weight:bold">{esc(a.get("symbol",""))}</span> '
                 f'<span style="color:{DIM}">{esc(a.get("name",""))}</span> &nbsp; {flags}'
                 f'</td></tr></table></td></tr>')
    return section("On watch", "what changed") + f'<tr><td><table width="100%" cellpadding="0" cellspacing="0" role="presentation">{rows}</table></td></tr>'


def build_html(S):
    meta = S.get("meta", {})
    session = str(meta.get("session", "pre-open"))
    sess_label = "PRE-OPEN BRIEF" if "pre" in session else "POST-CLOSE BRIEF"
    asof = meta.get("as_of_date", "")
    mode = meta.get("data_mode", "")
    try:
        gen = datetime.fromisoformat(str(meta.get("generated_at", "")).replace("Z", "+00:00"))
        datestr = gen.strftime("%a %b %d, %Y · %H:%M UTC")
    except Exception:
        datestr = asof
    badge_bg = GREEN if mode == "LIVE" else AMBER
    ins = [i for i in S.get("instruments", []) if i.get("verified")]
    cards = "".join(instrument_card(i) for i in ins)
    unverified = [i for i in S.get("instruments", []) if not i.get("verified")]
    unv = ""
    if unverified:
        names = ", ".join(esc(i.get("symbol", "")) for i in unverified)
        unv = (f'<tr><td style="font-family:{MONO};font-size:11px;color:{AMBER};padding:6px 2px">'
               f'Withheld this run (sources disagreed / feed down): {names}. Self-corrects next run.</td></tr>')

    preheader = "Structural reads, key levels, and the next catalyst — no noise."
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"></head>
<body style="margin:0;padding:0;background:{BG}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader}</div>
<table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:{BG};padding:18px 10px">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" role="presentation" style="width:640px;max-width:100%">

  <tr><td style="background:{PANEL};border:1px solid {LINE};border-top:3px solid {AMBER};border-radius:3px;padding:14px 16px">
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation"><tr>
      <td style="font-family:{MONO}">
        <span style="color:{TEXT};font-size:21px;font-weight:bold;letter-spacing:4px">SIG<span style="color:{AMBER}">N</span>AL</span>
        <span style="color:{badge_bg};font-size:9px;font-weight:bold;letter-spacing:1.5px;border:1px solid {badge_bg};border-radius:2px;padding:2px 6px"> &nbsp;{esc(mode)} </span>
        <div style="color:{AMBER};font-size:11px;letter-spacing:2px;padding-top:6px">{sess_label}</div>
      </td>
      <td align="right" style="font-family:{MONO};color:{DIM};font-size:11px;vertical-align:top">{esc(datestr)}<br>data as of {esc(asof)}</td>
    </tr></table>
  </td></tr>

  {pulse_line(S)}
  {breadth_bar(S)}
  {onwatch_block(S)}

  {section("Intermarket backdrop")}
  {backdrop_row(S.get("backdrop", []))}

  {section("Watchlist", f"{len(ins)} verified names")}
  {cards}
  {unv}

  {screener_block(S)}

  {fed_block(S)}

  <tr><td style="padding:22px 0 6px 0">
    <a href="{SITE}" style="display:inline-block;background:{AMBER};color:#0a0a0a;font-family:{MONO};
       font-weight:bold;font-size:12px;letter-spacing:1px;text-decoration:none;padding:11px 20px;border-radius:3px">
       OPEN THE LIVE TERMINAL →</a>
  </td></tr>

  <tr><td style="font-family:{MONO};color:{DIM};font-size:10px;line-height:1.6;padding:14px 0 0 0;border-top:1px solid {LINE};margin-top:10px">
    SIGNAL · structural reads and screens only — not financial advice. Numbers are cross-source verified and
    fail-closed (withheld rather than shown wrong). You're getting this because you set up the SIGNAL daily brief.
  </td></tr>

</table>
</td></tr></table>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="write HTML to this file and exit (preview, no send)")
    args = ap.parse_args()

    S = load_state()
    html = build_html(S)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"wrote preview -> {args.out} ({len(html)} bytes)")
        return

    host = os.environ.get("SMTP_HOST"); port = os.environ.get("SMTP_PORT")
    user = os.environ.get("SMTP_USER"); pw = os.environ.get("SMTP_PASS")
    to = os.environ.get("EMAIL_TO")
    if not all([host, port, user, pw, to]):
        print("SMTP_* not fully configured — skipping send (no error).")
        return

    meta = S.get("meta", {})
    session = str(meta.get("session", "pre-open"))
    label = "Pre-open" if "pre" in session else "Post-close"
    try:
        gen = datetime.fromisoformat(str(meta.get("generated_at", "")).replace("Z", "+00:00"))
        ds = gen.strftime("%b %d")
    except Exception:
        ds = meta.get("as_of_date", "")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"SIGNAL · {label} brief · {ds}"
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText("Open in an HTML-capable client to view the SIGNAL brief. " + SITE, "plain"))
    msg.attach(MIMEText(html, "html"))

    port = int(port)
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
            s.login(user, pw); s.sendmail(user, [t.strip() for t in to.split(",")], msg.as_string())
    else:
        with smtplib.SMTP(host, port) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, pw); s.sendmail(user, [t.strip() for t in to.split(",")], msg.as_string())
    print(f"sent '{msg['Subject']}' to {to}")


if __name__ == "__main__":
    main()
