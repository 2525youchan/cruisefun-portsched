"""公式の行（rows.json）を、サイトの港・船ページと今のデータに照らして、ある月の一覧を作る。

使い方:
    python -I compare.py OUTDIR YYYY-MM SITE_PAGES.json WC_ROWS.json FIXES.json

SITE_PAGES.json  サイトの review 投稿（id・slug・title）の一覧
WC_ROWS.json     WEB CRUISE の行 [[date, ship, port, in, out], ...]（{"rows": [...]} でもよい）
FIXES.json       今の「入港予定の変更」（cf_sched_fix）の JSON

出力: OUTDIR/month_YYYY-MM.json と OUTDIR/month_YYYY-MM.md
"""
import sys, os, re, json, html, unicodedata, datetime
from collections import defaultdict

# 資料の港名 → サイトの港の名前（サイトの港ページの題名から（県）を除いたもの）
PORT_ALIAS = {
    '石垣島': '石垣港', '石垣港': '石垣港', '平良港（宮古島）': '宮古島・平良港', '平良港': '宮古島・平良港',
    '二見港': '小笠原・二見港', '岡田港': '伊豆大島・岡田港', '岡田/日の出浜': '伊豆大島・岡田港',
    '神湊漁港': '八丈島・神湊港', '八丈島': '八丈島・神湊港', '神湊港': '八丈島・神湊港',
    '小木港': '佐渡島・小木港', '両津港': '佐渡島・両津港', '船川港': '男鹿・船川港', '高知港': '高知新港',
}


# 資料の船名の表記ゆれ → サイトの船ページの名前
SHIP_ALIAS = {
    'イースタンヴィーナス': 'イースタンビーナス', 'イースタン・ヴィーナス': 'イースタンビーナス', 'イースタン・ビーナス': 'イースタンビーナス',
    'ウェステルダム': 'ウエステルダム', 'ミツイ・オーシャン・サクラ': '三井オーシャンサクラ', 'ミツイ・オーシャン・フジ': '三井オーシャンフジ',
    'ルミナラ': 'ルミナーラ', 'セレブレティミレニアム': 'セレブリティ・ミレニアム', 'SEABORUN ENCORE': 'シーボーン・アンコール', 'VISIO': 'ビジオ',
}


def norm(s):
    s = unicodedata.normalize('NFKC', html.unescape(s or ''))
    s = s.replace('ⅱ', 'ii').replace('ⅲ', 'iii')
    s = re.sub(r'[\s​・･.\-‐－—_\'’"“”*★☆]', '', s).lower()
    return s


def ship_keys(s):
    """船名の照合用のキー（日本語・英語の両方）。飛鳥2・飛鳥3 → 飛鳥ii・飛鳥iii"""
    n = norm(SHIP_ALIAS.get(s, s))
    n = re.sub(r'飛鳥(2|ii|Ⅱ)$', '飛鳥ii', n)
    n = re.sub(r'飛鳥(3|iii|Ⅲ)$', '飛鳥iii', n)
    n = n.replace('asuka2', 'asukaii').replace('asuka3', 'asukaiii')
    return {n}


def load_site(path):
    pages = json.load(open(path, encoding='utf-8'))
    ports, ships = {}, {}
    for p in pages:
        t = html.unescape(p['title'])
        m = re.match(r'^(.*?)（(.*)）$', t)
        if not m:
            continue
        a, b = m.group(1), m.group(2)
        if re.search(r'[都道府県]$', b) and not re.search(r'の', a):
            name = re.sub(r'（[^）]*）', '', a)
            ports[norm(name)] = (p['id'], name, p['slug'])
        elif re.search(r'[A-Za-z]', b):
            for k in ship_keys(a) | ship_keys(b):
                ships[k] = (p['id'], a, p['slug'])
    return ports, ships


