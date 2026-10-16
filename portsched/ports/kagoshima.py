"""鹿児島港（鹿児島県 土木部 港湾空港課）

年ごとのページ kagoshimakour<令和年>yotei.html にある「令和N年鹿児島港寄港予定表」PDF
（ファイル名は ID_タイムスタンプ で毎回変わる）を探して読む。今年と来年のページを試す。
pdftotext -raw では、係船場所（マリンポート / かごしま）や長い船名が次の行に分かれるので、
番号で始まる行から次の番号行までを 1 件にまとめてから読む。
"""
import re
import common
from urllib.parse import urljoin

PORT = '鹿児島港'
PAGE = 'https://www.pref.kagoshima.jp/ah09/infra/port/minato/cruising/kagoshimakour{r}yotei.html'

START = re.compile(r'^\d{1,3}(\s+\S|$)')
REC = re.compile(
    r'^\d{1,3}\s+(?P<ship>.+?)\s+(?P<flag>\S+)\s+[\d,]+\s*トン\s+(?P<m1>\d{1,2})/(?P<d1>\d{1,2})\s*\(.\)\s+(?P<t1>\S+)\s+'
    r'(?P<m2>\d{1,2})/(?P<d2>\d{1,2})\s*\(.\)\s+(?P<t2>\S+)\s*(?P<rest>.*)$', re.S)
BERTH = re.compile(r'(マリンポート|ふ頭|埠頭|岸壁|港区|桟橋|沖)')


def _pdf_urls(ctx):
    r_now = common.TODAY.year - 2018
    urls = []
    for r in (r_now, r_now + 1):
        page = PAGE.format(r=r)
        try:
            html = ctx.get(page)
        except Exception:
            if r == r_now:
                raise
            continue
        for m in re.finditer(r'<a\b[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I):
            text = re.sub(r'<[^>]+>', '', m.group(2))
            if '予定' in text and f'令和{r}年' in common.z2h(text):
                u = urljoin(page, m.group(1))
                if u not in urls:
                    urls.append(u)
    if not urls:
        raise ValueError('schedule PDF link not found')
    return urls


def _records(text):
    recs, cur = [], None
    for line in text.splitlines():
        s = common.z2h(line).strip()
        if not s:
            continue
        if s.startswith('※') or re.match(r'^船\s*名', s) or '入港予定' in s or '現在' in s \
                or s.startswith('鹿児島港'):
            continue  # 見出し・注記（ページの切れ目にも出る）
        if START.match(s) and not re.match(r'^\d{1,2}/\d', s):
            cur = [s]
            recs.append(cur)
        elif cur is not None:
            cur.append(s)
    return recs


def _parse(text, url):
    zt = common.z2h(text)
    m = re.search(r'令和\s*(\d+)\s*年', zt)
    if not m:
        raise ValueError('year not found')
    year = 2018 + int(m.group(1))
    out = []
    for lines in _records(text):
        rec = '\n'.join(lines)
        m = REC.match(rec)
        if not m:
            continue
        ship = m.group('ship').replace('\n', '').strip()
        rest = m.group('rest').replace('マリンポート\nかごしま', 'マリンポートかごしま').split()
        berth = ''
        if rest and BERTH.search(rest[0]):
            berth = rest.pop(0)
        prev = rest[0] if len(rest) > 0 else ''
        nxt = rest[1] if len(rest) > 1 else ''
        note = ' '.join(rest[2:])
        status = 'scheduled'
        if re.search(r'中止|キャンセル|取消|抜港', rec):
            status = 'cancelled'
        clean = lambda p: '' if p in ('-', '－', '―') else p
        d1 = common.ymd(year, m.group('m1'), m.group('d1'))
        y2 = year + (1 if int(m.group('m2')) < int(m.group('m1')) else 0)
        out.append(common.row(date=d1, end=common.ymd(y2, m.group('m2'), m.group('d2')), port=PORT, ship=ship,
                              **{'in': common.hhmm(m.group('t1')), 'out': common.hhmm(m.group('t2'))},
                              berth=berth, prev=clean(prev), next=clean(nxt), status=status, note=note,
                              source=url, raw=rec.replace('\n', ' ')))
    return out


def fetch(ctx):
    rows = []
    for url in _pdf_urls(ctx):
        rows += _parse(ctx.pdf_text(url, raw=True), url)
    return rows
