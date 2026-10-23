# 歴史マスター v1.6.9：シークレットぬいぐるみ3種類

Issue #12の確定仕様を実装する。初期基点はmain `f29b4f6`（v1.6.7）。作業中にマージされたIssue #13を含む最新main `9724f94`（v1.6.8）へ追従済み。専用ブランチは `feat/secret-plushies`。
mainへのマージとGitHub Pagesへのデプロイは行わず、PRでレビューを待つ。

## Issue #13との並行開発

作業開始時、Issue #13はPR #16（v1.6.8、`fix/safari-history-navigation`）として未マージだった。本変更のアプリ版は次のv1.6.9とする。Issue #13の作業ブランチ・PRは変更していない。

本ブランチはv1.6.7から独立して作成したため、**Issue #13がmainへマージされた後、最新mainへ追従する必要がある**という条件に従い、PR作成中に検出したマージコミット `9724f94` を本ブランチへ取り込んだ。両方の変更を保持して競合を解消し、Issue #13の追加30件を含む全テストを再実行する。履歴連携を取り込んだ状態も今回の検証に含める。

`catchCrane()` / `animatePendingCrane()` の保存後に追加した `revealSecretPrize()` は、Issue #13の中断判定・画面世代確認の内側で呼ぶ。公開待ちの間にも画面世代と手動再開フラグを確認し、古い公開処理が戻り先を上書きしないようにする。`renderArcade()` / `refreshArcadeHome()` / `renderArcadeCollection()` の古い描画を除外するガード、履歴の追加、復帰処理、`pageshow`、`popstate`、`show()` はIssue #13の実装を保持する。READMEは双方の資料を残し、版番号はv1.6.9とした。

`navigate`、`navigateHome`、`restoreRoute`、`reconcilePage`、`restoreQuiz`、`grade`、`saveAnswer`、`getAvailableCoins`、`refreshCoinDisplay`、`startCrane`、`commitCraneOutcome`、`finishCranePlay`、`purchaseCranePlay`、`resetStudentViewAfterDataChange`、`applyRestore` の15関数は最新mainと本文一致を確認した。キャッチャー周辺の変更でも、画面世代・描画要求番号・プロフィールのガードを保持している。

## 統合時の再開ボタンテスト失敗の調査

失敗したのは `HistoryNavigationTest.test_arcade_aiming_back_forward_page_return_requires_manual_resume`。87件の初回統合実行で、期待値「追加料金なし」に対し、実際のボタンテキストは「100金貨でプレイ」だった。

原因は、テストが `arcadeResumeRequired && arcadeSweepFrame===null` だけを待ち、`restoreRoute()` が画面を表示してから `renderArcade()` が保存プレイを読み終える前に文言を検査したこと。保存読み込みをゲートで遅延させ、架空データで次を再現した。

| 状態 | 再開待ち | アーム | 開始ボタン | 保存済みプレイ／消費 |
|---|---|---|---|---|
| 履歴復帰・読み込み中 | true | 停止 | 旧文言、非表示・無効 | aiming／100枚の1件 |
| 読み込み完了 | true | 停止 | 「前回のプレイを再開（追加料金なし）」、表示・有効 | 同じaiming／同じ1件 |
| 再開ボタンの操作後 | false | 往復開始 | 通常開始ボタンは非表示 | 同じプレイ／同じ1件 |

読み込み前後の画面世代と描画要求番号は同じ（再現例では6と4）。正当な描画が古いものとして捨てられたわけではない。回答・コイン獲得・復習・消費・景品の記録に追加や削除はなく、実際の再開動作も期待どおりだった。

期待値は新仕様と矛盾していないため維持した。テストの待機条件に、復元後の「追加料金なし」表示を追加し、その後の既存assertを残す。アプリの手動再開フラグ、ボタン判定、履歴・保存復元、安全ガードはこの失敗の修正のためには変更していない。秘密の公開は `commitCraneOutcome()` → `animateCraneOutcome()` → `finishCranePlay()` → `revealSecretPrize()` の順を保ち、運搬中断ではresolvingを手動再開、保存確定後の中断ではfinishedを静的に再表示する。

## 変更内容

