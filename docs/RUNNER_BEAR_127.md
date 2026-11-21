# Issue #127 クマ通常キャラクター追加

基点: main `7cad746`（PR #142マージ済み、v1.7.55）。専用ブランチ `feature/127-runner-bear-character`。
APP_VERSIONと親ページ・iframe・ES Module・CSSの配信識別子をv1.7.56へ同期。

## 能力案と選択

| 通常キャラ | 速度px/秒 | 高さpx | 滞空秒 | ハート | 追加ジャンプ |
| --- | ---: | ---: | ---: | ---: | ---: |
| しば犬 | 200 | 120 | 0.90 | 2 | 0 |
| なまけもの | 170 | 125 | 1.10 | 2 | 0 |
| 金魚 | 185 | 160 | 1.05 | 2 | 0 |
| オオサンショウウオ | 230 | 105 | 0.82 | 3 | 0 |
| **くま / bear** | **180** | **130** | **1.00** | **3** | **0** |

クマは本タスク指定の暫定値。なまけものに近い低速とハート3つを組み合わせ、
ゆっくり走って操作しやすい通常キャラとして追加する。速度表示「低」、ジャンプ表示「中」、
説明「ゆっくり走る・ハート3つ」。数値はPRレビューで最終調整する。
student/testの両方で初期選択可能。UFOのクマ景品所持とは連動しない。
ゆにこの定義・空中追加ジャンプ・同一プロフィール実獲得による権限判定を維持。

選択カード、能力・ハート表示、キャラ別最高得点は既存のCHARACTERS共通描画により追加される。
初期のクマ得点は「記録なし」。保存・同点順位用RUNNER_CHARACTER_IDSでは既存5IDを同順序で保ち、
bearを末尾に追加。画面では通常5匹→秘密ロック／獲得済みゆにこの順。

## 画像の出所・使用許可

ユーザーが本タスクに添付した `runner_bear_anim_webp.zip` を使用。
不足素材と公開・加工・再配布の許可を求めた後の「添付を使ってください」という指示を、
本PRでの画像使用許可として記録する。
ZIPのreadmeには「ユーザー提供3×3原画から抽出、再描画なし、JPEG由来の輪郭軟化あり」と記載されている。
以前のチャット原画そのものは本環境にないため、提供済み9枚の実際の姿勢を確認して採用した。

- ZIP SHA-256: `195dc9764f6500eba9147118506c46c2700579bd00b9e04d4e1cfcecc255fa57`
- `runner/assets/bear/` の9枚はZIP内WebPと**全てバイト一致**。512×512、RGBA透過、全9枚異なる内容。
- ZIP・原画・readme・feet_positions.jsonは配信物に追加しない。PR用9ポーズ一覧のみ添付preview.pngを使用。
- 選択カードと画像失敗時の最終画像は既存 `assets/plush/bear.webp`。既存素材への変更なし。

## ポーズと足元

既存周期を使用（run_1〜4は各0.1秒、着地0.12秒、頂点判定は既存の窓幅）。人工的な上下揺れは付けない。
顔・耳・短い手足・右向きを全9枚で確認。

| ファイル | 確認した姿勢と用途 | 足先境界Y / feetRatio |
| --- | --- | --- |
| idle.webp | 地上で四肢を下ろして待機 | 449 / 512 |
| run_1.webp | 前足片側を上げた踏み出し | 449 / 512 |
| run_2.webp | 前後脚を広げた走行 | 449 / 512 |
| run_3.webp | 低い重心で脚を前へ運ぶ走行 | 449 / 512 |
| run_4.webp | 前脚を下ろして次の踏み出しへ | 449 / 512 |
| jump_up.webp | 上向きに伸びた跳び上がり | 420 / 512 |
| jump_top.webp | 脚をたたんだ空中姿勢 | 404 / 512 |
| jump_down.webp | 脚を下へ伸ばし始めた下降 | 422 / 512 |
| land.webp | 四肢をつき体を沈めた着地 | 449 / 512 |

透明画素を除く実体の下端を各画像で計測し、同梱JSONの境界とブラウザのRGBA読取りが一致。
画像下端の数値は排他的境界（最後の有色画素Y+1）。これをstate.feetYに合わせ、地面と足場で共通使用する。
ジャンプ画像の余白で物理ジャンプ高さを二重加算しない。描画最大サイズは他キャラ同様100論理px。
既存fallbackは微小なアルファの孤立点を足と誤認しないよう、視認できる足先（Y=440）を基準にした。
共通の失敗処理（前回成功フレーム→idle→同キャラ静止画→名前）と、選択時のみ9枚を読み込むキャッシュを使用。

## 保存互換性と保護範囲

変更はキャラ定義、画像設定、許可ID、キャラ別ハート上限のみ。保存形式の変更・新ストア・移行は不要。
DB v10 / backup v10 / snapshot v2を維持し、既存購入済みプレイ・クリア・最高得点をそのまま扱う。
student30コイン、test0コイン、支払済み再開の追加課金なし、リタイアの最高得点除外を維持。
S01〜S06全コースと全stageVersion、物理・当たり判定・障害物・得点計算・UFO景品/抽選には差分なし。
Issue #85のS05/S06延長は今回実装していない。

## 限定テスト

