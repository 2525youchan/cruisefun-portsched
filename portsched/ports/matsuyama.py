"""松山港（愛媛県 土木部 河川港湾局 港湾海岸課「クルーズ船寄港情報（県管理港湾）」）

ページ /page/1074.html の HTML 表。表の見出し（caption）が港名（松山港・宇和島港）。
入港年月日は和暦（令和8年1月24日）、出港月日は年なし、時刻は「8時00分」。
セルにゼロ幅文字（&#8203;）が混じるので取り除く。宇和島港の行も、その港の名前で出す。
"""
import re
import common
from bs4 import BeautifulSoup

PORT = '松山港'
LANDING = 'https://www.pref.ehime.jp/page/1074.html'
ZW = dict.fromkeys(map(ord, '​‌‍﻿ '), ' ')


def _t(el):
    return re.sub(r'\s+', ' ', common.z2h(el.get_text(' ', strip=True).translate(ZW))).strip()


def _parse(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for table in soup.find_all('table'):
        cap = table.caption
        name = _t(cap) if cap else ''
        if not name:
            prev = table.find_previous(['h2', 'h3', 'h4'])
            name = _t(prev) if prev else ''
        mport = re.search(r'(\S+港)', name)
        if not mport:
            continue
        port = mport.group(1)
        head = None
        for tr in table.find_all('tr'):
            cells = [_t(c) for c in tr.find_all(['td', 'th'])]
            if head is None:
                if any('入港' in c for c in cells) and any('船名' in c for c in cells):
                    head = cells
                continue
            col = {h: i for i, h in enumerate(head)}

            def g(key):
                for h, i in col.items():
                    if key in h and i < len(cells):
                        return cells[i]
                return ''
            d_in = g('入港年月日') or g('入港日')
            m = re.search(r'(?:令和\s*(\d+)|(\d{4}))\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', d_in)
            if not m:
                continue
            year = 2018 + int(m.group(1)) if m.group(1) else int(m.group(2))
            mo, da = int(m.group(3)), int(m.group(4))
            date = common.ymd(year, mo, da)
            end = date
            d_out = g('出港月日') or g('出港年月日')
            m2 = re.search(r'(?:(?:令和\s*(\d+)|(\d{4}))\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日', d_out)
            if m2:
                if m2.group(1) or m2.group(2):
                    y2 = 2018 + int(m2.group(1)) if m2.group(1) else int(m2.group(2))
                else:
                    y2 = year + (1 if int(m2.group(3)) < mo else 0)
                end = common.ymd(y2, m2.group(3), m2.group(4))
            ship = g('船名')
            if not ship:
                continue
            status, note = 'scheduled', ''
            joined = ' '.join(cells)
            mm = re.search(r'\S*(中止|キャンセル|取消|抜港)\S*', joined)
            if mm:
                status, note = 'cancelled', mm.group(0)
            out.append(common.row(date=date, end=end, port=port, ship=ship,
                                  **{'in': common.hhmm(g('入港時間')), 'out': common.hhmm(g('出港時間'))},
                                  berth=g('係留場所') or g('岸壁'), prev=g('前港'), next=g('次港') or g('後港'),
                                  status=status, note=note, source=url, raw=' | '.join(cells)))
    return out


def fetch(ctx):
    rows = _parse(ctx.get(LANDING), LANDING)
    if not any(r['port'] == PORT for r in rows):
        raise ValueError('no 松山港 rows parsed from ' + LANDING)
    return rows
