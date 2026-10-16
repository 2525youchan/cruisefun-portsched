"""東京港（東京都 港湾局）クルーズ客船入港予定カレンダー（Power BI 公開レポート）

港湾局ページ https://www.kouwan.metro.tokyo.lg.jp/kanko/cruise の「客船入港予定（PowerBI WEB版）」
のリンク（app.powerbi.com/view?r=...）からリソースキーを取り出し、ブラウザ表示と同じ公開 API
（modelsAndExploration → querydata）でデータを読む。ログイン不要・読み取りのみ。

同じデータに伊豆・小笠原諸島の港（二見港・八丈島 など）が入っているので、
東京国際クルーズターミナル / 晴海客船ターミナル → 港 '東京港'（岸壁にターミナル名）、
それ以外 → 港名のまま（例 '二見港'）とする。
"""
import re, json, base64, hashlib, datetime, os
import requests
from bs4 import BeautifulSoup
import common

PORT = '東京港'
PAGE = 'https://www.kouwan.metro.tokyo.lg.jp/kanko/cruise'
FALLBACK_KEY = 'd715d5a6-c629-4e37-ba97-2ced1fcf68a6'
FALLBACK_VIEW = 'https://app.powerbi.com/view?r=eyJrIjoiZDcxNWQ1YTYtYzYyOS00ZTM3LWJhOTctMmNlZDFmY2Y2OGE2IiwidCI6ImQwMzAyZmNjLTNlODEtNDljMy04MjM1LWQzMTFhMzY4NGNmYyJ9'
API = 'https://wabi-japan-east-api.analysis.windows.net'
TOKYO_TERMINALS = ('東京国際クルーズターミナル', '晴海客船ターミナル', '晴海ふ頭', '竹芝客船ターミナル', '日の出ふ頭', '大井ふ頭', '青海ふ頭', '有明ふ頭', '東京港')
COLS = [('t', '到着日'), ('t', '到着時刻'), ('t', '出発日'), ('t', '出発時刻'), ('t', '港名'), ('t', '前港'), ('t', '次港'),
        ('t', '備考１'), ('t1', '客船名_日本語')]


def _resource_key(ctx):
    try:
        html = ctx.get(PAGE)
    except Exception:
        return FALLBACK_KEY, FALLBACK_VIEW
    soup = BeautifulSoup(html, 'html.parser')
    cands = []
    for a in soup.find_all(['a', 'iframe']):
        u = a.get('href') or a.get('src') or ''
        m = re.search(r'app\.powerbi\.com/view\?r=([A-Za-z0-9_=%-]+)', u)
        if not m:
            continue
        txt = a.get_text(strip=True) + ' ' + (a.get('title') or '')
        score = ('入港予定' in txt) * 2 + ('WEB' in txt.upper()) - ('実績' in txt) * 5
        cands.append((score, m.group(1)))
    for _, r in sorted(cands, key=lambda x: -x[0]):
        try:
            r = r.replace('%3D', '=')
            d = json.loads(base64.b64decode(r + '=' * (-len(r) % 4)))
            if re.fullmatch(r'[0-9a-f-]{36}', d.get('k', '')):
                return d['k'], 'https://app.powerbi.com/view?r=' + r
        except Exception:
            continue
    return FALLBACK_KEY, FALLBACK_VIEW


def _save(ctx, url, body, status):
    name = hashlib.sha1((url + str(len(ctx.log))).encode()).hexdigest()[:10] + '_querydata.json'
    with open(os.path.join(ctx.dir, name), 'wb') as f:
        f.write(body)
    ctx.log.append({'url': url, 'method': 'POST', 'status': status, 'bytes': len(body),
                    'sha256': hashlib.sha256(body).hexdigest(), 'saved': name,
                    'at': datetime.datetime.now().isoformat(timespec='seconds')})


