"""portsched/checks.py の点検（報告だけ）を、作った小さなデータで確かめる。pytest は要らない。

    python -I tests/test_checks.py
"""
import os, sys, json, shutil, tempfile, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'portsched'))
sys.stdout.reconfigure(encoding='utf-8')
import checks

TODAY = datetime.date(2026, 10, 18)
OK, NG = [], []


def check(name, cond, info=''):
    (OK if cond else NG).append(name)
    print(('OK ' if cond else 'NG ') + name + ('' if cond else f'  → {info}'))


def R(src, port, ship, date, end=None, tin='08:00', tout='17:00', prev='', nxt='', status='scheduled'):
    return {'src_key': src, 'port': port, 'port_name': port, 'ship': ship, 'ship_name': ship, 'date': date, 'end': end or date,
            'in': tin, 'out': tout, 'prev': prev, 'next': nxt, 'status': status, 'note': '', 'berth': ''}


def cls(res, date, port, ship):
    for it in res['items']:
        if it['date'] == date and it['port'] == port and it['ship'] == ship:
            return it['cls']
    return None


# ---------------------------------------------------------------- 1. 東京港・那覇港の裏付け
def test_cross():
    rows = [
        # 裏付けあり（次港）：清水 10/20 →（次港 東京）→ 東京 10/21
        R('tokyo', '東京港', '飛鳥Ⅱ', '2026-10-21'),
        R('shimizu', '清水港', '飛鳥II', '2026-10-20', nxt='東京'),
        # 裏付けあり（前港）：東京 10/22 → 神戸 10/24（前港 東京港）
        R('tokyo', '東京港', 'ダイヤモンド・プリンセス', '2026-10-22'),
        R('kobe', '神戸港', 'ダイヤモンド プリンセス', '2026-10-24', prev='東京港'),
        # 材料なし：同じ船が近い日に別の港にいるだけ（前港・次港に東京がない）
        R('tokyo', '東京港', 'にっぽん丸', '2026-10-23'),
        R('yokohama', '横浜港', 'にっぽん丸', '2026-10-24', prev='清水', nxt='神戸'),
        # 食い違いの可能性：同じ日に別の港（時刻も重なる）
        R('tokyo', '東京港', 'セレブリティ・ミレニアム', '2026-10-25', tin='08:00', tout='18:00'),
        R('yokohama', '横浜港', 'セレブリティ・ミレニアム', '2026-10-25', tin='09:00', tout='19:00'),
        # 出港した日に次の港に入る移動は食い違いにしない（横浜を 06:00 に出て東京に 14:00）
        R('tokyo', '東京港', 'シルバー・ムーン', '2026-10-26', tin='14:00', tout='22:00'),
        R('yokohama', '横浜港', 'シルバー・ムーン', '2026-10-25', end='2026-10-26', tin='08:00', tout='06:00', nxt='東京'),
        # 食い違いの可能性：次港は東京だが、東京の行は5日後（2日以内にない）
        R('tokyo', '東京港', 'ウエステルダム', '2026-11-02'),
        R('kagoshima', '鹿児島港', 'ウエステルダム', '2026-10-28', nxt='東京'),
        # 同じ取得元（東京都の資料）の別の港は裏付けにしない
        R('tokyo', '東京港', 'ぱしふぃっくびいなす', '2026-10-27'),
        R('tokyo', '二見港', 'ぱしふぃっくびいなす', '2026-10-25', nxt='東京'),
        # 向きが逆（前港が東京なのに東京より前の日付）は裏付けにしない
        R('tokyo', '東京港', 'アマデア', '2026-10-29'),
        R('osaka', '大阪港', 'アマデア', '2026-10-27', prev='東京'),
        # 3日の開き：裏付けにも食い違いにもしない
        R('tokyo', '東京港', 'クイーン・エリザベス', '2026-10-30'),
        R('nagasaki', '長崎港', 'クイーン・エリザベス', '2026-10-27', nxt='東京'),
        # 中止の行は使わない
        R('tokyo', '東京港', 'ルミナーラ', '2026-10-31'),
        R('shimizu', '清水港', 'ルミナーラ', '2026-10-31', status='cancelled'),
        # 那覇：英語の Naha・大文字小文字の違い
        R('nacru', '那覇港', 'MSC BELLISSIMA', '2026-10-21', tin='07:00', tout='16:00'),
        R('kagoshima', '鹿児島港', 'MSC Bellissima', '2026-10-23', prev='Naha'),
        # 那覇の表にない寄港を示す他港の行（参考：前後7日に那覇の行がない）
        R('nacru', '那覇港', 'スター・ナビゲーター', '2026-10-05'),
        R('kagoshima', '鹿児島港', 'スター・ナビゲーター', '2026-10-21', nxt='那覇'),
        # 期間外（31日より先）の東京の行は数えない
        R('tokyo', '東京港', '遠い船', '2026-12-01'),
    ]
    res = checks.cross_check(rows, TODAY, 30)
    T, N = '東京港', '那覇港'
    check('cross: 次港=東京・1日前 → 裏付けあり（Ⅱ/II の違いも同じ船）', cls(res, '2026-10-21', T, '飛鳥Ⅱ') == '裏付けあり', res['items'])
    check('cross: 前港=東京港・2日後 → 裏付けあり', cls(res, '2026-10-22', T, 'ダイヤモンド・プリンセス') == '裏付けあり')
    check('cross: 同じ船・近い日だけ → 材料なし（一致にしない）', cls(res, '2026-10-23', T, 'にっぽん丸') == '材料なし')
    check('cross: 同じ日に別の港（時刻が重なる） → 食い違いの可能性', cls(res, '2026-10-25', T, 'セレブリティ・ミレニアム') == '食い違いの可能性')
    check('cross: 出港した日に東京へ移動 → 食い違いにしない（裏付けあり）', cls(res, '2026-10-26', T, 'シルバー・ムーン') == '裏付けあり')
    check('cross: 次港=東京だが東京の行は5日後 → 食い違いの可能性', cls(res, '2026-11-02', T, 'ウエステルダム') == '食い違いの可能性')
    check('cross: 同じ取得元の別の港は使わない → 材料なし', cls(res, '2026-10-27', T, 'ぱしふぃっくびいなす') == '材料なし')
    check('cross: 前港=東京なのに東京より前の日付 → 裏付けにせず、食い違いの可能性', cls(res, '2026-10-29', T, 'アマデア') == '食い違いの可能性')
    check('cross: 3日の開き → 材料なし', cls(res, '2026-10-30', T, 'クイーン・エリザベス') == '材料なし')
    check('cross: 中止の行は使わない → 材料なし', cls(res, '2026-10-31', T, 'ルミナーラ') == '材料なし')
    check('cross: 那覇（前港 Naha・大文字小文字） → 裏付けあり', cls(res, '2026-10-21', N, 'MSC BELLISSIMA') == '裏付けあり')
    check('cross: 那覇の表にない寄港 → 参考（orphans）に出る', any(o['ship'] == 'スター・ナビゲーター' for o in res['orphans']), res['orphans'])
    check('cross: 31日より先の行は数えない', cls(res, '2026-12-01', T, '遠い船') is None)
    c = res['counts'][T]
    check('cross: 件数の集計', c == {'裏付けあり': 3, '食い違いの可能性': 3, '材料なし': 4}, c)
    md = '\n'.join(checks.cross_md(res))
    check('cross: 報告に「証明ではありません」と食い違いの表', '証明ではありません' in md and 'ウエステルダム' in md and '鹿児島港 10/28' in md)
    check('cross: 名前の正規化 Ⅲ → 3', checks.name_key('飛鳥Ⅲ') == checks.name_key('飛鳥 III') == checks.name_key('飛鳥3'))
    check('cross: 前港・次港の書き方（東京港・Tokyo・東京(東京都)）', all(checks.names_port(x, checks.TARGETS['tokyo'][1]) for x in ('東京港', 'Tokyo', '東京(東京都)', 'TOKYO'))
          and not checks.names_port('東京湾クルーズ', checks.TARGETS['tokyo'][1]) and not checks.names_port('', checks.TARGETS['tokyo'][1]))


