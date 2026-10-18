"""取り込み案（import.json）の各行に入る src_updated（公式の資料に書いてある更新日）を確かめる。pytest は要らない。
ネットにはつながない（daily.py の取得・サイトの読み取りは、小さな作りものに置き換える）。

    python -I tests/test_import_src_updated.py
"""
import os, sys, json, shutil, tempfile, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'portsched'))
sys.stdout.reconfigure(encoding='utf-8')
import checks
import daily

TODAY = datetime.date(2026, 10, 18)
OK, NG = [], []
KEYS = ['date', 'end', 'port', 'ship', 'in', 'out', 'berth', 'source_title', 'source_url', 'checked']


def check(name, cond, info=''):
    (OK if cond else NG).append(name)
    print(('OK ' if cond else 'NG ') + name + ('' if cond else f'  → {info}'))


# ---------------------------------------------------------------- 1. row_src_updated（1行に入れる値）
def test_row_value():
    dates = {'yokohama': {'date': '2026-10-06', 'where': '最終更新日'}, 'beppu': {'date': '', 'where': ''},
             'bad': {'date': '2026-02-30', 'where': 'x'}, 'bad2': {'date': '2026/10/06'}, 'bad3': 'x'}
    check('row: 分かっている日付はそのまま', checks.row_src_updated(dates, 'yokohama') == '2026-10-06')
    check('row: 不明 → ""', checks.row_src_updated(dates, 'beppu') == '')
    check('row: 取得元がない → ""', checks.row_src_updated(dates, 'tokyo') == '')
    check('row: 実在しない日付 → ""', checks.row_src_updated(dates, 'bad') == '')
    check('row: 形が違う → ""', checks.row_src_updated(dates, 'bad2') == '' and checks.row_src_updated(dates, 'bad3') == '')
    check('row: 結果が空・None → ""', checks.row_src_updated({}, 'yokohama') == '' and checks.row_src_updated(None, 'yokohama') == '')


# ---------------------------------------------------------------- 2. daily.py の取り込み案
def R(src, port, ship, date, tin='08:00', tout='17:00'):
    return {'src_key': src, 'port': port, 'ship': ship, 'date': date, 'end': date, 'in': tin, 'out': tout,
            'prev': '', 'next': '', 'status': 'scheduled', 'note': '', 'berth': ''}


