"""全港（または指定した港）の公式入港予定を取得して、1つの JSON にまとめる。

使い方:
    python -I run.py OUTDIR [port_key ...]
    例: python -I run.py ../../tools/data/portsched/20261016

OUTDIR/rows.json   すべての行
OUTDIR/report.json 港ごとの結果（行数・期間・エラー・取得記録）
OUTDIR/raw/<港>/   取得した元ファイル
"""
import sys, os, importlib, traceback, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
sys.stdout.reconfigure(encoding='utf-8')

PORTS = [
    'yokohama', 'tokyo', 'shimizu', 'osaka', 'kobe', 'kanazawa', 'sakaiminato', 'niigata',
    'nagasaki', 'hakata', 'kagoshima', 'hiroshima', 'kochi', 'sasebo', 'matsuyama', 'hososhima',
    'nacru', 'hakodate', 'aomori', 'akita', 'sakata', 'miyako',
    'aburatsu', 'miyazaki', 'beppu', 'tokushima',
]


def main():
    out = sys.argv[1]
    keys = sys.argv[2:] or PORTS
    rows, report = [], {}
    for k in keys:
        t0 = datetime.datetime.now()
        ctx = common.Ctx(out, k)
        try:
            mod = importlib.import_module('ports.' + k)
            got = mod.fetch(ctx)
            for r in got:
                r['src_key'] = k
            rows += got
            ds = sorted(r['date'] for r in got if r['date'])
            report[k] = {'ok': True, 'rows': len(got), 'from': ds[0] if ds else '', 'to': ds[-1] if ds else '',
                         'ports': sorted({r['port'] for r in got}), 'fetch': ctx.log}
        except Exception as e:
            report[k] = {'ok': False, 'error': repr(e), 'trace': traceback.format_exc()[-1500:], 'fetch': ctx.log}
        report[k]['sec'] = round((datetime.datetime.now() - t0).total_seconds(), 1)
        print(k, 'OK' if report[k]['ok'] else 'NG', report[k].get('rows', report[k].get('error')))
    common.save_json(os.path.join(out, 'rows.json'), rows)
    common.save_json(os.path.join(out, 'report.json'), report)


if __name__ == '__main__':
    main()
