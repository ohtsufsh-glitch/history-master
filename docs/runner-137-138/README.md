# Issue #137② / #138 レビュー資料

最新main `0f2f8bd`（v1.7.51）から修正。APP_VERSIONとJS/CSS配信識別子はv1.7.52。

## 実装

`runnerUnlockedStageIds(summary, who)`で、testだけ全ステージIDを返す。
`runnerLobbyData()`と`purchaseRunnerPlay()`で共用し、studentは正式クリア由来の従来の集計を使う。
`summary`自体は変更しないので、クリア・最高点・次ステージ解放の記録を捏造しない。
購入済みactiveプレイの返却順序、ゆにこの同一プロフィール実獲得判定、0/30コイン処理は変更なし。
テスト用では不要なステージロック説明も非表示。

ホーム料金のspanにIDを付け、`refreshRunnerHome()`でプロフィール別に更新。
非同期応答後の`viewCurrent(ctx)`検証を通った場合だけ反映。CSS変更なし。
DB v10 / バックアップv10 / runner snapshot v2を維持。

## 限定テスト（Chromium）

- `runner_test_mode_test`：4件成功（10.816秒）。履歴0件のS01〜S06選択・開始・終了後も全解放、0コイン6回、テスト履歴削除、未獲得ゆにこ拒否、student未解放5ステージ購入拒否・初期表示・30コイン、プロフィール分離、active再開優先。
- 同4件内で、テスト開始/終了、再描画、ホーム復帰、再読込、戻る/進む、遅れた旧プロフィール応答の抑止を確認。
- `runner_storage_test`全9件、`runner_session_test`の残高境界・正式クリア解放・旧購入再開の3件、`runner_integration_test`のホーム購入再読込再開・S01実クリア後S02選択の2件、代表画面1件：計15件成功（22.872秒）。
- 代表画面は390×844 / 844×390 / 1024×768。料金1行、横はみ出しなし、student/testでカード高不変。要素画像は撮影時のみ固定ヘッダーを隠す。撮影調整後に画面テスト1件再実行成功（5.641秒）。
- 親JS・runner/game.jsの構文、差分空白、コミット済み版検査を実行。
- CIに新規テストを追加。最終CI結果はPR本文を参照。
- 全キャラ×全ステージ攻略、UFO描画・学習全体回帰は未実施（Issue #74の選択的テスト方針）。

## 画像

いずれも独立ブラウザ内で作成した公開可能な合成データ。実端末の学習履歴・バックアップは含まない。

| サイズ | studentホーム | testホーム | test選択画面 |
| --- | --- | --- | --- |
| iPhone縦390×844 | [画像](home-student-390x844.png) | [画像](home-test-390x844.png) | [画像](choices-test-390x844.png) |
| iPhone横844×390 | [画像](home-student-844x390.png) | [画像](home-test-844x390.png) | [画像](choices-test-844x390.png) |
| iPad横1024×768 | [画像](home-student-1024x768.png) | [画像](home-test-1024x768.png) | [画像](choices-test-1024x768.png) |

## Safari実機で要確認

iPhone/iPadの日本語フォントでの料金ピル1行表示、縦横回転後のカード・選択画面、戻る/進む・bfcache復帰時の料金、タッチでのS01〜S06開始と購入済み再開。Safari/WebKit/VoiceOver実機は未検証。

トゲ岩デザイン、強制終了、ゲーム物理、コース定義・stageVersion、崩れる足場、iframe・ジャンプ・停止・スクロール処理は変更しない。
