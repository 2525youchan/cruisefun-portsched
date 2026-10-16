# cruisefun-portsched

cruisefun.jp の「入港予定」のために、各港の公式の予定表（22か所）を GitHub Actions で自動取得する仕組みです。
**サイトには何も書き込みません。** 違いや取り込み案を Issue で知らせ、反映はオーナーの承認のあと管理画面で行います。

## 動き

| いつ | 何をする | 知らせ方 |
|---|---|---|
| 毎朝 5:30（日本時間） | 公式の予定表を取得し、サイトの港ページの表示（30日以内）と比べる | 違いが前の日から変わったときだけ Issue「入港予定の違い YYYY-MM-DD」 |
| 毎月20日 6:00 | 来月分の一覧と、取り込み案を作る | Issue「来月の入港予定 YYYY-MM」 |
| 取得に失敗したとき | 実行が失敗になる／Issue の「取得できなかったもの」に出る | GitHub からメール |

- 結果は `proposals/日付/` に残ります（`daily.md` 報告、`import.json` 取り込み案、`report.json` 港ごとの取得結果）。
- 取得した元ファイル（PDF など）は、実行の記録（Actions）に14日だけ残ります。
- 「ツール ＞ 公式の入港予定」は一覧を丸ごと置き換える作りなので、取り込み案は「今日〜92日後」の全件です。

## 反映（承認のあと）
1. Issue の違いを確かめる（Claude に「この Issue の違いを判断して」と頼める）。
2. 取り込み案 `import.json` を「ツール ＞ 公式の入港予定」に貼り、確認だけ → 保存（手動モード・バックアップのあと）。
3. 公式にないのにサイトに出ているもの（中止の候補）は「ツール ＞ 入港予定の変更」で寄港中止にする。
4. 関係するページのキャッシュを削除する。

## オーナーが決めたこと（次から知らせない）
`config/decisions.json` に入れます。

- `official`：公式の行を取り込まない（例：仮の予約に見える行）
- `site_only`：公式にないがサイトに残す（例：その港の公式表に載らない船）
- `time`：時刻の違いを出さない（例：公式表が古い港）

## 手元で動かす
```
pip install -r requirements.txt
python -I portsched/daily.py work
```
PDF の読み取りに pdftotext（Git for Windows に入っている版）を使います。Actions も同じものを使うため Windows で動かしています。

## ファイル
- `portsched/run.py`：22か所を取得して `rows.json`・`report.json` を作る
- `portsched/ports/*.py`：港ごとの読み取り
- `portsched/daily.py`：サイトの表示と比べて報告と取り込み案を作る
- `portsched/compare.py`：ある月の一覧を作る
- `portsched/export.py`：取得元の名前と URL（`SOURCES`・`NACRU`）
