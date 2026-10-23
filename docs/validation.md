# 第1段階の検証記録

実施日: 2026-10-23（日本時間）。Python 3.12.14 / PyYAML 6.0.3 / FFmpeg 7.1.5、Linux CPU環境。

| 実行内容 | 結果 |
|---|---|
| `python -m unittest discover -s tests -v` | 23件成功、失敗・skipなし |
| `python -m glass_fruit --config configs/prototype.yaml demo --output-dir outputs/prototype-verified` | 6.0秒、1080×1920、30fps、H.264/yuv420p + AAC、全編デコード成功 |
| `python -m glass_fruit demo --output-dir outputs/timeline-70s-verified` | 70.0秒、同サイズ・fps・コーデック、4シーン、全編デコード成功 |
| `python -m glass_fruit prompts` | イチゴ・リンゴ・ブドウ・スイカの順、計70秒のJSON計画を出力 |
| Actions YAMLのローカル構造確認 | `workflow_dispatch` のみ、`contents: read`、prototype / timeline-70s の2択 |
| `git diff --check` | 問題なし |

テストは、外部音声の正の遅延と負の前詰めをPCMの実サンプルで確認し、
元音声の保持、無音入力、複数ショット、切り出し開始位置、出力の上書き拒否も実行した。
尺不足、シーン不足、間隙、設定の不正値、有料モード、壊れたメディア、fps・解像度・尺の不一致は
失敗することを確認した。

生成物は**常時ラベル付きの合成テスト**。写実的なガラス果物の生成結果ではない。
動画・音声はGit管理対象外で、ここには検証結果だけを記録する。

GitHub Actionsをリモートで起動した結果ではない。GitHub側のActions権限・利用枠・
Artifactsの実ダウンロードは未検証。自動投稿・課金・生成APIリクエストはゼロ。
実写風イチゴ5〜10秒、実素材の完成70秒作品、視聴による品質承認は未実施。
研究資料の未確認項目は [比較レポート](provider-comparison.md) に明記。
