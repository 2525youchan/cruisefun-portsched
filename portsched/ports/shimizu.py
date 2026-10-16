"""清水港（清水港客船誘致委員会）寄港予定

年度ページ https://www.shimizu-port.jp/shipinfo_R08.html （令和の年度で URL が変わる）
  表: No | 入港日時 | 出港日時 | 船名 | 種別 | トン数 | 前港 | 次港
  取り消し線（span.linethrough）の行 = 寄港取りやめ → status='cancelled'
  船名の ★ = 初寄港、【日の出1号・見学不可】等 = 岸壁の注記
同じページの最新 PDF（「【YYMMDD現在】…寄港予定…pdf」）は HTML より新しいことがあるので、
PDF が載せている月は PDF の時刻・前港・次港で上書きし、HTML に無い行は追加する。
"""
import re, datetime
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup
import common

PORT = '清水港'
BASE = 'https://www.shimizu-port.jp/'
TYPES = ('外国客船', '邦船')


def _fys():
    t = common.TODAY
    fy = t.year if t.month >= 4 else t.year - 1
    fys = [fy]
    if t.month in (2, 3):
        fys.append(fy + 1)
    return fys


def _ship_parts(s):
    """船名セル → (船名, 岸壁, 備考)"""
    s = common.z2h(s).replace('　', ' ')
    notes, berth = [], ''
    if '★' in s:
        notes.append('★初寄港')
        s = s.replace('★', ' ')
    for x in re.findall(r'【([^】]*)】', s):
        parts = [p.strip() for p in re.split(r'[・･]', x) if p.strip()]
        for p in parts:
            if re.search(r'号|興津|袖師|富士見|江尻|岸壁', p) and not berth:
                berth = p
            else:
                notes.append(p)
    s = re.sub(r'【[^】]*】', ' ', s)
    return re.sub(r'\s+', ' ', s).strip(), berth, ' / '.join(notes)


def _dt(s, fy=None):
    s = common.z2h(s)
    m = re.search(r'(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})日', s)
    if not m:
        return '', ''
    y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
    date = common.ymd(y, mo, d) if y else common.fiscal_year_date(fy, mo, d)
    return date, common.hhmm(s[m.end():])


def _place(s):
    s = re.sub(r'\s+', '', common.z2h(s or '')).strip()
    return '' if s in ('-', '－', '―', '未定') else s


def _norm(s):
    return re.sub(r'[\s・･=＝]', '', s)


def _parse_html(html, fy, url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for t in soup.find_all('table'):
        for tr in t.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) < 8:
                continue
            c = [x.get_text(' ', strip=True) for x in tds]
            date, tin = _dt(c[1], fy)
            if not date:
                continue
            end, tout = _dt(c[2], fy)
            ship, berth, note = _ship_parts(c[3])
            status = 'scheduled'
            if tr.select('.linethrough, s, del, strike'):
                status = 'cancelled'
                note = ' / '.join(x for x in ('表に取り消し線（寄港取りやめ）', note) if x)
            rows.append(common.row(date=date, end=end or date, port=PORT, ship=ship, **{'in': tin, 'out': tout},
                                   berth=berth, prev=_place(c[6]), next=_place(c[7]), status=status, note=note,
                                   source=url, raw=' | '.join(c), _no=c[0].strip()))
    return rows


DATE_RE = r'(\d{1,2})月(\d{1,2})日\s*\S?\s*(\d{1,2}:\d{2})'


