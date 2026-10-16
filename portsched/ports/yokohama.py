"""横浜港（横浜市 港湾局）客船入港予定 HTML 表

https://www.city.yokohama.lg.jp/kanko-bunka/minato/kyakusen/nyuko/<年>.html
月ごとの表: 月 | 入港(日時) | 出港(日時) | 着岸場所 | 船名 | 前港 | 次港
"""
import re, datetime
from bs4 import BeautifulSoup
import common

PORT = '横浜港'
BASE = 'https://www.city.yokohama.lg.jp/kanko-bunka/minato/kyakusen/nyuko/{y}.html'


def _years():
    y = common.TODAY.year
    ys = [y]
    if common.TODAY.month >= 10:
        ys.append(y + 1)
    return ys


def _clean_ship(s):
    s = re.sub(r'\s+', ' ', s.replace('　', ' ')).strip()
    notes, status = [], 'scheduled'
    m = re.search(r'※\s*([^\s]*?(?:中止|抜港|キャンセル)[^\s]*)', s)
    if m:
        status = 'cancelled'
        notes.append(m.group(0).strip())
        s = s.replace(m.group(0), ' ')
    for x in re.findall(r'【([^】]*)】', s):
        notes.append(x)
    s = re.sub(r'【[^】]*】', ' ', s)
    for x in re.findall(r'[（(]([^）)]*(?:寄港|入港|航海|変更)[^）)]*)[）)]', s):
        notes.append(x)
    s = re.sub(r'[（(][^）)]*(?:寄港|入港|航海|変更)[^）)]*[）)]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s, status, ' / '.join(notes)


def _place(s):
    s = re.sub(r'\s+', ' ', s.replace('　', ' ')).strip()
    return '' if s in ('－', '-', '―', '−', 'ー') else s


def _parse_page(html, year, url):
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    title = soup.title.get_text() if soup.title else ''
    if f'{year}年' not in title:   # 存在しない年のページ（エラーページ等）
        return out
    for t in soup.find_all('table'):
        for tr in t.find_all('tr'):
            c = [x.get_text(' ', strip=True) for x in tr.find_all(['td', 'th'])]
            if len(c) < 7 or not re.fullmatch(r'\d{1,2}', common.z2h(c[0]).strip()):
                continue
            mon = int(common.z2h(c[0]))
            a, d = common.z2h(c[1]), common.z2h(c[2])
            ma = re.search(r'(?:(\d{1,2})月)?\s*(\d{1,2})日', a)
            md = re.search(r'(?:(\d{1,2})月)?\s*(\d{1,2})日', d)
            note_extra = []
            if ma:
                am = int(ma.group(1) or mon)
                date = common.ymd(year, am, int(ma.group(2)))
                tin = common.hhmm(a[ma.end():])
            else:
                date, tin = '', ''
                if a.strip():
                    note_extra.append('入港:' + a.strip())
            end, tout = '', ''
            if md:
                ref = datetime.date.fromisoformat(date) if date else datetime.date(year, mon, 1)
                dm = int(md.group(1)) if md.group(1) else ref.month
                dd = int(md.group(2))
                dy = ref.year
                if not md.group(1) and dd < ref.day:
                    dm += 1
                if dm < ref.month:
                    dy += 1
                if dm > 12:
                    dm, dy = 1, dy + 1
                end = common.ymd(dy, dm, dd)
                tout = common.hhmm(d[md.end():])
            elif d.strip():
                note_extra.append('出港:' + d.strip())
            if not date:
                date = end
            if not date:
                continue
            ship, status, note = _clean_ship(c[4])
            note = ' / '.join(x for x in [note] + note_extra if x)
            out.append(common.row(date=date, end=end or date, port=PORT, ship=ship, **{'in': tin, 'out': tout},
                                  berth=_place(c[3]), prev=_place(c[5]), next=_place(c[6]), status=status,
                                  note=note, source=url, raw=' | '.join(c)))
    return out


def fetch(ctx):
    rows, err = [], None
    for i, y in enumerate(_years()):
        url = BASE.format(y=y)
        try:
            body = ctx.get(url, binary=True)
        except Exception as e:
            if i == 0:
                raise
            continue
        rows += _parse_page(body, y, url)
    seen, out = set(), []
    for r in rows:
        k = (r['date'], r['ship'], r['in'], r['berth'])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out
