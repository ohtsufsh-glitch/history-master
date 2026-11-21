# Issue #85 S05/S06 距離延長・最終難所（版8）

基点: main `4132cf78e29d2f33c4587b16b58e48f7ef3e17d9` / v1.7.56。PR #136（崩れる足場）、#142（リタイア）、#143（クマ）を確認。
専用ブランチ `feature/85-runner-s05-s06-extension`。APP_VERSIONと親/iframe/ES Module/CSSの配信識別子を **v1.7.57** に同期。
Refs #85。実機評価・最終確認が完了するまでIssueはクローズしない。

## コース・版の保護

| ステージ | 公開済み版7 | 新規購入の版8 |
|---|---:|---:|
| S05 | 7,200px | 8,000px |
| S06 | 8,000px | 9,000px |

S01〜S04と、S05/S06の版1〜7の定義・旧ゴール・ID・挙動を保持する。
新版は版7から独立した定義オブジェクト/配列を生成し、STAGESは版8を返す。
getStage(ID,版)と親RUNNER_STAGE_VERSIONSで旧版も正確に選択する。購入済みactiveは変換しない。
新版のスター移動後・追加イベントの安定ソート後に、各崩れる足場の世界Xから最終配列のIDを再計算する。
版7のIDを流用しない。版7の定義生成コードは編集しない。

物理・能力・画像・トゲ岩/電撃ブロックの描画・料金・リタイア・学習/UFO・iframe/スクロールは変更なし。
DB v10 / backup v10 / snapshot v2 / runnerPlays schemaVersion 1のまま。保存処理の変更は受理するコース版の追加のみ。

## 全体配置図・延長部

- [S05 版7/8の全体図](screenshots/runner-85-extension/s05-comparison.png) / [SVG](screenshots/runner-85-extension/s05-comparison.svg)
- [S06 版7/8の全体図](screenshots/runner-85-extension/s06-comparison.png) / [SVG](screenshots/runner-85-extension/s06-comparison.svg)
- [延長部の座標拡大図](screenshots/runner-85-extension/extension-detail.png) / [SVG](screenshots/runner-85-extension/extension-detail.svg)
- [正規ルートと再ジャンプ省略の比較](screenshots/runner-85-extension/route-comparison.png) / [実測座標](screenshots/runner-85-extension/route-comparison.json)
- [新旧の全コース定義JSON](screenshots/runner-85-extension/courses.json)

図の高さは地面基準px。足場は緑/茶（崩れる）、電撃壁は紫、スターは金、鳥は青、上下トゲは赤い移動範囲。
鳥の図上Xはしば犬との中心遭遇地点（実際の初期世界Xは下表）。軌道線は足元の高さ。

## 新規足場・危険物

| ステージ | 足場中心X | 幅 | 高さ | 版8のID | 連続接地から崩壊まで |
|---|---:|---:|---:|---:|---:|
| S05 | 7310 | 280 | 120 | 33 | 1.15秒 |
| S05 | 7650 | 280 | 70 | 34 | 0.95秒 |
| S06 | 7880 | 280 | 110 | 36 | 1.15秒 |
| S06 | 8220 | 280 | 170 | 37 | 1.15秒 |
| S06 | 8560 | 220 | 100 | 38 | 1.00秒 |

厚さ32px、足元支持の既存半幅20px。ジャンプすると連続接地タイマーは解除され、再着地で再計測する既存仕様。
早い入力でも次の再ジャンプまで足場が残るよう、低段・高段別に幅と期限を実測調整した。
S05は既存X6970の足場→X7120の岩を越えるジャンプ→新しい高さ120/70の連鎖。
S06は既存X7540の足場からX7880へ着地し、既存X7900のトゲを含む接続を通る。
新しい足場の位置は旧ゴール前から視認でき、ゴール境界で突然難所が出現する構成ではない。

| ステージ | 追加する穴 | 追加する対向鳥（初期世界X / 高度 / 速度） |
|---|---|---|
| S05 | 7180〜7770 | 11984 / 163 / 120px秒 |
| S06 | 7810〜8730 | 12896 / 153 / 120、13440 / 213 / 120、13952 / 143 / 120 |

| ステージ | 上下トゲX | 中心高度 | 振幅 | 周期 | 初期位相rad |
|---|---:|---:|---:|---:|---:|
| S05 | 7760 | 60 | 25 | 2.6秒 | 0.5 |
| S06 | 8190 | 70 | 20 | 2.5秒 | 1 |
| S06 | 8540 | 50 | 20 | 2.3秒 | 2 |

トゲ半径26px、鳥半径28px。既存と同じゲーム内elapsedから計算し、追加の保存状態はない。
しば犬で対向鳥は最初の可視輪郭から最初の水平接触まで約2.33秒、トゲは約3.73秒の視認時間。
上下トゲは全位相で地面の上・Canvas内に収まる。ゴールまで穴終了から230/270px、最終トゲ輪郭から214px以上を確保する。
S06は3足場、上昇段差、高い鳥を含む3羽の連続回避があり、S05の2足場・1羽より複合操作が多い。

