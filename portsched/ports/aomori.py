"""青森港・八戸港（青森県 港湾空港課）: 「クルーズ客船の寄港予定・実績」ページの「YYYY年 … 寄港予定」PDF。

PDF は青森港の表のあとに八戸港の表が続く。文字の取り出し（pypdf、だめなら pdftotext -raw）では
見出し【青森港】【八戸港】が表の後ろに出てくることがあるので、No. が 1 に戻ったところで次の港（見出しの出てくる順）に切り替える。
番号のない行（抜港など）はそのときの港に入れる。
"""
import io, re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import pypdf
import common

PORT = '青森港'
LANDING = 'https://www.pref.aomori.lg.jp/soshiki/kendo/kowan/2023-aomori-cruise.html'
CANCEL = re.compile(r'抜港|中止|キャンセル|取り?止め|取消')
PORT_NAMES = {'青森港': '青森港', '八戸港': '八戸港'}

LINE = re.compile(
    r'^(?:(?P<no>\d+)\s+)?(?P<m1>\d{1,2})月(?P<d1>\d{1,2})日\s+(?P<t1>\S*\d{1,2}:\d{2})\s+'
    r'(?P<m2>\d{1,2})月(?P<d2>\d{1,2})日\s+(?P<t2>\S*\d{1,2}:\d{2})\s+'
    r'(?P<ship>.+?)\s+[\d,]+\s*t\s+L=\s*[\d.]+\s*m\s+(?P<berth>\S+)\s+(?P<rest>.*)$')
REST = re.compile(r'^(?P<pn>.*?)\s+[\d,]+\s+[\d,]+(?:\s+(?P<note>.*))?$')


def _pdfs(ctx):
    s = BeautifulSoup(ctx.get(LANDING), 'html.parser')
    out = {}
    for a in s.find_all('a', href=True):
        t = common.z2h(a.get_text(' ', strip=True))
        m = re.search(r'(20\d\d)年.*寄港予定', t)
        if m and a['href'].lower().endswith('.pdf'):
            out.setdefault(urljoin(LANDING, a['href']), int(m.group(1)))
    if not out:
        raise RuntimeError('青森: 寄港予定 PDF のリンクが見つかりません: ' + LANDING)
    return out


def fetch(ctx):
    rows = []
    for url, year in _pdfs(ctx).items():
        # 文字の取り出しは pypdf（環境で結果が変わらない）。読めなければ pdftotext -raw
        body = ctx.get(url, binary=True)
        text = '\n'.join((pg.extract_text() or '') for pg in pypdf.PdfReader(io.BytesIO(body)).pages)
        got = _parse(text, url, year)
        if not got:
            got = _parse(ctx.pdf_text(url, raw=True), url, year)
        rows += got
    return rows


def _parse(text, url, year):
    rows = []
    order = []
    for m in re.finditer(r'【\s*(\S+?港)\s*】', text):
        p = PORT_NAMES.get(m.group(1), m.group(1))
        if p not in order:
            order.append(p)
    order = order or [PORT]
    idx, last_no = 0, 0
    for line in text.splitlines():
        ln = re.sub(r'[ 　]+', ' ', common.z2h(line)).strip()
        m = LINE.match(ln)
        if not m:
            continue
        if m.group('no'):
            no = int(m.group('no'))
            if no <= last_no and idx + 1 < len(order):
                idx += 1
            last_no = no
        port = order[idx]
        berth = m.group('berth')
        if '八太郎' in berth:
            port = '八戸港'
        rest = m.group('rest')
        r2 = REST.match(rest)
        pn, note = (r2.group('pn'), r2.group('note') or '') if r2 else (rest, '')
        parts = re.split(r'(?<!,)\s+', pn.strip())
        prev, nxt = (parts[0], ' '.join(parts[1:])) if len(parts) >= 2 else (pn, '')
        d = common.ymd(year, m.group('m1'), m.group('d1'))
        e = common.ymd(year, m.group('m2'), m.group('d2'))
        if e < d:
            e = common.ymd(year + 1, m.group('m2'), m.group('d2'))
        rows.append(common.row(
            date=d, end=e, port=port, ship=m.group('ship').strip(),
            **{'in': common.hhmm(m.group('t1')), 'out': common.hhmm(m.group('t2'))},
            berth=berth, prev=prev, next=nxt,
            status='cancelled' if CANCEL.search(note) else 'scheduled',
            note=note.strip(), source=url, raw=line.strip()))
    return rows
