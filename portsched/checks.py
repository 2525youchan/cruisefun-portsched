"""毎日の確認に足す「報告だけ」の点検（daily.py から呼ぶ）。どれも行や取り込み案を変えない・消さない。

1. cross_check   東京港・那覇港の行を、ほかの港の公式の行（前港・次港）で裏付けられるか調べる
2. count_check   取得元ごとの件数の急な変化・取得の失敗・読み取りの失敗（state/source_counts.json と比べる）
3. src_dates     取得元の資料そのものに書いてある更新日（見つからなければ ''＝不明。推測しない）

daily.py は、それぞれを try で囲んで呼ぶ（失敗しても Issue にひとこと出るだけで、ほかの処理は続く）。
"""
import os, re, json, html, datetime, subprocess, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, '..', 'state', 'source_counts.json')

# ---------------------------------------------------------------------------
# 共通
# ---------------------------------------------------------------------------


def _d(s):
    return datetime.date.fromisoformat(s)


def _md(s):
    return f'{int(s[5:7])}/{int(s[8:10])}'


def name_key(s):
    """船名の照合用キー：NFKC・小文字・空白や記号（・ . - など）を除く・Ⅱ/Ⅲ（ii/iii）→ 2/3"""
    s = unicodedata.normalize('NFKC', html.unescape(s or '')).casefold()
    s = re.sub(r'[\W_]', '', s)
    s = re.sub(r'iii$', '3', s)
    s = re.sub(r'ii$', '2', s)
    return s


# ---------------------------------------------------------------------------
# 1. 東京港・那覇港の裏付け
# ---------------------------------------------------------------------------

# 調べる港：取得元 → (港の名前, 前港・次港の欄での書き方（name_key・末尾の「港」を除いたもの）)
TARGETS = {
    'tokyo': ('東京港', ('東京', 'tokyo', '晴海', '竹芝', '東京国際クルーズターミナル', '晴海客船ターミナル')),
    'nacru': ('那覇港', ('那覇', 'naha')),
}
SUPPORT_DAYS = 2    # 他港を出て2日以内に着く（次港）／出て2日以内に他港に着く（前港）なら「裏付けあり」
LOOSE_DAYS = 4      # 3〜4日の開き：遠い港からの移動もあるので、裏付けにも食い違いにもしない
NEAR_DAYS = 7       # 前港・次港が東京（那覇）なのに合う行がないとき、前後7日の東京（那覇）の行に「食い違いの可能性」を付ける


def _place_key(s):
    s = re.sub(r'[（(][^）)]*[）)]', '', s or '')
    s = name_key(s)
    return re.sub(r'(港|port)$', '', s)


def names_port(field, words):
    k = _place_key(field)
    return bool(k) and k in {name_key(w) for w in words}


def _overlap_conflict(t, e):
    """同じ船が t（東京・那覇）と e（他港）に同時にいることになるか。出港した日に次の港に入る移動は除く（時刻が空欄なら移動とみなす）"""
    a, b = max(t['date'], e['date']), min(t['end'], e['end'])
    if a > b:
        return False
    if a != b:
        return True
    d = a

    def ok(x_out, y_in):  # x を出てから y に入れるか
        return not x_out or not y_in or x_out <= y_in
    if e['end'] == d and t['date'] == d and ok(e['out'], t['in']):
        return False
    if t['end'] == d and e['date'] == d and ok(t['out'], e['in']):
        return False
    return True


def _desc(e, field=None):
    s = f"{e['port_name']} {_md(e['date'])}" + (f"〜{_md(e['end'])}" if e['end'] != e['date'] else '')
    t = f"{e['in'] or '—'}–{e['out'] or '—'}"
    s += f'（{t}'
    if field:
        s += f"、{'次港' if field == 'next' else '前港'}：{e[field]}"
    return s + f"、出典 {e['src_key']}）"


