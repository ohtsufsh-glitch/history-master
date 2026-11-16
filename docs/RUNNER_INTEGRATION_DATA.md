# ランナー正式統合の保存設計（C3-A / Issue #91）

実装前の分析対象はPR #90反映済みmain（アプリv1.7.24）。本PRでは保存形式・検証・純粋集計のみ追加する。課金、実開始・再開・終了、ホーム入口、ページ間通信、景品認可UIは後続Issue #92〜#94。

## 現行仕様と移行

DB名は `history-master-sample-v1` を維持。v9の16ストア（questions, progress, sessions, answers, awards, sampleSettings, coinClaims, coinEvents, coinMeta, reviewEvents, coinSpends, arcadePlays, arcadePrizes, arcadeBoards, questionFeedback, studySets）を値・キーごと保持し、v10でrunnerPlaysだけ追加。既存onblocked/onversionchange処理を維持する。
残高はcoinEvents + reviewEvents − coinSpends。クレーンはpurchaseCranePlayが残高再確認と100枚（test無料）の支出・プレイを単一TXで記録。景品はarcadePrizesの実獲得記録で、runnerの成績とは別。
完全バックアップは全ストアの単一readonly TX、復元・初期化は単一readwrite TX。途中の失敗は全ストアをロールバックする。プロフィール初期化では対象profileの履歴・支出・景品だけ削除し、coinMetaを維持。完全初期化後は既存の移行処理を使う。

## 単一の正本

runnerPlays: keyPath `id`、autoIncrementなし、追加indexなし（現段階は全件読込・profile抽出）。最大100,000件。idは全ゲーム共通で一意な1〜100文字の文字列。profileはstudent/test。gameはrunner。各レコードは以下のフィールドだけを持つ。

- schemaVersion: 1、stageId: S01〜S06、characterId: shiba/sloth/goldfish/salamander/secret_yuniko。
- stageVersion: 正の安全整数。ステージ定義版を保存し、現在対応する版（1）と異なる途中記録も保持するが再開不可。版不一致で追加課金・記録削除を自動実行しない。
- startedAt / updatedAt: UTC ISO（ミリ秒付き）、開始≦更新。
- status: active / finished。1プロフィールのactiveは最大1件。
- score: 整数0〜100。正式成績はfinishedのみ。
- activeではsnapshot必須、result禁止。finishedではresult必須、snapshot禁止。
- result: reason（clear/gameover）、at（updatedAtと同じ）、livesRemaining（整数、キャラの初期残機以下）。clearは残機1以上、gameoverは0。正式クリアはreasonから導出し、重複フラグを保存しない。
- snapshot: version:1、distance（0〜1,000,000）、elapsedSeconds（0〜86,400）、livesRemaining（1〜初期残機）、collectedStarIds（重複なし整数0〜999、最大1,000件）、player（x/y/vx/vy:有限数、絶対値≦1,000,000）、shieldSeconds（0〜1）、airJumpsUsed（通常0、ゆにこ0〜1）。全フィールド必須・未知フィールド拒否。時間・移動・跳躍・被弾シールド・取得済みスターを保持する再開用契約。実ゲームからの変換とステージ定義に対する座標・スター対応検査はC3-Bで行う。JSONで64KiB以下。

## 支払対応と取引境界

coinSpendsのidがプレイid。runnerはgame:runner、studentはamount:30、testはamount:0、atはstartedAtと一致。全プレイにちょうど1支出。ゲーム跨ぎのid衝突・重複・欠落・プロフィール差異・負残高を拒否。craneは従来の100/0互換を保持し、atはv9と同じ非空文字列（64文字以下）のみ検証する。craneのatとstartedAtの一致は要求しない。v1〜v9にrunner支出が混入したら拒否する。
形式検証だけでは多重タブ競合を防げない。後続の購入処理はcoinEvents/reviewEvents/coinSpends/runnerPlaysを同一readwrite TXで読み、残高と既存activeを再確認し支出・activeをaddする。同じ支払済みidを再利用し、再開には課金しない。終了確定も同一TXで既存状態を確認して冪等に更新する。C3-Aは書込APIや実課金を追加しない。

