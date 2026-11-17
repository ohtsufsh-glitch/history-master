# Issue #114 最高得点一覧の検証

基準main: aad39e4（PR #124反映済み）。APP_VERSION v1.7.40 → v1.7.41。
独立したChromium contextの合成IndexedDBのみ使用。Safari実機未確認。

一覧だけ最大500px。dt/ddを1組ずつdivで包み、行背景・枠・上下10pxの余白で対応を明確にした。得点は右揃え・等幅数字。名前はモデルの正式名称を維持（現行モデルでは「なまけもの」）。選択行は緑の背景・左アクセントと独立した「選択中」バッジ。dlの意味・名前→選択中→得点の読み上げ順を維持する。

## 比較（CSS px）

同じ金魚・100点の文字Rangeを測定。距離は名前の文字末尾から得点文字の先頭まで（バッジ部分を含む空間）。名前と得点の列間gapそのものではない。

|画面|一覧幅 前→後|名前と得点の距離 前→後|
|---|---|---|
|1180×820|812 → 500|696.39 → 397.66|
|1024×768|812 → 500|696.39 → 397.66|
|820×1180|712 → 500|596.39 → 397.66|
|390×844|298 → 298|182.39 → 195.66|

iPhoneは一覧幅を維持し、左右の内側余白・太字・名前からの記号除去により文字間距離は約13px増加。全4サイズで横スクロール・dt/dd内部のはみ出しなし。画像は一覧section全体の切り出し（全ステージを展開）。

- [iPad前](before-1180x820.png) / [iPad後](after-1180x820.png)
- [iPhone前](before-390x844.png) / [iPhone後](after-390x844.png)
- 実測: [before.json](before.json) / [after.json](after.json)

## 検証

- 新規UI 2件成功: 上記4サイズ、0点/100点/記録なし、キャラ選択3回、アクセシビリティツリーの「名前 選択中」、dt→dd順、S02切替、student/test分離、未所持シークレット非表示、Enter/Spaceで全ステージ開閉。
- 既存runner_results_testの3件成功: test_stage_character_records_and_strict_improvements / test_committed_result_retry_single_charge_and_home / test_refresh_records_secret_reset_and_other_profile。
- home_arcade_test.HomeArcadeTest.test_layout成功（既存7サイズ、PR #124の配置維持）。
- app_version_test 9件成功。親inline JS・runner/game.js構文、git diff --check成功。
- 初回のfixtureは保存上限100点を超えて検証に失敗。100点/70点へ修正。選択操作もhidden selectから実際のキャラクターカードへ修正し、最終成功。

再現: `RECORDS_OUTPUT=/tmp/records-114 PYTHONPATH=tests python3 -m unittest -v runner_records_ui_test.RunnerRecordsUITest`。
画像の更新には `RECORDS_OUTPUT=docs/records-114` を指定。前画像は基準mainの配信ファイルに対し `RECORDS_PHASE=before` で配置テストのみ実行。

保存集計・DB/バックアップ/問題JSON/snapshot版・料金・解放条件・Canvas/操作/スクロール・ホームCSSは変更しない。全ステージ攻略・フル回帰は対象外。#117の下部空白改善には着手していない。

公開前レビュー時にiPad/iPhone Safari実機で、回転・文字拡大時の折返し、タッチによる選択と開閉、VoiceOverのdl読み上げと選択状態、一覧までのスクロールと下部の余白を確認すること。
