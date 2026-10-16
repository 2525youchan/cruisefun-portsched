"""那覇港・石垣港・平良港（NACRU クルーズ船寄港予約システム。3 港共同、Salesforce Experience Cloud）。

公開ページ https://nacru.my.site.com/s/ はゲスト（ログインなし）で一覧を見せる SPA で、
ページ自身が POST /s/sfsites/aura を呼んで一覧を読み込んでいる。ここではその同じ読み取り用の呼び出し
（一覧ビューの一覧 getInitialListViews と、一覧の中身 ListViewDataManager.getItems）を requests で行う。
fwuid などの値は毎回トップページから取り直す（Salesforce の更新で変わるため）。

一覧ビューは「那覇港：2026年」のように港・年ごと。ビュー名（View2, X20261 …）は決め打ちせず、
ビューの一覧から「港：YYYY年」のラベルで選ぶ。今年以降の年のビューを読む（過去の年は実績なので読まない）。
取消の表示はない（取り消された申請は一覧から消えるとみられる）ので、status はすべて scheduled。
"""
import os, re, json, hashlib, datetime
import urllib.parse as up
import requests
import common

PORT = '那覇港'
BASE = 'https://nacru.my.site.com'
TOP = BASE + '/s/'
AURA = BASE + '/s/sfsites/aura'
ENTITY = 'NHCR_ApplicationPublic__c'
# ビューの港名 → サイトの港名、運航経路での書き方
PORTS = {
    '那覇港': ('那覇港', ('那覇', '沖縄', 'naha', 'okinawa')),
    '石垣港': ('石垣島', ('石垣', 'ishigaki')),
    '平良港': ('平良港（宮古島）', ('平良', '宮古', '宮古島', 'hirara', 'miyako', 'miyakojima', 'miyakozima')),
}
FIRST_YEAR = common.TODAY.year  # これより前の年のビューは読まない
PAGE = 500


class _Aura:
    def __init__(self, ctx):
        self.ctx = ctx
        self.s = requests.Session()
        self.s.headers['User-Agent'] = common.UA
        html = ctx.get(TOP)
        m = re.search(r'/s/sfsites/l/(%7B[^/"\']*?fwuid[^/"\']*?)/', html)
        if not m:
            raise RuntimeError('NACRU: トップページから aura の設定（fwuid）が読めません')
        cfg = json.loads(up.unquote(m.group(1)))
        self.context = {'mode': cfg.get('mode', 'PROD'), 'fwuid': cfg['fwuid'], 'app': cfg.get('app', 'siteforce:communityApp'),
                        'loaded': cfg.get('loaded', {}), 'dn': [], 'globals': {}, 'uad': False}
        self.n = 0

    def call(self, descriptor, params, retry=True):
        self.n += 1
        short = descriptor.split('/ACTION$')[0].rsplit('.', 1)[-1].replace('Controller', '') + '.' + descriptor.rsplit('$', 1)[-1]
        msg = {'actions': [{'id': '%d;a' % self.n, 'descriptor': descriptor, 'callingDescriptor': 'UNKNOWN', 'params': params}]}
        url = AURA + '?r=%d&%s=1' % (self.n, short)
        r = self.s.post(url, data={'message': json.dumps(msg), 'aura.context': json.dumps(self.context),
                                   'aura.pageURI': '/s/', 'aura.token': 'null'}, timeout=60)
        body = r.content
        name = 'aura_%02d_%s.json' % (self.n, re.sub(r'[^A-Za-z0-9]', '_', str(params.get('filterName', short)))[:40])
        with open(os.path.join(self.ctx.dir, name), 'wb') as f:
            f.write(body)
        self.ctx.log.append({'url': url, 'method': 'POST', 'params': params, 'status': r.status_code, 'bytes': len(body),
                             'sha256': hashlib.sha256(body).hexdigest(), 'saved': name,
                             'at': datetime.datetime.now().isoformat(timespec='seconds')})
        text = r.text
        if 'clientOutOfSync' in text and retry:
            m = re.search(r'"fwuid"\s*:\s*"([^"]+)"', text)
            if m:
                self.context['fwuid'] = m.group(1)
                return self.call(descriptor, params, retry=False)
        r.raise_for_status()
        text = text[text.find('{'):]
        d = json.loads(text)
        a = d['actions'][0]
        if a.get('state') != 'SUCCESS':
            raise RuntimeError('NACRU: aura の呼び出しが失敗: %s %s' % (a.get('state'), json.dumps(a.get('error'), ensure_ascii=False)[:300]))
        return a.get('returnValue') or {}, d