## 導出と認可の境界

集計は検証済みプレイ配列とprofileを入力する純粋関数。S01は初期解放、同プロフィールの前ステージclearがあれば次を解放（キャラ・点数を問わず0点も可）。S06の次は作らない。最高得点はfinished（clear/gameover）だけを対象にステージ×キャラ別最大を求め、総合最高はその最大。同点はキャラ登録順、同キャラは開始日時→idの昇順で安定化。activeや無料プレビューから成績を作らない。testの正式無料プレイは集計対象。
ゆにこの過去成績復元は現在の景品所持と独立して許可する。将来の開始認可は同プロフィールのarcadePrizesのprizeId:secret_yuniko実獲得を参照する。URLパラメータだけで認可しない。正式UIは本体の支払済みセッションを根拠に通信・開始する（後続）。静的GitHub Pagesでは端末所有者によるJSON/DB改変の真正な防止は保証できない。本検証は整合性を保証する境界でありサーバ認証ではない。

## バックアップ互換・削除

BACKUP_VERSION=10、17ストア。v1〜v9はrunnerPlays=[]を補完。旧形式に混入したrunnerデータは採用しない。v1〜v3のcoinMeta/既報酬移行、v1〜v6盤面導出、v1〜v7のローカルquestionFeedback保持、v1〜v8のstudySets空補完を維持。旧版のrunner消費は補完で隠さず拒否する。
旧バックアップ復元は現在の両プロフィールのランナー記録・途中状態・クリア・最高得点を削除する。この破壊的影響をプレビューと最終確認で明示する。プロフィール別削除・完全初期化・履歴件数にrunnerPlaysを含める。

## 検証とマージ条件

独立localhost/一時ブラウザDBで16ストアのv9→v10値一致、v10往復、v1〜v9互換、混在課金、不正形式・重複・残高・プロフィール、集計、プロフィール削除、完全削除、復元失敗ロールバックを確認する。実学習DBは使用しない。
**マージ前に利用端末で既存データの完全バックアップを保存すること。** DB版更新後の古いアプリへの単純な戻しは保証しない。
iPhone/iPad Safari実機でバックアップ保存・再読込、v9→v10の履歴/残高/景品保持、複数タブのonblockedとonversionchange、旧版復元警告とキャンセル/実行、プロフィール別初期化、ストレージ失敗時の保持を確認する。Chromium自動試験だけではSafari実機確認を代替しない。

## 実施結果（2026-11-16）

- Chromium・独立localhost/一時コンテキストの合成DBのみ使用。実ユーザーのDB・バックアップは使用しない。
- 専用runner_storage_test: 8件成功。全16ストアに値を入れたv9→v10更新と残高一致、v10ダウンロード/復元、旧v1〜v9、旧版の破壊的警告とキャンセル、厳密形式/課金検証、集計/同点/全ステージ解放、プロフィール両方向の初期化、同期・非同期エラーによる復元ロールバック。
- 既存plush_test / positive_coin_reward_test / study_coin_integration_test / question_feedback_test / study_modes_test: 92件成功（200.4秒）。旧版移行、coinMeta、ローカル指摘保持、報酬・セット・景品の保存整合、blocked/versionchangeも含む。
- クレーンの取引直列化・旧版復元・景品・プロフィール・ロールバック、および秘密景品の復元/検証から選択13件成功（69.8秒）。
- 既存管理・履歴・コイン表示・景品ポップアップ・問題形式の保存スモーク8件成功（19.1秒）、指摘書出しの保存不変1件成功。版のテスト9件成功。JS構文、差分空白検査成功。
- テスト期待値はv10/17ストアへ更新。旧版用の入力フィクスチャは旧版のまま維持。テスト実装のAPI誤り等は修正して該当ケースを再確認済み。未解決の失敗なし。
- 未実施: Safari/WebKit/VoiceOver実機、全体回帰、ランナー全攻略、無関係なUFO描画回帰。実機項目は上記マージ条件に従う。
- アプリ版v1.7.24→v1.7.25。runner/index.htmlとgame.jsの配信クエリも1.7.25へ統一。ゲーム挙動・画像・問題JSON・公開の秘密キャラ選択は変更しない。

