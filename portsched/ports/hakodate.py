"""函館港（函館市 港湾空港振興課）: 年度ごとの「クルーズ客船入港予定」ページの CSV。

入口: 港湾空港振興課のページ（安定）→「令和N年度のクルーズ客船入港予定」ページ（年度ごとに ID が変わる）
     → ページ内の CSV（UTF-8 BOM）。
"""
import csv, io, re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import common

PORT = '函館港'
BASE = 'https://www.city.hakodate.hokkaido.jp/'
LANDING = BASE + 'soshiki/kouwan_dept/port-dev/'
CANCEL = re.compile(r'キャンセル|中止|抜港|取り?止め|取消|欠航')


def _schedule_pages(ctx):
    s = BeautifulSoup(ctx.get(LANDING), 'html.parser')
    pages = {}
    for a in s.find_all('a', href=True):
        t = common.z2h(a.get_text('', strip=True))
        m = re.search(r'令和(\d+)年度の?クルーズ客船入港予定', t)
        if m:
            pages[urljoin(LANDING, a['href'])] = 2018 + int(m.group(1))
    if not pages:
        raise RuntimeError('函館: 入港予定ページへのリンクが見つかりません: ' + LANDING)
    return pages


def _cell(s):
    return re.sub(r'[ 　]+', ' ', (s or '').replace('\r', '')).strip()


def _ship(s):
    lines = [_cell(x) for x in (s or '').split('\n') if _cell(x)]
    return common.z2h(lines[0]) if lines else ''


def _dt(s, fy):
    s = common.z2h(s or '')
    m = re.search(r'(\d{1,2})/(\d{1,2})', s)
    if not m:
        return '', ''
    d = common.fiscal_year_date(fy, m.group(1), m.group(2))
    rest = s[m.end():]
    rest = re.sub(r'\([^)]*\)', ' ', rest)
    return d, common.hhmm(rest)


def fetch(ctx):
    rows = []
    for page, fy in _schedule_pages(ctx).items():
        s = BeautifulSoup(ctx.get(page), 'html.parser')
        h = s.find('h1')
        m = re.search(r'令和(\d+)年度', common.z2h(h.get_text() if h else (s.title.text if s.title else '')))
        if m:
            fy = 2018 + int(m.group(1))
        csvs = [urljoin(page, a['href']) for a in s.find_all('a', href=True) if a['href'].lower().endswith('.csv')]
        if not csvs:
            raise RuntimeError('函館: CSV が見つかりません: ' + page)
        body = ctx.get(csvs[0], binary=True)
        try:
            text = body.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = body.decode('cp932')
        recs = list(csv.reader(io.StringIO(text)))
        head = [common.z2h(_cell(x)).replace(' ', '') for x in recs[0]]

        def col(*names):
            for i, x in enumerate(head):
                if any(n in x for n in names):
                    return i
            return None
        c_ship, c_in, c_out = col('船名'), col('入港'), col('出港')
        c_berth, c_chg, c_rem, c_no = col('係留', '岸壁', 'バース'), col('変更'), col('備考'), col('NO', 'No')
        if None in (c_ship, c_in, c_out):
            raise RuntimeError('函館: CSV の列名が想定と違います: %r' % head)
        g = lambda r, i: (r[i] if i is not None and i < len(r) else '')
        for r in recs[1:]:
            if not any(x.strip() for x in r):
                continue
            ship = _ship(g(r, c_ship))
            d, tin = _dt(g(r, c_in), fy)
            e, tout = _dt(g(r, c_out), fy)
            if not ship or not d:
                continue
            chg, rem = _cell(g(r, c_chg)), _cell(g(r, c_rem)).replace('\n', ' ')
            note = ': '.join(x for x in (chg, rem) if x)
            st = 'cancelled' if CANCEL.search(rem + chg) else 'scheduled'
            rows.append(common.row(date=d, end=e or d, port=PORT, ship=ship, **{'in': tin, 'out': tout},
                                   berth=_cell(g(r, c_berth)), status=st, note=note, source=csvs[0],
                                   raw=' | '.join(_cell(x).replace('\n', ' / ') for x in r)))
    return rows
