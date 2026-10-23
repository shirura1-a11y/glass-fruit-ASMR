# 無料・オフラインで開発する

この段階には生成APIクライアント、課金処理、自動投稿機能はない。APIキーも不要。
`enable_paid_api: true` や予算ゼロ以外の設定はすべてのCLIコマンドでエラーになる。
ネットワーク通信を行うのは依存関係の取得と、別途行う公式ドキュメントの調査だけ。

## 導入

Python 3.12 と FFmpeg / ffprobe が必要。FFmpeg は H.264 (`libx264`)、AAC、
`drawtext` フィルタとフォントを含むものを使う。Debian/Ubuntu の `ffmpeg` パッケージで確認。
GPUは不要。変換のエンコーダスレッド数は2。ローカルで完結する。

```bash
cd glass-fruit-ASMR
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

用意済みクラウド環境では `source /workspace/.venvs/glass-fruit-asmr/bin/activate` でもよい。
コマンドはすべてリポジトリのルートから実行する。

## プロンプトと6秒の動作確認

```bash
python -m glass_fruit --config configs/prototype.yaml prompts
python -m glass_fruit --config configs/prototype.yaml demo --output-dir outputs/prototype-01
python -m glass_fruit --config configs/prototype.yaml validate outputs/prototype-01/SYNTHETIC-DEMO.mp4
```

`demo` は単色のテストパターンとテスト音を作り、画面に
`SYNTHETIC TEST - NOT AI FOOTAGE` と常時表示する。実写風のイチゴでもASMR完成品でもない。
プロトタイプの尺・コーデックの確認用。実際の映像品質を承認する材料にはしない。
出力先は新しいディレクトリを指定する。既存ディレクトリは上書きしない。

```bash
# 4シーン・70秒の編集処理のみを確認（完成動画ではない）
python -m glass_fruit demo --output-dir outputs/timeline-01
```

各シーンを別の色・音で作り、実素材と同じ編集経路を通す。
出力MP4、設定に対応する素材マニフェスト、合成素材、検査レポートが残る。
`outputs/` と動画・音声は Git 管理対象外。

## 利用許諾を確認したローカル素材を編集する

6秒のマニフェスト例は [manifest.example.json](manifest.example.json)。
パスはマニフェストが置かれたディレクトリからの相対パス、またはローカル絶対パス。
例のパスはプレースホルダーなので手持ちの素材に置き換える。
HTTP URLやネットワーク上のプレイリストは入力に使わない。FFmpegの入力プロトコルも `file,pipe` に制限。

```bash
python -m glass_fruit --config configs/prototype.yaml assemble \
  --manifest docs/manifest.example.json --output outputs/strawberry-edit.mp4
```

- `scenes` は設定と同じ順序・果物にする。各シーンの `clips` は1件以上。
- `video`: 必須。`video_start`: 元動画の切り出し開始秒、既定0。
- `duration`: 必須。編集に使う秒数。各クリップの尺とシーン境界はフレーム単位に合わせる。
- `audio`: 任意の外部音声。省略時は元動画の音声を保持し、音声がなければ無音。
- `audio_offset`: 切り出した動画に対する秒数。正なら音を遅らせ、負なら音声冒頭を削る。
  外部音声は元ファイルの先頭、元動画音声は `video_start` からを基準にする。
- 各シーン内の `duration` の合計はそのシーンの尺と一致させる。
  15〜21秒のシーンには異なる短いショットを複数配置できる。自動ループ・静止延長はしない。
- 映像が短すぎる場合は失敗する。音声の余りは切り、足りない末尾は無音で埋める。
  動作音が映像と一致するかは人が視聴して調整する。自動の意味的同期判定は未実装。
- アスペクト比は保持して中央に配置し、余白を追加する。縦型への変換は画質向上を保証しない。
- 既存の出力MP4/レポートは上書きしない。失敗時の中間ファイルは一時ディレクトリごと削除する。

結合はフレームレート・サイズ・音声形式を揃えた中間MOV（H.264 + PCM）で行う。
ミリ秒単位のタイムベースで結合時にフレームレートがずれる問題を避け、最終AAC化は結合後の1回だけ。

## 検査の範囲

`validate` は1本のH.264/yuv420p映像と1本のAAC音声、サイズ、fps、予定尺、
音声と映像の長さ・開始時刻を調べ、全編をデコードする。失敗は終了コード1。
レポートの `visual_quality_reviewed: false` は、リアリティ、切断動作、音の内容、
権利やTikTok収益化適格性を自動判定していないことを示す。
単体の `validate` は入力を検査してJSONを標準出力に出すだけで、合成素材かどうかを推測しない。

## GitHubから動画を取得する

コミットしたワークフローは手動の `workflow_dispatch` 専用。pushや毎日の定時実行はない。
GitHub → Actions → **Offline media checks and synthetic demo** → **Run workflow**。
`prototype`（6秒）または `timeline-70s`（70秒の合成テスト）を選ぶ。
完了後、その実行の **Artifacts** から `SYNTHETIC-NOT-AI-FOOTAGE-...` をダウンロードし、
ZIP内の `demo/SYNTHETIC-DEMO.mp4` を再生する。保存期間は7日。
ダウンロードにはリポジトリへのアクセス権が必要。

生成APIのSecretsや投稿権限は使用しない。成果物をコミットしたりReleaseとして公開したりもしない。
GitHub Actions/Artifactsはリポジトリ種別やアカウントの枠を超えると料金が発生し得るため、
実行前に自身のActions利用枠を確認する。この開発作業ではリモートActionsは起動しない。

## 未完成の部分

実写風AI切断映像、生成API接続、素材の商用利用確認、意味的な音声同期、
最終70秒の制作と視聴確認、公開・ダウンロードのリモート実行確認は未完了。
まず無料で用意できる適法な素材で編集できる。今後も有料APIは許可されるまで使わない。
