"""毎日の確認：各港の公式の予定表と、サイトの港ページの表示（30日以内）を比べる。サイトには何も書き込まない。

使い方:
    python -I daily.py WORKDIR [--no-fetch]
    （--no-fetch：WORKDIR/rows.json と report.json がすでにあるとき、取得をやり直さない）

出力:
    WORKDIR/daily.json   違いの一覧（機械用）
    WORKDIR/daily.md     違いの報告（人が読む用。GitHub の Issue の本文になる）
    WORKDIR/import.json  「ツール ＞ 公式の入港予定」に貼る案（今日〜92日後。確認だけ → 保存はオーナーの承認後）
    WORKDIR/fingerprint  違いの指紋（前の日と同じなら Issue を作らない）
"""
import sys, os, re, json, html, hashlib, datetime, subprocess
import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf-8')
import common
import compare as C
from export import SOURCES, NACRU

SITE = 'https://cruisefun.jp'
DAYS_CHECK = 30    # 港ページが表示する期間
DAYS_IMPORT = 92   # 取り込み案に入れる期間
CONFIG = os.path.join(HERE, '..', 'config', 'decisions.json')


JST = datetime.timezone(datetime.timedelta(hours=9))


def today_jst():
    return datetime.datetime.now(JST).date()


def get(url, **kw):
    r = requests.get(url, headers={'User-Agent': common.UA}, timeout=60, **kw)
    r.raise_for_status()
    return r


SNAPSHOT = os.path.join(HERE, '..', 'config', 'site_pages.json')


def site_pages(work, notes):
    """review 投稿（港・船のページ）の一覧。
    公開の REST API から読む。サーバーが海外からの REST API を断る（GitHub Actions では 403）ときは、
    config/site_pages.json（手元で取った一覧）を使い、サイトマップにあって一覧にないページだけ、ページの見出し（h1＝題名）を読んで足す"""
    out, page = [], 1
    try:
        while True:
            r = get(f'{SITE}/wp-json/wp/v2/review', params={'per_page': 100, 'page': page, '_fields': 'id,slug,title'})
            out += [{'id': p['id'], 'slug': p['slug'], 'title': p['title']['rendered']} for p in r.json()]
            if page >= int(r.headers.get('X-WP-TotalPages', 1)):
                break
            page += 1
    except requests.RequestException:
        out = json.load(open(SNAPSHOT, encoding='utf-8'))
        known = {p['slug'] for p in out}
        sm = get(f'{SITE}/wp-sitemap-posts-review-1.xml').text
        slugs = re.findall(r'<loc>' + re.escape(SITE) + r'/review/([^/<]+)/</loc>', sm)
        if not slugs:
            notes.append('サイトマップから港・船のページが読めない')
        for s in slugs:
            if s in known:
                continue
            h1 = BeautifulSoup(get(f'{SITE}/review/{s}/').text, 'html.parser').select_one('h1')
            if h1 is not None:
                out.append({'id': 0, 'slug': s, 'title': h1.get_text().strip()})
                notes.append(f'新しいページ {s}（{h1.get_text().strip()}）：config/site_pages.json に足すと速くなる')
    common.save_json(os.path.join(work, 'site_pages.json'), out)
    return out


def md_to_date(md, today):
    m, d = md.split('/')
    return common.guess_year(m, d, today)


def site_rows(slug, port_name, ship_by_slug, today):
    """港ページの「この港にこれから来る客船（30日以内）」を読む"""
    soup = BeautifulSoup(get(f'{SITE}/review/{slug}/').text, 'html.parser')
    box = soup.select_one('div.cf-sched:not(.cf-sched--all)')
    if box is None:
        return None  # 一覧の枠がない（30日以内に入港がない港では枠ごと出ない）
    rows = []
    for li in box.select('ul.cf-sched__list > li'):
        dt = li.select_one('.cf-sched__date')
        for b in dt.select('.cf-sched__badge'):
            b.decompose()
        ds = re.findall(r'(\d{1,2}/\d{1,2})', dt.get_text())
        a = li.select_one('.cf-sched__main a')
        txt = li.select_one('.cf-sched__main').get_text().strip()
        ship = txt
        if a is not None:
            s = a['href'].rstrip('/').rsplit('/', 1)[-1]
            ship = ship_by_slug.get(s, txt)
        tm = li.select_one('.cf-sched__time').get_text() if li.select_one('.cf-sched__time') else ''
        t_in = re.search(r'入港\s*([0-9]{2}:[0-9]{2})', tm)
        t_out = re.search(r'出港\s*([0-9]{2}:[0-9]{2})', tm)
        rows.append({'date': md_to_date(ds[0], today), 'end': md_to_date(ds[-1], today), 'port': port_name, 'ship': ship,
                     'in': t_in.group(1) if t_in else '', 'out': t_out.group(1) if t_out else ''})
    return rows


