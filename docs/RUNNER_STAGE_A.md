# Issue #74 段階A：固定6ステージ

2026-11-15。ユーザー提供の `runner_stage_design_v1.json`（`draft-1`）を初期データとして実装。
ID・名称・難易度・ゴール距離・全イベントは元JSONと一致し、配置修正は不要だった。
入力ファイルのSHA-256は `da1911071720aca94d60e9038f824fed579f936cc62f4853dbebb32509915221`。

| ID | 名称 | 難易度 | ゴール距離 | 走行秒数 | トゲ岩 | 足場 | スター／最大得点 |
|---|---|---:|---:|---:|---:|---:|---:|
| S01 | はじめての草原 | 1 | 4000px | 20 | 2 | 0 | 10／100点 |
| S02 | トゲ岩の道 | 2 | 4800px | 24 | 3 | 0 | 10／100点 |
| S03 | スターへの挑戦 | 3 | 5600px | 28 | 4 | 1 | 10／100点 |
| S04 | 空中の足場 | 4 | 6400px | 32 | 5 | 2 | 10／100点 |
| S05 | トゲ岩と足場 | 5 | 7200px | 36 | 6 | 2 | 10／100点 |
| S06 | マスターコース | 6 | 8000px | 40 | 8 | 3 | 10／100点 |

## データと互換性

`runner/stages.js` の `STAGES` は `{ stageId, name, difficulty, goalDistance, course }` の配列。
元JSONの `id` を `stageId`、`events` を `course` に対応させる。定義は各イベントまで変更不可とし、プレイごとに複製する。
追加ステージは配列に定義を追加し、ゲーム側のID分岐や固定件数を増やす必要はない。

```js
import { STAGES } from './stages.js';
import { createRunnerState } from './game.js';

const state = createRunnerState(STAGES.find(stage => stage.stageId === 'S03'));
const retry = createRunnerState(state); // ID・距離・配置を維持して初期化
```

上記は既存ランナー画面内での利用例。`game.js` は従来どおり画面を初期化するモジュール。
段階Aではステージ選択UIを追加せず、独立ランナーの起動時は旧 `COURSE` のまま。
`createRunnerState()` と `createRunnerState(course配列)`、旧 `COURSE_LENGTH=6400` のexportも維持する。
ステージを渡した状態の移動上限・旗位置・進行度・クリア判定には `state.goalDistance` を使う。
リトライは得点・距離・経過時間・出現管理・接地状態を初期化し、選択ステージを維持する。

## 時刻と操作

`course[].at` は右端 `SPAWN_X=1008` での**出現時刻**。元JSONも既にこの意味なので再変換しない。
中心がキャラ `CHARACTER_X=186` に到達する秒数は `at + (1008-186)/200 = at + 4.11`。
例：S01の最初の岩は4.89秒に出現し、中心到達は9秒。幅・当たり判定があるため接触開始は9秒より前。

ジャンプ高さ120px・地上滞空0.9秒、速度200px/秒、物理サブステップ1/120秒を維持。
足場は従来の高さ80px・幅190px。接触1回で終了し、残機の追加、途中復活、チェックポイント、無敵時間はない。

テスト用攻略は岩の中心到達0.45秒前にジャンプする。100点経路では、足場スターの中心到達1秒前のジャンプも加える。
ステージ配置から攻略時刻を逆算するだけにせず、元設計の中心時刻を独立した期待値として保持する。
各フレームの入力で `startJump` を呼び、ゲーム状態・物体座標・得点を操作して攻略を成立させることはしない。
足場を使わずに走破する経路も全ステージで検証する。

## 検証

```sh
python3 -m unittest discover -s tests -p 'runner_stages_test.py' -v
python3 -m unittest discover -s tests -p 'runner_canvas_test.py' -v
python3 -m unittest discover -s tests -p '*_test.py' -v
python3 scripts/check_app_version.py --base origin/main --head HEAD
```

新規テストはIDの一意性、全イベントの出現、元設計の中心時刻と高さ、各ゴール距離、衝突優先、接触1回の終了、停止中の不変性、状態分離、将来の追加ステージ、不正距離の拒否を検証する。
60Hz／120Hzで全6ステージの通常クリアと100点クリアを実ゲームの更新処理で検証し、Canvasへのタップと実際の描画ループでも全6ステージの100点クリアを確認する。
一時停止・再開・リトライを全6ステージで確認する。旧ランナーの足場着地・再ジャンプ・落下などは既存テストで確認する。
全ランナーテストはストレージへのアクセスを禁止し、親アプリの読み込みがないことも監視する。

Chromium結果：新規9テスト成功（更新処理24経路、実Canvas操作12プレイを含む）。既存ランナー29テストも成功。
既存全体回帰は353テスト中352成功・1失敗。失敗は下記のmainでも再現する既存UFOアニメーション検証のみで、学習・コイン・保存／復元の検証は成功した。

WebKitは環境未導入で、Playwrightの配布元への接続がHTTP 403 `Domain forbidden` となり導入できなかった。
iPhone／iPad Safari実機の縦横表示、タップの操作感、アプリ切替・復帰は未確認。実機確認はブラウザ自動テストで代替したとは扱わない。

全体回帰の既知の不安定箇所：`arcade_board_test.py` の `test_crane_grip_and_lift_stay_together_across_widths_and_prize_sizes` は、CSSアニメーション終端の透明度を文字列 `0` と厳密比較する。
今回のブランチで微小値（約0.00042）が残る失敗を観測し、元のmainをそのまま配信した同じテストでも再現した。無関係なアニメーションやテストは変更しない。

## 変更範囲

`runner/stages.js`、`runner/game.js`、`runner/index.html`、`tests/runner_stages_test.py`、本書、`index.html` のAPP_VERSIONのみ。
APP_VERSIONは `v1.7.17` → `v1.7.18`。ランナーのCSS/JS更新識別子も揃える。
学習・UFOキャッチャー・コイン・IndexedDB・バックアップの処理、DB版とバックアップ版は変更しない。
ホーム画面連携、ステージ選択・解放・保存、50コイン課金、複数キャラ、ランダム生成は後続段階。
この段階はドラフトPRで停止し、mainへのマージ・タグ作成・本番デプロイは行わない。