## スターは10個・最高100点

新版だけでX420のスター1個を終盤へ移動。他の9個は維持。スター追加による11個化はしない。

| ステージ | 世界X:高度（10個） |
|---|---|
| S05 | 940:120、1300:90、1730:90、2460:80、3100:320、3500:70、4780:80、5610:70、6970:70、7650:70 |
| S06 | 900:120、1300:90、1740:80、2600:80、3400:330、3860:70、5360:80、6180:70、7540:70、8560:100 |

通常しば犬・空中追加ジャンプなしで、全10個取得と無傷ゴールを両立。各フレームで100点を超えないことも確認する。
クマを含む通常5匹の選択・能力・保存を維持。全5匹それぞれの100点攻略は要求外として未測定。

## 実入力による物理測定

位置・速度・ハート・無敵を変更せず、実際のstartJump/updateRunnerで測定する。
正式画面でもpointerdown→正式セッションのジャンプ処理を使用。時刻のみテストで制御する。

| ステージ | キャラ | 30Hz | 60Hz | 120Hz | ゴール時刻 |
|---|---|---|---|---|---|
| S05 | しば犬 | 8000px / 100点 / ♥2 | 同左 | 同左 | 40.000秒 |
| S06 | しば犬 | 9000px / 100点 / ♥2 | 同左 | 同左 | 45.000秒 |

[全ジャンプ・着地・星取得・鳥/トゲの最接近時刻/位置](screenshots/runner-85-extension/physics.json) / [入力計画](../tests/runner_extension_cases.py)

60Hzの接続部・新規区間の代表測定（時刻はゲーム内秒、Xは足元距離）:

| ステージ | ジャンプ時刻 | 次の着地時刻 / X / 高さ | 着地後の次入力まで | 跳ばなかった場合の崩壊期限 |
|---|---:|---|---:|---:|
| S05 | 35.350 | 36.150 / 7230 / 120 | 約0.90秒 | 約37.29秒 |
| S05 | 37.050 | 38.050 / 7610 / 70 | 約0.70秒 | 約38.99秒 |
| S05 | 38.750 | 39.767 / 7953 / 地面 | — | — |
| S06 | 38.200 | 39.033 / 7807 / 110 | 約0.87秒 | 約40.17秒 |
| S06 | 39.900 | 40.683 / 8137 / 170 | 約0.72秒 | 約41.82秒 |
| S06 | 41.400 | 42.417 / 8483 / 100 | 約0.73秒 | 約43.41秒 |
| S06 | 43.150 | 44.217 / 8843 / 地面 | — | — |

正規ルートは崩壊前に離陸する。[全16足場×30/60/120Hzの自然着地・崩壊期限](screenshots/runner-85-extension/timers.json)では、入力を止めて実際の消滅・支持解除を確認する。

### 入力幅と失敗経路

[全入力×30/60/120Hzの連続成功幅](screenshots/runner-85-extension/input-windows.json)。対象入力をフレーム間隔ずつ前後に動かし、他の入力は固定。
100点・無傷・全ジャンプ受理を成功条件とし、基準入力から連続成功する区間を最大±0.7秒まで測定した。
**接続部を含む新終盤の最小成功幅は0.30秒**。S05は0.333秒以上、S06は0.300秒以上。
維持した中盤S05の22.65秒入力だけは30Hzで0.167秒（22.55〜22.717秒）。60/120Hzでは0.2秒以上。
この既存区間を新版都合で変更せず、30Hzの既存例外として記録する。

[代表操作省略の全結果](screenshots/runner-85-extension/failures.json):

- S05の35.35秒/37.05秒省略は穴落下で残機0。38.75秒省略はトゲ被弾で♥1クリア。
- S06の38.2秒/39.9秒省略は落下で残機0。41.4秒/43.15秒省略は鳥等の被弾で♥1クリア。
- 両方とも終盤全入力省略・追加足場なしでは落下失敗。地上を走るだけの無傷ルートは成立しない。
- 省略のたびに即終了を強制する設計ではない。無傷の正規攻略が存在するため、無敵突破だけが正解にはならない。

## 保存・課金・旧版互換

[版7の全フレーム比較](screenshots/runner-85-extension/v7-traces.json)は、変更前mainの独立コピーから採った[固定fixture](../tests/fixtures/runner85-extension-base.json)とSHA-256で一致。
2ステージ×3Hz×正常/操作省略の12本で、ゴール/落下までの全snapshotを比較。旧版1〜7の全定義も完全一致。
従来の版7入力/既存fixtureは書き換えず、新fixtureを別名で追加した。