- 通常20種類のID・名称・画像を維持し、`secret_koryun`（こりゅん）、`secret_yuniko`（ゆにこ）、`secret_kappamaru`（かっぱまる）を追加。
- 新規7枠盤面と無料入れ替えは、90%で通常7体、10%で通常6体＋秘密1体。秘密3種類・配置7枠はそれぞれ等確率。通常は20種類から等確率・重複あり。
- 既存盤面は初期化しない。空枠や古いプレイのスナップショットもそのまま保持する。
- 実際に狙った枠が秘密の場合だけcarryを0.9倍にする。grab、通常景品の判定、アーム速度・位置・操作、運搬時間、100コイン／テスト無料は維持する。

| 位置精度 | grab（共通） | 通常carry | 秘密carry | 秘密の最終獲得率 |
|---|---:|---:|---:|---:|
| perfect | 0.90 | 0.84 | 0.756 | 68.04% |
| good | 0.75 | 0.67 | 0.603 | 45.225% |
| edge | 0.38 | 0.53 | 0.477 | 18.126% |

判定関数の呼び出しはキャッチ時の1回。grab・carry・必要な落下位置を既存どおり抽選し、保存済み結果を再開時にも使用する。

## 正体非公開と公開演出

通常定義 `PLUSH_TYPES` / `PLUSH_IDS`、秘密の実景品定義 `SECRET_PLUSH_TYPES` / `SECRET_PLUSH_IDS`、表示素材 `SECRET_UNKNOWN` を分離する。`secret_unknown` は抽選・保存IDの検証を通らず、獲得種類数にも含めない。

`plushPresentation()` が盤面・つかむ・運搬・失敗・落下・未獲得コレクションの画像と名前を共通「？」へ置き換える。盤面に本来の画像URLや名前、秘密IDのdata属性を出さない。獲得済みの種類が再登場しても同じ「？」を表示する。開発者向けソースや公開アセットのURL自体を隠す機能ではない。

成功時は既存の出口への運搬を維持し、秘密の名前を先出ししていた `animateCraneOutcome()` のメッセージを修正する。`finishCranePlay()` のIndexedDBトランザクションが完了し、景品付与・空枠化・プレイ完了が一括確定してから、次を表示する。

1. 「🎉 シークレットゲット！」と共通「？」を1秒表示。
2. 正式画像と名前を公開し、1.4秒表示。その後も結果画像を残す。

追加演出は計2.4秒。表示領域を画面内へスクロールし、小さい画面でも結果を見られるようにする。画像の軽い0.4秒の表示効果は `prefers-reduced-motion` で停止する。保存失敗では公開せず、`resolving`のまま手動で再試行できる。既に`finished`の結果は、再公開の待ち時間やアニメーションを繰り返さず静的に表示する。景品を再登録しない。

## コレクションと将来の拡大表示

通常x/20種類とシークレットx/3種類を別々に表示し、個数・コンプリート判定も分ける。ホームでもそれぞれの進捗を表示する。未獲得の秘密3枠は同じ画像・名前「？？？」・「未獲得」。獲得済みだけ正式画像・名前・累計数を表示する。student/testの解禁はそれぞれの獲得記録で判定する。

通常と秘密は共通の `plushCollectionItem()` と `.plush-item` 構造を使い、獲得済み項目だけに `data-prize-id` を付ける。Issue #15ではこの共通構造を拡大表示へ利用できる。クリックや拡大ポップアップ自体は今回追加しない。

## データとバックアップ

DB名 `history-master-sample-v1`、**DB_VERSION=7、BACKUP_VERSION=7、14ストア**を維持。新しい保存フィールド・スキーマ変更・移行は不要。

実際の秘密IDを既存の `arcadeBoards.slots`、`arcadePlays.prizes`、`arcadePrizes.prizeId` へ保存する。描画のためにIDを書き換えない。`purchaseCranePlay()` / `commitCraneOutcome()` / `finishCranePlay()` の保存構造と原子性を保持する。

- 旧v1〜v7を引き続き受理する。旧3体・7体プレイも手動再開できる。
- 新しい秘密IDを含むv7の書き出し→プレビュー→復元→リロードで14ストアの全件一致を検証。
- プレビューだけでは保存データを変更しない。`secret_unknown`・未登録IDは拒否する。
- 既存問題・回答・習得・コイン・利用履歴・通常20種類の記録を維持する。
- **秘密IDを含むv7バックアップを旧v1.6.7へ復元することは保証しない**。アプリを戻す場合は、更新前に非公開保存したバックアップを別の安全な環境で利用する。DBの初期化で対処しない。