# ---------------------------------------------------------------- 2. 件数の急な変化・失敗
def rep_ok(n):
    return {'ok': True, 'rows': n, 'fetch': [{'url': 'u', 'status': 200, 'bytes': 1000, 'at': '2026-10-18T05:31:00'}]}


def up_rows(src, n, past=0):
    out = [R(src, 'X港', f's{i}', '2026-10-20') for i in range(n)]
    out += [R(src, 'X港', f'p{i}', '2026-01-01') for i in range(past)]
    return out


def test_counts():
    state = {'a': {'date': '2026-10-17', 'rows': 60, 'upcoming': 40}, 'b': {'date': '2026-10-17', 'rows': 60, 'upcoming': 40},
             'c': {'date': '2026-10-17', 'rows': 60, 'upcoming': 40}, 'd': {'date': '2026-10-17', 'rows': 20, 'upcoming': 10},
             'e': {'date': '2026-10-17', 'rows': 50, 'upcoming': 40}, 'f': {'date': '2026-10-17', 'rows': 50, 'upcoming': 40},
             'g': {'date': '2026-10-17', 'rows': 50, 'upcoming': 40}, 'h': {'date': '2026-10-17', 'rows': 50, 'upcoming': 5},
             'i': {'date': '2026-10-17', 'rows': 500, 'upcoming': 400}}
    report = {
        'a': rep_ok(30), 'b': rep_ok(52), 'c': rep_ok(45), 'd': rep_ok(15),
        'e': {'ok': False, 'error': "HTTPError('503 Server Error')", 'fetch': []},
        'f': {'ok': False, 'error': "ValueError('schedule PDF link not found')", 'fetch': [{'url': 'u', 'status': 200, 'bytes': 5000}]},
        'g': {'ok': True, 'rows': 0, 'fetch': [{'url': 'u', 'status': 200, 'bytes': 5000}]},
        'h': rep_ok(20), 'i': rep_ok(500), 'new': rep_ok(5),
    }
    rows = (up_rows('a', 26, 4) + up_rows('b', 52) + up_rows('c', 45) + up_rows('d', 5, 10)
            + up_rows('h', 0, 20) + up_rows('i', 330, 170) + up_rows('new', 5))
    th = {'default': {'pct': 0.30, 'abs': 10}, 'per_source': {'i': {'pct': 0.15, 'abs': 50}}}
    warns, new, firsts = checks.count_check(report, rows, TODAY, state, th)
    W = {w['src']: w['kind'] for w in warns}
    check('count: 40 → 26（-35%・-14） → 急な変化', W.get('a') == 'jump', warns)
    check('count: 40 → 52（+30%・+12） → 急な変化（増えたときも）', W.get('b') == 'jump')
    check('count: 40 → 45（+12%） → 知らせない', 'c' not in W)
    check('count: 10 → 5（-50% でも 5行だけ） → 知らせない', 'd' not in W)
    check('count: 取得に失敗（HTTPError） → fetch_ng', W.get('e') == 'fetch_ng')
    check('count: ページは取れたが読み取り失敗 → parse_ng', W.get('f') == 'parse_ng')
    check('count: ページは取れたが0行 → zero', W.get('g') == 'zero')
    check('count: これからの行が0に → zero_upcoming', W.get('h') == 'zero_upcoming')
    check('count: 取得元ごとのしきい値（i：400 → 330、-17.5%・-70）', W.get('i') == 'jump')
    check('count: 初めての取得元は知らせず記録だけ', 'new' not in W and firsts == ['new'] and new['new']['upcoming'] == 5)
    check('count: 失敗・0行のときは記録を変えない', new['e'] == state['e'] and new['f'] == state['f'] and new['g'] == state['g'])
    check('count: 成功したときは記録を更新', new['a'] == {'date': '2026-10-18', 'rows': 30, 'upcoming': 26})
    check('count: 元の state は書き換えない', state['a']['upcoming'] == 40)
    md = '\n'.join(checks.count_md(warns, firsts))
    check('count: 見出し「取得件数の急な変化・失敗」と「消していません」', '取得件数の急な変化・失敗' in md and '消していません' in md)
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, 'state', 'source_counts.json')
        checks.save_state(new, p)
        check('count: state を保存して読み直せる', checks.load_state(p) == new)
        check('count: state がなければ空', checks.load_state(os.path.join(tmp, 'none.json')) == {})
    finally:
        shutil.rmtree(tmp)


