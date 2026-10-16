"""宮古港（岩手県宮古市 観光課）: 「YYYY年クルーズ船寄港予定」ページの表。

入口: 観光課「クルーズ船」カテゴリ一覧（安定）→ 年ごとのページ（ページ ID は年ごとに変わる）。
時刻は「7時」「12時 30分」「ー」（宮古港発で入港なし）。
"""
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import common

PORT = '宮古港'
LANDING = 'https://www.city.miyako.iwate.jp/gyosei/soshiki/kanko/1_1/'
CANCEL = re.compile(r'キャンセル|中止|抜港|取り?止め|取消')


def _clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def fetch(ctx):
    s = BeautifulSoup(ctx.get(LANDING), 'html.parser')
    pages = {}
    for a in s.find_all('a', href=True):
        m = re.search(r'(20\d\d)年\s*クルーズ船寄港予定', common.z2h(a.get_text('', strip=True)))
        if m:
            pages.setdefault(urljoin(LANDING, a['href']), int(m.group(1)))
    if not pages:
        raise RuntimeError('宮古: 寄港予定ページへのリンクが見つかりません: ' + LANDING)
    rows = []
    for url, year in pages.items():
        s = BeautifulSoup(ctx.get(url), 'html.parser')
        h1 = s.find('h1')
        m = re.search(r'(20\d\d)年', common.z2h(h1.get_text() if h1 else ''))
        if m:
            year = int(m.group(1))
        for t in s.find_all('table'):
            trs = t.find_all('tr')
            if not trs:
                continue
            head = [re.sub(r'\s+', '', c.get_text()) for c in trs[0].find_all(['th', 'td'])]
            if not any('日付' in h for h in head) or not any('船名' in h for h in head):
                continue
            ix = lambda key: next((i for i, h in enumerate(head) if key in h), None)
            c_d, c_s, c_in, c_out, c_b, c_n = ix('日付'), ix('船名'), ix('入港'), ix('出港'), ix('場所'), ix('備考')
            last = None
            for tr in trs[1:]:
                cells = [c.get_text(' ', strip=True) for c in tr.find_all(['td', 'th'])]
                g = lambda i: common.z2h(cells[i]) if i is not None and i < len(cells) else ''
                md = re.search(r'(\d{1,2})月\s*(\d{1,2})日', g(c_d))
                ship = _clean(g(c_s))
                if not md or not ship:
                    continue
                y = year
                if last and (int(md.group(1)), int(md.group(2))) < last:
                    year += 1  # 表が年をまたぐとき
                    y = year
                last = (int(md.group(1)), int(md.group(2)))
                d =common.ymd(y, md.group(1), md.group(2))
                note = _clean(g(c_n))
                ends = re.findall(r'(\d{1,2})月\s*(\d{1,2})日', g(c_out))
                e = common.ymd(y, *ends[-1]) if ends else d
                rows.append(common.row(
                    date=d, end=e if e >= d else d, port=PORT, ship=ship,
                    **{'in': common.hhmm(re.sub(r'\s', '', g(c_in))), 'out': common.hhmm(re.sub(r'\s', '', re.sub(r'\d{1,2}月\s*\d{1,2}日', '', g(c_out))))},
                    berth=_clean(g(c_b)), status='cancelled' if CANCEL.search(note) else 'scheduled',
                    note=note, source=url, raw=' | '.join(_clean(c) for c in cells)))
    return rows