def cross_check(rows, today, days=30, key=None):
    """rows：daily.py の公式の行（port_name・ship_name・src_key 付き）。
    返り値 {'items': [東京・那覇の行ごとの結果], 'counts': {...}, 'orphans': [合う東京・那覇の行がない他港の行]}"""
    key = key or (lambda r: name_key(r.get('ship_name') or r['ship']))
    t0, lim = today.isoformat(), (today + datetime.timedelta(days)).isoformat()
    live = [r for r in rows if r.get('status') != 'cancelled' and not r.get('excluded') and r.get('date')]
    out, orphans = [], []
    for src, (pname, words) in TARGETS.items():
        tgt_all = [r for r in live if r['src_key'] == src and r['port_name'] == pname]
        if not tgt_all:
            continue
        cover = max(r['end'] for r in tgt_all)
        targets = [r for r in tgt_all if t0 <= r['date'] <= lim]
        # 他の取得元の行（同じ取得元の別の港＝同じ仕組みの資料は、裏付けにしない）
        others = [r for r in live if r['src_key'] != src and _place_key(r['port_name']) != _place_key(pname)]
        by_ship = {}
        for r in others:
            by_ship.setdefault(key(r), []).append(r)
        tgt_by_ship = {}
        for r in tgt_all:
            tgt_by_ship.setdefault(key(r), []).append(r)
        res = {id(t): {'date': t['date'], 'end': t['end'], 'port': pname, 'ship': t['ship_name'], 'in': t['in'], 'out': t['out'],
                       'src': src, 'support': [], 'conflict': []} for t in targets}
        for t in targets:
            for e in by_ship.get(key(t), []):
                if _overlap_conflict(t, e):
                    res[id(t)]['conflict'].append('同じ日に別の港：' + _desc(e))
        # 前港・次港が東京（那覇）の行
        for k, es in by_ship.items():
            ts = tgt_by_ship.get(k, [])
            for e in es:
                for field in ('next', 'prev'):
                    if not names_port(e.get(field, ''), words):
                        continue
                    if field == 'next':
                        gap = lambda t: (_d(t['date']) - _d(e['end'])).days
                    else:
                        gap = lambda t: (_d(e['date']) - _d(t['end'])).days
                    fit = [t for t in ts if 0 <= gap(t) <= SUPPORT_DAYS]
                    loose = [t for t in ts if SUPPORT_DAYS < gap(t) <= LOOSE_DAYS]
                    for t in fit:
                        if id(t) in res:
                            res[id(t)]['support'].append(_desc(e, field))
                    if fit or loose:
                        continue
                    ref = e['end'] if field == 'next' else e['date']
                    if not (t0 <= ref <= lim) or ref > cover:
                        continue  # 調べる期間の外・東京（那覇）の表が出ていない先の日付
                    near = [t for t in targets if abs((_d(t['date']) - _d(ref)).days) <= NEAR_DAYS and key(t) == k]
                    msg = f"{_desc(e, field)} だが、{pname}の公式の行と日付が合わない（{SUPPORT_DAYS}日以内に合う行がない）"
                    if near:
                        t = min(near, key=lambda t: abs((_d(t['date']) - _d(ref)).days))
                        res[id(t)]['conflict'].append(msg)
                    else:
                        orphans.append({'port': pname, 'ship': e['ship_name'], 'evidence': _desc(e, field)})
        for t in targets:
            it = res[id(t)]
            it['cls'] = '食い違いの可能性' if it['conflict'] else ('裏付けあり' if it['support'] else '材料なし')
            out.append(it)
    out.sort(key=lambda x: (x['date'], x['port'], x['ship']))
    counts = {}
    for it in out:
        c = counts.setdefault(it['port'], {'裏付けあり': 0, '食い違いの可能性': 0, '材料なし': 0})
        c[it['cls']] += 1
    return {'items': out, 'counts': counts, 'orphans': orphans}


def cross_md(res, days=30):
    L = [f'## 東京港・那覇港の裏付け（ほかの港の公式の前港・次港から。今日〜{days}日後）', '',
         '東京港（Power BI）・那覇港（予約システム）の資料は手で確かめにくいので、ほかの港の公式の行で'
         '「前港・次港が東京（那覇）」になっているかを見ました。**「裏付けあり」は手がかりがあるという意味で、正しいことの証明ではありません。**'
         '日付が近い・船の名前が同じだけでは「裏付けあり」にしません。', '']
    for p, c in res['counts'].items():
        L.append(f"- {p}：裏付けあり {c['裏付けあり']}件／食い違いの可能性 {c['食い違いの可能性']}件／材料なし {c['材料なし']}件")
    L.append('')
    bad = [it for it in res['items'] if it['cls'] == '食い違いの可能性']
    if bad:
        L += ['### 食い違いの可能性（要確認。自動では何も変えていません）', '',
              '| 日付 | 港 | 船 | 東京・那覇の公式（入/出） | ほかの港の公式（食い違い） | ほかの港の公式（裏付け） |', '|---|---|---|---|---|---|']
        for it in bad:
            dd = _md(it['date']) + (f"〜{_md(it['end'])}" if it['end'] != it['date'] else '')
            L.append(f"| {dd} | {it['port']} | {it['ship']} | {it['in'] or '—'} / {it['out'] or '—'}（出典 {it['src']}） | "
                     + '<br>'.join(it['conflict'][:4]) + ' | ' + ('<br>'.join(it['support'][:3]) or '—') + ' |')
        L.append('')
    if res['orphans']:
        L += [f"他港の資料では前港・次港が東京・那覇なのに、東京・那覇の公式表に前後{NEAR_DAYS}日の同じ船の行がない：{len(res['orphans'])}件（参考）", '']
        L += [f"- {o['port']} ／ {o['ship']}：{o['evidence']}" for o in res['orphans'][:10]]
        L.append('')
    return L


