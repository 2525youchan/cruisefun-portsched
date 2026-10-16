"""酒田港（酒田市 商工港湾課）: 「酒田港 クルーズ船寄港予定及び実績」ページの表（年度ごとに上書き）。

時刻は全角コロン（８：００）。時刻欄が「寄港中止」なら中止。
1 つのセルに日付が 2 つある行（酒田港発着のクルーズ: 出港日と帰港日）は 2 行に分ける。
"""
import re
from bs4 import BeautifulSoup
import common

PORT = '酒田港'
URL = 'https://www.city.sakata.lg.jp/sangyo/kotsu/kouwan/shoko0320191023.html'
CANCEL = re.compile(r'寄港中止|中止|キャンセル|抜港|取り?止め')


def _lines(cell):
    return [re.sub(r'\s+', ' ', common.z2h(x)).strip() for x in cell.get_text('\n').split('\n') if x.strip()]


def fetch(ctx):
    s = BeautifulSoup(ctx.get(URL), 'html.parser')
    berth = ''
    for h in s.find_all(['h2', 'h3']):
        if '寄港場所' in h.get_text():
            nx = h.find_next(['p', 'div'])
            berth = re.sub(r'\s+', ' ', nx.get_text(' ', strip=True)) if nx else ''
            break
    rows = []
    for t in s.find_all('table'):
        trs = t.find_all('tr')
        if not trs:
            continue
        head = [re.sub(r'\s+', '', c.get_text()) for c in trs[0].find_all(['th', 'td'])]
        if not any('寄港予定日' in h or h == '日付' for h in head) or not any('船名' in h for h in head):
            continue
        # 年度: 表の前の見出し「令和N年度…」
        cap = t.find_previous(['h2', 'h3', 'caption'])
        m = re.search(r'令和(\d+)年度', common.z2h(cap.get_text() if cap else ''))
        if not m:
            m = re.search(r'令和(\d+)年度', common.z2h(s.get_text()))
        if not m:
            raise RuntimeError('酒田: 年度が読めません')
        year = 2018 + int(m.group(1))
        ix = lambda key: next((i for i, h in enumerate(head) if key in h), None)
        c_d, c_in, c_out, c_s = ix('予定日') if ix('予定日') is not None else ix('日付'), ix('入港'), ix('出港'), ix('船名')
        last = None
        for tr in trs[1:]:
            cells = tr.find_all(['td', 'th'])
            if len(cells) < len(head):
                continue
            dl = _lines(cells[c_d])
            ins, outs = _lines(cells[c_in]), _lines(cells[c_out])
            sl = _lines(cells[c_s])
            if not sl:
                continue
            notes = []
            ship = sl[0]
            for k in re.findall(r'【([^】]*)】', ship):
                notes.append(k)
            ship = re.sub(r'【[^】]*】', '', ship).strip()
            for x in sl[1:]:
                notes.append(x.strip('()（）') if re.match(r'^[(（].*[)）]$', x) else x)
            b = berth
            for x in notes:
                mb = re.search(r'(\S+?)に着岸', x)
                if mb and 'ふ頭' in mb.group(1):
                    b = mb.group(1).split('から')[-1].lstrip('※')
            dates = [(mm, dd, ln) for ln in dl for mm, dd in re.findall(r'(\d{1,2})月(\d{1,2})日', ln)]
            raw = ' | '.join(' / '.join(_lines(c)) for c in cells)
            for k, (mm, dd, ln) in enumerate(dates):
                key = (int(mm), int(dd))
                if last and key < last and key[0] < 4 <= last[0]:
                    year += 1
                last = key
                tin = ins[k] if k < len(ins) else (ins[0] if ins else '')
                tout = outs[k] if k < len(outs) else (outs[0] if outs else '')
                n = list(notes)
                if '参考' in ln:
                    n.insert(0, '参考')
                cancelled = bool(CANCEL.search(tin + tout))
                if cancelled:
                    n.insert(0, '寄港中止' if '寄港中止' in tin + tout else (tin or tout))
                for x in (tin, tout):
                    if x and not common.hhmm(x) and not CANCEL.search(x):
                        n.append(x)  # 非公表 など
                rows.append(common.row(
                    date=common.ymd(year, mm, dd), port=PORT, ship=ship,
                    **{'in': common.hhmm(tin), 'out': common.hhmm(tout)}, berth=b,
                    status='cancelled' if cancelled else 'scheduled',
                    note=' / '.join(dict.fromkeys(n)), source=URL, raw=raw))
    return rows
