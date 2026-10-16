"""大阪港（大阪港振興協会）クルーズ客船入港予定表 PDF

入口: https://www.oppa.or.jp/calender.html の「大阪港クルーズ客船入港予定表（…）」PDF リンク
PDF（pdftotext -raw）は 1 行 1 隻:
  No 船名[★] 総トン数 t 船籍 入港場所 MM/DD(曜) HH:MM MM/DD(曜) HH:MM 前港 次港 [歓迎イベント]
同じ PDF の「入港実績」（その年の過去分）も読む。
"""
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import common

PORT = '大阪港'
PAGE = 'https://www.oppa.or.jp/calender.html'
DT = r'(\d{1,2})/(\d{1,2})\s*[（(]\s*\S\s*[)）]\s*(\d{1,2}:\d{2})'
LINE = re.compile(r'^(\d{1,3})\s+(.+?)\s+([\d,]+)\s*t\s+(\S+)\s+(\S+)\s+' + DT + r'\s+' + DT + r'\s+(\S+)\s+(\S+)(?:\s+(.*))?$')


def _pdf_links(ctx):
    html = ctx.get(PAGE, binary=True)
    soup = BeautifulSoup(html, 'html.parser')
    urls = []
    for a in soup.find_all('a', href=True):
        t = a.get_text(strip=True)
        if '.pdf' in a['href'].lower() and '予定' in t:
            u = urljoin(PAGE, a['href'])
            if u not in urls:
                urls.append(u)
    if not urls:
        raise RuntimeError('入港予定表 PDF のリンクが見つからない')
    return urls


def _place(s):
    s = (s or '').strip()
    return '' if s in ('未定', '確認中', '―', 'ー', '-', '－') else s


def _parse(text, url):
    text = common.z2h(text)
    m = re.search(r'(\d{4})年\s*[)）]?\s*大阪港', text) or re.search(r'[（(](\d{4})年[)）]', text)
    year = int(m.group(1)) if m else common.TODAY.year
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows = []
    section = 'plan'
    prev_mon, y = None, year
    i = 0
    while i < len(lines):
        l = lines[i]
        if '入港実績' in l:
            section, prev_mon, y = 'past', None, year
        mm = LINE.match(l)
        if not mm and re.match(r'^\d{1,3}\s+\S', l) and i + 1 < len(lines):
            j = l + ' ' + lines[i + 1]   # 長い船名などで行が分かれた場合
            mm = LINE.match(j)
            if mm:
                l = j
                i += 1
        i += 1
        if not mm:
            continue
        g = mm.groups()
        no, ship, ton, flag, berth = g[0:5]
        am, ad, at, dm, dd, dt = g[5:11]
        prev, nxt, ev = g[11], g[12], (g[13] or '').strip()
        am, dm = int(am), int(dm)
        if prev_mon is not None and am < prev_mon - 6:
            y += 1
        prev_mon = am
        date = common.ymd(y, am, ad)
        ey = y + (1 if dm < am - 6 else 0)
        end = common.ymd(ey, dm, dd)
        ship = ship.strip()
        notes = []
        if '★' in ship:
            notes.append('★初入港')
            ship = ship.replace('★', ' ')
        ship = re.sub(r'\s+', ' ', ship).strip()
        status = 'scheduled'
        if re.search(r'中止|キャンセル|抜港|取りやめ|取止', l):
            status = 'cancelled'
            notes.append(re.search(r'\S*(?:中止|キャンセル|抜港|取りやめ|取止)\S*', l).group(0))
        if ev and ev not in ('― ー', '― ―', '未定 未定', 'ー', '―') and not re.fullmatch(r'[―ー\-\s]+', ev) and ev != '未定 未定':
            notes.append('歓迎イベント: ' + ev)
        if section == 'past':
            notes.append('入港実績')
        rows.append(common.row(date=date, end=end, port=PORT, ship=ship, **{'in': common.hhmm(at), 'out': common.hhmm(dt)},
                               berth=berth, prev=_place(prev), next=_place(nxt), status=status,
                               note=' / '.join(notes), source=url, raw=l))
    return rows


def fetch(ctx):
    rows = []
    for u in _pdf_links(ctx):
        rows += _parse(ctx.pdf_text(u, raw=True), u)
    seen, out = set(), []
    for r in rows:
        k = (r['date'], r['ship'], r['in'])
        if k not in seen:
            seen.add(k)
            out.append(r)
    out.sort(key=lambda r: (r['date'], r['in']))
    return out
