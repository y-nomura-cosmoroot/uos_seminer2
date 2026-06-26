---
name: create-design-md
description: 指定された「URL」または「.pptxファイル」を分析し、Google Stitch形式の DESIGN.md を生成する。WebサイトならHTML/CSSから、PowerPointファイルなら内部XMLを深掘りして、カラーパレット、タイポグラフィ、コンポーネント、レイアウト等のデザイントークンを実測値で抽出する。URLが渡された場合、pptxファイルパスが渡された場合、どちらにも対応。デザインシステム化、DESIGN.md生成、既存資料の再利用、PowerPointをテンプレ化したいといった依頼が来たら必ずこのSkillを使うこと。引数は [URL または .pptxファイルパス]。
allowed-tools: WebFetch Bash Read Write Edit Glob Grep Agent
---

# Design MD Generator

URL または `.pptx` ファイルを受け取り、Google Stitch 形式の DESIGN.md（9セクション構成）を生成する。

## Input

- `$ARGUMENTS` — 分析対象。以下のいずれか:
  - URL (例: `https://example.com`)
  - .pptx ファイルパス (例: `/path/to/deck.pptx`)

## Routing

引数を見て処理を分岐する:

1. `http://` または `https://` で始まる → **URL Workflow**（Section A）
2. `.pptx` で終わる、またはそのパスに .pptx ファイルが存在する → **PPTX Workflow**（Section B）
3. どちらにも該当しない → ユーザーに「URL か .pptx パスを指定してください」と確認する

どちらのワークフローも最後は同じ **9セクション構成の DESIGN.md** を作業ディレクトリ（または同じフォルダにpptxがある場合はそこ）に出力する。

---

## Section A: URL Workflow

### A-1. サイト情報の収集

以下を並行して収集する:

1. **トップページのHTML** — WebFetch でページ全体の構成、セクション、ナビゲーション、コンポーネントを取得
2. **CSSファイルの解析** — curl で HTML を取得し `<link>` から CSS の URL を特定。CSS を curl で取得し、以下を抽出:
   - カラー: `grep -oP '#[0-9a-fA-F]{3,6}'` / `grep -oP 'rgba?\([^)]+\)'`
   - フォント: `grep -oP 'font-family:[^;]+'` / `grep -oP 'font-size:[^;]+'`
   - 角丸: `grep -oP 'border-radius:[^;]+'`
   - 影: `grep -oP 'box-shadow:[^;]+'`
   - ブレイクポイント: `grep -oP '@media[^{]+'`
3. **主要サブページ** — WebFetch で会社概要・サービス・採用等を確認し、パターンを補強

### A-2. デザイントークンの整理

- カラー（Primary / Accent / Neutral / Status / Surface & Border / Shadow）
- タイポグラフィ（family, size, weight, line-height, letter-spacing）
- コンポーネント（buttons, cards, nav, forms, headings）
- レイアウト（container, grid, spacing, radius）
- エレベーション、レスポンシブ

---

## Section B: PPTX Workflow

### B-1. 深掘り抽出スクリプトを実行

スキル同梱の `scripts/analyze_pptx.py` を使う。このスクリプトは以下を自動でやる:

- pptxを解凍
- `theme1.xml` のカラースキームとフォントスキームを **完全解決**（`schemeClr val="tx2"` → `#353E49` まで辿る）
- 全スライドの `<p:sp>` を走査し、**Shape の塗り** と **テキスト色** を **別物として** 抽出
- `<p:pic>` の位置と大きさを記録（画像があるかどうかがレイアウト判定の鍵）
- グラデーションを停止点・角度・アルファまで保存
- ウォーターマーク検出（塗りなしボックス + 明色の巨大文字）
- 2カラムレイアウト / Before-After 構成の検出
- 使用フォント・使用色の集計

実行:

```bash
python3 <このskillディレクトリ>/scripts/analyze_pptx.py "<pptx_path>" --out /tmp/pptx_design_report.json
```

生成された JSON は構造化済みで、そのまま DESIGN.md 執筆の基礎資料になる。

### B-2. レポートを読み、**自分でも PPTX を直接確認する**

スクリプトは強力だが完璧ではない。レポートを読んだ上で、最低限以下を自分で確認する:

1. 表紙スライド（通常 slide1）の背景 — 単色なのか、**グラデーション**なのか、画像なのか
2. 各スライドの一番大きな要素（典型的には上部の「帯」に見えるもの）の正体 — **塗りつぶしの矩形** か、それとも **塗りなしテキストボックスに淡色の巨大文字** か
3. 画像（`<p:pic>`）がスライドのどこを占めているか — 右半分に大きな画像があれば「左テキスト／右画像」の2カラム構成
4. テキストの色 — 本文が純黒 `#000000` なのか、それともダークグレー（`tx2`）なのか

### B-3. 典型的な落とし穴（過去の失敗パターン）

以下は実際に発生した誤分析の例。必ず避ける:

