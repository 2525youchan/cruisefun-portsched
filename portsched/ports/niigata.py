"""新潟港（新潟県 交通政策局 港湾振興課）新潟県内港クルーズ船寄港予定 PDF

入口: https://www.pref.niigata.lg.jp/site/kowanshinko/ の「YYYY年度新潟県内港クルーズ船寄港予定」PDF
（/uploaded/life/xxx_misc.pdf の番号は差し替えで変わるので毎回ページから探す）
PDF（-raw）は 1 行 1 隻、年度の表（1〜3月は翌年）:
  No 月日 曜 入港 出港 船名[※n] 総トン数 定員 寄港場所 接岸ふ頭 前港 次港
区分「1 新潟西港」「2 新潟東港」→ 港 '新潟港'（岸壁に「西港 山の下ふ頭」など）
区分「3 佐渡」→ 寄港場所の港名（'小木港' / '両津港'）
"""
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import common

PORT = '新潟港'
PAGE = 'https://www.pref.niigata.lg.jp/site/kowanshinko/'
LINE = re.compile(r'^(\d{1,3})\s+(\d{1,2})月(\d{1,2})日\s+\S\s+(\S+)\s+(\S+)\s+(.+?)\s+([\d,]+)\s+([\d,]+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$')


def _pdf_links(ctx):
    soup = BeautifulSoup(ctx.get(PAGE, binary=True), 'html.parser')
    out = []
    for a in soup.find_all('a', href=True):
        t = common.z2h(a.get_text(strip=True))
        m = re.search(r'(\d{4})年度.*クルーズ船寄港予定', t)
        if m and '.pdf' in a['href'].lower():
            u = urljoin(PAGE, a['href'])
            if u not in [x[1] for x in out]:
                out.append((int(m.group(1)), u))
    if not out:
        raise RuntimeError('寄港予定 PDF のリンクが見つからない')
    return out


def _place(s):
    return '' if s in ('-', '－', '―', 'ー', '未定') else s


def _parse(text, fy, url):
    text = common.z2h(text)
    m = re.search(r'(\d{4})年度\s*新潟県内港クルーズ船寄港予定', text)
    if m:
        fy = int(m.group(1))
    marks = dict(re.findall(r'※(\d)\s*[:：]\s*([^\n]+)', text))
    section = ''
    rows = []
    for l in (x.strip() for x in text.splitlines()):
        ms = re.match(r'^(\d)\s+(新潟西港|新潟東港|佐渡)', l)
        if ms:
            section = ms.group(2)
            continue
        mm = LINE.match(l)
        if not mm:
            continue
        no, mon, day, tin, tout, ship, ton, cap, place, quay, prev, nxt = mm.groups()
        notes = []
        for k in re.findall(r'※\s*(\d)', ship):
            w = marks.get(k, '').strip()
            if k == '2' and w:
                w = 'ターンアラウンド'
            elif k == '3' and w:
                w = '新潟港発着のクルーズ'
            notes.append(f'※{k} {w}'.strip())
        ship = re.sub(r'※\s*\d', '', ship).strip()
        if section == '佐渡':
            port, berth = place, quay
        else:
            port, berth = PORT, f'{place} {quay}'.strip()
        date = common.fiscal_year_date(fy, mon, day)
        status = 'scheduled'
        if re.search(r'中止|キャンセル|抜港', l):
            status = 'cancelled'
            notes.append(re.search(r'\S*(?:中止|キャンセル|抜港)\S*', l).group(0))
        rows.append(common.row(date=date, end=date, port=port, ship=ship, **{'in': common.hhmm(tin), 'out': common.hhmm(tout)},
                               berth=berth, prev=_place(prev), next=_place(nxt), status=status,
                               note=' / '.join(notes), source=url, raw=l))
    return rows


def fetch(ctx):
    rows = []
    for fy, u in _pdf_links(ctx):
        rows += _parse(ctx.pdf_text(u, raw=True), fy, u)
    seen, out = set(), []
    for r in rows:
        k = (r['port'], r['date'], r['ship'], r['in'])
        if k not in seen:
            seen.add(k)
            out.append(r)
    out.sort(key=lambda r: (r['date'], r['in']))
    return out
