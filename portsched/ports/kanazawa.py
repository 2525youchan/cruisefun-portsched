"""金沢港（金沢港振興協会）客船寄港実績・予定

https://www.k-port.jp/cruise/ の表（月ごと。1 隻ごとに入れ子の table）
  1 行目: 船名 | 運航会社 | 総トン数 | 全長 | 定員 | イベント
  2 行目: 入港日 / 時刻 入 | 行程（…-前港-【金沢】-次港-…） | 着岸埠頭
  3 行目: 出港日（〃=同じ日）/ 時刻 出 | （行程が往復で分かれるときは帰りの行程）
HTML コメントの中には古いデータ・古いお知らせが残っているので、最初に取り除く。
お知らせの「M月D日(曜)入港予定の船名は、寄港中止となりました」は、表に残っていれば cancelled。
"""
import re
from bs4 import BeautifulSoup, Comment
import common

PORT = '金沢港'
URL = 'https://www.k-port.jp/cruise/'
HOME = '【金沢】'


def _md(s):
    m = re.search(r'(\d{1,2})月\s*(\d{1,2})日', common.z2h(s))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _route(s):
    """行程 → (前港, 次港)"""
    s = common.z2h(s).replace(' ', '').replace('　', '')
    s = s.replace('【金沢】', HOME)
    i = s.find(HOME)
    if i < 0:
        return '', ''
    before, after = s[:i], s[i + len(HOME):]
    while after.startswith(HOME):   # 「…-【金沢】【金沢】-…」（下船・乗船の折り返し）
        after = after[len(HOME):]
    clean = lambda x: re.sub(r'[()（）]', '', x).strip()
    pb = [clean(x) for x in before.split('-') if clean(x)]
    pa = [clean(x) for x in re.sub(r'\(\d+/\d+\)', '', after).split('-') if clean(x)]
    return (pb[-1] if pb else ''), (pa[0] if pa and pa[0] != HOME else '')


def _norm(s):
    return re.sub(r'[\s・･]', '', common.z2h(s))


def fetch(ctx):
    html = ctx.get(URL, binary=True)
    soup = BeautifulSoup(html, 'html.parser')
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()
    for t in soup(['script', 'style']):
        t.decompose()
    text = common.z2h(soup.get_text(' '))
    m = re.search(r'(\d{4})年金沢港客船寄港', text) or re.search(r'(\d{4})年\d{1,2}月\d{1,2}日現在', text)
    year = int(m.group(1)) if m else common.TODAY.year
    cancels = []
    for mm in re.finditer(r'(\d{1,2})月(\d{1,2})日\s*\([^)]*\)\s*入港予定の\s*(.+?)\s*は、?\s*(寄港中止|中止|キャンセル|抜港)[^。]*。?', text):
        cancels.append(((int(mm.group(1)), int(mm.group(2))), _norm(mm.group(3)), mm.group(0).strip()))
    main = soup.find('table', class_='contentsTable') or soup
    rows = []
    prev_mon, y = None, year
    for inner in main.find_all('table'):
        trs = inner.find_all('tr', recursive=False)
        if not trs and inner.find('tbody'):
            trs = inner.find('tbody').find_all('tr', recursive=False)
        if len(trs) < 3:
            continue
        st = trs[0].find('strong')
        if not st:
            continue
        ship = re.sub(r'\s+', ' ', st.get_text(' ', strip=True))
        c1 = trs[1].find_all('td', recursive=False)
        c2 = trs[2].find_all('td', recursive=False)
        if not c1:
            continue
        dt1 = c1[0].find('dt')
        dd1 = c1[0].find('dd')
        a = _md(dt1.get_text() if dt1 else c1[0].get_text())
        if not a:
            continue
        if prev_mon is not None and a[0] < prev_mon - 6:
            y += 1
        prev_mon = a[0]
        date = common.ymd(y, *a)
        tin = common.hhmm(dd1.get_text() if dd1 else c1[0].get_text())
        route_in = c1[1].get_text(' ', strip=True) if len(c1) > 1 else ''
        berth = c1[2].get_text(' ', strip=True) if len(c1) > 2 else ''
        end, tout = date, ''
        if c2:
            dt2, dd2 = c2[0].find('dt'), c2[0].find('dd')
            d = _md(dt2.get_text() if dt2 else '')
            if d:
                end = common.ymd(y + (1 if d[0] < a[0] else 0), *d)
            tout = common.hhmm(dd2.get_text() if dd2 else c2[0].get_text())
        route_out = c2[1].get_text(' ', strip=True) if len(c2) > 1 else ''
        prev, nxt = _route(route_in)
        if route_out:
            nxt = _route(route_out)[1]
        rawtxt = re.sub(r'\s+', ' ', inner.get_text(' ', strip=True))
        status, notes = 'scheduled', []
        mm = re.search(r'\S*(?:寄港中止|中止|キャンセル|抜港)\S*', rawtxt)
        if mm:
            status = 'cancelled'
            notes.append(mm.group(0))
        for cd, cn, w in cancels:
            if cd == a and cn == _norm(ship) and status != 'cancelled':
                status = 'cancelled'
                notes.append(w)
        rows.append(common.row(date=date, end=end, port=PORT, ship=ship, **{'in': tin, 'out': tout}, berth=berth,
                               prev=prev, next=nxt, status=status, note=' / '.join(notes), source=URL,
                               raw=' | '.join(x for x in (ship, date, route_in, route_out, berth) if x)))
    seen, out = set(), []
    for r in rows:
        k = (r['date'], r['ship'], r['in'])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out
