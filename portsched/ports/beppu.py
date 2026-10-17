"""別府港（大分県 別府土木事務所「別府港 クルーズ船等 入港予定 YYYY」）

ページ /site/beppu17003/YYYYcruising.html の本文に、1寄港1行で「10月04日 (日曜日) Viking Venus 【47842トン、…】」。
年は URL（暦年のページ）。入出港の時刻と岸壁は行ごとには書いていない（場所は「別府港 第4ふ頭」とページに1回だけ）。
船名は英語。今年と来年のページを読む（来年のページがまだなければ飛ばす）。
"""
import re
import common
from bs4 import BeautifulSoup

PORT = '別府港'
URL = 'https://www.pref.oita.jp/site/beppu17003/{y}cruising.html'
LANDING = URL.format(y=2026)
LINE = re.compile(r'^(\d{1,2})月(\d{1,2})日\s*\([^)]*\)\s*(.+?)\s*(?:【.*】)?\s*$')


def _parse(html, url, year):
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find(id='main') or soup.find('main') or soup.body
    text = common.z2h(main.get_text('\n', strip=True)).replace('\t', ' ')
    berth = ''
    mb = re.search(r'別府港\s*(第\S+?ふ頭)', text)
    if mb:
        berth = mb.group(1)
    out = []
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if not m:
            continue
        mo, da, ship = m.groups()
        status = 'cancelled' if re.search(r'中止|キャンセル|取消|抜港', line) else 'scheduled'
        out.append(common.row(date=common.ymd(year, mo, da), port=PORT, ship=ship.strip(), berth=berth,
                              status=status, note='入出港時刻の記載なし', source=url, raw=line.strip()))
    return out


def fetch(ctx):
    y0 = common.TODAY.year
    rows = []
    for y in (y0, y0 + 1):
        url = URL.format(y=y)
        try:
            html = ctx.get(url)
        except Exception:
            if y == y0:
                raise
            continue
        rows += _parse(html, url, y)
    if not rows:
        raise ValueError('no rows parsed from ' + URL.format(y=y0))
    return rows
