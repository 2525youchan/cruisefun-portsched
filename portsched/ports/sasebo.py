"""佐世保港（一般社団法人長崎県観光連盟「ながさき旅ネット」掲載の予定表。佐世保市港湾部が入港情報の掲載先として案内）

ページ cruise-achievement/ の「佐世保港」見出しのブロックにある「予定表を見る」リンク
（/downloads/media/<ID>、更新ごとに ID が変わる）から PDF を読む。pdftotext -raw で 1 行 1 寄港。
"""
import re
import common
from urllib.parse import urljoin
from bs4 import BeautifulSoup

PORT = '佐世保港'
LANDING = 'https://www.nagasaki-tabinet.com/houjin/report/cruise-achievement/'

REC = re.compile(r'^\d{1,3}\s+(\d{1,2})月(\d{1,2})日\s+[A-Za-z]{3}\.?\s+(.+?)\s+[\d,]+\s+[\d.]+\s+(\S+)\s+(\S+)\s+(.+)$')


def _pdf_urls(ctx):
    soup = BeautifulSoup(ctx.get(LANDING), 'html.parser')
    urls = []
    for h in soup.find_all(['h2', 'h3', 'h4']):
        if common.z2h(h.get_text(strip=True)) != PORT:
            continue
        box = h.find_parent('li') or h.parent
        for a in box.find_all('a', href=True):
            if '予定' in a.get_text() or 'downloads/media' in a['href']:
                u = urljoin(LANDING, a['href'])
                if u not in urls:
                    urls.append(u)
    if not urls:
        raise ValueError('佐世保港 schedule link not found on ' + LANDING)
    return urls


def _parse(text, url):
    zt = common.z2h(text)
    m = re.search(r'(\d{4})\s*\(令和\s*\d+\)\s*年', zt) or re.search(r'(\d{4})\s*年', zt)
    if not m:
        raise ValueError('year not found')
    year = int(m.group(1))
    out = []
    for line in zt.splitlines():
        s = line.strip()
        m = REC.match(s)
        if not m:
            continue
        mo, da, ship, tin, tout, rest = m.groups()
        toks = rest.split()
        berth = toks.pop() if toks else ''
        while toks and re.fullmatch(r'[A-Za-z][A-Za-z.\-]*', toks[-1]) and len(toks) > 2:
            toks.pop()  # 船籍（英語）
        prev = toks[0] if toks else ''
        nxt = ' '.join(toks[1:])
        clean = lambda p: '' if p in ('-', '－', '―') else p
        status, note = 'scheduled', ''
        mm = re.search(r'\S*(中止|キャンセル|取消|抜港)\S*', s)
        if mm:
            status, note = 'cancelled', mm.group(0)
        out.append(common.row(date=common.ymd(year, mo, da), port=PORT, ship=ship.strip(),
                              **{'in': common.hhmm(tin), 'out': common.hhmm(tout)}, berth=berth,
                              prev=clean(prev), next=clean(nxt), status=status, note=note, source=url, raw=s))
    return out


def fetch(ctx):
    rows = []
    for url in _pdf_urls(ctx):
        rows += _parse(ctx.pdf_text(url, raw=True), url)
    return rows
