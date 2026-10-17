"""徳島小松島港（徳島県 県土整備部 港湾政策課「クルーズ客船寄港予定」）

ページの HTML 表（No／入港日時／出港日時／船名／寄港岸壁／前港／次港／備考）。表は年ごと（caption の【令和8（2026）年】）。
日付と時刻は同じセルに改行区切り（例: 3月14日(土)\n10:30）。時刻が未定・中止の行は「ー」。
船名の★（初寄港）は note へ。備考の「寄港中止」は status=cancelled。
"""
import re
import common
from bs4 import BeautifulSoup

PORT = '徳島小松島港'
LANDING = 'https://www.pref.tokushima.lg.jp/ippannokata/kendozukuri/kowan/5034248/'


def _year(text):
    m = re.search(r'\((\d{4})\)\s*年', text) or re.search(r'(\d{4})\s*年', text)
    if m:
        return int(m.group(1))
    m = re.search(r'令和\s*(\d+)', text)
    return 2018 + int(m.group(1)) if m else None


def _dt(cell):
    m = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日', cell)
    t = re.search(r'(\d{1,2}:\d{2})', cell)
    return (m.groups() if m else None), (t.group(1) if t else '')


def _parse(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for table in soup.find_all('table'):
        head = [common.z2h(c.get_text(strip=True)) for c in table.find('tr').find_all(['th', 'td'])]
        if '船名' not in head or '入港日時' not in head:
            continue
        # 年は表の caption（【令和8（2026）年】 R8.9.2更新）
        cap = table.caption.get_text(' ', strip=True) if table.caption else ''
        year = _year(common.z2h(cap))
        if not year:
            raise ValueError('year heading not found')
        col = {k: i for i, k in enumerate(head)}
        for tr in table.find_all('tr')[1:]:
            cells = [common.z2h(c.get_text('\n', strip=True)) for c in tr.find_all(['td', 'th'])]
            if len(cells) < len(head):
                continue
            (din, tin), (dout, tout) = _dt(cells[col['入港日時']]), _dt(cells[col['出港日時']])
            if not din:
                continue
            date = common.ymd(year, *din)
            end = common.ymd(year + (1 if dout and int(dout[0]) < int(din[0]) else 0), *dout) if dout else date
            ship = cells[col['船名']].replace('\n', ' ')
            notes = []
            mk = re.search(r'\s*※\s*(.+)$', ship)  # 例: 飛鳥2 ※オーバーナイト
            if mk:
                notes.append(mk.group(1).strip())
                ship = ship[:mk.start()].strip()
            if '★' in ship:
                notes.append('初寄港')
                ship = ship.replace('★', '').strip()
            bikou = cells[col['備考']] if '備考' in col else ''
            status = 'cancelled' if re.search(r'中止|キャンセル|取消|抜港', bikou) else 'scheduled'
            if bikou:
                notes.append(bikou.replace('\n', ' '))
            out.append(common.row(date=date, end=end, port=PORT, ship=ship,
                                  **{'in': common.hhmm(tin), 'out': common.hhmm(tout)},
                                  berth=cells[col['寄港岸壁']] if '寄港岸壁' in col else '',
                                  prev=cells[col['前港']] if '前港' in col else '', next=cells[col['次港']] if '次港' in col else '',
                                  status=status, note=' '.join(notes), source=url, raw=' | '.join(c.replace('\n', ' ') for c in cells)))
    return out


def fetch(ctx):
    rows = _parse(ctx.get(LANDING), LANDING)
    if not rows:
        raise ValueError('no rows parsed from ' + LANDING)
    return rows
