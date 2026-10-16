"""神戸港（神戸観光局 港湾振興部）客船入港予定

https://www.kobe-meriken.or.jp/terminal/eta/ （当月を含む約 3 か月分、月ごとの表）
  船名（*は初入港） | 総トン数 | バース | 入港日 | 入港時刻 | 出港日 | 出港時刻 | 前港 | 次港
船名は英語の大文字表記のまま。お知らせ欄の「10/7「船名」の入港がキャンセルとなりました」は、
表に残っている行を status='cancelled' にする。
"""
import re
from bs4 import BeautifulSoup
import common

PORT = '神戸港'
URL = 'https://www.kobe-meriken.or.jp/terminal/eta/'


def _norm(s):
    return re.sub(r'[\s*＊・･]', '', common.z2h(s)).upper()


def _md(s):
    m = re.search(r'(\d{1,2})月\s*(\d{1,2})日', common.z2h(s))
    return (int(m.group(1)), int(m.group(2))) if m else None


def fetch(ctx):
    html = ctx.get(URL, binary=True)
    soup = BeautifulSoup(html, 'html.parser')
    text = common.z2h(soup.get_text(' '))
    m = re.search(r'(\d{4})年の入港予定', text)
    base_year = int(m.group(1)) if m else common.TODAY.year
    # キャンセルのお知らせ
    cancels = []
    for s in soup.find_all(string=re.compile(r'キャンセル|中止|取りやめ|抜港')):
        t = common.z2h(s.strip())
        for mm in re.finditer(r'(\d{1,2})/(\d{1,2})\s*「([^」]+)」[^。、]*?(?:キャンセル|中止|取りやめ|抜港)[^。]*', t):
            cancels.append((int(mm.group(1)), int(mm.group(2)), _norm(mm.group(3)), mm.group(0).strip()))
    rows = []
    first_mon = None
    for t in soup.find_all('table'):
        for tr in t.find_all('tr'):
            c = [x.get_text(' ', strip=True) for x in tr.find_all(['td', 'th'])]
            if len(c) < 9:
                continue
            a = _md(c[3])
            if not a:
                continue
            if first_mon is None:
                first_mon = a[0]
            y = base_year + (1 if a[0] < first_mon - 6 else 0)
            date = common.ymd(y, *a)
            d = _md(c[5]) or a
            end = common.ymd(y + (1 if d[0] < a[0] else 0), *d)
            ship = c[0].strip()
            notes = []
            if ship.startswith(('*', '＊')):
                notes.append('*初入港')
                ship = ship.lstrip('*＊ ').strip()
            ship = re.sub(r'\s+', ' ', ship)
            status = 'scheduled'
            for cm, cd, cn, wording in cancels:
                if (cm, cd) == a and cn == _norm(ship):
                    status = 'cancelled'
                    notes.append(wording)
            rows.append(common.row(date=date, end=end, port=PORT, ship=ship, **{'in': common.hhmm(c[4]), 'out': common.hhmm(c[6])},
                                   berth=common.z2h(c[2]).strip(), prev=c[7].strip(), next=c[8].strip(), status=status,
                                   note=' / '.join(notes), source=URL, raw=' | '.join(c)))
    seen, out = set(), []
    for r in rows:
        k = (r['date'], r['ship'], r['in'])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out