## 正式画像

ユーザー提供 `history_master_secret_plushies.zip` 内の正式RGBA PNG4枚から、Pillowで1024×1024・品質90・method=6の透過WebPを作成。変換後のアルファチャンネルは原本と全ピクセル一致した。公開するのは次の4枚だけ。通常20枚は変更しない。原本PNG・一覧画像・設計用manifest・ZIPはリポジトリへ追加しない。

| ファイル（assets/plush/） | サイズ |
|---|---:|
| secret_koryun.webp | 151,242 bytes |
| secret_yuniko.webp | 69,260 bytes |
| secret_kappamaru.webp | 85,134 bytes |
| secret_unknown.webp | 57,640 bytes |

## 変更ファイル

- `index.html`：版番号、秘密定義、抽選、運搬補正、描画、公開演出、コレクション・ホーム進捗。
- `assets/plush/secret_*.webp`：正式画像4枚。
- `tests/secret_plush_test.py`：追加21件（Issue #13との統合確認2件を含む）。
- `tests/plush_test.py`：既存の通常20種類の検証を通常欄に限定し、通常抽選の乱数列を注入。再開時は非同期描画後のボタン状態まで待機。
- `tests/arcade_board_test.py`：初期盤面の秘密IDと「？」画像の期待値を追加。
- `tests/ui_cleanup_test.py`：表示版番号をv1.6.9へ更新。
- `tests/history_navigation_test.py`：履歴復帰時に保存プレイの非同期読み込み後のボタン表示まで待機。既存30件と期待値を維持。
- 本書、`docs/SAFARI_TEST_v1.6.9.md`、`README.md`：仕様・互換性・実機手順の案内。

## 自動テスト

```sh
PYTHONDONTWRITEBYTECODE=1 HISTORY_MASTER_BROWSER=/usr/bin/chromium python -m unittest discover -s tests -p '*_test.py' -v
```

準備は `tests/question_editor_test.py` を参照。アプリの依存追加はない。Playwright・Chromium、localhost、一時ブラウザ、教材と無関係な架空データだけを使用する。

初期基点の既存38件は成功（112.465秒）。Issue #13取り込み前の実装は全57件成功（既存38件＋追加19件、116.550秒）。統合後は**全89件成功・失敗0件**（既存38件＋Issue #13の30件＋本Issueの19件＋統合2件、192.936秒）。テストの削除・skip・無効化はない。JavaScriptの `node --check` と `git diff --check` も成功。

追加テストは乱数区間の両端付近を列挙した8,400盤面で出現10%、上限1体、秘密3種類・7枠・通常20種類の等確率を検証する。無料入れ替えも両プロフィールで210盤面ずつ列挙する。grab/carry境界、全3種類のつかむ・運搬・出口到着・失敗・落下時のDOM、保存成功を待つ公開順序、実トランザクションの中断と再試行、二重確定、リロード・ブラウザプロセス終了、プロフィール分離、通常／秘密のコンプリート、v7全ストア往復、WebP復号・透過、画面幅・低モーションも検証する。

統合テストAは秘密の運搬中の履歴往復、手動再開、追加100枚消費・再抽選・二重付与なし、確定前「？」と確定後の公開を検証する。統合テストBは公開待ち中のプロフィール変更と履歴復帰で古い演出を排除した後、再読み込み・student/test切り替え・履歴往復・コレクション再表示・v7書き出し／復元を行い、正式画像と個数、履歴stateのプロフィール、回答・習得・コインを含む14ストアの全件一致を検証する。旧v1〜v6、旧3体・7体、DB6→7などは既存回帰テストで維持する。

## 既知の制約・実機確認

**iPhone/iPad Safari実機は未実施**。ChromiumはSafariのbfcache・OS終了・VoiceOver・画像の実際の見え方を保証しない。公開前に [Safari実機テスト手順](SAFARI_TEST_v1.6.9.md) とv1.6.8の履歴連携手順を実施する。今後mainが更新された場合も双方の変更を保持して追従し、全テストを再実行する。
