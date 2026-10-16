"""長崎港（長崎県 長崎港湾漁港事務所 nagasaki-port.jp）

一覧ページ cruiseschedule.html から R08_cruiseschedule.pdf などの PDF を探し、
今年と来年以降の分（和暦 R番号）を読む。
1泊以上の寄港は「出港 一泊」の行と「入港 一泊」の行に分かれているので、1行にまとめる。
"""
import re
import common

PORT = '長崎港'
BASE = 'https://nagasaki-port.jp/'
LANDING = BASE + 'cruiseschedule.html'

BERTHS = ('松が枝', '出島')
T = r'(\d{1,2}:\d{2}|一泊|-|－)'
REC = re.compile(
    r'^(?:\d+\s+)?(\d{1,2})月(\d{1,2})日\s+(.+?)\s+(\d{1,3}(?:,\d{3})+|\d+)\s+(\d+(?:\.\d+)?)\s+(.+?)\s+'
    + T + r'\s+' + T + r'\s+(.*)$')
START = re.compile(r'^(?:\d+\s+)?\d{1,2}月\d{1,2}日(\s|$)')


def _pdf_urls(ctx):
    reiwa_now = common.TODAY.year - 2018
    urls = {}
    try:
        html = ctx.get(LANDING)
        for m in re.finditer(r'href="([^"]*?R(\d{2})_cruiseschedule\.pdf)"', html, re.I):
            n = int(m.group(2))
            if n >= reiwa_now:
                href = m.group(1)
                urls[n] = href if href.startswith('http') else BASE + href.lstrip('./')
    except Exception:
        pass
    if reiwa_now not in urls:
        urls[reiwa_now] = BASE + f'nagasaki_cruiseschedule/R{reiwa_now:02d}_cruiseschedule.pdf'
    return [urls[k] for k in sorted(urls)]


def _records(text):
    recs, cur = [], None
    for line in text.splitlines():
        s = common.z2h(line).strip()
        if not s or s.startswith('※') or s.startswith('寄港月日') or re.match(r'^R\d+年', s):
            continue
        if re.fullmatch(r'\d+', s) or re.fullmatch(r'\d+\s*/\s*\d+', s):
            continue  # 行番号だけの行・ページ番号
        if START.match(s):
            cur = [s]
            recs.append(cur)
        elif cur is not None:
            cur.append(s)
    return [' '.join(r) for r in recs]


def _tail(rest):
    """前港 次港 接岸壁 備考 を分ける"""
    toks = rest.split()
    merged = []
    for t in toks:
        if merged and t.startswith('('):
            merged[-1] += t
        else:
            merged.append(t)
    berth, note, ports = '', '', merged
    for i, t in enumerate(merged):
        if t in BERTHS:
            berth, ports, note = t, merged[:i], ' '.join(merged[i + 1:])
            break
    prev = ports[0] if len(ports) > 0 else ''
    nxt = ports[1] if len(ports) > 1 else ''
    if len(ports) > 2:
        note = (' '.join(ports[2:]) + ' ' + note).strip()
    clean = lambda p: '' if p in ('-', '－') else p
    return clean(prev), clean(nxt), berth, note


def _parse(text, url):
    m = re.search(r'R\d+年\s*[(（]\s*(\d{4})年', common.z2h(text))
    if not m:
        raise ValueError('year header not found: ' + url)
    year = int(m.group(1))
    out, open_ = [], {}
    for rec in _records(text):
        m = REC.match(rec)
        if not m:
            m2 = re.match(r'^(?:\d+\s+)?(\d{1,2})月(\d{1,2})日\s+(.*)$', rec)
            if m2 and '非公開' in m2.group(3):
                d = common.ymd(year, m2.group(1), m2.group(2))
                out.append(common.row(date=d, port=PORT, ship='船名非公開', note=m2.group(3).strip(),
                                      source=url, raw=rec))
            continue
        mo, da, ship, _gt, _len, _flag, tin, tout, rest = m.groups()
        d = common.ymd(year, mo, da)
        prev, nxt, berth, note = _tail(rest)
        ship = ship.strip()
        if tin == '一泊' and ship in open_:
            r = open_[ship]
            r['end'] = d
            if tout != '一泊':
                r['out'] = common.hhmm(tout)
                r['next'] = nxt
                del open_[ship]
            if note and note not in r['note']:
                r['note'] = (r['note'] + ' ' + note).strip()
            r['raw'] = (r['raw'] + ' / ' + rec)[:300]
            continue
        r = common.row(date=d, port=PORT, ship=ship, **{'in': common.hhmm(tin), 'out': common.hhmm(tout)},
                       berth=berth, prev=prev, next=nxt, note=note, source=url, raw=rec)
        if tout == '一泊':
            open_[ship] = r
        out.append(r)
    return out


def fetch(ctx):
    rows = []
    for i, url in enumerate(_pdf_urls(ctx)):
        try:
            text = ctx.pdf_text(url, raw=True)
        except Exception:
            if i == 0:
                raise
            continue  # 来年分はまだ無いことがある
        rows += _parse(text, url)
    return rows
