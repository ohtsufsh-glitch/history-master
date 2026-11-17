Closes #111

## 変更内容・ファイル
最新main `c3a4ffe`（PR #121/#122/#123マージ済み、v1.7.39）から `feat/111-home-arcade-grid` を作成。開始時・PR前fetchで同じmain、同目的の進行中PRなしを確認。

- `index.html`：2カードをDOM順のまま共通gridで包み、幅1000px以上・高さ600px以上・横向きで2列/16px間隔。ホーム表示中だけmain最大幅1120px。現行は後段CSSにより740ではなく920px。カードは自然高の等高、ボタン下端を揃える。背景・画像・料金・文字サイズ・ボタンを維持し、2列時の内側余白を20→16pxへ調整。
- `refreshRunnerHome`：既存runnerLobbyDataのfinished履歴からclearのstageIdをSetで重複除外、履歴件数、activeの有無を表示。非同期のviewCurrentチェックを維持。新ストア・永続キャッシュなし。
- `runner/index.html` / `runner/game.js`：配信識別子のみ更新。
- `tests/home_arcade_test.py`：対象4テスト、`.github/workflows/runner-iframe.yml`：ホームテストを既存の選択的CIへ追加。
- `docs/home-111/*`：合成データの前後画像・寸法JSON・本記録。

APP_VERSION **v1.7.39 → v1.7.40**。親CSS/model/iframeと子CSS/module/importの識別子を同期。DB/バックアップ/問題JSON/snapshot版は変更なし。価格30/100、テスト無料、キャッチャー実績、親ランナー残高、Canvas/ジャンプ/スクロール、コイン購入/報酬/保存は変更なし。未所持キャラクター情報を新しく表示しません。#114/#117は対象外。

## 変更前後画像（Chromium・同一合成データ、カード部分の切り出し）
### iPad横 1180×820
変更前

![iPad変更前](https://raw.githubusercontent.com/ohtsufsh-glitch/history-master/feat/111-home-arcade-grid/docs/home-111/before-1180x820.png)

変更後

![iPad変更後](https://raw.githubusercontent.com/ohtsufsh-glitch/history-master/feat/111-home-arcade-grid/docs/home-111/after-1180x820.png)

### iPhone縦 390×844
変更前

![iPhone変更前](https://raw.githubusercontent.com/ohtsufsh-glitch/history-master/feat/111-home-arcade-grid/docs/home-111/before-390x844.png)

変更後

![iPhone変更後](https://raw.githubusercontent.com/ohtsufsh-glitch/history-master/feat/111-home-arcade-grid/docs/home-111/after-390x844.png)

## カード寸法比較（CSS px）
表は左/キャッチャー、右/ランナー。間隔は2列時は横、1列時は縦。

|viewport|変更前 幅×高（キャッチャー / ランナー）|変更後 幅×高（キャッチャー / ランナー）|間隔|
|---|---|---|---|
|1180x820|842.00×262.00 / 842.00×262.00|513.00×288.06 / 513.00×288.06|16|
|1024x768|842.00×262.00 / 842.00×262.00|465.00×365.83 / 465.00×365.83|16|
|1366x1024|842.00×262.00 / 842.00×262.00|513.00×288.06 / 513.00×288.06|16|
|820x1180|742.00×262.00 / 742.00×262.00|742.00×262.00 / 742.00×262.00|18|
|390x844|332.00×373.59 / 332.00×326.06|332.00×373.59 / 332.00×326.06|18|
|844x390|766.00×262.00 / 766.00×262.00|766.00×262.00 / 766.00×262.00|18|
|700x900|622.00×262.00 / 622.00×262.00|622.00×262.00 / 622.00×262.00|18|

iPad横3サイズは等幅・上端/下端/開始ボタン下端の差1px以内。開始ボタン高は全サイズ54px。全7サイズで横スクロール、内部要素の横はみ出しなし。iPad縦/iPhone縦横/Split Viewは1列、幅は維持。1180px横で他画面は従来どおりrunner/admin 920px・arcade 1030px。入口ボタン・ホーム帰還・runner入場時scrollY=0も確認。

1024pxでは料金行と長いキャッチャー説明/実績が折り返すため自然高が増えます。高さ固定・文字切り捨て・カードへのoverflow:hidden追加なし。ステータス更新で高さは自然に変わり、再開表示時も3サイズでボタン揃えと横はみ出しなしを確認。

## 実績集計・検証
独立ブラウザcontextの合成IndexedDBだけを使用。
- 未プレイ 0/6・0回。
- S01を3回clear → 1/6・3回。S02 clear追加→2/6・4回、gameover追加→2/6・5回。
- active追加→回数は5のまま「続きから遊べます」。test切替→0/6・0回で再開案内なし。testのみS03 clear→1/6・1回。studentへ戻ると2/6・5回と再開案内。
- リロード後も保存正本から再計算。履歴クリア後0/6・0回。キャッチャー実績は前後同一。
- 無料試遊を別ページでゲームオーバーまで進め、正式runnerPlaysが0件のまま・ホーム実績不変を確認。

## 自動テスト
- 変更前7サイズの測定1件成功。
- 最終ホーム4件成功（11.527秒）。配置7サイズ、再開時3サイズ、履歴/プロフィール/リロード/消去、無料試遊、他画面幅/入口。
- 関連既存2件成功：runner_results_testの結果保存/再挑戦/ホーム帰還、runner_header_testの残高/キャンセル/購入/再開/プロフィール。変更したのはその後ホーム専用CSS余白と追加テストのみ。
- app_version_test 9件成功。親インラインJS・runner/game.js構文、git diff --check、コミット済み版チェック成功。
- 初回実行ではテストのimportが既存RunnerSessionTestも収集し、不要な保存テスト11件まで実行しました（全成功）。importをモジュール参照に修正済み。以後は必要な対象のみを指定。テスト側の他画面幅期待値とリロード後fixture参照を修正して成功。

再現：`PYTHONPATH=tests python3 -m unittest home_arcade_test.HomeArcadeTest -v`。前画像はmain上で`HOME_PHASE=before`を指定して配置テストだけ実行。

## CI・未確認事項・残存リスク
GitHub CIはPR作成後に確認し追記します。全ステージ攻略・全学習機能・DB移行/バックアップのフル回帰は対象外。
Safari実機・WebKit・VoiceOver未検証。公開前レビューでiPad実機の横配置/縦回転/Split View、iPhone縦横、アドレスバーとSafe Area、文字拡大時の自然折り返し/タッチ到達、VoiceOverのキャッチャー→ランナー読み上げ順を確認してください。`:has()`の既存利用を踏襲しています。狭い1024pxでの自然高増加は上表のとおりで、実機フォント差による折り返しの差が残ります。

ドラフトPRでレビュー待ち。mainマージ・タグ・本番デプロイ・Issue手動クローズは行いません。