def _parse_pdf(text, fy, url):
    """pdftotext -raw の文字から行を作る（崩れた行はできる範囲で拾う）"""
    text = common.z2h(text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    recs, orphans = [], []
    cur = None
    for l in lines:
        if l.startswith('●'):
            cur = None
            continue
        m = re.match(r'^(?:(\d{1,3})\s+)?' + DATE_RE, l)
        if m and not m.group(1) and cur is not None and len(re.findall(DATE_RE, cur['text'])) == 1                 and not any(x in cur['text'] for x in TYPES):
            cur['text'] += ' ' + l   # 出港日時だけが次の行に分かれた
            continue
        if m:
            cur = {'no': m.group(1) or '', 'text': l[m.start(2) if m.group(1) else 0:]}
            recs.append(cur)
            continue
        m = re.match(r'^(\d{1,3})\s+(\S.*?(?:' + '|'.join(TYPES) + r').*)$', l)
        if m and not re.search(r'\d+月\d+日', l):
            orphans.append((m.group(1), m.group(2)))
            cur = None
            continue
        if cur is not None:
            cur['text'] += ' ' + l
    out = []
    for r in recs:
        t = r['text']
        ds = list(re.finditer(DATE_RE, t))
        if not ds:
            continue
        rest = t[ds[-1].end():] if len(ds) > 1 else t[ds[0].end():]
        if not any(x in rest for x in TYPES):
            if orphans:
                no, txt = orphans.pop(0)
                r['no'] = r['no'] or no
                rest = rest + ' ' + txt
            else:
                continue
        mt = re.search('|'.join(TYPES), rest)
        ship_part, after = rest[:mt.start()], rest[mt.end():]
        toks = after.split()
        if toks and re.fullmatch(r'[\d,]+', toks[0]):
            toks = toks[1:]
        merged = []
        for tk in toks:
            if merged and re.match(r'^[（(]', tk):
                merged[-1] += tk
            else:
                merged.append(tk)
        a = ds[0]
        date = common.fiscal_year_date(fy, a.group(1), a.group(2))
        if len(ds) > 1:
            end, tout = common.fiscal_year_date(fy, ds[1].group(1), ds[1].group(2)), common.hhmm(ds[1].group(3))
        else:
            end, tout = date, ''
        ship, berth, note = _ship_parts(ship_part)
        status = 'scheduled' if r['no'] else 'cancelled'
        if status == 'cancelled':
            note = ' / '.join(x for x in ('表に取り消し線（寄港取りやめ）', note) if x)
        out.append(common.row(date=date, end=end, port=PORT, ship=ship, **{'in': common.hhmm(a.group(3)), 'out': tout},
                              berth=berth, prev=_place(merged[0]) if merged else '', next=_place(merged[1]) if len(merged) > 1 else '',
                              status=status, note=note, source=url, raw=(r['no'] + ' ' + t).strip(), _no=r['no']))
    return out


def _page_url(ctx, fy):
    r = fy - 2018
    return urljoin(BASE, f'shipinfo_R{r:02d}.html')


def fetch(ctx):
    rows = []
    for i, fy in enumerate(_fys()):
        url = _page_url(ctx, fy)
        try:
            html = ctx.get(url, binary=True)
        except Exception:
            if i == 0:
                raise
            continue
        hrows = _parse_html(html, fy, url)
        # 最新 PDF
        soup = BeautifulSoup(html, 'html.parser')
        prows = []
        for a in soup.find_all('a', href=True):
            name = unquote(a['href'])
            if '.pdf' in name.lower() and '寄港予定' in (name + a.get_text()):
                purl = urljoin(url, a['href'])
                try:
                    prows += _parse_pdf(ctx.pdf_text(purl), fy, purl)
                except Exception as e:
                    ctx.log.append({'pdf_error': purl, 'error': repr(e)})
        rows += _merge(hrows, prows)
    seen, out = set(), []
    for r in rows:
        r.pop('_no', None)
        k = (r['date'], _norm(r['ship']), r['in'])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    out.sort(key=lambda r: (r['date'], r['in']))
    return out


def _merge(hrows, prows):
    if not prows:
        return hrows
    months = {r['date'][:7] for r in prows}
    used = set()
    out = []
    for h in hrows:
        if h['date'][:7] not in months:
            out.append(h)
            continue
        # PDF の対応する行を探す（日付＋船名、なければ日付＋入港時刻）
        cand = [i for i, p in enumerate(prows) if i not in used and p['date'] == h['date'] and _norm(p['ship']) == _norm(h['ship'])]
        if not cand:
            cand = [i for i, p in enumerate(prows) if i not in used and p['date'] == h['date'] and p['in'] == h['in']]
        if len(cand) >= 1:
            i = cand[0]
            used.add(i)
            p = prows[i]
            for f in ('in', 'out', 'end', 'prev', 'next'):
                if p[f]:
                    h[f] = p[f]
            if p['status'] == 'cancelled' and h['status'] != 'cancelled':
                h['status'], h['note'] = 'cancelled', p['note']
            elif p['_no'] and h['status'] == 'cancelled':
                h['status'] = 'scheduled'
                h['note'] = h['note'].replace('表に取り消し線（寄港取りやめ）', '').strip(' /')
            h['source'] = p['source']
            h['raw'] = (h['raw'] + ' || PDF: ' + p['raw'])[:300]
        out.append(h)
    for i, p in enumerate(prows):
        if i not in used:
            out.append(p)
    return out
