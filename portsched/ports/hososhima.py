"""細島港（宮崎県 県土整備部 港湾課／宮崎県ポートセールス協議会）

ページ「クルーズ船寄港情報」には細島港・宮崎港・油津港の PDF がどれも「寄港スケジュール」という
同じリンク名で並ぶので、直前の見出し（h2/h3 が「細島港」）で選ぶ。PDF の 1 行目の表題も確かめる。
PDF は暦年ごとの節（2025(令和7)年 / 2026(令和8)年 …）に分かれ、日付は月日のみ。
備考の「初寄港」は note へ。「終了」（寄港済み）は取り除く。
"""
import re
import common
from urllib.parse import urljoin
from bs4 import BeautifulSoup

PORT = '細島港'
LANDING = 'https://www.pref.miyazaki.lg.jp/kowan/kurashi/shakaikiban/m-port/cruise/20251212151322.html'

DATE = re.compile(r'^(\d{1,2})月(\d{1,2})日\s+\S\s+(.*)$')
TIME = re.compile(r'^\d{1,2}:\d{2}$')
NUM = re.compile(r'^(\d{1,3}(?:,\d{3})+|\d+)$')


def _pdf_urls(ctx):
    soup = BeautifulSoup(ctx.get(LANDING), 'html.parser')
    heading, urls = '', []
    for el in soup.find_all(['h2', 'h3', 'h4', 'a']):
        if el.name != 'a':
            heading = common.z2h(el.get_text(strip=True)).replace('\xa0', '').strip()
            continue
        href = el.get('href', '')
        if heading == PORT and href.lower().endswith('.pdf') and 'スケジュール' in el.get_text():
            u = urljoin(LANDING, href)
            if u not in urls:
                urls.append(u)
    if not urls:
        raise ValueError('細島港 schedule PDF link not found on ' + LANDING)
    return urls


def _parse(text, url):
    zt = common.z2h(text)
    if PORT not in zt[:200]:
        raise ValueError('PDF title is not 細島港: ' + url)
    out, year, cur = [], None, None
    recs = []
    for line in zt.splitlines():
        s = line.strip()
        if not s:
            continue
        my = re.match(r'^(\d{4})\s*\(令和\s*\d+\)\s*年$', s)
        if my:
            year, cur = int(my.group(1)), None
            continue
        if DATE.match(s):
            if year is None:
                raise ValueError('year section not found')
            cur = [year, s]
            recs.append(cur)
        elif cur is not None and re.fullmatch(r'(初寄港|終了|中止|キャンセル|抜港|\S*変更\S*)(\s+\S+)*', s):
            cur.append(s)
        else:
            cur = None  # 見出し・注記
    for rec in recs:
        y, first, extra = rec[0], rec[1], rec[2:]
        m = DATE.match(first)
        mo, da, rest = m.groups()
        toks = rest.split()
        tin = toks.pop(0) if toks and TIME.match(toks[0]) else ''
        tout = toks.pop(0) if toks and TIME.match(toks[0]) else ''
        # 名称 運航会社… 総トン数 乗客定員 発地 前港 後港 備考
        idx = None
        for i in range(len(toks) - 1):
            if NUM.match(toks[i]) and NUM.match(toks[i + 1]) and ',' in toks[i]:
                idx = i
                break
        if idx is None or idx < 1:
            continue
        ship = toks[0]
        after = toks[idx + 2:] + ' '.join(extra).split()
        place = [t for t in after if not re.fullmatch(r'初寄港|終了|中止|キャンセル|抜港|\S*変更\S*', t)]
        marks = [t for t in after if t not in place and t != '終了']
        prev = place[1] if len(place) > 1 else ''
        nxt = place[2] if len(place) > 2 else ''
        status = 'cancelled' if any(re.search(r'中止|キャンセル|抜港', t) for t in marks) else 'scheduled'
        out.append(common.row(date=common.ymd(y, mo, da), port=PORT, ship=ship,
                              **{'in': common.hhmm(tin), 'out': common.hhmm(tout)},
                              prev=prev, next=nxt, status=status, note=' '.join(marks), source=url,
                              raw=' '.join([first] + extra)))
    return out


def fetch(ctx):
    rows = []
    for url in _pdf_urls(ctx):
        rows += _parse(ctx.pdf_text(url, raw=True), url)
    return rows
