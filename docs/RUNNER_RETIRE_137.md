# ランナーのリタイア（Issue #137）

main `81286e6` / v1.7.54 を基準に、APP_VERSIONと配信識別子をv1.7.55に更新する提案。

## 動作

- 正式購入済みactiveプレイの走行中・一時停止中に、ヘッダーの44px以上の「リタイア」を表示する。無料デモでは非表示。
- 押下と同時に親のセッションを停止する。確認中はジャンプ、時間、落下、崩れる足場を進めない。親ページの`dialog.showModal()`で背景全体を操作不可にし、iframeの高さによる切れを避ける。
- キャンセルは元が走行中なら再開し、元が停止中なら停止を維持する。非表示中は再開しない。Escapeはキャンセル、初期フォーカスは「プレイに戻る」、終了後はゲーム内の操作へ戻す。
- 確定時は既存の保存キューへ最終状態を投入する。処理中の連打を抑止し、保存と正本の再集計が済むまで選択をロックする。
- 成功時は「リタイアしました」。保存失敗時は購入済みactiveを保持し、「最後の保存から再開（無料）」を使う。
- `updatedAt`の不一致は競合エラー。別タブで先に終了した場合は、保存済みのclear/gameover/retireを優先し上書きしない。確認前から走っていたactive保存が別タブの終了に負けた場合も、終了正本を再読取する。
- ステージとキャラを変更可能に戻し、次の学習プレイは従来どおり30コイン購入を確認する。testは0コイン。

## データ互換性

変更は終了理由の許容値を`clear / gameover / retire`へ拡張することだけ。`runnerPlays`の既存キー、schemaVersion 1、DB v10、バックアップv10、snapshot v2、全ステージ版を維持する。確認フラグと確認前のmodeはメモリ内にだけ保持し、フィールド・ストア・移行は追加しない。

終了レコードは`status: finished`、`result: {reason: retire, at: 終了保存時刻, livesRemaining: 実残機}`と途中の`score`を保持し、snapshotを持たない。retireは正の残機、gameoverは0、clearは正の残機として検証する。過去のclear/gameover・旧snapshot v1/v2・旧バックアップの読み込み条件を維持する。

料金の30コインは返還せず、リタイアで課金・返還・報酬イベントを追加しない。途中の得点は最高点・ランキング・初記録/新記録から除外する。次ステージ解放なし。終了履歴は保持し、プレイ回数は1回に数える。リタイアしかないステージの最高点は未記録として表示する。

**旧アプリへのロールバックは前方互換ではない。** v1.7.54のvalidatorは`retire`を拒否するため、新理由を含むバックアップ全体の復元に失敗する。旧集計コードは既存DBのretireを最高点候補に含める可能性もある。DB版を上げないため、旧版の起動自体でこの誤集計を防ぐことはできない。retire作成後のDB/バックアップは本変更以降のアプリで扱う。旧版へ戻すために終了履歴を削除したりgameoverへ偽装したりしない。新アプリ側は従来のバックアップを引き続き受け入れる。

## 限定検証

すべてローカルChromium、独立した一時IndexedDB、公開可能な合成データで実施。Issue #74の選択的テスト方針に従う。

- `runner_retire_test`（13件）: 走行/停止のキャンセル/確定、2機/3機、残機と得点、実際の崩れる足場上と落下中の凍結、保存遅延/二重確定、同期/非同期保存失敗と無料復旧、実際の別タブCAS、先行終了の採用、ゴール直前の100点リタイア、最高点/解放除外、v10書出し/復元/再読込、旧アプリでの拒否、フォーカス/Tab/Escape、回転/非表示復帰、次回購入、無料デモ分離。
- 既存`runner_session_test`（11件）、`runner_storage_test`（9件）、`runner_records_ui_test`（2件）: 原子的な購入、資産・プロフィール分離、保存失敗、旧v9→v10、旧snapshot/バックアップ、新旧終了記録、結果/最高点表示。
- `runner_integration_test.test_representative_touch_layout_and_single_engine`: 正式iframeと代表タッチ配置。
- `runner_layout_test`の全サイズ全状態、Split View、拡大文字/極小画面、`runner_header_test.test_sizes_initial_and_playing_coordinates_and_title`、`runner_results_test.test_failed_finish_is_unconfirmed_and_free_recovery`: 購入前/走行/停止/通常終了/保存失敗で画面と操作が移動せず、文字拡大時に読めること。
- JS構文、`git diff --check`、APP_VERSION検査。CIには`runner_retire_test`を追加。

全キャラ×全ステージ攻略、本体学習/UFOの全面回帰は省略。物理・配置・コース版・障害物デザインには変更なし。

## 表示画像

自動撮影のChromium画像であり、Safari実機画像ではない。ゲーム画面へユーザーがスクロールした位置で撮影。ヘッダー領域は購入前・終了後も確保し、iPadでは行間を調整してCanvasサイズを維持する。

| 画面 | ゲーム・操作 | 確認画面 |
| --- | --- | --- |
| iPhone縦390×844 | [表示](runner-retire-137/390x844-play.png) | [表示](runner-retire-137/390x844-dialog.png) |
| iPhone横844×390 | [表示](runner-retire-137/844x390-play.png) | [表示](runner-retire-137/844x390-dialog.png) |
| iPad横1024×768 | [表示](runner-retire-137/1024x768-play.png) | [表示](runner-retire-137/1024x768-dialog.png) |
| Split View相当507×768 | [表示](runner-retire-137/507x768-play.png) | [表示](runner-retire-137/507x768-dialog.png) |

[リタイア結果](runner-retire-137/507x768-result.png)

## Safari実機で残る確認

iPhone/iPad Safari・WebKit・VoiceOverは未実施。実機のタップと連打、アドレスバー伸縮/Safe Area、ピンチ/文字拡大、画面回転、バックグラウンド/BFCache復帰、モーダルの読み上げと親子間のフォーカス復帰、端末のファイルへのバックアップ書出し/復元を確認する。mainマージ・タグ・本番公開・Issueクローズは行わない。
