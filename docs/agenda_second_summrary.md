# UOS『AI Lead-Off』セミナー アジェンダ（各60分）

社内で実施したClaude Code活用セミナーをベースに、社外向けに再構成した各1時間のセミナーアジェンダです。

- 想定時間：各回 **1時間（60分）**
- 形式：講義 + デモ + ハンズオン中心

## 第2回：コーディング編 — Claude Codeで開発ワークフローを回す

題材は架空アプリ「Mandalart App」の LP です。**ClaudeDesign で LP を生成 → Claude Code へハンドオフして `docs/` 配下に取り込み → `/update-readme`・`/commit-changes` で main へ初回コミット＆プッシュ → 別ブランチを切り、顧客指摘（`アプリ設計2`）に沿って LP を修正 → `/update-readme`・`/commit-changes`・`/create-pr` で PR 作成 → `/review-and-fix` でセルフレビュー**、という GitHub 上の実開発フローを**一気通貫**で体験していただきます。冒頭では第1回（デモ中心）で紹介した `/rewrite-ai-tone`・`/create-design-md` を各自の手で試すハンズオンを挟み、続けて題材アプリの「アプリ設計（`アプリ設計.md`）＋ デザイン指定（`DESIGN.md`）→ ClaudeDesign で LP を生成」を各自体験してから開発フローに入ります（第1回未受講でも分かるよう補足します）。

### 第2回 タイムテーブル

| # | 時間 | セクション | 概要 |
| -- | ---- | ---- | ---- |
| 1 | 5分 | 開会・本日のゴール＋前提確認＋題材紹介 | 動作確認（`claude` / `gh` / fork / 作業ブランチ）、Mandalart App LP と本日の流れ |
| 2 | 5分 | 第1回で紹介したスキルを試してみよう【ハンズオン】 | デモのみだった `/rewrite-ai-tone`・`/create-design-md` を各自の手で実行 |
| 3 | 5分 | AIで変わるPGのやり方 | イシュー読まずに AI に渡す／ソース解析を AI に任せて rules 化／設計書とソースの差異確認、面倒だった作業の置き換え |
| 4 | 10分 | アプリ設計＋デザイン指定 → ClaudeDesign で LP 生成【ハンズオン】 | 同梱の `アプリ設計.md`（アプリ設計）＋ `DESIGN.md`（デザイン指定）を ClaudeDesign に渡し、アプリ設計から LP を起こす |
| 5 | 10分 | ClaudeDesign → Claude Code ハンドオフ：生成LPを docs 配下へ取り込み【ハンズオン】 | エクスポートの「ローカルのコーディングエージェントへ送る」で Claude Code に引き継ぎ、`docs/lp/` に配置 |
| 6 | 5分 | `/update-readme` → `/commit-changes` → main へ初回コミット＆プッシュ【ハンズオン】 | 取り込んだ LP から README を更新 → コミットメッセージ生成 → main に初回コミット＆push |
| 7 | 5分 | 別ブランチ作成 → 顧客指摘（`アプリ設計2`）に基づくLP修正【ハンズオン】 | 作業ブランチを切り、`アプリ設計2_顧客指摘.md` の §4 指示で LP を改訂2に更新 |
| 8 | 10分 | `/update-readme` → `/commit-changes` → `/create-pr` → `/review-and-fix`【ハンズオン】 | 改修差分を README 反映 → コミット → PR 作成 → 自作 PR をセルフレビューし指摘を1件ずつ吟味 |
| 9 | 5分 | Skill を作ってみよう | ○○ を改良した ○○（未定）を自作 |
| 10 | 5分 | 質疑応答・クロージング | 次のセミナーのご案内　アンケート |