### PR #95レビュー修正：クレーン日時の旧版互換

全ゲームに要求していた支出日時と開始日時の一致をrunnerだけに限定した。craneはv9と同じくatの非空文字列・64文字以下を検証し、既存レコードの値は変更しない。DB/BACKUP_VERSION=10、アプリv1.7.25を維持する。
実際の旧v9コードで、student/testの開始日時と異なる支出日時（旧版が受理する非ISO文字列も含む）を検証・保存し、v10へDB更新した後の旧v9復元・v10ダウンロード・再復元で全ストアの値が一致する回帰テストを追加。修正前の互換性エラーを再現し、修正後の成功を確認した。
今回の選択テストはrunner_storage_testの9件と既存クレーン整合/課金/取引の4件、計13件成功（18.7秒）。さらにクレーンの空/長すぎるat、student/test両方のrunner日時不一致の拒否ケースを追加して該当テストの成功を確認。JS構文・差分空白・コミット済み版検査も確認する。無関係な全体回帰とSafari実機は未実施。実学習データは使用していない。

## C3-B / Issue #92：購入・再開・結果確定（v1.7.26）

PR #95マージ済みmain `614ff02`（v1.7.25 / IndexedDB v10）を基点とする。
DB名・DB_VERSION・BACKUP_VERSION・レコードschemaVersionは変更しない。既存17ストアを維持し、snapshotの識別値だけv2を追加する。公開導線と正式選択UIはIssue #93。無料試遊は正式APIに接続しない。URLや無料試遊の選択値を支払い済み根拠にはしない。

### 内部APIと認可

- `purchaseRunnerPlay({profile,stageId,characterId,id?})`：確定後の正本を返す。coinEvents / reviewEvents / coinSpends / runnerPlays / arcadePlays / arcadePrizesを単一readwrite TXで読む。現在の残高、同プロフィールのactive、IDのゲーム間衝突、前ステージの正式clear、同プロフィールの実景品secret_yunikoを確認し、支出とプレイをaddする。student30枚、test0枚（支出記録あり）。同期例外・非同期書込失敗は両方ロールバック。UFOとcoinSpendsを共有するため購入は直列化される。学習報酬とも対象ストアが重なる。
- 既存activeを最優先で返す。ステージ・キャラの指定が変わっていても再課金しない。終了済みIDの再利用は拒否し、新規リトライは新IDで新規購入。
- `openRunnerSession(profile,id,{lifecycle=true})`：DB正本からプロフィール・active・定義版・snapshotを確認して復元する。常に一時停止から始める。`view`はコピーであり、その変更は正本やゲーム状態を変えない。
- セッションの`resume / jump / advance(seconds) / pause / checkpoint / close`は非同期。ホストは操作をawaitし、advanceには走行中のフレーム時間だけを渡す。rendererへの接続はview.stateを使う。公開ランナー画面は今回このAPIに接続しない。
- 開始、明示一時停止、ジャンプ、残機/点数変化、終了、走行2秒ごと、pagehide / visibilitychange(hidden)で保存。pageshowでは走行を再開しない。非表示中の実時間は加算しない。ホスト側の回転・画面サイズ変更時もpauseを呼ぶ。
- `saveRunnerState(profile,id,expectedUpdatedAt,snapshot)`：同一TX内で正本を再確認する。updatedAtはDB内の前値より最低1ms大きくし、比較交換の世代値にも使う。複数タブの古い書込は拒否して停止する。距離・時間・スター・得点の巻戻しと残機の回復も拒否する。正本がfinishedなら終了再確定は既存結果を返し、途中保存は拒否する。

