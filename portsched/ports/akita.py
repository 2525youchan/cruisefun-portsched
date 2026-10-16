"""秋田港・船川港・能代港（秋田県 インバウンド・クルーズ誘客推進室）: 「令和N年のクルーズ船寄港予定」PDF。

入口: 推進室のジャンルページ（安定）→ 年ごとの記事ページ（archive ID は年ごとに変わる）→ PDF（名前に日付入り）。
PDF は 1 件が 3 行（日付・船名 / No.・寄港港・定員・寄港地 / 時刻・総トン数）に分かれ、pdftotext では
列の順番が崩れるので、pypdf で文字の座標を取り、入港日の位置で 1 件ずつに区切って読む。
"""
import io, re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import pypdf
import common

PORT = '秋田港'
LANDING = 'https://www.pref.akita.lg.jp/pages/genre/95116'
PORTS = {'秋田港': '秋田', '船川港': '船川', '能代港': '能代'}
SEA = re.compile(r'終日クルーズ|クルーズ$|^$|海峡$|瀬戸内海')
CANCEL = re.compile(r'抜港|中止|キャンセル|取り?止め|取消')
MD = re.compile(r'^(\d{1,2})月(\d{1,2})日$')


def _year(text):
    t = common.z2h(text)
    m = re.search(r'(20\d\d)年', t)
    if m:
        return int(m.group(1))
    m = re.search(r'令和(\d+)年', t)
    return 2018 + int(m.group(1)) if m else None


def _find_pdfs(ctx):
    s = BeautifulSoup(ctx.get(LANDING), 'html.parser')
    pages = []
    for a in s.find_all('a', href=True):
        t = common.z2h(a.get_text('', strip=True))
        if re.search(r'令和\d+年の?クルーズ船寄港予定', t):
            u = urljoin(LANDING, a['href'])
            if u not in pages:
                pages.append(u)
    if not pages:
        raise RuntimeError('秋田: 寄港予定の記事ページが見つかりません: ' + LANDING)
    pdfs = {}
    for p in pages:
        s = BeautifulSoup(ctx.get(p), 'html.parser')
        for a in s.find_all('a', href=True):
            t = common.z2h(a.get_text('', strip=True))
            if '寄港予定' in t and '実績' not in t and a['href'].lower().endswith('.pdf'):
                pdfs.setdefault(urljoin(p, a['href']), _year(t))
    if not pdfs:
        raise RuntimeError('秋田: 寄港予定 PDF が見つかりません: %s' % pages)
    return pdfs


def _items(page):
    out = []

    def v(text, cm, tm, fd, fs):
        t = (text or '').strip()
        if t:
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            out.append((-y, x, common.z2h(t).strip()))
    page.extract_text(visitor_text=v)
    return sorted(out)


def _prev_next(route, short, date):
    """寄港地（例 '(3/13)神戸～…～秋田～青森～…'）から前後の港。終日クルーズなどは飛ばす"""
    m = re.match(r'^\s*[(（]\s*(\d{1,2})/(\d{1,2})\s*[)）]\s*', route)
    start = (int(m.group(1)), int(m.group(2))) if m else None
    body = route[m.end():] if m else route
    parts = [x.strip() for x in re.split(r'[~～]', body)]
    idx = [i for i, x in enumerate(parts) if x == short or x == short + '港']
    if not idx:
        return '', ''
    i = idx[0]
    if len(idx) > 1 and i == 0 and start and (start != (int(date[5:7]), int(date[8:10]))):
        i = idx[1]
    prev = next((parts[j] for j in range(i - 1, -1, -1) if not SEA.search(parts[j]) and parts[j] != short), '')
    nxt = next((parts[j] for j in range(i + 1, len(parts)) if not SEA.search(parts[j]) and parts[j] != short), '')
    return prev, nxt


def fetch(ctx):
    rows = []
    for url, year in _find_pdfs(ctx).items():
        body = ctx.get(url, binary=True)
        reader = pypdf.PdfReader(io.BytesIO(body))
        if not year:
            year = _year(reader.pages[0].extract_text() or '')
        if not year:
            raise RuntimeError('秋田: 年が読めません: ' + url)
        for page in reader.pages:
            items = _items(page)
            anchors = [it for it in items if it[1] < 135 and MD.match(it[2])]
            for k, a in enumerate(anchors):
                y0 = a[0] - 3
                y1 = anchors[k + 1][0] - 3 if k + 1 < len(anchors) else a[0] + 24
                band = [it for it in items if y0 <= it[0] < y1]
                dep = next((it for it in band if 135 <= it[1] < 200 and MD.match(it[2])), None)
                times = [it for it in band if it[1] < 200 and re.match(r'^\d{1,2}時(\d{1,2}分)?$', it[2])]
                tin = next((common.hhmm(it[2]) for it in times if it[1] < 140), '')
                tout = next((common.hhmm(it[2]) for it in times if it[1] >= 140), '')
                no = next((it[2] for it in band if it[1] < 80 and it is not a and not MD.match(it[2])), '')
                port = next((it[2] for it in band if 290 <= it[1] < 335 and it[2] in PORTS), PORT)
                shipparts = [it for it in band if 195 <= it[1] < 295 and not re.match(r'^\([\d,]+t\)$', it[2]) and it[2] != '初']
                ship = ' '.join(it[2] for it in shipparts).strip()
                ship = re.sub(r'^[(（]\s*(船名非公開)\s*[)）]$', r'\1', ship)
                first = any(it[2] == '初' for it in band if it[1] < 300)
                right = ''.join(it[2] for it in band if it[1] >= 500).strip()
                route, notes = '', []
                if re.search(r'[~～]', right):
                    route = right
                elif right:
                    notes.append(right)
                if first:
                    notes.insert(0, '初')
                status = 'scheduled'
                if CANCEL.search(no):
                    status = 'cancelled'
                    notes.insert(0, no)
                d = common.ymd(year, *MD.match(a[2]).groups())
                e = common.ymd(year, *MD.match(dep[2]).groups()) if dep else d
                if e < d:
                    e = common.ymd(year + 1, *MD.match(dep[2]).groups())
                prev, nxt = _prev_next(route, PORTS.get(port, port), d) if route else ('', '')
                raw = ' '.join(it[2] for it in sorted(band, key=lambda t: (round(t[0] / 4), t[1])))
                rows.append(common.row(date=d, end=e, port=port, ship=ship, **{'in': tin, 'out': tout},
                                       prev=prev, next=nxt, status=status, note=' / '.join(notes),
                                       source=url, raw=raw + (' | 寄港地: ' + route if route else '')))
    return rows
