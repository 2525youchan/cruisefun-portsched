"""各港の公式入港予定を読み取るための共通部品。

港ごとのモジュール（ports/xxx.py）は、次の2つを持つ:
    PORT = '横浜港'            # サイト（WEB CRUISE）と同じ港の名前
    def fetch(ctx) -> list[dict]  # 公表されている全期間の行を返す

1行（dict）の形:
    date     'YYYY-MM-DD'（2日以上にまたがる寄港は、入港日の行にまとめ、end に出港日）
    end      'YYYY-MM-DD'（出港日。同じ日なら date と同じ）
    port     サイトの港の名前（例 '横浜港'。同じ資料に別の港があれば、その港の名前）
    ship     公式資料の船名のまま（英語ならそのまま。対応表は別に作る）
    in       'HH:MM' か ''（不明）
    out      'HH:MM' か ''
    berth    岸壁（なければ ''）
    prev     前の港（なければ ''）
    next     次の港（なければ ''）
    status   'scheduled' / 'cancelled'（資料に中止・抜港と書いてあるもの）
    note     備考（初入港・時刻変更など、資料の文のまま）
    source   取得元の URL（PDF ならその PDF の URL）
    raw      資料の元の行（確認用。長ければ 300 文字まで）
"""
import os, re, json, time, hashlib, datetime, subprocess, unicodedata
import requests

UA = 'Mozilla/5.0 (cruisefun.jp arrival schedule; info@cruisefun.jp)'
TODAY = datetime.date.today()


class Ctx:
    """取得の記録（元ファイルの保存先など）"""

    def __init__(self, outdir, port_key):
        self.dir = os.path.join(outdir, 'raw', port_key)
        os.makedirs(self.dir, exist_ok=True)
        self.log = []

    def get(self, url, binary=False, **kw):
        h = kw.pop('headers', {})
        h.setdefault('User-Agent', UA)
        r = requests.get(url, headers=h, timeout=60, **kw)
        r.raise_for_status()
        body = r.content
        name = hashlib.sha1(url.encode()).hexdigest()[:10] + '_' + re.sub(r'[^A-Za-z0-9._-]', '_', url.rsplit('/', 1)[-1] or 'index')[:60]
        with open(os.path.join(self.dir, name), 'wb') as f:
            f.write(body)
        self.log.append({'url': url, 'status': r.status_code, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'saved': name, 'at': datetime.datetime.now().isoformat(timespec='seconds')})
        if binary:
            return body
        r.encoding = r.apparent_encoding if (r.encoding or '').lower() in ('iso-8859-1', '') else r.encoding
        return r.text

    def pdf_text(self, url, raw=True, layout=False):
        """PDF を取得して pdftotext で文字にする（raw=True で -raw）"""
        body = self.get(url, binary=True)
        p = os.path.join(self.dir, hashlib.sha1(url.encode()).hexdigest()[:10] + '.pdf')
        with open(p, 'wb') as f:
            f.write(body)
        args = ['pdftotext', '-enc', 'UTF-8']
        if raw:
            args.append('-raw')
        if layout:
            args.append('-layout')
        out = subprocess.run(args + [p, '-'], capture_output=True, check=True).stdout.decode('utf-8', 'replace')
        return out


def z2h(s):
    """全角英数字・記号を半角に（NFKC）。ローマ数字Ⅱ・Ⅲは残す"""
    keep = {'Ⅱ': '\0II\0', 'Ⅲ': '\0III\0', 'Ⅰ': '\0I\0'}
    for k, v in keep.items():
        s = s.replace(k, v)
    s = unicodedata.normalize('NFKC', s)
    for k, v in keep.items():
        s = s.replace(unicodedata.normalize('NFKC', v), k)
    # PDF に出る部首の文字・旧字（⻑ ⼾→戶）を普通の漢字に
    s = s.replace('⻑', '長').replace('戶', '戸')
    return s.replace('\0', '')


def hhmm(s):
    """'8:00' '８：００' '7時' '12時30分' '翌8:50' → 'HH:MM'。読めなければ ''"""
    if not s:
        return ''
    s = z2h(str(s)).strip()
    m = re.search(r'(\d{1,2})\s*[:時]\s*(\d{1,2})?', s)
    if not m:
        return ''
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        return ''
    return f'{h:02d}:{mi:02d}'


def ymd(y, m, d):
    return datetime.date(int(y), int(m), int(d)).isoformat()


def guess_year(m, d, base=None):
    """年の書いていない月日に年を補う。今日から見て 3 か月より前なら翌年とみなす"""
    base = base or TODAY
    y = base.year
    try:
        dt = datetime.date(y, int(m), int(d))
    except ValueError:  # 2月29日：次のうるう年
        for yy in range(y + 1, y + 5):
            try:
                return datetime.date(yy, int(m), int(d)).isoformat()
            except ValueError:
                pass
        raise
    if (base - dt).days > 90:
        dt = datetime.date(y + 1, int(m), int(d))
    return dt.isoformat()


def fiscal_year_date(fy, m, d):
    """年度（4月〜翌3月）の表の月日 → 日付"""
    y = int(fy) + (1 if int(m) <= 3 else 0)
    return ymd(y, m, d)


def row(**kw):
    r = {'date': '', 'end': '', 'port': '', 'ship': '', 'in': '', 'out': '', 'berth': '', 'prev': '', 'next': '',
         'status': 'scheduled', 'note': '', 'source': '', 'raw': ''}
    r.update({k: (v if v is not None else '') for k, v in kw.items()})
    if not r['end']:
        r['end'] = r['date']
    r['raw'] = str(r['raw'])[:300]
    return r


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