**誤り1: `srgbClr val="F7F7F7"` を見たら即「グレー塗り」と判定する**
- 正しい手順: その色が `<p:spPr>` 内の `<a:solidFill>` か、`<a:rPr>` 内の `<a:solidFill>` か、を必ず確認する
- `<p:spPr>` が `<a:noFill/>` でテキスト色が F7F7F7 だった場合、それは「塗りつぶしの帯」ではなく「白背景に浮かぶ淡灰色のウォーターマーク文字」

**誤り2: `schemeClr val="tx2"` を「ダーク色」程度の曖昧な理解で止める**
- 正しい手順: theme1.xml の `<a:dk2>` を調べて `#353E49` のようにHEXまで解決する
- この違いで「純黒の本文」か「ダークグレーの本文」かが変わり、再現スライドの印象が大きく変わる

**誤り3: グラデーション背景を単色と誤認する**
- 正しい手順: `<a:gradFill>` があれば `<a:gs pos="...">` の停止点・色・`<a:alpha>`・`<a:lin ang="...">` の角度まですべて記録する
- 角度は 60000分の1度単位（例: `18900000` = 315°）

**誤り4: `<p:pic>` を無視する**
- 正しい手順: 画像の pos と size を必ず取り、テキスト位置と突き合わせる
- 右側に大きな画像があるスライドが複数あれば「左テキスト／右画像」の2カラム構成が定型フォーマット

**誤り5: Bold 指定を落とす**
- 正しい手順: `<a:rPr b="1" ...>` の `b="1"` を必ず記録する
- 和文でも Noto Sans JP Bold が標準で使われているケースは多い

### B-4. DESIGN.md 執筆時に必ず書くこと

PPTX由来のDESIGN.mdでは、下記の項目を具体値で書く:

- **スライドサイズ**（inch と EMU の両方、16:9標準か大判か）
- **背景の種類**: 単色 / グラデーション（停止点・角度・アルファ） / 画像
- **ウォーターマークの有無**と、その色・サイズ・フォント・文字列例
- **コンポーネント位置の実測値**: タグ (x, y) / ヘッドライン (x, y, w, h) / 画像領域 (x, y, w, h)
- **テキスト色が純黒かダークグレーか**: `#000000` / `#353E49` / その他
- **和文と英字のフォント別指定**: 例 `Noto Sans JP (Bold)` + `Montserrat (Bold)`
- **2カラム構成の有無**: 左テキスト／右画像、など

---

## Output Format (両ワークフロー共通): Google Stitch DESIGN.md

以下の **9 セクション構成** を厳守する。全セクション、具体的な HEX / フォント名 / サイズ値を本文に埋め込み、「青系の色」といった曖昧な表現を避ける。

```markdown
# Design System Inspired by {ソース名}

## 1. Visual Theme & Atmosphere
全体の雰囲気、デザイン哲学、視覚的特徴。具体的な HEX・フォント・サイズを本文に含める。
**Key Characteristics:** として主要特徴を箇条書き。

## 2. Color Palette & Roles
### Primary / Accent Colors / Dark & Neutral / Interactive / Surface & Borders / Shadow Colors / Status
各セクションで HEX + 用途 + 出典（テーマ色なのかハードコードなのか）を明示。

## 3. Typography Rules
### Font Family (和文・英字それぞれ明記)
### Hierarchy (Level, Size, Weight, Font, Color, Use のテーブル)
### Principles

## 4. Component Stylings
### Title / Headline / Tag / Body / Lead / Callout / Buttons / Cards / Navigation / Forms / Images
各要素で 位置・サイズ・フォント・色・Bold 有無を具体値で記述。

## 5. Layout Principles
### Spacing System / Grid & Container / Whitespace Philosophy / Border Radius Scale

## 6. Depth & Elevation
シャドウ有無と使い所。フラットならその旨明記。

## 7. Do's and Don'ts
### Do / Don't
PPTX なら「F7F7F7 を塗りとして実装しない（透明ボックス＋淡色文字で実装する）」など、再現時の落とし穴を具体的に書く。

## 8. Responsive Behavior
### Breakpoints / Touch Targets / Collapsing Strategy / Image Behavior
PPTX なら Web 展開時の推奨値を記述。

## 9. Agent Prompt Guide
### Quick Color Reference
### Example Component Prompts (5本以上、具体値入りでそのまま使える形)
### Iteration Guide (番号付き、失敗パターンを予防する観点で書く)
```

---

## Important Rules

- **具体値で書く**: 「青系の色」ではなく `#023F73`。「大きめのフォント」ではなく `115pt`。
- **セマンティック命名**: HEX に加えて用途名も書く（`#353E49 (body ink, not pure black)`）。
- **実測主義**: CSS / XML から実際に抽出した値を書く。推測はセクション9の推奨値にのみ限定。
- **9セクション厳守**: どのソースでも同じ骨格で書く。
- **Agent Prompt Guide を充実させる**: 最低5本、そのままコピペで別デッキ／別UIが作れる粒度。
- **PPTX の場合は `scripts/analyze_pptx.py` を先に走らせてから執筆する**。スクリプト結果と自分の目視の両輪でまとめる。