### 調査結果とsnapshot v2

v1のplayer.x/y/vx/vyでは、実装のfeetY/velocityYへの座標対応すら未確定だった。特にsupportId=nullと足場接地の区別、追加ジャンプ残数、取得後にobjectsから消えたスターは距離だけから推測できない。

| 分類 | フィールドと扱い |
|---|---|
| 定義から生成可能 | course（at順）、goalDistance、speed、jump、initialLives：stageId / characterId / stageVersionから生成 |
| 計算で照合可能 | nextSpawn、objectsのid・spawnDistance・x・寸法：距離とcourseから生成し、取得済みスターと画面外物体を除外して保存値と照合。xは浮動小数誤差1e-6未満を許容 |
| 保存必須 | distance、elapsed、lives、score、collectedStarIds、feetY、velocityY、supportId、jumpOriginY、airAction、airJumpsRemaining、invincibleRemaining |
| 表示継続にも必要 | animationTime、landingUntil、hitFeedbackRemaining、hitPoint、mode、reason |

v2は上記可変フィールド全件（nextSpawn / objectsも含む）を丸めず保存する。通常の進行スナップショットmodeはready/running/paused、reasonはnull。取得スターのcourse内IDを実取得時に記録し、score=取得数×10を検証する。足場の存在・水平重なり・高さ、地面接地、ジャンプ回数、残機、shield、コース物体の数/座標/種類を復元時と保存時に検証する。形式検証は未知フィールドと64KiB超過を拒否し、実際のステージに対する照合はゲームモデルで行う。
objectsは理論上再生成可能だが、保存値自体を復元することで丸めによる位置差を避け、再生成結果は整合検査に使う。スター取得履歴、接地・空中状態は再シミュレーションしない。

### 保存失敗・互換性・終了

保存成功の表示根拠はTXのoncompleteだけ。view.savedPlayは最後に確定した正本、view.dirtyは未確定の変化、view.errorは失敗理由。書込待ち中もdirty=true。失敗・競合後は走行/ジャンプ/再開を拒否し、未保存状態を保存済みとして扱わない。ページ破棄時の非同期TXの完了は保証できない。

再読込後はDBに確定済みの直前チェックポイントを再開する。失敗した最後の区間（最後のスター・被弾・終了も含む）は復元できない場合があるが、追加課金せず同一プレイを保持する。未保存区間の記憶上の進行と違う場合があることを正式UIで説明する必要がある。正常に保存されたハート・スター・得点・位置を巻き戻す処理はない。別タブとの競合時は勝ったタブの正本を開き直し、古いタブの状態を上書きしない。

旧v10 snapshot v1は形式検証・バックアップ往復で値を保持する。情報不足を推測で補完せず、再開は説明付きエラーにする。stageVersion不一致も同様であり、active・支出を削除せず、新規購入も行わない。将来の変換/互換エンジン対応まで保持する。旧v1〜v9バックアップ復元の既存の破壊的警告と処理も維持する。v2を含む新バックアップを旧v1.7.25アプリで読むことはできない（旧検証が拒否する）。新データ作成後の旧アプリへのダウングレードは保証しない。

ゴール到達かつ残機ありはclear、ゲームモデルのcollisionかつ残機0はgameoverに変換する。そのほかの停止では終了しない。モデルで終了条件を検証後、同一runnerPlaysレコードをfinishedに更新してsnapshotを除きresultを作る。得点は0〜100、clear/gameover両方が既存の最高得点集計対象。clearだけが次ステージ解放の根拠。コイン報酬はない。

### Safari実機の確認手順（公開前、未実施）

