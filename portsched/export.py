"""照合した一覧（month_YYYY-MM.json）から、管理画面「公式の入港予定」に貼る JSON を作る。

使い方:
    python -I export.py OUTDIR YYYY-MM [YYYY-MM ...] > import.json
    中止の行は入れない。港・船の名前はサイトのページの名前にそろえる（ページがなければ資料のまま）。
"""
import sys, os, json, datetime
sys.stdout.reconfigure(encoding='utf-8')

# 取得元 → 出典の名前と、人が見るための案内ページ（PDF の URL は毎回変わるので使わない）
SOURCES = {
    'yokohama': ('横浜市「横浜港 客船入港予定」', 'https://www.city.yokohama.lg.jp/kanko-bunka/minato/kyakusen/nyuko/'),
    'tokyo': ('東京都港湾局「クルーズ客船入港予定」', 'https://www.kouwan.metro.tokyo.lg.jp/kanko/cruise'),
    'shimizu': ('清水港客船誘致委員会「客船寄港予定」', 'https://www.shimizu-port.jp/'),
    'osaka': ('大阪港振興協会「客船入港予定」', 'https://www.oppa.or.jp/calender.html'),
    'kobe': ('神戸観光局「客船入港予定」', 'https://www.kobe-meriken.or.jp/terminal/eta/'),
    'kanazawa': ('金沢港振興協会「クルーズ客船寄港予定」', 'https://www.k-port.jp/cruise/'),
    'sakaiminato': ('境夢みなとターミナル「客船寄港予定」', 'https://www.sakai-tottori.jp/archives/xo_event_cat/pcs'),
    'niigata': ('新潟県「クルーズ船寄港予定」', 'https://www.pref.niigata.lg.jp/site/kowanshinko/'),
    'nagasaki': ('長崎県「長崎港クルーズ客船寄港実績および予定」', 'https://nagasaki-port.jp/cruiseschedule.html'),
    'hakata': ('福岡市「博多港クルーズ船寄港予定」', 'https://www.city.fukuoka.lg.jp/kowan/k-kikaku/hakata-port/cruise1.html'),
    'kagoshima': ('鹿児島県「鹿児島港クルーズ船寄港予定」', 'https://www.pref.kagoshima.jp/ah09/infra/port/minato/cruising/kagoshimakour8yotei.html'),
    'hiroshima': ('広島県「広島港客船入港予定」', 'https://www.pref.hiroshima.lg.jp/soshiki/221/cruise-joho.html'),
    'kochi': ('高知県「高知県のクルーズ客船寄港予定」', 'https://www.pref.kochi.lg.jp/doc/kochi_cruise/'),
    'sasebo': ('長崎県観光連盟「佐世保港 クルーズ客船寄港予定」', 'https://www.nagasaki-tabinet.com/houjin/report/cruise-achievement/'),
    'matsuyama': ('愛媛県「クルーズ船寄港予定」', 'https://www.pref.ehime.jp/page/1074.html'),
    'hososhima': ('宮崎県「細島港 クルーズ船寄港スケジュール」', 'https://www.pref.miyazaki.lg.jp/kowan/kurashi/shakaikiban/m-port/cruise/20251212151322.html'),
    'hakodate': ('函館市「クルーズ客船入港予定」', 'https://www.city.hakodate.hokkaido.jp/docs/2026030900040/'),
    'aomori': ('青森県「クルーズ船寄港予定」', 'https://www.pref.aomori.lg.jp/soshiki/kendo/kowan/2023-aomori-cruise.html'),
    'akita': ('秋田県「クルーズ船寄港予定」', 'https://www.pref.akita.lg.jp/pages/genre/95116'),
    'sakata': ('酒田市「クルーズ船寄港予定」', 'https://www.city.sakata.lg.jp/sangyo/kotsu/kouwan/shoko0320191023.html'),
    'miyako': ('宮古市「クルーズ船寄港予定」', 'https://www.city.miyako.iwate.jp/gyosei/soshiki/kanko/1_1/'),
}
# NACRU（3港共同）は港ごとの案内ページ
NACRU = {
    '那覇港': ('那覇港管理組合「クルーズ船寄港予定」', 'https://nahaport.jp/users/kyakusen/'),
    '石垣港': ('石垣市「クルーズ船寄港予定」', 'https://www.city.ishigaki.okinawa.jp/soshiki/kowan/kuruzusenn/370.html'),
    '宮古島・平良港': ('宮古島市「クルーズ船寄港予定」', 'https://www.city.miyakojima.lg.jp/soshiki/shityo/kensetsu/kouwan/oshirase/2024-0222-0902-121.html'),
}


def main():
    out, months = sys.argv[1], sys.argv[2:]
    rep = json.load(open(os.path.join(out, 'report.json'), encoding='utf-8'))
    rows, seen = [], set()
    for m in months:
        for i in json.load(open(os.path.join(out, f'month_{m}.json'), encoding='utf-8')):
            if i['status'] == 'cancelled':
                continue
            port = i['site_port'] or i['port']
            ship = i['site_ship'] or i['ship']
            k = (i['date'], port, ship)
            if k in seen:
                continue
            seen.add(k)
            t, u = NACRU[port] if i['src_key'] == 'nacru' else SOURCES[i['src_key']]
            at = min((f['at'] for f in rep[i['src_key']]['fetch']), default=datetime.datetime.now().isoformat())
            rows.append({'date': i['date'], 'end': i['end'], 'port': port, 'ship': ship, 'in': i['in'], 'out': i['out'],
                         'berth': i['berth'][:60], 'source_title': t, 'source_url': u, 'checked': at[:10]})
    rows.sort(key=lambda r: (r['date'], r['port'], r['in']))
    json.dump({'imported': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'months': months, 'rows': rows},
              sys.stdout, ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
