"""広島港（広島県 広島港湾振興事務所）

ページ cruise-joho.html にある「YYYY年度広島港客船入港予定表」PDF（/uploaded/attachment/<番号>.pdf、
更新ごとに番号が変わる）を探して読む。pdftotext -raw で 1 行 1 寄港。
行頭の「初」は初入港の印 → note へ。

同じページには、近い期間（約1か月）の入出港予定の表（HTML、「(M月D日更新)」）もある。PDF より新しく更新されて
いることがあるので（2026-10-18：10/23 ルミナーラ・10/24 ダイヤモンド・プリンセスの時刻が PDF と違った）、
HTML の更新日が PDF の日付と同じか新しければ、同じ日・同じ船の行の時刻・岸壁を HTML に合わせ、note に書く。
PDF にない日の HTML の行は足す。PDF の行は消さない（HTML にない行は note に書くだけ）。
"""
import re
import common
from urllib.parse import urljoin

PORT = '広島港'
LANDING = 'https://www.pref.hiroshima.lg.jp/soshiki/221/cruise-joho.html'

DT = r'(\d{4})/(\d{1,2})/(\d{1,2})\s+\S\s+(\S+)'
REC = re.compile(r'^(初\s+)?\d{1,3}\s+(.+?)\s+' + DT + r'\s+' + DT +
                 r'\s+[\d,]+\s+[\d.]+\s+\S+\s+(\S+)\s+(客船|\S+)\s+(.*)$')
BERTH = re.compile(r'(バース|岸壁|ふ頭|埠頭|桟橋)')


def _pdf_urls(ctx):
    html = ctx.get(LANDING)
    urls = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I):
        text = common.z2h(re.sub(r'<[^>]+>', '', m.group(2)))
        if re.search(r'\d{4}年度広島港客船入港予定', text):
            u = urljoin(LANDING, m.group(1))
            if u not in urls:
                urls.append(u)
    if not urls:
        raise ValueError('schedule PDF link not found on ' + LANDING)
    return urls


def _parse(text, url):
    out = []
    for line in text.splitlines():
        s = common.z2h(line).strip()
        m = REC.match(s)
        if not m:
            continue
        first, ship, y1, m1, d1, t1, y2, m2, d2, t2, _flag, _use, rest = m.groups()
        toks = rest.split()
        berth = ''
        if toks and BERTH.search(toks[-1]):
            berth = toks.pop()
        prev = toks[0] if len(toks) > 0 else ''
        nxt = ' '.join(toks[1:]) if len(toks) > 1 else ''
        notes = []
        if first:
            notes.append('初入港')
        status = 'scheduled'
        mm = re.search(r'\S*(中止|キャンセル|取消|抜港)\S*', s)
        if mm:
            status = 'cancelled'
            notes.append(mm.group(0))
        out.append(common.row(date=common.ymd(y1, m1, d1), end=common.ymd(y2, m2, d2), port=PORT, ship=ship.strip(),
                              **{'in': common.hhmm(t1), 'out': common.hhmm(t2)}, berth=berth,
                              prev=prev, next=nxt, status=status, note=' '.join(notes), source=url, raw=s))
    return out