# ---------------------------------------------------------------- 3. 公式の更新日
def test_dates():
    tmp = tempfile.mkdtemp()
    try:
        def page(key, name, body):
            d = os.path.join(tmp, 'raw', key)
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, name), 'w', encoding='utf-8').write(body)
            return {'url': 'u', 'status': 200, 'bytes': len(body), 'saved': name, 'at': '2026-10-18T05:31:00'}
        H = '<html><body>{}</body></html>'
        report = {
            'yokohama': {'ok': True, 'fetch': [page('yokohama', 'a.html', H.format('横浜港客船入港予定 最終更新日 2026年10月6日 印刷する'))]},
            'kobe': {'ok': True, 'fetch': [page('kobe', 'a', H.format('<p>更新内容</p><p>2026.10.17 10/20「VIKING ORION」</p>'))]},
            'kochi': {'ok': True, 'fetch': [page('kochi', 'a', H.format('入港予定について （令和８年10月５日時点） 現在'))]},
            'tokushima': {'ok': True, 'fetch': [page('tokushima', 'a', H.format('【令和8（2026）年】 R8.9.2更新 No.'))]},
            'kanazawa': {'ok': True, 'fetch': [page('kanazawa', 'a', H.format('<!-- 2026年12月1日現在 古いお知らせ --> 2026年10月8日現在'))]},
            'sakata': {'ok': True, 'fetch': [page('sakata', 'a', H.format('更新日：2026年12月16日'))]},   # 未来の日付は使わない
            'beppu': {'ok': True, 'fetch': [page('beppu', 'a', H.format('日付の書いていないページ'))]},
            'tokyo': {'ok': True, 'fetch': [page('tokyo', 'a', H.format('最終更新日 2026年10月1日'))]},   # 規則がない取得元は不明
            'akita': {'ok': False, 'error': 'x', 'fetch': []},
        }
        r = checks.src_dates(tmp, report, TODAY)
        check('date: 横浜 最終更新日 → 2026-10-06', r['yokohama']['date'] == '2026-10-06', r['yokohama'])
        check('date: 神戸 更新内容 2026.10.17', r['kobe']['date'] == '2026-10-17', r['kobe'])
        check('date: 高知 全角の令和「…時点」', r['kochi']['date'] == '2026-10-05', r['kochi'])
        check('date: 徳島 R8.9.2更新', r['tokushima']['date'] == '2026-09-02', r['tokushima'])
        check('date: 金沢 HTML コメントの中の日付は使わない', r['kanazawa']['date'] == '2026-10-08', r['kanazawa'])
        check('date: 未来の日付 → 不明', r['sakata']['date'] == '', r['sakata'])
        check('date: 書いていない → 不明', r['beppu']['date'] == '')
        check('date: 東京（規則なし） → 不明', r['tokyo']['date'] == '')
        check('date: 取得に失敗した取得元 → 不明', r['akita']['date'] == '')
        labels = {k: k for k in report}
        md = '\n'.join(checks.sources_md(report, {}, r, labels))
        check('date: 表に「公式の更新日」「取得日」「不明」', '公式の更新日' in md and '取得日' in md and '| 不明 |' in md and '2026-10-18' in md)
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    for t in (test_cross, test_counts, test_dates):
        try:
            t()
        except Exception as e:
            import traceback
            traceback.print_exc()
            NG.append(t.__name__ + ' raised ' + repr(e))
    print(f'\nOK {len(OK)} / NG {len(NG)}')
    sys.exit(1 if NG else 0)
