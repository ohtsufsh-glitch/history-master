# Issue #104 ランナー共通アニメーション検証

## 実装と互換性

PR #103マージ済みmain `1a9d1de`（v1.7.31）を基点に、専用ブランチで実装。
APP_VERSIONと親画面・iframe・ES Module・CSSの配信識別子をv1.7.32へ統一。

添付 `runner_extra_anim_fixed.zip` の `runner/assets/` 以下36枚を無加工で追加。
元ZIPとのバイト一致、各フォルダ9枚、512×512透過WebPのブラウザデコードを検証。
マニフェスト、確認用GIF、スプライトシートは配信しない。

`ANIMATION_SETS` にキャラ別の描画サイズ・走行周期・ポーズ別足元を定義。
`characterPose(state)`、ゲーム物理、当たり判定、足元座標、保存状態の形式は維持。
5匹が同じ `drawCharacter` を使用し、走行は全員0.1秒/コマ。

実画像の足先とアルファ境界を確認し、追加4匹は画像下端から約51〜53pxの余白を補正。
全て最大100論理px、足先を `state.feetY` に合わせる。地面・足場で同じ補正を使う。
オオサンショウウオは体高を引き伸ばさず、低い体形のまま接地。
追加4匹は素材自身の動きを使い、人工的な上下揺れを加えない。
しば犬の画像・既存サイズ・上下揺れ・ポーズ周期は維持。

選択時にそのキャラの9枚と既存ぬいぐるみ静止画を生成し、キャラID単位でキャッシュ。
画像イベントは既存の1枠に集約される再描画要求だけを行い、入力・保存・進行は待たせない。
失敗したImageも保持するので404を繰り返さない。
フォールバックは同じキャラの前回成功フレーム→待機画像→ぬいぐるみ静止画→名前。
キャラ変更後に別キャラのキャッシュを描くことはない。

秘密キャラの使用権は既存のプロフィール別獲得判定を維持。
未獲得・獲得済み未選択のアニメーションを先読みしない。
通常4匹の能力、ゆにこのハート3個・追加空中ジャンプ1回を変更しない。
DB/backup v10、snapshot v2、保存処理、課金、景品・問題データは変更なし。

## 実行した検証

独立Chromium・一時ブラウザコンテキスト・合成IndexedDBのみ使用。
実際の学習履歴・コインにはアクセスしていない。

- 新規6件：36枚のパス/形式/サイズ/透過/デコード、5匹×9ポーズの画像選択・地面/足場の足元、フォールバック全段階、選択時のみ9枚/切替キャッシュ、追加3匹の遅延/404時の入力と進行、60/120Hz周期・停止/再開、ゆにこの未獲得時通信なし・獲得後描画/追加ジャンプ。
- 関連既存71件：Safari回帰、セッション課金/保存、正式画面統合、結果・最高得点、選択、キャラUI、ゆにこ、版管理、しば犬の描画/周期/フレーム失敗/遅延。
- iPhone縦390×844・横844×390、iPad820×1180：タッチ配置/結果/選択テストに加え、通常4匹のゲームCanvasを撮影して位置と大きさを確認。
- ZIP内36枚とのバイト比較、親JS・runner JS構文、`git diff --check`、APP_VERSION検査。

既存の画像失敗テストには、PR #103以前の汎用仮キャラを期待する箇所、成功済みコマがあっても静止画を期待する箇所が残っていた。
今回の指定順に期待値を更新し、該当テストを再実行。全画像失敗の名前表示テストでは追加9コマも404にして検証。

再現コマンド（Playwright/Chromium導入済み環境）：

```sh
PYTHONPATH=tests python -m unittest -v \
  runner_animation_test runner_safari_test \
  runner_session_test.RunnerSessionTest \
  runner_integration_test.RunnerIntegrationTest \
  runner_results_test runner_selection_test runner_character_ui_test \
  runner_yuniko_test app_version_test \
  runner_canvas_test.RunnerCanvasTest.test_shiba_sprite_follows_run_and_jump_and_missing_image_uses_fallback \
  runner_canvas_test.RunnerCanvasTest.test_shiba_pose_timing_freezes_and_matches_at_60_and_120_hz \
  runner_canvas_test.RunnerCanvasTest.test_each_missing_shiba_frame_uses_old_shiba_without_changing_jump \
  runner_canvas_test.RunnerCanvasTest.test_delayed_shiba_frame_loads_while_hidden_without_advancing_or_auto_resuming
```

## 未実施・公開前のSafari実機確認

Safari実機/WebKit、VoiceOver、実端末の通信/メモリ/フレーム時間計測は未実施。
Issue #74の選択的テスト方針により全393件回帰・全48攻略・無関係なUFO描画テストは省略。
既存ゆにこテストの6ステージ攻略は関連回帰の範囲で実行。

公開前に安全なテストプロフィールで、以下をiPhone/iPad Safariで確認する。

1. 5匹の待機・連続走行・上昇/頂点/下降・地面/足場着地。特にオオサンショウウオの接地、ゆにこの追加ジャンプ。
2. 停止/再開、アプリ切替/OSロック/BFCache復帰後の画像と入力。低速回線・初回画像読み込み中も操作が止まらないこと。
3. 縦横回転とアドレスバー出入り後の表示、カードまでスクロールした位置の維持。
4. 実端末60/120Hzの滑らかさと、複数キャラ切替後のメモリ使用感。
5. 開始時のみ30コイン、無料再開・テスト無料、保存中→確定結果。実利用データを破壊する操作は行わない。

## 変更ファイル

- `index.html`、`runner/index.html`：v1.7.32と配信識別子。
- `runner/game.js`：共通アニメーション・選択キャラ画像キャッシュ・足元補正。
- `runner/assets/{sloth,goldfish,salamander,secret_yuniko}/`：各 `idle.webp`、`run_1.webp`〜`run_4.webp`、`jump_up.webp`、`jump_top.webp`、`jump_down.webp`、`land.webp`（計36枚）。
- `tests/runner_animation_test.py`：新規6件。
- `tests/runner_canvas_test.py`、`tests/runner_character_ui_test.py`：画像失敗時の期待値/条件を現行仕様に整合。
- `.github/workflows/runner-iframe.yml`：新規テストを既存CIへ追加。
- `docs/RUNNER_ANIMATION_104.md`：本報告。

既存 `runner/assets/shiba/`、`assets/plush/`、キャラ能力定義、ステージ定義は差分なし。
ドラフトPRで停止し、mainマージ・タグ作成・本番デプロイは行わない。
