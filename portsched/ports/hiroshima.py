"""広島港（広島県 広島港湾振興事務所）

ページ cruise-joho.html にある「YYYY年度広島港客船入港予定表」PDF（/uploaded/attachment/<番号>.pdf、
更新ごとに番号が変わる）を探して読む。pdftotext -raw で 1 行 1 寄港。
行頭の「初」は初入港の印 → note へ。
"""
import re
import common
from urllib.parse import urljoin

PORT = '広島港'
LANDING = 'https://www.pref.hiroshima.lg.jp/soshiki/221/cruise-joho.html'

DT = r'(\d{4})/(\d{1,2})/(\d{1,2})\s+\S\s+(\S+)'
REC = re.compile(r'^(初\s+)?\d{1,3}\s+(.+?)\s+' + DT + r'\s+' + DT +
                 r'\s+[\d,]+\s+[\d.]+\s+\S+\s+(\S+)\s+(客船|\S+)\s+(.*)$')
BERTH = re.compile(r'(バース|岸壁|ふ頭|埠頭|桟橋)')


def _pdf_urls(ctx):
    html = ctx.get(LANDING)
    urls = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I):
        text = common.z2h(re.sub(r'<[^>]+>', '', m.group(2)))
        if re.search(r'\d{4}年度広島港客船入港予定', text):
            u = urljoin(LANDING, m.group(1))
            if u not in urls:
                urls.append(u)
    if not urls:
        raise ValueError('schedule PDF link not found on ' + LANDING)
    return urls


def _parse(text, url):
    out = []
    for line in text.splitlines():
        s = common.z2h(line).strip()
        m = REC.match(s)
        if not m:
            continue
        first, ship, y1, m1, d1, t1, y2, m2, d2, t2, _flag, _use, rest = m.groups()
        toks = rest.split()
        berth = ''
        if toks and BERTH.search(toks[-1]):
            berth = toks.pop()
        prev = toks[0] if len(toks) > 0 else ''
        nxt = ' '.join(toks[1:]) if len(toks) > 1 else ''
        notes = []
        if first:
            notes.append('初入港')
        status = 'scheduled'
        mm = re.search(r'\S*(中止|キャンセル|取消|抜港)\S*', s)
        if mm:
            status = 'cancelled'
            notes.append(mm.group(0))
        out.append(common.row(date=common.ymd(y1, m1, d1), end=common.ymd(y2, m2, d2), port=PORT, ship=ship.strip(),
                              **{'in': common.hhmm(t1), 'out': common.hhmm(t2)}, berth=berth,
                              prev=prev, next=nxt, status=status, note=' '.join(notes), source=url, raw=s))
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