def main():
    out, month, site_path, wc_path, fix_path = sys.argv[1:6]
    rows = json.load(open(os.path.join(out, 'rows.json'), encoding='utf-8'))
    report = json.load(open(os.path.join(out, 'report.json'), encoding='utf-8'))
    ports, ships = load_site(site_path)
    wc = json.load(open(wc_path, encoding='utf-8'))
    wc = wc['rows'] if isinstance(wc, dict) else wc
    fixes = json.load(open(fix_path, encoding='utf-8'))

    def site_port(p):
        p2 = PORT_ALIAS.get(p, p)
        return ports.get(norm(p2)) or ports.get(norm(re.sub(r'（[^）]*）', '', p2)))

    def site_ship(s):
        for k in ship_keys(s):
            if k in ships:
                return ships[k]
        return None

    first = month + '-01'
    y, m = map(int, month.split('-'))
    last = (datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(1)).isoformat()
    sel = [r for r in rows if r['date'] <= last and r['end'] >= first and not r.get('note', '').startswith('入港実績')]
    wc_keys = {(r[0], norm(PORT_ALIAS.get(r[2], r[2])), next(iter(ship_keys(r[1])))) for r in wc}
    fix_keys = {}
    for f in fixes:
        if f.get('type') == 'add':
            fix_keys[(f['date'], norm(PORT_ALIAS.get(f['port'], f['port'])), next(iter(ship_keys(f['ship']))))] = f
    items = []
    by_ship_day = defaultdict(list)
    for r in sel:
        sp = site_port(r['port'])
        ss = site_ship(r['ship'])
        it = dict(r)
        it['site_port'] = sp[1] if sp else ''
        it['site_port_id'] = sp[0] if sp else 0
        it['site_ship'] = ss[1] if ss else ''
        it['site_ship_id'] = ss[0] if ss else 0
        pk = norm(sp[1]) if sp else norm(r['port'])
        sk = next(iter(ship_keys(ss[1] if ss else r['ship'])))
        it['in_wc'] = (r['date'], pk, sk) in wc_keys
        f = fix_keys.get((r['date'], pk, sk))
        it['in_fix'] = bool(f)
        it['fix_same'] = bool(f) and f['set']['in'] == r['in'] and (f['set']['out'] == r['out'] or (r['end'] != r['date'] and f['set']['out'] == '23:59'))
        flags = []
        if not sp:
            flags.append('港ページなし')
        if not ss:
            flags.append('船ページなし')
        if not r['in'] or not r['out']:
            flags.append('時刻が空欄')
        if r['status'] == 'cancelled':
            flags.append('中止')
        it['flags'] = flags
        items.append(it)
        d = datetime.date.fromisoformat(r['date'])
        while d.isoformat() <= r['end']:
            by_ship_day[(sk, d.isoformat())].append(it)
            d += datetime.timedelta(1)
    # 同じ船が同じ日に別の港にいる（どちらかの資料が古い・誤り）
    for (sk, day), lst in by_ship_day.items():
        live = [i for i in lst if i['status'] != 'cancelled']
        # 出港した日に次の港に入る（出港 < 入港）のは、移動なので問題にしない
        live = [i for i in live if not (i['end'] == day and i['date'] != day and any(j['date'] == day and i['out'] and j['in'] and i['out'] < j['in'] for j in live if j is not i))]
        ps = {i['site_port'] or i['port'] for i in live}
        if len(ps) > 1:
            for i in lst:
                msg = '同じ日に別の港にも：' + '・'.join(sorted(ps - {i['site_port'] or i['port']}))
                if msg not in i['flags']:
                    i['flags'].append(msg)
    items.sort(key=lambda i: (i['date'], i['site_port'] or i['port'], i['in']))
    json.dump(items, open(os.path.join(out, f'month_{month}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    L = [f'# {month} の公式入港予定（取得 {datetime.datetime.now():%Y-%m-%d %H:%M}）', '']
    L.append('| 取得元 | 結果 | 全行数 | 掲載の最後 | この月 |')
    L.append('|---|---|---|---|---|')
    cnt = defaultdict(int)
    for i in items:
        cnt[i['src_key']] += 1
    for k, v in report.items():
        L.append(f"| {k} | {'OK' if v['ok'] else 'NG ' + v.get('error', '')[:60]} | {v.get('rows', '')} | {v.get('to', '')} | {cnt[k]} |")
    L += ['', f'合計 {len(items)} 件（中止 {sum(1 for i in items if i["status"] == "cancelled")}、横浜の手入力と同じ {sum(1 for i in items if i["fix_same"])}）', '']
    L.append('| 日付 | 港 | 船 | 入港 | 出港 | 岸壁 | 前港→次港 | 注意 |')
    L.append('|---|---|---|---|---|---|---|---|')
    for i in items:
        dd = i['date'][5:] + ('〜' + i['end'][5:] if i['end'] != i['date'] else '')
        port = i['site_port'] or i['port']
        ship = i['site_ship'] or i['ship']
        if i['site_ship'] and norm(i['site_ship']) != norm(i['ship']):
            ship += f"（資料：{i['ship']}）"
        fl = list(i['flags'])
        if i['fix_same']:
            fl.append('横浜の手入力と同じ')
        elif i['in_fix']:
            fl.append('横浜の手入力と時刻が違う')
        if i['note']:
            fl.append(i['note'][:40])
        L.append(f"| {dd} | {port} | {ship} | {i['in']} | {i['out']} | {i['berth'][:12]} | {i['prev'][:10]}→{i['next'][:10]} | {'；'.join(fl)} |")
    open(os.path.join(out, f'month_{month}.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print(len(items), 'items')


if __name__ == '__main__':
    main()
