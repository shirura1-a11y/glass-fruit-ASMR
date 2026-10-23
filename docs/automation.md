# 無料のローカル自動編集と、公式APIの境界

2026-10-23（日本時間）。この機能はAPI契約・生成・投稿を行わない。

## Google Vids と代替API

Google Vidsの画面で生成できたことは、外部プログラム向けの生成APIが提供されている証拠にはならない。
今回 `https://developers.google.com/workspace/vids`、Gemini動画ガイド・料金、Runway料金の
公式本文を再取得しようとしたが、このクラウドの通信プロキシから403で拒否された。
**Google Vidsの公開AI動画生成APIの有無は今回の調査では確定できない。**
非公式の画面操作、Cookieの流用、内部エンドポイントの利用は実装しない。
Vidsで使えるアカウントの特典がGemini/CloudのAPI無料枠になるとは扱わない。

既存の[公式情報比較](provider-comparison.md)に記録された候補は以下。
これは既存記録からの参考値であり、今回の再確認済み料金や発注可能性ではない。

|公式API候補|既存調査にある音声・単価|70秒の単純換算|保留事項|
|---|---|---|---|
|Google Gemini現行動画モデル|既存記録のOmni 720p動画出力 約$0.10136/秒|約$7.10 + 入力等|現行モデルID・提供地域・認証・料金を再確認。古いVeo previewを固定しない|
|Runway経由Veo Fast|音声あり $0.15/秒|$10.50|モデル提供継続・生成尺・商用条件・実音を確認|
|Runway gen4.5|映像 $0.12/秒、音声別|$8.40 + 音声|硬質音は別途必要。縦720pからの拡大は画質向上ではない|

ショットの生成尺単位・編集余白・再生成・税・為替で増額する。
現行の4シーンを8秒単位で計画すると11ショット、生成依頼の想定合計は88秒。
既存単価でVeo Fastなら$13.20、gen4.5なら$10.56（音声別）が参考になるが、
8秒が各APIで選べるかを含めて契約前の再確認が必要。
APIの無料生成枠は確認できていない。ローカル処理は外部生成API費用ゼロ、
GitHub Actions/Artifactsは利用枠・保存量により有料になり得る。

必要な次の調査は、Vids公式ヘルプ/API一覧、Gemini動画ガイド・料金、
Vertex AIの現行Veoモデル仕様、Runwayのモデル別仕様・料金を通信可能な環境で再取得すること。
API採用前にはモデル、最大試行回数、1回の予算を提示し、ユーザーの事前承認を得る。
未確認モデルに接続するクライアントは追加していない。

## 果物指定とショット計画

```bash
source /workspace/.venvs/glass-fruit-asmr/bin/activate
cd /workspace/glass-fruit-ASMR
python -m glass_fruit plan > /tmp/fruit-shots.json
# 全ショットをリンゴ用に計画（計画のみ。config/素材構成は変更しない）
python -m glass_fruit plan --fruit apple --shot-seconds 8
```

標準はイチゴ15秒・リンゴ17秒・ブドウ17秒・スイカ21秒の70秒。
接触・破断・分離の異なる構図と硬質音のプロンプトを作る。計画は生成成功や音の品質を保証しない。
`--fruit` はプロンプトのみの指定で、編集タイムラインは `--config` の内容を使う。

## 今回のイチゴMP4を利用する

元動画はまだこの作業環境に届いていない。受領後、次のように配置する。
ファイル名順で使い、各シーンの最後だけ必要尺にトリムする。再利用ループ・静止延長はしない。

```text
assets/
  strawberry/01-vids.mp4
  strawberry/02-other-shot.mp4
  apple/01.mp4
  grapes/01.mp4
  watermelon/01.mp4
```

