# Glass Fruit ASMR

TikTok向けの実写風ガラス果物ASMR動画の自動制作プロジェクト。

## 目標
- 65〜75秒、縦型9:16、目標1080×1920
- 透明なガラスのイチゴ、リンゴ、ブドウ、スイカ等を自然な動きで切断
- ナレーション・BGMなし、切断音中心
- 短い動画の単純ループではなく複数の展開で構成
- Python + FFmpegで結合・音声同期・品質検査
- 低スペックPCを考慮してクラウド実行を優先
- 完成MP4はGitHub ReleasesまたはActions artifactsで取得
- 費用と商用利用条件を確認した上で動画生成APIを採用

## 第1号
70秒を目標に、イチゴ(0〜15秒)、リンゴ(15〜32秒)、ブドウ(32〜49秒)、スイカ(49〜70秒)を題材とする。

## 開発順序
1. 動画生成サービスのAPI、料金、無料枠、音声生成、商用利用、TikTok規約の現状を一次情報で調査
2. 5〜10秒の本物の切断映像で品質・費用を検証（課金前に承認）
3. Python/FFmpegの編集・結合・検証パイプラインを実装
4. 第1号70秒の制作とダウンロードの動作確認
5. 良好なら日次制作へ拡張

## 安全設定
**有料API実行、契約、課金、自動投稿はユーザーの事前承認があるまで禁止。**
APIキーをコミットしないこと。既存のずんだもん関連リポジトリには一切アクセス・変更しないこと。
ダミー動画を実写級の生成結果と偽らないこと。

## 現状
第1段階のオフライン編集基盤を実装。**実写風AI映像・完成70秒動画・API連携は未実装。**

- [公式情報の比較・費用・未確認事項](docs/provider-comparison.md)
- [導入・使い方・マニフェスト・Actionsからの取得方法](docs/development.md)
- Python + FFmpegで複数ショットの結合、元音声の保持、外部音声の位置調整、解像度・尺・fps・全編デコード検査
- 画面に明示する合成テスト動画を6秒または70秒で作成可能（実写風の生成結果ではない）
- 手動GitHub Actionsでテストと合成デモを実行し、MP4をArtifactsとして取得可能
- 有料APIクライアント・自動投稿なし。APIキー不要

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m glass_fruit --config configs/prototype.yaml prompts
python -m glass_fruit --config configs/prototype.yaml demo --output-dir outputs/prototype-01
```

必要なシステムツール: FFmpeg / ffprobe（libx264・AAC・drawtext対応）。
GitHub Actionsは手動実行のみで、自動実行しない。利用枠・料金を確認してから実行する。
Kling直販の条件とCreator Rewardsの現行参加要件は公式本文の確認が残っている。

## 素材取り込み・音声改善の自動化

ショット別プロンプト、不足素材の秒数報告、任意の硬質音EQ、実素材のActions編集・Artifacts取得を追加。
[手順・API調査の制約・参考費用](docs/automation.md)を参照。生成API呼び出しは未実装、有料利用は事前承認が必要。

MP4はZIPにせず、そのままGitHub Releaseへ添付して取り込めます。
[スマートフォン向け取り込み手順](docs/upload-guide.md)を参照してください。

[7種類×10秒のYouTube Shorts制作](docs/shorts-seven.md)に対応。
既存イチゴと残り6種類を同じReleaseへ追加し、専用Actionsで不足確認・70秒結合・Artifacts保存を実行できます。