# ---------------------------------------------------------------------------
# 2. 件数の急な変化・失敗
# ---------------------------------------------------------------------------

# しきい値（取得元ごとに変えるときは PER_SOURCE に入れる）
#   これからの行（今日以降に出港する、中止でない行）の数が、前に取得できたときから
#   pct 以上 かつ abs 以上 変わったら知らせる。
THRESHOLDS = {
    'default': {'pct': 0.30, 'abs': 10},
    'per_source': {},   # 例 'nacru': {'pct': 0.20, 'abs': 30}
}
NET_ERRORS = ('HTTPError', 'ConnectionError', 'Timeout', 'ReadTimeout', 'ConnectTimeout', 'SSLError',
              'ChunkedEncodingError', 'TooManyRedirects', 'ProxyError', 'RemoteDisconnected')


def upcoming(rows, today):
    t0 = today.isoformat()
    n = {}
    for r in rows:
        if r.get('status') != 'cancelled' and (r.get('end') or r.get('date') or '') >= t0 and not r.get('note', '').startswith('入港実績'):
            n[r['src_key']] = n.get(r['src_key'], 0) + 1
    return n


def load_state(path=STATE):
    try:
        return json.load(open(path, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def count_check(report, rows, today, state, thresholds=THRESHOLDS):
    """返り値 (warnings, new_state, firsts)。warnings は [{'src','kind','msg'}]。
    new_state は、取得に成功し1行以上読めた取得元だけ更新したもの（失敗・0行のときは前のまま）"""
    up = upcoming(rows, today)
    new = {k: dict(v) for k, v in state.items()}
    warns, firsts = [], []
    for k, v in report.items():
        last = state.get(k)
        lastdesc = f"（前に取得できたとき {last['date']}：全{last['rows']}行・これから{last['upcoming']}行）" if last else ''
        if not v.get('ok'):
            err = v.get('error', '')
            fetched = [f for f in v.get('fetch', []) if f.get('status') == 200 and f.get('bytes', 0) > 0]
            if any(n in err for n in NET_ERRORS) or not fetched:
                warns.append({'src': k, 'kind': 'fetch_ng', 'msg': f'取得に失敗：{err[:120]}' + lastdesc})
            else:
                warns.append({'src': k, 'kind': 'parse_ng', 'msg': f'ページは取得できたが読み取りに失敗（表・ページの形が変わった可能性）：{err[:120]}' + lastdesc})
            continue
        n_all, n_up = v.get('rows', 0), up.get(k, 0)
        if n_all == 0:
            fetched = [f for f in v.get('fetch', []) if f.get('bytes', 0) > 0]
            why = 'ページは取得できたが0行（表・ページの形が変わった可能性）' if fetched else '0行（取得したページがない）'
            warns.append({'src': k, 'kind': 'zero', 'msg': why + lastdesc})
            continue
        if last:
            th = dict(thresholds['default'], **thresholds.get('per_source', {}).get(k, {}))
            a = last.get('upcoming', 0)
            diff = n_up - a
            if n_up == 0 and a > 0:
                warns.append({'src': k, 'kind': 'zero_upcoming', 'msg': f'これからの行が0になった（全{n_all}行）' + lastdesc})
            elif a and abs(diff) >= th['abs'] and abs(diff) / a >= th['pct']:
                warns.append({'src': k, 'kind': 'jump', 'msg': f"これからの行が {a} → {n_up}（{'+' if diff > 0 else ''}{diff}、{diff / a:+.0%}）" + lastdesc})
        else:
            firsts.append(k)
        new[k] = {'date': today.isoformat(), 'rows': n_all, 'upcoming': n_up}
    return warns, new, firsts


def save_state(new, path=STATE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(new.items())), f, ensure_ascii=False, indent=1)
        f.write('\n')


def count_md(warns, firsts):
    L = ['## 取得件数の急な変化・失敗', '']
    if warns:
        L += ['データは消していません（取り込み案は前の日までの行も「公式から消えた行」として残します）。公式のページを見て確かめてください。', '']
        L += [f"- {w['src']}：{w['msg']}" for w in warns]
    else:
        L.append('ありませんでした。')
    if firsts:
        L.append(f"- 初めて記録した取得元（次回から比べます）：{'、'.join(firsts)}")
    L.append('')
    return L


# ---------------------------------------------------------------------------
# 3. 公式の資料の更新日
# ---------------------------------------------------------------------------

_Y = r'(20\d\d)\s*年\s*(?:\([^)]*\))?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'
_YS = r'(20\d\d)\s*[/.]\s*(\d{1,2})\s*[/.]\s*(\d{1,2})'
_W = r'(?:令和|R)\s*(\d{1,2})\s*[年.]\s*(\d{1,2})\s*[月.]\s*(\d{1,2})\s*日?'
D = '(?:' + '|'.join([_Y, _YS, _W]) + ')'

# 取得元 → [(資料の種類 'pdf'/'html', 探す形（{D} が日付）, 表示)]。上から順に試し、最初に見つかった規則の日付（複数なら新しいほう）を使う
SRC_DATE_RULES = {
    'yokohama': [('html', r'最終更新日\s*{D}', 'ページの最終更新日')],
    'shimizu': [('pdf', r'{D}\s*現在', 'PDF「…現在」')],
    'osaka': [('pdf', r'更新日\s*:?\s*{D}', 'PDFの更新日')],
    'kobe': [('html', r'更新内容\s*{D}', 'ページの「更新内容」の最新')],
    'kanazawa': [('html', r'{D}\s*現在', '表の「…現在」')],
    'sakaiminato': [('pdf', r'更新日\s*:?\s*{D}', 'PDFの更新日')],
    'niigata': [('pdf', r'{D}\s*現在', 'PDF「…現在」')],
    'nagasaki': [('pdf', r'更新日\s*:?\s*{D}', 'PDFの更新日')],
    'hakata': [('pdf', r'{D}\s*現在', 'PDF「…現在」')],
    'kagoshima': [('pdf', r'{D}\s*現在', 'PDF「…現在」')],
    'kochi': [('html', r'\(\s*{D}\s*時点', 'ページ「…時点」')],
    'sasebo': [('pdf', r'{D}\s*更新', 'PDF「…更新」')],
    'matsuyama': [('html', r'{D}\s*現在', '表の「…現在」')],
    'hososhima': [('html', r'更新日\s*:?\s*{D}', 'ページの更新日（細島・宮崎・油津で共通。PDFは月までしか書いていない）')],
    'aburatsu': [('html', r'更新日\s*:?\s*{D}', 'ページの更新日（細島・宮崎・油津で共通。PDFは月までしか書いていない）')],
    'miyazaki': [('html', r'更新日\s*:?\s*{D}', 'ページの更新日（細島・宮崎・油津で共通。PDFは月までしか書いていない）')],
    'hakodate': [('html', r'更新日\s*{D}', 'ページの更新日')],
    'aomori': [('pdf', r'{D}\s*時点', 'PDF「…時点」'), ('html', r'更新日付\s*:?\s*{D}', 'ページの更新日付')],
    'akita': [('html', r'更新日\s*:?\s*{D}', 'ページの更新日')],
    'sakata': [('html', r'更新日\s*:?\s*{D}', 'ページの更新日')],
    'miyako': [('html', r'更新日\s*:?\s*{D}', 'ページの更新日')],
    'beppu': [('html', r'更新日\s*:?\s*{D}', 'ページの更新日')],
    'tokushima': [('html', r'{D}\s*更新', '表の「…更新」')],
    # hiroshima は下の _hiroshima（PDF の2行目の日付と、HTML の表の「(M月D日更新)」）
    # tokyo（Power BI）・nacru（予約システム）は、資料の更新日が読めないので「不明」
}


def _date_of(groups):
    g = [x for x in groups if x is not None]
    if len(g) != 3:
        return ''
    y, m, d = map(int, g)
    if y < 100:  # 令和
        y += 2018
    try:
        return datetime.date(y, m, d).isoformat()
    except ValueError:
        return ''


def _z2h(s):
    return unicodedata.normalize('NFKC', s)


def _html_text(body):
    from bs4 import BeautifulSoup, Comment
    soup = BeautifulSoup(body, 'html.parser')
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()
    for t in soup(['script', 'style']):
        t.decompose()
    return re.sub(r'\s+', ' ', _z2h(soup.get_text(' ')))


def _pdf_text(path):
    out = subprocess.run(['pdftotext', '-enc', 'UTF-8', '-raw', '-l', '2', path, '-'], capture_output=True, timeout=60)
    return re.sub(r'[ \t　]+', ' ', _z2h(out.stdout.decode('utf-8', 'replace')))


def _files(work, key, rep):
    """取得記録（report の fetch）にある、保存した元ファイル → [(種類, 中身の文字)]"""
    seen, out = set(), []
    for f in rep.get('fetch', []):
        name = f.get('saved')
        if not name or name in seen or f.get('status', 200) != 200:
            continue
        seen.add(name)
        p = os.path.join(work, 'raw', key, name)
        if not os.path.exists(p):
            continue
        body = open(p, 'rb').read()
        if body[:5] == b'%PDF-':
            out.append(('pdf', _pdf_text(p)))
        elif re.search(rb'<html|<!doctype html|<body', body[:5000], re.I):
            out.append(('html', _html_text(body)))
    return out


def _hiroshima(files, today):
    from ports import hiroshima as H
    best, where = '', ''
    for kind, text in files:
        if kind == 'pdf':
            d = H._pdf_date(text)
            if d and d > best:
                best, where = d, 'PDFの2行目の日付'
    return best, where


def src_dates(work, report, today):
    """{取得元: {'date': 'YYYY-MM-DD' か ''（不明）, 'where': どこに書いてあったか}}"""
    lim = (today + datetime.timedelta(1)).isoformat()
    res = {}
    for k, rep in report.items():
        item = {'date': '', 'where': ''}
        res[k] = item
        try:
            if not rep.get('ok'):
                continue
            files = _files(work, k, rep)
            if k == 'hiroshima':
                best, where = _hiroshima(files, today)
                # HTML の表の「(M月D日更新)」（年は表の期間から。読み取りの部品を使う）
                p = [f for f in rep.get('fetch', []) if f.get('saved', '').endswith('.html')]
                if p:
                    from ports import hiroshima as H
                    raw = open(os.path.join(work, 'raw', k, p[0]['saved']), 'rb').read().decode('utf-8', 'replace')
                    upd = H._parse_html(raw)[0]
                    if upd and upd <= lim and upd > best:
                        best, where = upd, 'ページの近い期間の表「(M月D日更新)」'
                if best and '2020-01-01' <= best <= lim:
                    item.update(date=best, where=where)
                continue
            for kind, pat, label in SRC_DATE_RULES.get(k, []):
                rx = re.compile(pat.replace('{D}', D))
                ds = [_date_of(m.groups()) for t_kind, text in files if t_kind == kind for m in rx.finditer(text)]
                ds = [d for d in ds if d and '2020-01-01' <= d <= lim]
                if ds:
                    item.update(date=max(ds), where=label)
                    break
        except Exception as e:  # この取得元だけ「不明」にする
            item['where'] = f'読み取りの失敗 {e!r}'[:120]
    return res


def fetched_at(rep):
    ats = [f['at'] for f in rep.get('fetch', []) if f.get('at')]
    return min(ats)[:10] if ats else ''


def sources_md(report, upc, dates, labels):
    L = ['## 取得元ごとの状況', '',
         '「公式の更新日」は、資料（PDF・ページ）に書いてある日付です。見つからないときは「不明」（推測していません）。',
         '', '| 取得元 | 結果 | 全行数 | これから | 公式の更新日 | 取得日 |', '|---|---|---|---|---|---|']
    for k, v in report.items():
        d = dates.get(k, {}) if dates else {}
        upd = (d.get('date') or '不明') + (f"（{d['where']}）" if d.get('date') and d.get('where') else '')
        res = 'OK' if v.get('ok') else 'NG'
        L.append(f"| {labels.get(k, k)} | {res} | {v.get('rows', '—')} | {upc.get(k, 0) if v.get('ok') else '—'} | {upd} | {fetched_at(v) or '—'} |")
    L.append('')
    return L
