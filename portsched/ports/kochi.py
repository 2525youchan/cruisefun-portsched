"""高知新港（高知県 港湾・海岸課 ポートセールス担当）

ページ /doc/kochi_cruise/ の HTML 表（年度表。年は書いていないので見出しの「令和N年度」から補う）。
表は【高知港】【宿毛湾港】などの見出し行で港が分かれている。
県は「高知港」とだけ書き、新港・浦戸を区別しないので、【高知港】はサイトの「高知新港」として出す
（備考の岸壁名 例:7-2岸壁 は berth に入れる）。他の港の行はその港の名前で出す。
船名の「（乗客定員）」は取り除き、★（初寄港）は note へ。
"""
import re
import common
from bs4 import BeautifulSoup

PORT = '高知新港'
LANDING = 'https://www.pref.kochi.lg.jp/doc/kochi_cruise/'
PORT_MAP = {'高知港': PORT, '高知新港': PORT}


def _fy(text):
    m = re.search(r'令和\s*(\d+)\s*年度', text)
    if m:
        return 2018 + int(m.group(1))
    m = re.search(r'(\d{4})\s*年度', text)
    return int(m.group(1)) if m else None


def _clean_ship(s):
    notes = []
    if '★' in s:
        notes.append('初寄港')
    s = s.replace('★', '')
    s = re.sub(r'\(\s*[\d,]+\s*(人|名)?\s*\)', '', s)  # 乗客定員
    s = re.sub(r'\s*・\s*', '・', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s, notes


def _parse(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    page_fy = _fy(common.z2h(soup.get_text(' ')))
    for table in soup.find_all('table'):
        cells0 = [common.z2h(c.get_text(' ', strip=True)) for c in table.find_all(['th', 'td'])]
        if not any('船名' in c for c in cells0):
            continue
        fy = _fy(' '.join(cells0[:3])) or page_fy
        if not fy:
            raise ValueError('fiscal year not found')
        port = PORT
        for tr in table.find_all('tr'):
            cells = [common.z2h(c.get_text(' ', strip=True)).replace('​', '') for c in tr.find_all(['td', 'th'])]
            if len(cells) == 1:
                m = re.match(r'^【(.+?)】', cells[0])
                if m:
                    port = PORT_MAP.get(m.group(1), m.group(1))
                continue
            if len(cells) < 7 or not re.match(r'^\d+$', cells[0]):
                continue
            no, ship, dcell, tin, tout, prev, nxt = cells[:7]
            note_cell = cells[7] if len(cells) > 7 else ''
            m = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日', dcell)
            if not m:
                continue
            mo, da = m.groups()
            date = common.fiscal_year_date(fy, mo, da)
            end = date
            m2 = re.search(r'[～~〜\-]\s*(?:(\d{1,2})\s*月)?\s*(\d{1,2})\s*日', dcell[m.end():])
            if m2:
                end = common.fiscal_year_date(fy, m2.group(1) or mo, m2.group(2))
            ship, notes = _clean_ship(ship)
            berth = ''
            rest = note_cell.strip()
            mb = re.search(r'\S*(岸壁|バース|桟橋|ふ頭|埠頭)', rest)
            if mb:
                berth = mb.group(0)
                rest = (rest[:mb.start()] + rest[mb.end():]).strip()
            if rest:
                notes.append(rest)
            status = 'scheduled'
            if re.search(r'中止|キャンセル|取消|抜港', ' '.join(cells)):
                status = 'cancelled'
            out.append(common.row(date=date, end=end, port=port, ship=ship,
                                  **{'in': common.hhmm(tin), 'out': common.hhmm(tout)}, berth=berth,
                                  prev=prev if prev not in ('-', '－') else '', next=nxt if nxt not in ('-', '－') else '',
                                  status=status, note=' '.join(notes), source=url, raw=' | '.join(cells)))
    return out


def fetch(ctx):
    rows = _parse(ctx.get(LANDING), LANDING)
    if not rows:
        raise ValueError('no rows parsed from ' + LANDING)
    return rows
