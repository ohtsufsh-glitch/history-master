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
