# v1.6.14 — 指摘から改善依頼JSONを作成（Issue #20 Phase 2）

## 目的
v1.6.13のPhase 1で保存・集約された報告を、問題作成チャットへ安全に渡し、既存の問題マスター一括更新ワークフローへつなぐ。

## 変更点
- 管理画面「問題を管理する > 問題の指摘・改善管理」に、未確認・確認中の一括出力と、選択した指摘のみの出力を追加。
- 専用 `history-master-improvement-request` 形式v1で、報告を問題IDごとに集約し、現在の問題文・選択肢・正解・解説・難易度・ジャンル・改訂番号、報告時スナップショット、版不一致、対応状況を出力。
- 修正適用可能な問題のみ `baseRevision/baseHash` を含める。内蔵サンプル・削除/非表示・現存しない問題は、更新できない理由を明記。
- 指摘一覧で版不一致の報告について、修正前後の問題と変更項目を比較でき、保護者が「修正確認待ち」に手動変更可能。
- 既存一括更新後に開いている指摘一覧を再取得。指摘は自動削除・対応済み変更しない。
- 出力対象は最大100問、整形後8MiB以下。多い場合は対象の指摘を選んで分割。
- 新規自動テストは `tests/improvement_request_test.py` を追加。

## 互換性・変更しない事項
- DB名と `DB_VERSION=8`、15ストア、`BACKUP_VERSION=8` を維持。DB移行なし。
- 問題JSONの `schemaVersion=1`、既存 `questionUpdateFormat/formatVersion`、`baseRevision/baseHash` の更新前照合を維持。
- 回答履歴、習得判定、コイン、カード、ぬいぐるみ、クレーン、プロフィール分離、Phase 1の指摘JSON交換・重複管理・状態変更を維持。
- 改善依頼JSONは新規問題取り込み用でも更新用でもない。外部への自動送信はしない。
- 実教材由来の問題・指摘データは公開リポジトリに登録しない。

## ファイル
- `index.html`：管理UI、改善依頼パック生成、版比較、修正後の指摘一覧表示。
- `tests/improvement_request_test.py`：架空データによる回帰テスト。
- `docs/IMPROVEMENT_REQUEST_FORMAT_v1.md`：専用JSON仕様と運用手順。
- `docs/SAFARI_TEST_v1.6.14.md`：実機確認。
- `README.md`：機能説明・リンク。

## 実行と未検証
`python -m unittest discover -s tests -p '*_test.py' -v` をCodexまたはローカル開発環境で実行し、既存テストも含めて確認すること。

このPRはチャットからGitHubコネクタでコードを更新したもので、**この環境ではPlaywright/Chromiumのテストを独立実行できていない**。JS構文・実機Safariは未検証として、マージ前の必須作業とする。