def _views(au):
    rv, _ = au.call('serviceComponent://ui.force.components.controllers.lists.listViewPickerDataProvider.'
                    'ListViewPickerDataProviderController/ACTION$getInitialListViews',
                    {'scope': ENTITY, 'maxMruResults': 10, 'maxAllResults': 500})
    out = []
    for v in rv.get('listViews', []):
        m = re.match(r'^\s*(\S+港)\s*[:：]\s*(\d{4})年\s*$', common.z2h(v.get('label', '')).replace(':', '：'))
        if m and m.group(1) in PORTS and int(m.group(2)) >= FIRST_YEAR:
            out.append((m.group(1), int(m.group(2)), v['name'], v.get('label')))
    if not out:
        raise RuntimeError('NACRU: 「港：YYYY年」の一覧ビューが見つかりません: %r' % [v.get('label') for v in rv.get('listViews', [])])
    return out


def _items(au, view):
    recs, offset = [], 0
    while True:
        rv, d = au.call('serviceComponent://ui.force.components.controllers.lists.listViewDataManager.'
                        'ListViewDataManagerController/ACTION$getItems',
                        {'filterName': view, 'entityName': ENTITY, 'pageSize': PAGE, 'layoutType': 'LIST',
                         'sortBy': None, 'getCount': True, 'enableRowActions': False, 'offset': offset})
        store = {}
        for g in d.get('context', {}).get('globalValueProviders', []):
            if g.get('type') == '$Record':
                store = g.get('values', {}).get('records', {})
        ids = [x['recordId'] for x in rv.get('recordIdActionsList', [])]
        for i in ids:
            rec = store.get(i, {}).get(ENTITY, {}).get('record')
            if rec:
                recs.append(rec)
            else:
                raise RuntimeError('NACRU: 一覧の行のデータがありません: %s %s' % (view, i))
        if not rv.get('hasMoreData') or not ids:
            return recs
        offset += len(ids)


def _val(rec, f):
    v = rec.get('fields', {}).get(f, {})
    return v.get('value') if v.get('value') is not None else (v.get('displayValue') or '')


def _dt(s):
    m = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})', s or '')
    if not m:
        return '', ''
    return common.ymd(*m.groups()), common.hhmm(s[m.end():].split(')')[-1])


def _prev_next(route, names):
    """運航経路（例 '基隆-那覇-石垣-基隆'、'上海―那覇ー江汀ー上海'）から前後の港"""
    t = common.z2h(route or '')
    # 区切り: ハイフン類。長音「ー」は前後がカタカナでないときだけ区切りとみなす（ホーチミン などを割らない）
    parts = re.split(r'\s*(?:[-－‐―‑–—~～]|(?<![ァ-ヴ])ー|ー(?![ァ-ヴ]))\s*', t)
    parts = [p.strip() for p in parts if p.strip()]
    key = lambda p: re.sub(r'\s+', '', p).lower().rstrip('港')
    idx = [i for i, p in enumerate(parts) if key(p) in names]
    if not idx:
        return '', ''
    inner = [i for i in idx if 0 < i < len(parts) - 1]
    i = inner[0] if inner else idx[0]
    return (parts[i - 1] if i > 0 else ''), (parts[i + 1] if i + 1 < len(parts) else '')


def fetch(ctx):
    au = _Aura(ctx)
    rows, seen = [], set()
    for vport, year, view, label in _views(au):
        port, names = PORTS[vport]
        for rec in _items(au, view):
            rid = rec.get('id') or _val(rec, 'Id')
            if (port, rid) in seen:
                continue
            seen.add((port, rid))
            sin, sout = str(_val(rec, 'NHCR_AppPub_InDateTimeDisplay__c')), str(_val(rec, 'NHCR_AppPub_OutDateTimeDisplay__c'))
            d, tin = _dt(sin)
            e, tout = _dt(sout)
            if not d:
                continue
            route = str(_val(rec, 'NHCR_AppPub_FlightRoute__c') or '')
            prev, nxt = _prev_next(route, names)
            ship = re.sub(r'\s+', ' ', common.z2h(str(_val(rec, 'NHCR_AppPub_ShipName__c')))).strip()
            note = []
            if _val(rec, 'NHCR_AppPub_OverNightdisplay__c') is True:
                note.append('OverNight')
            raw = ' | '.join(str(x) for x in (_val(rec, 'Name'), ship, sin, sout, _val(rec, 'NHCR_AppPub_Berth__c'), route,
                                              _val(rec, 'NHCR_AppPub_Capacity__c'), _val(rec, 'NHCR_AppPub_AccountText__c'),
                                              'view=' + str(label)))
            rows.append(common.row(date=d, end=e or d, port=port, ship=ship, **{'in': tin, 'out': tout},
                                   berth=common.z2h(str(_val(rec, 'NHCR_AppPub_Berth__c') or '')).strip(),
                                   prev=prev, next=nxt, note=' / '.join(note),
                                   source=TOP + '?%s-filterId=%s' % (ENTITY, view), raw=raw))
    return rows