def run_daily(tmp, rows, report, approved, break_dates=False):
    work = os.path.join(tmp, 'work')
    os.makedirs(work, exist_ok=True)
    json.dump(rows, open(os.path.join(work, 'rows.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(report, open(os.path.join(work, 'report.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    appr = os.path.join(tmp, 'approved.json')
    json.dump({'imported': '2026-10-17 07:00', 'months': [], 'rows': approved}, open(appr, 'w', encoding='utf-8'), ensure_ascii=False)
    saved = (daily.today_jst, daily.site_pages, daily.site_rows, daily.APPROVED, sys.argv, checks.src_dates)

    def fake_pages(w, notes):
        shutil.copy(daily.SNAPSHOT, os.path.join(w, 'site_pages.json'))

    def boom(*a, **k):
        raise RuntimeError('test')

    try:
        daily.today_jst = lambda: TODAY
        daily.site_pages = fake_pages
        daily.site_rows = lambda *a, **k: []
        daily.APPROVED = appr
        if break_dates:
            checks.src_dates = boom
        sys.argv = ['daily.py', work, '--no-fetch', '--no-state']
        daily.main()
    finally:
        daily.today_jst, daily.site_pages, daily.site_rows, daily.APPROVED, sys.argv, checks.src_dates = saved
    return json.load(open(os.path.join(work, 'import.json'), encoding='utf-8'))


def page(tmp, key, name, body):
    d = os.path.join(tmp, 'work', 'raw', key)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, name), 'w', encoding='utf-8').write(body)
    return {'url': 'u', 'status': 200, 'bytes': len(body), 'saved': name, 'at': '2026-10-18T05:31:00'}


def test_daily():
    tmp = tempfile.mkdtemp()
    try:
        H = '<html><body>{}</body></html>'
        report = {
            'yokohama': {'ok': True, 'rows': 2, 'fetch': [page(tmp, 'yokohama', 'a.html', H.format('横浜港客船入港予定 最終更新日 2026年10月6日'))]},
            'beppu': {'ok': True, 'rows': 1, 'fetch': [page(tmp, 'beppu', 'a.html', H.format('日付の書いていないページ'))]},
        }
        rows = [R('yokohama', '横浜港', 'ダイヤモンド・プリンセス', '2026-10-25'),
                R('yokohama', '横浜港', '飛鳥Ⅲ', '2026-11-02'),
                R('beppu', '別府港', 'ダイヤモンド・プリンセス', '2026-10-28')]
        # いま保存されている一覧にあって、公式から消えた行（src_updated のない古い形）
        gone = {'date': '2026-10-30', 'end': '2026-10-30', 'port': '横浜港', 'ship': 'ノルウェージャン・ジュエル', 'in': '07:00', 'out': '18:00',
                'berth': '', 'source_title': 't', 'source_url': 'https://www.city.yokohama.lg.jp/kanko-bunka/minato/kyakusen/nyuko/', 'checked': '2026-10-17'}
        imp = run_daily(tmp, rows, report, [gone])
        by = {(r['date'], r['port']): r for r in imp['rows']}
        y = by.get(('2026-10-25', '横浜港'), {})
        b = by.get(('2026-10-28', '別府港'), {})
        g = by.get(('2026-10-30', '横浜港'), {})
        check('daily: 形は {imported, months, rows}', set(imp) == {'imported', 'months', 'rows'}, list(imp))
        check('daily: 前からの項目は全部ある', all(all(k in r for k in KEYS) for r in imp['rows']), imp['rows'][:1])
        check('daily: 横浜の行 src_updated = 2026-10-06', y.get('src_updated') == '2026-10-06', y)
        check('daily: 横浜の2行目も同じ', by.get(('2026-11-02', '横浜港'), {}).get('src_updated') == '2026-10-06')
        check('daily: 別府（資料に日付なし）→ ""（推測しない）', b.get('src_updated') == '', b)
        check('daily: checked は今までどおり今日', y.get('checked') == '2026-10-18' and b.get('checked') == '2026-10-18')
        check('daily: 公式から消えた行は残り、src_updated は ""', g.get('ship') == 'ノルウェージャン・ジュエル' and g.get('src_updated') == '' and g.get('checked') == '2026-10-17', g)
        check('daily: 全部の行に src_updated（文字列）', all(isinstance(r.get('src_updated'), str) for r in imp['rows']))
        md = open(os.path.join(tmp, 'work', 'daily.md'), encoding='utf-8').read()
        check('daily: 報告の表に公式の更新日が出る（今までどおり）', '2026-10-06' in md)
        # 時刻が変わる行があるとき：指紋は src_updated で変わらない（更新日だけ違っても新しい Issue にしない）
        fps = []
        for day in ('6', '7'):
            shutil.rmtree(os.path.join(tmp, 'work'))
            rep = {'yokohama': {'ok': True, 'rows': 2, 'fetch': [page(tmp, 'yokohama', 'a.html', H.format(f'最終更新日 2026年10月{day}日'))]}}
            old = dict(rows[0], port=rows[0]['port'], source_title='t', source_url='u', checked='2026-10-17', **{'in': '09:00'})
            imp3 = run_daily(tmp, rows[:1], rep, [{k: old[k] for k in KEYS}])
            fps.append(open(os.path.join(tmp, 'work', 'fingerprint')).read())
            ch = json.load(open(os.path.join(tmp, 'work', 'daily.json'), encoding='utf-8'))['changed']
            check(f'daily: 時刻が変わる行が報告に出る（更新日 10/{day}）', len(ch) == 1 and imp3['rows'][0]['src_updated'] == f'2026-10-0{day}', ch)
        check('daily: 指紋は src_updated（10/6 と 10/7）で変わらない', fps[0] == fps[1], fps)
        # 更新日の読み取りが失敗しても、取り込み案は作られ、src_updated は全部 ""
        shutil.rmtree(os.path.join(tmp, 'work'))
        report2 = {'yokohama': {'ok': True, 'rows': 2, 'fetch': [page(tmp, 'yokohama', 'a.html', H.format('最終更新日 2026年10月6日'))]}}
        imp2 = run_daily(tmp, rows[:2], report2, [], break_dates=True)
        check('daily: 更新日の読み取りに失敗 → 取り込み案はでき、src_updated は ""', len(imp2['rows']) == 2 and all(r['src_updated'] == '' for r in imp2['rows']), imp2['rows'])
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    for t in (test_row_value, test_daily):
        try:
            t()
        except Exception as e:
            import traceback
            traceback.print_exc()
            NG.append(t.__name__ + ' raised ' + repr(e))
    print(f'\nOK {len(OK)} / NG {len(NG)}')
    sys.exit(1 if NG else 0)
