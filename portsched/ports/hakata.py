"""博多港（福岡市 港湾空港局）

ページ cruise1.html から「クルーズ客船寄港予定」PDF（ファイル名は R8yoteiMMDD.pdf のように毎回変わる）を探して読む。
PDF は 1 行 1 寄港（着岸日時・離岸日時・船名・諸元・船席・前港・次港）。
公表は直近 2 か月ほどのみ。
"""
import re
import common
from urllib.parse import urljoin

PORT = '博多港'
LANDING = 'https://www.city.fukuoka.lg.jp/kowan/k-kikaku/hakata-port/cruise1.html'

# CJK 部首補助の文字（NFKC で直らないもの）
RADICALS = {'⻑': '長', '⻘': '青', '⻄': '西', '⻝': '食', '⻤': '鬼', '⻩': '黄', '⻭': '歯', '⻁': '虎', '⻲': '亀', '⻯': '竜', '戶': '戸'}


def norm(s):
    s = common.z2h(s)
    for k, v in RADICALS.items():
        s = s.replace(k, v)
    return s


DT = r'(\d{4})/(\d{1,2})/(\d{1,2})\s*\(.\)\s*(\S*?)'
REC = re.compile(r'^\d+\s+' + DT + r'\s+' + DT + r'\s+(.+?)\s+[\d,]+\s+[\d.]+\s+[\d,]+\s+[\d.]+\s+(\S+)\s+(.+)$')


def _pdf_urls(ctx):
    html = ctx.get(LANDING)
    urls = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I):
        text = re.sub(r'<[^>]+>', '', m.group(2))
        if '寄港予定' in text or 'yotei' in m.group(1).lower():
            u = urljoin(LANDING, m.group(1))
            if u not in urls:
                urls.append(u)
    if not urls:
        raise ValueError('schedule PDF link not found on ' + LANDING)
    return urls


def _parse(text, url):
    out = []
    for line in text.splitlines():
        s = norm(line).strip()
        m = REC.match(s)
        if not m:
            continue
        y1, m1, d1, t1, y2, m2, d2, t2, ship, berth, rest = m.groups()
        ports = rest.split()
        prev, nxt, note = '', '', ''
        if len(ports) >= 2:
            prev, nxt = ports[0], ' '.join(ports[1:])
        elif ports:
            prev = ports[0]
        status = 'scheduled'
        if re.search(r'中止|キャンセル|取消|抜港', s):
            status, note = 'cancelled', re.search(r'\S*(中止|キャンセル|取消|抜港)\S*', s).group(0)
        clean = lambda p: '' if p in ('-', '－', '―') else p
        out.append(common.row(date=common.ymd(y1, m1, d1), end=common.ymd(y2, m2, d2), port=PORT, ship=ship.strip(),
                              **{'in': common.hhmm(t1), 'out': common.hhmm(t2)}, berth=berth,
                              prev=clean(prev), next=clean(nxt), status=status, note=note, source=url, raw=s))
    return out


def fetch(ctx):
    rows, seen = [], set()
    for url in _pdf_urls(ctx):
        for r in _parse(ctx.pdf_text(url, raw=True), url):
            k = (r['date'], r['ship'], r['in'])
            if k not in seen:
                seen.add(k)
                rows.append(r)
    return rows