def _decode_dsr(res):
    """Power BI の圧縮 DSR 形式を行の list に展開する"""
    data = res['results'][0]['result']['data']
    ds = data['dsr']['DS'][0]
    vd = ds.get('ValueDicts', {})
    dm = ds['PH'][0]['DM0']
    n = len(data['descriptor']['Select'])
    schema = None
    prev = [None] * n
    out = []
    for item in dm:
        if 'S' in item:
            schema = item['S']
        c = item.get('C', [])
        rep, nul = item.get('R', 0), item.get('Ø', 0)
        cur, ci = [], 0
        for i in range(n):
            if rep >> i & 1:
                cur.append(prev[i])
            elif nul >> i & 1:
                cur.append(None)
            else:
                cur.append(c[ci] if ci < len(c) else None)
                ci += 1
        prev = cur
        rec = []
        for i, v in enumerate(cur):
            s = schema[i] if schema and i < len(schema) else {}
            if s.get('DN') and isinstance(v, int):
                v = vd[s['DN']][v]
            if s.get('T') == 7 and isinstance(v, (int, float)):
                v = (datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=v)).strftime('%Y-%m-%d %H:%M')
            rec.append(v)
        out.append(rec)
    return out


def _time(v):
    if not v:
        return ''
    m = re.search(r'[T ](\d{2}):(\d{2})', str(v))
    return f'{m.group(1)}:{m.group(2)}' if m else common.hhmm(v)


def _date(v):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(v or ''))
    return f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else ''


def fetch(ctx):
    key, view = _resource_key(ctx)
    hdr = {'X-PowerBI-ResourceKey': key, 'User-Agent': common.UA}
    mae = json.loads(ctx.get(f'{API}/public/reports/{key}/modelsAndExploration?preferReadOnlySession=true', headers=dict(hdr)))
    model = mae['models'][0]
    report_id = mae['exploration']['report']['objectId']
    sel = [{'Column': {'Expression': {'SourceRef': {'Source': s}}, 'Property': p}, 'Name': f'x{i}'} for i, (s, p) in enumerate(COLS)]
    q = {'Version': 2,
         'From': [{'Name': 't', 'Entity': 'T03_入港スケジュール', 'Type': 0}, {'Name': 't1', 'Entity': 'T02_船マスタ (2)', 'Type': 0}],
         'Select': sel,
         'OrderBy': [{'Direction': 1, 'Expression': {'Column': {'Expression': {'SourceRef': {'Source': 't'}}, 'Property': '到着日'}}}]}
    body = {'version': '1.0.0', 'queries': [{'Query': {'Commands': [{'SemanticQueryDataShapeCommand': {
        'Query': q, 'Binding': {'Primary': {'Groupings': [{'Projections': list(range(len(COLS)))}]},
                                'DataReduction': {'DataVolume': 3, 'Primary': {'Window': {'Count': 5000}}}, 'Version': 1}}}]},
        'QueryId': '', 'ApplicationContext': {'DatasetId': model['dbName'], 'Sources': [{'ReportId': report_id}]}}],
        'cancelQueries': [], 'modelId': model['id']}
    url = f'{API}/public/reports/querydata?synchronous=true'
    r = requests.post(url, data=json.dumps(body).encode(), headers=dict(hdr, **{'Content-Type': 'application/json'}), timeout=60)
    _save(ctx, url, r.content, r.status_code)
    r.raise_for_status()
    recs = _decode_dsr(r.json())
    rows, seen = [], set()
    for rec in recs:
        ad, at, dd, dt, pname, prev, nxt, note, ship = (rec + [None] * 9)[:9]
        date = _date(ad)
        if not date or not ship:
            continue
        pname = (pname or '').strip()
        if any(pname.startswith(t) for t in TOKYO_TERMINALS):
            port, berth = PORT, pname
        else:
            port, berth = pname, ''
        note = (note or '').strip()
        status = 'cancelled' if re.search(r'中止|抜港|キャンセル|取りやめ|取止', note) else 'scheduled'
        ship = str(ship).strip()
        # 船名に（初入港）等が付いていれば備考へ
        m = re.search(r'[（(【]([^）)】]*)[）)】]\s*$', ship)
        if m and re.search(r'初|中止|変更', m.group(1)):
            note = ' / '.join(x for x in (m.group(1), note) if x)
            ship = ship[:m.start()].strip()
        k = (port, date, ship, _time(at))
        if k in seen:
            ctx.log.append({'dup_skipped': k})
            continue
        seen.add(k)
        un = lambda x: '' if (x or '').strip() in ('未定', '-', '－') else (x or '').strip()
        rows.append(common.row(date=date, end=_date(dd) or date, port=port, ship=ship, **{'in': _time(at), 'out': _time(dt)},
                               berth=berth, prev=un(prev), next=un(nxt), status=status, note=note, source=view,
                               raw=json.dumps(rec, ensure_ascii=False)))
    return rows