[旧購入済み版7と新版8の再開結果](screenshots/runner-85-extension/paid-v7-v8.json)。版7をstudentで再開すると7200/8000px、新しいtest購入は8000/9000px。
版7と8の混在backup v10を往復し、実ページ再読込後も版7のゴールを保持する。
版8の新しい最終足場上で保存→リロード→残り時間後に消滅→混在バックアップ復元→再リロードでも消滅状態を保持する。
新版の毎フレーム復元・次軌道、鳥/トゲ位相も一致。実iframeの非表示/復帰は時間を停止し、手動再開する。

student30/test0コイン、student前ステージクリアで解放/test全ステージ、再開の追加課金なし、リタイア得点の最高点除外、別コースへの新規購入を確認。
旧版1〜6の既存保存fixtureと旧バックアップを使った再開・復元も実行する。

## 実ゲーム画面

localhost・一時Chromium・合成データ・正式購入・実iframe。Safari実機画像ではない。
ゲーム画面へユーザーがスクロールした位置で撮影。親のスクロール仕様は変更しない。

| ステージ/場面 | iPhone縦390×844 | iPhone横844×390 | iPad横1024×768 |
|---|---|---|---|
| S05 新難所 | [画像](screenshots/runner-85-extension/s05-390x844-extension.png) | [画像](screenshots/runner-85-extension/s05-844x390-extension.png) | [画像](screenshots/runner-85-extension/s05-1024x768-extension.png) |
| S05 ゴール付近 | [画像](screenshots/runner-85-extension/s05-390x844-goal.png) | [画像](screenshots/runner-85-extension/s05-844x390-goal.png) | [画像](screenshots/runner-85-extension/s05-1024x768-goal.png) |
| S06 新難所 | [画像](screenshots/runner-85-extension/s06-390x844-extension.png) | [画像](screenshots/runner-85-extension/s06-844x390-extension.png) | [画像](screenshots/runner-85-extension/s06-1024x768-extension.png) |
| S06 ゴール付近 | [画像](screenshots/runner-85-extension/s06-390x844-goal.png) | [画像](screenshots/runner-85-extension/s06-844x390-goal.png) | [画像](screenshots/runner-85-extension/s06-1024x768-goal.png) |

## 限定テスト・再現

Issue #74の選択的テスト方針。個人の学習データには接続せず、一時DB・公開可能な合成データを使う。

- 新規 `runner_extension_test` 12件: 100点攻略、入力幅、視認/安全距離、失敗経路、全フレーム復元、16足場のタイマー、版7全フレーム、正式課金/再開/混在backup/リタイア、実タッチ3画面サイズ。
- 既存関連57件: crumbling9、vertical保存4、balance保存1、ascent保存1、session11、storage9、retire13、bear5、test mode4。旧版7専用試験は明示した合成の旧購入記録を使う。
- 旧版保存/密度関連: phase1/phase2a/tuningの互換性クラス、density全件を実行。
- APP_VERSIONの開発ツール9件、親/変更JS構文、差分空白、コミット後のAPP_VERSION比較。

初回検証で新足場の幅/期限の不整合を検出し調整。テスト補助のリロード後の再設定と、非表示復帰後の非同期再開待ちも修正。
旧版専用UI試験の購入経路は旧版fixtureへ分離。修正後の該当試験は成功。既存の固定期待・攻略入力・旧画面資料は保持する。

```sh
RUNNER_CAPTURE=1 PYTHONPATH=tests python3 -m unittest -v runner_extension_test
PYTHONPATH=tests python3 -m unittest -v runner_crumbling_test runner_vertical_test.RunnerVerticalCompatibilityTest runner_balance_test.RunnerBalanceCompatibilityTest runner_ascent_test.RunnerAscentCompatibilityTest runner_session_test runner_storage_test runner_retire_test runner_bear_test runner_test_mode_test
PYTHONPATH=tests python3 -m unittest -v runner_phase1_test.RunnerPhase1CompatibilityTest runner_phase2a_test.RunnerPhase2ACompatibilityTest runner_tuning_test.RunnerTuningCompatibilityTest runner_density_test
python3 scripts/runner_extension_review.py
```

図の生成だけ開発用matplotlibを使用（アプリ依存は追加しない）。CIに新版試験を追加する。CI結果はPRへ記載。
全キャラ×全コース、無関係な学習/UFOの全面回帰は省略。既存CIが実行する広い範囲はその結果を別途確認する。

## Safari実機で未確認

iPhone/iPad Safari・WebKit・VoiceOverは未検証。縦横の視認性と実タップでの連続着地/再ジャンプ、アドレスバー/Safe Area、回転・アプリ切替・BFCache、読み上げ/フォーカス、実端末でのバックアップ入出力と追加課金なしの再開を確認する。
既存中盤の30Hz入力幅0.167秒の操作感も評価対象。実機評価が完了するまでIssue #85は維持する。
mainマージ、タグ作成、本番デプロイ、Issueクローズを行わず、ドラフトPRでレビュー待ちとする。