独立Chromium・一時コンテキスト・合成IndexedDBのみ。実際の学習データには接続していない。

- 新規5件: クマの30/60/120Hz、速度180・頂点130・1秒後着地、3→2→1→0、追加ジャンプ不可。
  9枚のサイズ/透過/異なる内容/実足先とfeetRatio、正式購入→一時停止→再開→clear/gameover/retire、
  student/test分離、5匹混在＋両プロフィール途中状態のbackup v10復元、旧v1/v9復元、S05/S06版7の両プロフィール保存再開。
  実画面のページ再読込→無料再開、4サイズ・200%文字・44px以上カード・秘密ロック・クマ初期記録なし。
- 既存37件: アニメーション6、選択5、権限/プロフィール統合1、最高得点1、能力カタログ1、
  通常5匹UI/残ハート2、ゆにこ追加ジャンプ1、セッション11、保存9。
- 既存4匹×6現行ステージ×30/60/120Hzの72トレースを、変更前mainの同じ入力/全フレームsnapshotとSHA-256比較し全一致。
- 版管理9件、ZIP内WebPとのバイト比較、親JS・変更JS構文、差分空白、コミット後のAPP_VERSION検査。

既存の4匹固定攻略テストは対象を従来4IDに限定し、攻略入力・固定トレース・期待スコアは変更していない。
旧カタログ試験に残っていた「内部モデルがsecret_yunikoを拒否する」というC2以前の期待は除去し、
公開UIの獲得権限は専用テストで確認。初期化UI試験は現行コースの距離0以前にある足場を正しく考慮する期待に更新。
初回テストでは新テスト補助メソッド不足、ページ再読込の自動画面復帰、旧初期オブジェクト期待を修正して該当範囲を再実行。
画像遅延試験は一度5秒待ちで失敗し、再実行で成功。今後失敗時に未完了URLを出す診断を追加。

再現コマンド（Chromium/Playwright導入済み）:

```sh
PYTHONPATH=tests python3 -m unittest -v \
  runner_bear_test runner_animation_test runner_selection_test \
  runner_session_test.RunnerSessionTest runner_storage_test.RunnerStorageTest \
  runner_integration_test.RunnerIntegrationTest.test_locks_secret_profiles_restore_and_free \
  runner_results_test.RunnerResultsTest.test_stage_character_records_and_strict_improvements \
  runner_characters_test.RunnerCharactersTest.test_catalog_and_character_specific_jump_at_60_and_120_hz \
  runner_character_ui_test.RunnerCharacterUITest.test_five_options_image_abilities_and_default_are_preview_only \
  runner_character_ui_test.RunnerCharacterUITest.test_two_and_three_life_cycles_at_60_and_120_hz \
  runner_yuniko_test.RunnerYunikoTest.test_air_jump_budget_landing_and_normal_characters
```

CIにはrunner_bear_testを既存Runner iframe workflowに追加。CIの確定結果はドラフトPRのChecksで確認。
Issue #74に従い、全体回帰・クマ全6ステージ100点攻略・無関係なUFO画面試験は省略。
Safari実機、WebKit、VoiceOver実機は未実施。

## PR用画像

[9ポーズ一覧](screenshots/runner-127-bear/nine-poses.png) /
[通常5匹の実描画比較](screenshots/runner-127-bear/five-characters.png)

| サイズ | キャラクター選択 | 走行 |
| --- | --- | --- |
| iPhone縦390×844 | [選択](screenshots/runner-127-bear/choices-390x844.png) | [走行](screenshots/runner-127-bear/running-390x844.png) |
| iPhone横844×390 | [選択](screenshots/runner-127-bear/choices-844x390.png) | [走行](screenshots/runner-127-bear/running-844x390.png) |
| iPad横1024×768 | [選択](screenshots/runner-127-bear/choices-1024x768.png) | [走行](screenshots/runner-127-bear/running-1024x768.png) |
| Split View507×768 | [選択](screenshots/runner-127-bear/choices-507x768.png) | [走行](screenshots/runner-127-bear/running-507x768.png) |

[上昇](screenshots/runner-127-bear/jump_up-1024x768.png) /
[頂点](screenshots/runner-127-bear/jump_top-1024x768.png) /
[下降](screenshots/runner-127-bear/jump_down-1024x768.png) /
[着地](screenshots/runner-127-bear/land-1024x768.png) /
[クマのゲームオーバー保存後](screenshots/runner-127-bear/result-1024x768.png) /
[文字200%](screenshots/runner-127-bear/choices-390x844-text200.png)

## Safari実機のレビュー項目

1. 指定4サイズと縦横回転、文字拡大時のカード折返し・親スクロール・ジャンプ/一時停止/リタイアの操作。
2. VoiceOverでキャラ名、選択状態、走力/ジャンプ/ハート、秘密ロック、記録の読み上げ順とフォーカス維持。
3. 走行4コマ、上昇/頂点/下降/着地の滑らかさ、顔の視認性、地面/足場の接地、背景色上のJPEG抽出輪郭。
4. 低速回線・画像失敗、アプリ切替・OSロック・Safari復帰後の停止/再開と、購入済み再開での追加課金なし。

ドラフトPRでレビュー待ち。mainマージ・タグ・デプロイ・Issueクローズは行わない。