def match_rule(rule, r):
    for k in ('date', 'port', 'ship'):
        if rule.get(k) and C.norm(rule[k]) != C.norm(r.get(k, '')):
            return False
    return True


def main():
    work = sys.argv[1]
    os.makedirs(work, exist_ok=True)
    today = today_jst()
    common.TODAY = today
    if '--no-fetch' not in sys.argv:
        subprocess.run([sys.executable, '-I', os.path.join(HERE, 'run.py'), work], check=True)
    rows = json.load(open(os.path.join(work, 'rows.json'), encoding='utf-8'))
    report = json.load(open(os.path.join(work, 'report.json'), encoding='utf-8'))
    dec = json.load(open(CONFIG, encoding='utf-8')) if os.path.exists(CONFIG) else {}
    ignore = dec.get('ignore', [])

    page_err = []
    site_pages(work, page_err)
    ports, ships = C.load_site(os.path.join(work, 'site_pages.json'))
    ship_by_slug = {v[2]: v[1] for v in ships.values()}

    def sport(p):
        p2 = C.PORT_ALIAS.get(p, p)
        return ports.get(C.norm(p2)) or ports.get(C.norm(re.sub(r'（[^）]*）', '', p2)))

    def sship(s):
        for k in C.ship_keys(s):
            if k in ships:
                return ships[k]
        return None

    def skey(name):
        return next(iter(C.ship_keys(name)))

    # サイトは「今日」を UTC で数えるので、前日に出港した船や30日目の船が出たり出なかったりする。1日ずつ内側だけを比べる
    lim_check = (today + datetime.timedelta(DAYS_CHECK - 1)).isoformat()
    t_keep = (today - datetime.timedelta(2)).isoformat()
    lim_import = (today + datetime.timedelta(DAYS_IMPORT)).isoformat()
    t0 = today.isoformat()

    # 公式の行：サイトの名前にそろえる
    off, cover = [], {}
    for r in rows:
        if r.get('note', '').startswith('入港実績') or r['end'] < t_keep:
            continue
        sp, ss = sport(r['port']), sship(r['ship'])
        it = dict(r, site_port=sp[1] if sp else '', site_slug=sp[2] if sp else '', site_ship=ss[1] if ss else '')
        it['port_name'] = it['site_port'] or r['port']
        it['ship_name'] = it['site_ship'] or r['ship']
        if any(x.get('kind') == 'official' and match_rule(x, {'date': r['date'], 'port': it['port_name'], 'ship': it['ship_name']}) for x in ignore):
            it['excluded'] = True
        off.append(it)
        if sp:
            cover[sp[2]] = max(cover.get(sp[2], ''), r['end'])

    # サイトの港ページ（公式の予定表がある港だけ）
    site, boxes = [], 0
    for slug in sorted(cover):
        name = next(v[1] for v in ports.values() if v[2] == slug)
        try:
            got = site_rows(slug, name, ship_by_slug, today)
        except Exception as e:
            page_err.append(f'{slug}: {e!r}')
            continue
        if got is not None:
            boxes += 1
            site += got
    if cover and not boxes:
        page_err.append('どの港ページにも入港予定の一覧がない（サイトの表示の仕組みが変わった可能性）')

    O = {(r['date'], C.norm(r['port_name']), skey(r['ship_name'])): r for r in off
         if r['status'] != 'cancelled' and not r.get('excluded') and r['site_slug'] and r['date'] <= lim_check}
    S = {(r['date'], C.norm(r['port']), skey(r['ship'])): r for r in site}
    diffs = []
    for k, r in sorted(O.items()):
        if r['end'] < t0:
            continue
        if k not in S:
            diffs.append({'kind': 'add', 'date': r['date'], 'end': r['end'], 'port': r['port_name'], 'ship': r['ship_name'],
                          'official': [r['in'], r['out']], 'site': None, 'src': r['src_key'],
                          'note': '' if r['site_ship'] else '船ページなし（資料の船名：' + r['ship'] + '）'})
        else:
            s = S[k]
            if (s['in'], s['out'], s['end']) != (r['in'], r['out'], r['end']):
                if any(x.get('kind') == 'time' and match_rule(x, {'date': r['date'], 'port': r['port_name'], 'ship': r['ship_name']}) for x in ignore):
                    continue
                diffs.append({'kind': 'time', 'date': r['date'], 'end': r['end'], 'port': r['port_name'], 'ship': r['ship_name'],
                              'official': [r['in'], r['out']], 'site': [s['in'], s['out'], s['end']], 'src': r['src_key'], 'note': ''})
    slug_of = {v[1]: v[2] for v in ports.values()}
    for k, s in sorted(S.items()):
        if k in O or s['end'] < t0 or s['date'] > lim_check or s['date'] > cover.get(slug_of.get(s['port'], ''), ''):
            continue
        if any(x.get('kind') == 'site_only' and match_rule(x, s) for x in ignore):
            continue
        # 公式では同じ日に別の港にいる？
        other = [f"{r['port_name']} {r['in']}–{r['out']}" for r in off if r['status'] != 'cancelled' and r['date'] <= s['date'] <= r['end']
                 and skey(r['ship_name']) == k[2] and C.norm(r['port_name']) != k[1]]
        cancelled = any(r['status'] == 'cancelled' and r['date'] == s['date'] and skey(r['ship_name']) == k[2] for r in off)
        diffs.append({'kind': 'site_only', 'date': s['date'], 'end': s['end'], 'port': s['port'], 'ship': s['ship'],
                      'official': None, 'site': [s['in'], s['out'], s['end']], 'src': '',
                      'note': ('公式に「中止」とある。' if cancelled else '') + ('公式では同じ日に ' + '、'.join(other) if other else '')})
    diffs.sort(key=lambda d: (d['date'], d['port'], d['ship']))

    # 取り込み案（今日〜92日後。ツール ＞ 公式の入港予定 に貼る形）
    imp, seen = [], set()
    for r in sorted(off, key=lambda r: (r['date'], r['port_name'], r['in'])):
        if r['status'] == 'cancelled' or r.get('excluded') or r['date'] > lim_import:
            continue
        k = (r['date'], C.norm(r['port_name']), C.norm(r['ship_name']))
        if k in seen:
            continue
        seen.add(k)
        t, u = NACRU[r['port_name']] if r['src_key'] == 'nacru' else SOURCES[r['src_key']]
        end = r['end'] if (datetime.date.fromisoformat(r['end']) - datetime.date.fromisoformat(r['date'])).days <= 7 else r['date']
        imp.append({'date': r['date'], 'end': end, 'port': r['port_name'], 'ship': r['ship_name'], 'in': r['in'], 'out': r['out'],
                    'berth': r['berth'][:60], 'source_title': t, 'source_url': u, 'checked': t0})
    stamp = datetime.datetime.now(JST).strftime('%Y-%m-%d %H:%M')
    common.save_json(os.path.join(work, 'import.json'), {'imported': stamp, 'months': [], 'rows': imp})

    ng = {k: v.get('error', '') for k, v in report.items() if not v['ok']}
    zero = [k for k, v in report.items() if v['ok'] and not v.get('rows')]
    common.save_json(os.path.join(work, 'daily.json'), {'date': t0, 'diffs': diffs, 'fetch_ng': ng, 'zero_rows': zero, 'page_err': page_err, 'import_rows': len(imp)})
    fp = hashlib.sha256(json.dumps([diffs, sorted(ng), zero, page_err], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    open(os.path.join(work, 'fingerprint'), 'w').write(fp)

    # 報告（Issue の本文）
    lab = {'add': 'サイトにない（追加の候補）', 'time': '時刻・日付が違う', 'site_only': '公式にない（中止の候補）'}
    L = [f'# 入港予定の毎日の確認（{stamp} JST）', '',
         f'各港の公式の予定表（{len(report)}か所）と、サイトの港ページの表示（今日〜{DAYS_CHECK}日後）を比べた結果です。**サイトはまだ変えていません。**', '']
    if ng or zero or page_err:
        L.append('## 取得できなかったもの')
        L += [f'- {k}：{e[:120]}' for k, e in ng.items()] + [f'- {k}：0行（表の形が変わった可能性）' for k in zero] + [f'- サイト {e[:120]}' for e in page_err]
        L.append('')
    if diffs:
        for kind in ('site_only', 'time', 'add'):
            ds = [d for d in diffs if d['kind'] == kind]
            if not ds:
                continue
            L += [f'## {lab[kind]}（{len(ds)}件）', '', '| 日付 | 港 | 船 | 公式（入/出） | サイト（入/出） | メモ |', '|---|---|---|---|---|---|']
            for d in ds:
                dd = d['date'][5:].replace('-', '/') + ('〜' + d['end'][5:].replace('-', '/') if d['end'] != d['date'] else '')
                o = ' / '.join(x or '—' for x in d['official']) if d['official'] else '—'
                s = ' / '.join(x or '—' for x in d['site'][:2]) + (f"（〜{d['site'][2][5:]}）" if d['site'] and d['site'][2] != d['end'] else '') if d['site'] else '—'
                L.append(f"| {dd} | {d['port']} | {d['ship']} | {o} | {s} | {d['note']} |")
            L.append('')
    else:
        L += ['違いはありませんでした。', '']
    L += ['## 次にすること', '- 違いを確かめて、直すものを決める（Claude に「この Issue の違いを判断して」と頼めます）。',
          f'- 取り込み案 `import.json`（{len(imp)}件、今日〜{DAYS_IMPORT}日後）は、承認のあと「ツール ＞ 公式の入港予定」で確認だけ → 保存。',
          '- 直さないと決めたものは `config/decisions.json` に入れると、次から出ません。']
    open(os.path.join(work, 'daily.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('diffs', len(diffs), 'ng', len(ng), 'import', len(imp), 'fp', fp)


if __name__ == '__main__':
    main()
