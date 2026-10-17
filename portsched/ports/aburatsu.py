"""油津港（宮崎県 県土整備部 港湾課／宮崎県ポートセールス協議会）

細島港と同じページ・同じ形の PDF（見出し「油津港」の下の「寄港スケジュール」）。読み取りは ports/hososhima.py を使う。
"""
from ports import hososhima

PORT = '油津港'
LANDING = hososhima.LANDING


def fetch(ctx):
    return hososhima.fetch(ctx, PORT)