PDF_DATE = re.compile(r'^\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*$')
HTML_RANGE = re.compile(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*[〜~～-]\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*までのクルーズ客船')
HTML_UPD = re.compile(r'[(（]\s*(\d{1,2})月\s*(\d{1,2})日\s*更新')
HTML_DT = re.compile(r'(\d{1,2})月\s*(\d{1,2})日\s*(?:[(（]\S[)）])?\s*(\d{1,2}時\d{0,2}分?)?')


def _pdf_date(text):
    """PDF の2行目あたりの「2026/10/7」（作成日）。なければ ''"""
    for line in text.splitlines()[:6]:
        m = PDF_DATE.match(common.z2h(line))
        if m:
            return common.ymd(*m.groups())
    return ''


def _name_key(s):
    s = common.z2h(s or '').replace('Ⅲ', '3').replace('Ⅱ', '2').replace('Ⅰ', '1')
    return re.sub(r'[\s・.\-]', '', s).upper()


def _parse_html(html):
    """近い期間の表 → (更新日 'YYYY-MM-DD' か '', 期間の最初と最後, 行のリスト)"""
    text = common.z2h(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html.replace('&nbsp;', ' '))))
    rg = HTML_RANGE.search(text)
    if not rg:
        return '', '', '', []
    y1, m1, d1, y2, m2, d2 = rg.groups()
    start, last = common.ymd(y1, m1, d1), common.ymd(y2, m2, d2)
    up = HTML_UPD.search(text, rg.end())
    upd = ''
    if up:
        uy = int(y1) if int(up.group(1)) >= int(m1) else int(y1) + 1
        upd = common.ymd(uy, up.group(1), up.group(2))
        if upd > last:  # 期間の前の年の更新
            upd = common.ymd(uy - 1, up.group(1), up.group(2))
    out = []
    for tb in re.findall(r'<table.*?</table>', html, re.S):
        head = common.z2h(re.sub(r'<[^>]+>', '', ''.join(re.findall(r'<th[^>]*>.*?</th>', tb, re.S))))
        if '船名' not in head or '入港' not in head:
            continue
        for tr in re.findall(r'<tr.*?</tr>', tb, re.S):
            cells = [common.z2h(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', c.replace('&nbsp;', ' ')))).strip()
                     for c in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
            if len(cells) < 6:
                continue
            a, b = HTML_DT.search(cells[0]), HTML_DT.search(cells[1])
            if not a or not b:
                continue

            def _d(m):
                y = int(y1) if int(m.group(1)) >= int(m1) else int(y1) + 1
                return common.ymd(y, m.group(1), m.group(2))
            out.append({'date': _d(a), 'end': _d(b), 'ship': cells[2], 'in': common.hhmm(a.group(3) or ''),
                        'out': common.hhmm(b.group(3) or ''), 'prev': cells[3], 'next': cells[4], 'berth': cells[5]})
        if out:
            break
    return upd, start, last, out


def _merge_html(rows, html, pdf_date):
    """HTML の表（PDF と同じ日か新しい）で、同じ日・同じ船の行の時刻・岸壁を直す。PDF の行は消さない"""
    upd, start, last, hrows = _parse_html(html)
    if not hrows or not upd or (pdf_date and upd < pdf_date):
        return rows
    label = f'HTMLの表（{int(upd[5:7])}/{int(upd[8:10])}更新）'
    for h in hrows:
        same_day = [r for r in rows if r['date'] == h['date'] and r['status'] != 'cancelled']
        hit = [r for r in same_day if _name_key(r['ship']) == _name_key(h['ship'])]
        if not hit:
            hb = _name_key(h['berth'])
            hit = [r for r in same_day if _name_key(r['berth']) == hb] if len(same_day) and hb else []
            hit = hit if len(hit) == 1 else []
        if hit:
            r = hit[0]
            chg = []
            for k in ('end', 'in', 'out'):
                if h[k] and h[k] != r[k]:
                    chg.append(f'{k} {r[k] or "—"}→{h[k]}')
                    r[k] = h[k]
            if h['berth'] and _name_key(h['berth']) != _name_key(r['berth']):
                chg.append(f'岸壁 {r["berth"] or "—"}→{h["berth"]}')
                r['berth'] = h['berth']
            if chg:
                r['note'] = (r['note'] + ' ' if r['note'] else '') + label + 'に合わせた（' + '、'.join(chg) + '）'
            r['_html'] = True
        elif not same_day:
            rows.append(common.row(date=h['date'], end=h['end'], port=PORT, ship=h['ship'], **{'in': h['in'], 'out': h['out']},
                                   berth=h['berth'], prev=h['prev'], next=h['next'], note=label + 'にだけある行',
                                   source=LANDING, raw=' | '.join([h['date'], h['ship'], h['in'], h['out'], h['berth']])))
    for r in rows:
        if start <= r['date'] <= last and r['status'] != 'cancelled' and not r.pop('_html', False):
            r['note'] = (r['note'] + ' ' if r['note'] else '') + label + 'にない'
        r.pop('_html', None)
    return rows


def fetch(ctx):
    rows, seen = [], set()
    pdf_date = ''
    for url in _pdf_urls(ctx):
        text = ctx.pdf_text(url, raw=True)
        pdf_date = max(pdf_date, _pdf_date(text))
        for r in _parse(text, url):
            k = (r['date'], r['ship'], r['in'])
            if k not in seen:
                seen.add(k)
                rows.append(r)
    return _merge_html(rows, ctx.get(LANDING), pdf_date)
