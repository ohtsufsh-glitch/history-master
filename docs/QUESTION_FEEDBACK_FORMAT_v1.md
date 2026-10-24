# 指摘交換JSON v1（Issue #20 Phase 1）

この形式は指摘の手動集約専用。問題の追加・一括更新・完全バックアップとは別形式で、問題マスターや回答・報酬を書き換えない。教材や個人の指摘を含むファイルを公開GitHubに置かない。

## 外側の構造

| キー | 型・値 |
| --- | --- |
| feedbackFormat | `"history-master-feedback"` |
| formatVersion | 数値 `1` |
| exportedAt | UTCのISO日時（`YYYY-MM-DDTHH:mm:ss.sssZ`、実在する日時） |
| reports | 下記の報告配列。0〜5,000件。ファイル全体で8MiB以下 |

未知のキーを拒否する。選択書き出し・全件書き出しの形式は共通。全件が上限を超える場合は5,000件または約7MiB単位で分割する。各ファイルを順に取り込む。Safariでは複数ファイルのダウンロード許可・保存確認が必要な場合がある。

## reportsの各要素（本文は作成後不変）

| キー | 型・条件 |
| --- | --- |
| reportId | 小文字のUUID v4（`crypto.randomUUID()`） |
| questionId | スナップショットのidと同じ。3〜64文字、既存の問題ID規則 |
| questionRevision | 1以上の安全な整数。未設定問題は1 |
| questionHash | 小文字16進64桁のSHA-256 |
| questionSnapshot | 下記の問題スナップショット |
| reporterRole | `learner` または `admin` |
| sourceProfile | `student` または `test`。learnerでは必須。管理画面からの報告では省略 |
| category | 下記8カテゴリのうち1つ。learnerは共通5種のみ |
| comment | 0〜500 UTF-16コード単位の文字列。空文字可（textareaのmaxlengthと同じ） |
| createdAt | UTCのISO日時。exportedAtと同じ検証 |

管理状態 `status` / `statusUpdatedAt` を含めない。未知のキーも拒否する。表示はテキストとして扱い、HTMLを解釈しない。プロフィールの種別以外の個人名フィールド、実際の回答選択、回答履歴、成績は含まない。

| category | 表示 | 利用者 |
| --- | --- | --- |
| answer | 正解がちがうと思う | 共通 |
| explanation | 説明がわかりにくい | 共通 |
| too_hard | むずかしすぎる | 共通 |
| too_easy | かんたんすぎる | 共通 |
| other | そのほか | 共通 |
| fact | 史実・問題文に誤りがある | 保護者 |
| options | 選択肢が不適切 | 保護者 |
| wording | 表現・誤字・表示の問題 | 保護者 |

## questionSnapshotとハッシュ

`{...exportableQuestion(q), deleted: !!q.deleted}`。問題JSONそのもののschemaVersionは1のままで変更しない。

- 必須：`id`, `eraId`（E01〜E10）, `question`（空白のみ不可・最大2,000）, `type`（single/multiple）, `options`（2〜6個）, `correctAnswers`, `explanation`（空白のみ不可・最大4,000）, `shuffleOptions`（boolean）, `deleted`（boolean）。
- optionsは`{id,text}`。IDは元の配列順に`"1"`〜`"6"`、textは空白のみ不可・最大500。画面上のシャッフル順を使わない。
- correctAnswersは重複なしでoptionsのIDを参照。singleは1つ、multipleは2つ以上。
- 任意：`difficulty`（basic/standard/advanced）, `tag`（person/politics/culture/society/war_diplomacy）。未設定の場合は省略する。
- 未知のキーを拒否する。問題文・選択肢・解説は検証時にもtrimや改行の正規化をせず、報告時の内容を保持する。

ハッシュは既存の `sha256Text(questionFingerprintSource(q))` を使用する。すなわち既存順序の `exportableQuestion(q)` の後ろに `revision:questionRevision(q)`, `deleted:!!q.deleted` を足したオブジェクトをJSON.stringifyしてSHA-256にする。スナップショットから元の内部表現を復元して同じ関数で検証する。選択肢の表示順や実際の回答を混ぜない。解説・タグだけの変更も検知できる。一括更新のbaseRevision/baseHashの方式は変更しない。

## IndexedDBと管理状態

DB名 `history-master-sample-v1`、DB_VERSION=8。`questionFeedback` はkeyPath=`reportId`。インデックスなし。交換用フィールドに以下を加えて保存する。

| キー | 条件 |
| --- | --- |
| status | unreviewed / reviewing / fix_pending / resolved / dismissed |
| statusUpdatedAt | UTCのISO日時。createdAt以降 |

新規・取り込み時は未確認、statusUpdatedAt=createdAt。状態は保護者画面でのみ更新できる。readwriteトランザクション内で保存済みの状態と更新日時を読み直し、画面で確認した値と一致した場合だけ状態を更新する。他タブの変更は上書きせず、再確認を促す。日時は前回より最低1ms進める。本文は変更しない。

## 重複・衝突・版不一致

- 同じreportId・同じ不変本文：重複としてスキップ。既存の管理状態を維持。
- 同じreportId・異なる不変本文：衝突。プレビューに件数を表示して実行不可。保存前に他タブで衝突が生じても全件ロールバック。
- ファイル内の同じreportId：内容が同じでも不正ファイルとして全件拒否。
- オブジェクトのキー順は比較に影響しない。フィールドを既定順に再構成して本文を照合する。配列順と文章内の空白は保持し、相違として扱う。
- 異なるreportIdは同一問題・同一コメントでも別報告として保持。報告は自動削除しない。
- 現在の問題がない・改訂番号が異なる・内容ハッシュが異なる場合は「要確認」。保存自体は妨げず、報告時のスナップショットを閲覧可能。非表示で指摘を削除しない。

ファイル選択は検査と件数表示のみ。「指摘を取り込む」で、指摘と問題を対象に1つのreadwriteトランザクションを開始し、既存IDを再照合して指摘だけを追加する。途中失敗・衝突は全件取り消す。結果には新規・重複・衝突・版不一致件数を表示する。

## 完全バックアップ

BACKUP_VERSION=8は15ストアを保存し、指摘の管理状態も含める。v8復元では現在の指摘も置換する。v1〜v7では入力にquestionFeedbackが混入していても無視し、ローカルの指摘ストアをクリアしない。旧形式の14ストアの正規化・検証は従来どおり。どちらの復元も対象ストアを1トランザクションで置換し、失敗時は全体を取り消す。v8の指摘は最大100,000件、本文・状態・重複IDを検証し、ファイルプレビューと復元実行時にスナップショットハッシュも照合する。
