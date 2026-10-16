"""境港（境夢みなとターミナル）クルーズ客船寄港予定 PDF

入口: https://www.sakai-tottori.jp/archives/xo_event_cat/pcs の「クルーズスケジュール(R8.10.13)」PDF リンク
  （PDF は WordPress のハッシュ名なので毎回ページから探す）
PDF（-raw）: 寄港日 入港 出港 [中止] [★/▲/■]船名 総トン数 全長 定員 国籍 前港 次港
  「中止」スタンプは「中」「止」が別の行に分かれて出る。
  ★=境港初寄港、▲=昭和北岸壁、■=昭和南もしくは中野岸壁
"""
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import common

PORT = '境港'
PAGE = 'https://www.sakai-tottori.jp/archives/xo_event_cat/pcs'
START = re.compile(r'^(\d{1,2})月(\d{1,2})日\s*\(\S\)')


def _pdf_links(ctx):
    soup = BeautifulSoup(ctx.get(PAGE, binary=True), 'html.parser')
    urls = []
    for a in soup.find_all('a', href=True):
        if '.pdf' in a['href'].lower() and re.search(r'スケジュール|寄港予定', a.get_text()):
            u = urljoin(PAGE, a['href'])
            if u not in urls:
                urls.append(u)
    if not urls:
        raise RuntimeError('クルーズスケジュール PDF のリンクが見つからない')
    return urls


def _parse(text, url):
    text = common.z2h(text)
    m = re.search(r'(\d{4})年\s*クルーズ客船寄港予定', text)
    year = int(m.group(1)) if m else common.TODAY.year
    recs, cur = [], None
    for l in (x.strip() for x in text.splitlines()):
        if not l:
            continue
        if START.match(l):
            cur = [l]
            recs.append(cur)
        elif l.startswith(('※', '境夢', '寄港日')) or re.match(r'^\d{4}年', l) or l.startswith('更新日'):
            cur = None
        elif cur is not None:
            cur.append(l)
    rows, prev_mon, y = [], None, year
    for rec in recs:
        t = ' '.join(rec)
        ms = START.match(t)
        mon, day = int(ms.group(1)), int(ms.group(2))
        if prev_mon is not None and mon < prev_mon - 6:
            y += 1
        prev_mon = mon
        rest = t[ms.end():]
        times = re.findall(r'\d{1,2}:\d{2}', rest)
        tin = common.hhmm(times[0]) if times else ''
        tout = common.hhmm(times[1]) if len(times) > 1 else ''
        rest = re.sub(r'^\s*(?:\d{1,2}:\d{2}\s*){0,2}', '', rest)
        status, notes, berth = 'scheduled', [], ''
        mc = re.search(r'中\s*止', rest)
        if mc:
            status = 'cancelled'
            notes.append('中止')
            rest = rest[:mc.start()] + ' ' + rest[mc.end():]
        mt = re.search(r'([\d,]+)\s*t\b', rest)
        ship_part = rest[:mt.start()] if mt else rest
        after = rest[mt.end():].split() if mt else []
        if '★' in ship_part:
            notes.append('★境港初寄港')
        if '▲' in ship_part:
            berth = '昭和北'
        if '■' in ship_part:
            berth = '昭和南もしくは中野岸壁'
        ship = re.sub(r'[★▲■☆]', ' ', ship_part)
        ship = re.sub(r'\s+', ' ', ship).strip()
        # after: 全長 定員 国籍 前港 次港
        prev = after[-2] if len(after) >= 5 else ''
        nxt = after[-1] if len(after) >= 5 else ''
        date = common.ymd(y, mon, day)
        rows.append(common.row(date=date, end=date, port=PORT, ship=ship, **{'in': tin, 'out': tout}, berth=berth,
                               prev=prev, next=nxt, status=status, note=' / '.join(notes), source=url, raw=t))
    return rows


def fetch(ctx):
    rows = []
    for u in _pdf_links(ctx):
        rows += _parse(ctx.pdf_text(u, raw=True), u)
    seen, out = set(), []
    for r in rows:
        k = (r['date'], r['ship'], r['in'])
        if k not in seen:
            seen.add(k)
            out.append(r)
    out.sort(key=lambda r: (r['date'], r['in']))
    return out