素材はGitへコミットしない。チェックアウト外のディレクトリを使うか、既存のignoredな
`outputs/assets` 配下を使う。Google Vidsから書き出した約10秒のMP4はそのまま入力可能。
標準タイムラインではイチゴが15秒なので、10秒素材なら追加で約5秒と他の果物素材が必要。
6秒の試作設定ならイチゴ1本から切り出して動作確認できる。

```bash
python -m glass_fruit prepare --assets outputs/assets --output-dir outputs/prepared-01 --audio-profile glass-bright
python -m glass_fruit assemble --manifest outputs/prepared-01/manifest.json --output outputs/finished-01.mp4
python -m glass_fruit validate outputs/finished-01.mp4
```

不足時は終了コード2。`asset-report.json` に不足秒数、`shot-plan.json` に計画を保存し、
不完全なマニフェストや完成動画を作らない。破損素材はエラーにし、無断でスキップしない。
出力ディレクトリは毎回新しい名前を指定する。

## 切断音の改善

`glass-bright` は180Hzの低域除去、3.2kHz付近の+4dB強調、ピークリミッター。
元映像を保持して音の濁りを減らし、高域の硬質感を強める任意のプリセット。
`original` が既定で、既存編集の音は変更しない。マニフェストの各クリップに
`"audio_profile": "glass-bright"` を指定しても使える。

**野菜の音を本物のガラス破断音に変換する機能ではない。** 自動的な意味的同期判定もない。
より良いガラス音を自作・利用許諾確認済みのWAVで用意した場合は、既存の `audio` と
`audio_offset` で差し替え・同期・同じEQ処理ができる。元音にガラス成分がなければ差し替えが適切。
AI生成する場合はショット計画の `audio_prompt` を使い、湿った咀嚼音・野菜音・音楽・声を抑制する。
自動検査だけでは自然さ・切断音の一致は保証できず、視聴確認が必要。

## GitHub Actionsで編集・取得

`.github/workflows/assemble-local.yml` は手動のみで、生成APIを呼ばない。
素材を一度渡せば、その後の素材検査・結合・技術検査・Artifactsへの保存を実行する。
入力は次のいずれか1つ。

1. GitHubのReleaseに、果物別フォルダを直下に入れた `fruit-assets.zip` を手動アップロードし、
   `source_release_tag` にそのタグを指定する。既存動画を使う試作は `configs/prototype.yaml` を選ぶ。
2. 同じリポジトリの別のワークフローがアップロードした `local-fruit-assets` artifactの実行IDを
   `source_run_id` に指定する。Artifactsのブラウザからの直接アップロード機能はない。

成功した実行のArtifactsから `glass-fruit-edit-<run_id>` をダウンロードする。
完成MP4と検査レポートが入る。不足時は完成MP4を作らず、不足レポートを残す。
既存の合成デモ用ワークフローは維持。Releaseへの自動公開やリモートActions起動は今回行っていない。
一度の素材アップロードは手動で、果物名だけから生成→完成までの全自動化は未達。
公式APIの仕様確認・事前の費用承認・認証設定・品質評価後に接続する必要がある。

## 今回の検証

- Python 3.12 / FFmpeg 7.1.5。既存23件と追加7件の計30件を実行。
- ショットの尺合計、4果物と単一果物指定、不足時の非生成、既存出力の保護、
  素材ディレクトリ外へのリンク拒否、EQの実サンプル変化・ピークと高低周波の比を検証。
- 合成素材を果物別フォルダへ配置し、`prepare` → `assemble` → 全編デコード検査を実行。
  70.0秒、1080×1920、30fps、H.264 + AAC、4シーン、`glass-bright`、検査成功。
  この70秒ファイルは画面に合成テストと表示したテスト用で、実写風の完成作品ではない。
- Actions YAMLの構文と手動トリガーのみであることをローカル確認。GitHub上の実行、
  Release入力取得、Artifactsダウンロード、ユーザーのイチゴ素材での品質は未検証。
- 公式サイト再調査はプロキシ403。API呼び出し・課金・契約・自動投稿はゼロ。
