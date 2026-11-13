# アプリバージョンの更新とPRチェック

## 今回の整合性修正

Issue #54対応時、最新main（`9aca7e1`、PR #53反映済み）と既存Gitタグ `v1.7.2` のどちらも、`index.html` の `APP_VERSION` は `v1.7.1` だった。今回のアプリ版は `v1.7.3` とする。既存タグ・履歴は変更せず、`v1.7.3` タグもこのPRでは作成しない。

`APP_VERSION` はリリース識別子、Git commit SHAは正確なビルド識別子。DB版・バックアップ版・問題JSON版とは異なる。今回 `DB_VERSION = 9`、`BACKUP_VERSION = 9`、問題追加JSONの `schemaVersion = 1` はすべて維持する。

## 更新の手順

リポジトリ直下で実行する。Python 3とGitがあればよく、外部パッケージは不要。

1. `git fetch origin main` で最新mainを取得し、最新コード・版を確認する。必要なら作業ブランチに取り込む。
2. アプリを変更するPRでは、通常 `python3 scripts/bump_app_version.py` でパッチを1増やす（例: `v1.7.3` → `v1.7.4`）。PR内で原則1回でよい。
3. 大きな節目のマイナー更新はユーザー承認を得て、`python3 scripts/bump_app_version.py v1.8.0` のように明示する。
4. 差分を確認してコミットし、`python3 scripts/check_app_version.py --base origin/main --head HEAD` を実行する。検査対象は作業中の未コミットファイルではなく、指定したGit参照の内容。
5. PRに変更前/後の版を記載する。並行PRが同じ版で先にマージされたら、最新mainを取り込み、再度上げてコミット・pushする。

更新スクリプトは `index.html` の `APP_VERSION` の値だけを置換する。引用符、改行、その他のUI・ロジックは保持する。定義・代入の欠損/重複、対応外の定義形式、無効な版、同一版への更新や後退では、ファイルを書き換えず終了コード1で失敗する。

対応する版は先頭ゼロのない `vX.Y.Z`（非負整数3個）。`1.7.4`、`v01.7.4`、プレリリースやビルドメタデータ付きの版は使わない。定義は単独行の `const APP_VERSION = "vX.Y.Z";` とする。管理画面は既存の `textContent` 更新でこの定数を表示するため、HTMLの表示文字列の別更新は不要。

## Actionsの判定と並行PR

ワークフロー **App version** のジョブ **Check app version** が、main向けの `pull_request`（作成・追加push・再オープン）で実行される。文書のみのPRもジョブを実行して成功させるため、ワークフローにパスフィルターは設けない。

| 変更の種類 | 判定 |
| --- | --- |
| `index.html`、`assets/**` の追加・修正・削除・移動 | PR版が実行時に取得した最新mainの版より厳密に大きい場合に成功 |
| `assets/**/.gitkeep` | 配信画像ではないため版更新不要 |
| 文書、`tests/**`、`scripts/**`、`.github/**` など、上記以外のみ | 版更新不要として成功 |

現在のアプリ本体は `index.html` と `assets/**`。将来JavaScript/CSSや他の配信ファイルを追加・分離するときは `scripts/check_app_version.py` の `is_app_path()` も更新する。

変更ファイルは最新mainとPR先端の**共通祖先からPR先端まで**を判定し、別PRでmainに入った変更を混ぜない。一方、版の比較は共通祖先やイベント内の古いbase SHAではなく、ジョブで取得し直した最新mainと行う。文字列順ではなく数値3要素で比較するため `v1.7.10 > v1.7.9`。更新漏れ、後退、同一番号、形式不正、重複定義は修正方法付きで失敗する。

PRジョブは `contents: read` のみ。自動コミット・push・タグ作成・デプロイは行わない。既存のPages設定は変更しない。

## ユーザーがGitHubで追加設定すること（本PRでは設定しない）

Actionsを追加するだけでは、失敗したPRや古い成功結果のままのPRのマージを禁止できない。main更新だけでは、ほかのPRのチェックも自動再実行されない。

導入PRのチェック実行後、ユーザーが権限と内容を確認し、承認した上で GitHubの **Settings → Branches → mainの保護ルール**（または同等のRuleset）を設定する。

1. **Require status checks to pass before merging** を有効にし、**Check app version** を必須にする。実際のチェック名はこのPRのChecks欄で確認する。
2. **Require branches to be up to date before merging** を有効にする。先行PRのマージ後、後続PRを最新mainへ追従させて再検査し、番号の重複を検出するために必要。
3. ルールの適用対象がmainであり、通常のマージ操作でバイパスされないことを確認する。

この設定を行わない間は、マージ前に最新mainを取り込み、チェックを再実行して結果を確認する運用が必要。GitHub Actions自体が無効なら有効化も必要。追加のSecretや有料サービスは不要。

## 確認方法

- 軽量テスト: `python3 -m unittest discover -s tests -p 'app_version_test.py' -v`
- 既存の表示・保存データ不変の確認: `PYTHONPATH=tests python3 -m unittest ui_cleanup_test.UiCleanupTest.test_version_is_admin_only_and_follows_the_constant -v`（既存のPlaywright/Chromium環境を使用）
- iPhone/iPad Safari実機は別途、レビュー用の安全な環境で保護者用管理画面に `アプリバージョン：v1.7.3` が表示されることを確認する。ホーム画面に版が表示されず、既存の問題・学習履歴・コインが保たれ、再読み込み後も変わらないことを確認する。実機未検証のまま公開成功とは扱わない。
