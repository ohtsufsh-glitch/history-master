# 改善依頼JSON v1（Issue #20 Phase 2）

## 用途と重要な区別

「問題の指摘・改善管理」から選んだ報告を、ChatGPTの**問題作成チャットに手動添付**するための専用形式。

- 識別子：`improvementRequestFormat: "history-master-improvement-request"`、`formatVersion: 1`
- **ゲームへ直接取り込むファイルではありません。** `history-master-feedback` の交換ファイルや `history-master-question-update` の修正適用ファイルとも別形式です。
- 自動送信・自動問題修正・自動ステータス変更はしません。
- 現在の問題マスター、報告時スナップショット、保護者の対応状況を、問題IDごとにまとめます。
- 各レコードの自由記述欄には利用者が記入した文章が含まれるため、名前などを書かないよう注意してください。教材由来の問題や指摘は公開GitHubにアップロードしないでください。

## トップレベル

| フィールド | 意味 |
| --- | --- |
| improvementRequestFormat | 固定文字列 `"history-master-improvement-request"` |
| formatVersion | 整数 `1` |
| exportedAt | UTC ISO日時 |
| questionCount | 対象の問題ID件数 |
| reportCount | 出力した報告件数 |
| questions | 問題IDの昇順の配列（最大100問） |

保存時に整形したJSONが8MiBを超える場合は書き出しを中止します。ファイル分割は利用者が状態・チェックボックスを使って行います。対象がない場合は出力しません。

## questions の各要素

| フィールド | 意味 |
| --- | --- |
| questionId | 問題ID |
| sourceType | `imported`（取り込み問題）／`builtin-sample`（内蔵サンプル）／`missing`（この端末に問題なし） |
| updateEligible | 既存の問題マスター一括更新を受け付ける対象か |
| updateRestriction | できない場合の理由。可能な場合は null |
| currentRevision | 今の改訂番号。問題なしの場合 null |
| currentQuestion | 現在の `exportableQuestion(q)` と同形式の問題情報。問題なしの場合 null |
| baseRevision | **更新可能な取り込み問題のみ**現在の改訂番号。それ以外は null |
| baseHash | **更新可能な取り込み問題のみ**現在の `sha256Text(questionFingerprintSource(q))` 。それ以外は null |
| reports | この問題への報告配列 |

`currentQuestion` は `id`、`eraId`、`question`、`type`、`options`、`correctAnswers`、`explanation`、任意の `difficulty`、`tag`、`shuffleOptions` を含みます。報告した時点の内容と異なることがあります。

### reports の各要素

Phase 1で定義した不変報告内容（`reportId`、`questionId`、`questionRevision`、`questionHash`、`questionSnapshot`、`reporterRole`、`sourceProfile`［該当時］、`category`、`comment`、`createdAt`）に以下を追加：

- `status`：集約端末の現在の対応状況（未確認、確認中、修正確認待ち、対応済み、対応不要に対応するコード）
- `versionMismatch`：報告時の問題改訂番号または内容が現在と異なる／現在の問題が存在しない場合 true
- `changedFields`：報告時と現在の問題の差分に対応するフィールドキー配列。現在の問題がない場合 null

報告の不変本文は保存時のまま保持します。元の報告JSONにステータスを追加して **交換形式として再利用しない**でください（Phase 1交換形式はステータス無し）。

## 書き出し対象

- 「未確認・確認中の指摘から改善依頼JSON」：その2状態の指摘をすべて対象にします。100問・8MiB上限に達した場合は、指摘を選んで分割してください。
- 「選択した指摘から改善依頼JSON」：チェックボックスで選んだ指摘を対象にします。対応済み・対応不要も、明示選択すれば含められます。
- 現在の問題は端末のIndexedDBから書き出す際に読み直し、保護者画面の古い一覧表示には依存しません。
- 報告内容・対応状況・回答・習得・コイン・景品・その他ストアは**一切更新しません**。

## 問題作成チャットとの往復

1. iPadにiPhoneの報告JSONを手動取り込みし、保護者用管理画面で確認・選択する。
2. 改善依頼JSONを書き出し、「ファイル」アプリからこのプロジェクトの**問題作成チャットへ添付**する。
3. 教科書・問題集に照らして指摘の妥当性を確認する。報告だけで自動的に正解・難易度を変更しない。
4. 修正対象で `updateEligible=true` の取り込み問題について、`currentQuestion` と `baseRevision/baseHash` を使って、**既存の** `questionUpdateFormat: "history-master-question-update"`、`formatVersion: 1`、`schemaVersion: 1` の修正JSONを作成する。元の `baseRevision/baseHash` は一切変更しない。
5. ゲームの「問題マスターの書き出し・一括更新」で修正JSONを選択し、差分・習得判定への影響を確認してから実行する。問題の一括更新は最大100問。端末の現在の版と異なる場合、更新処理が拒否するので、その端末の問題マスターを再出力して検証する。
6. 「問題の指摘・改善管理」で報告時と現在の問題を比較し、保護者が必要に応じて**明示的に**「修正確認待ち」→「対応済み」へ変更する。自動削除・自動状態変更はしない。
7. `builtin-sample` はアプリ本体の修正が必要であり、一括更新ファイルに含めない。`missing` と削除・非表示の取り込み問題も修正適用対象外。

改善依頼JSONに学習履歴や回答イベント、コイン残高などは出力しません。改訂後も古い報告時スナップショットを保持します。