本番データの完全バックアップを別途保存し、ローカル/検証用配信の一時データで実施する。今回は正式UIがないため、本体ページのSafari Web Inspectorから内部APIを操作する（テストプロフィールは無料、studentは合成残高を使用）。

1. `purchaseRunnerPlay({profile:'test',stageId:'S01',characterId:'shiba'})`のidで`openRunnerSession`を開く。resume→advance→pauseし、view.savedPlayとdirtyを確認。再読込後に同じidで開き、追加支出なし、一時停止復帰を確認。
2. 専用自動テストのS03入力例に従い足場上・端から落下中、実景品を持つ検証プロフィールのゆにこで追加ジャンプ後、被弾シールド中、スター取得後にpause→再読込。座標・足場・ジャンプ残数・ハート・スター・得点を比較。
3. ロック、Safari別タブ/別アプリ切替、戻る/進む（BFCache）、縦横回転で停止。復帰時に勝手に走行しないことと、最後に完了した保存内容を確認。
4. 同一プロフィールを2タブで購入して同一id・支出1件を確認。両タブから保存し、古いタブは競合エラーになることを確認。student残高29/30、UFOとの同時消費、testとの分離も確認。
5. 検証用DBで容量不足/書込例外を再現し、dirty/errorを確認。課金失敗は支出・プレイ両方なし、途中/結果保存失敗は支払済みactive保持であることを確認。再読込後は最後の保存地点から無料で再開。
6. ゴール/ハート0だけで終了、再確定で値不変、0点clearで次解放、100点gameoverで最高点のみ更新。snapshot v1・stageVersion不一致のactiveを開いても記録や支出が消えないことを確認。
7. 旧v10バックアップとv2バックアップの保存・再復元を確認。旧版へ戻して新snapshotを読めるとは扱わない。実機WebKitの低容量・バックグラウンド終了・VoiceOverはChromium試験とは別確認。

### C3-B 自動検証結果

- 合成データ・localhost・独立Chromiumコンテキストのみ使用。専用session 11件（約11秒）、既存runner_storage 9件（10.4秒）成功。実TXの29/30境界、test無料、二重購入/2タブ/UFO競合、同期・非同期ロールバック、認可、再開、世代競合、保存失敗、結果冪等、0点clear/100点gameover、旧snapshot保持、v2往復を含む。
- S03の通常/秘密キャラ、足場上・端離脱・空中追加ジャンプ・被弾・スター取得を含むフレーム群でsnapshotを復元し、その次フレームを中断なしのモデルと完全一致比較。全ステージ攻略の再実行ではない。
- 既存positive_coin_reward 8件（17.2秒）、study_coin_integration 8件（58.1秒）、plush 11件（62.3秒）、study_modes 23件（73.5秒）、question_feedback 42件（75.4秒）成功。課金・バックアップ・プロフィール・学習保存を省略しない。
- 既存UFOの取引/複数タブ/旧版復元/検証/プロフィール削除/結果ロールバックと秘密景品の保存/検証から選択8件成功（48.2秒）。無関係な描画は対象外。
- ランナー代表起動・非表示復帰・スター・残機4件とapp_version 9件、計13件成功（15.8秒）。JS構文・差分空白・コミット済み版検査も実施。
- 計133件。途中の失敗はテスト期待順序・入力不足・座標の厳密等値比較・非表示競合時の停止エラー期待値を修正して再確認。v9移行試験の基点は移動するorigin/mainから固定v9コミットb7b6b19へ修正。
- 未実施：Safari/WebKit/VoiceOver実機、全393件、全48攻略、無関係なUFO描画。未保存区間の復元、ブラウザ破棄時のTX完了、旧アプリでのv2読込は保証しない。静的クライアントの改変防止は対象外。
- APP_VERSION v1.7.25→v1.7.26、runner HTML/CSS/JSおよびモジュール依存の配信クエリも1.7.26。タグ・本番配信・mainへのマージは実施しない。
