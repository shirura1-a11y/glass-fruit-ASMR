# ZIP不要：スマートフォンからMP4を取り込む

動画の圧縮・ZIP作成・フォルダ分け・ローカルPython環境は不要。
スマートフォンのブラウザでMP4をReleaseに添付し、編集はGitHubのクラウドで実行する。
有料動画生成APIは使用しない。GitHub Actions/Artifactsの利用枠・保存量は別途アカウントで確認する。

## 最初のイチゴ動画を試す

1. [素材用Releaseを作る](https://github.com/shirura1-a11y/glass-fruit-ASMR/releases/new)。
   タグ名を例えば `fruit-inputs` にして、説明欄の下の添付欄からイチゴMP4を選び、Releaseを公開する。
   ファイル名は `VID_1234.MP4` のような名前のままでよい。既存の素材用Releaseがあれば編集して添付するだけ。
2. [編集用Actions](https://github.com/shirura1-a11y/glass-fruit-ASMR/actions/workflows/assemble-local.yml) を開き、
   **Run workflow** で以下を指定する。

   |入力欄|最初のイチゴ動画の値|
   |---|---|
   |source_run_id|空欄|
   |source_release_tag|`fruit-inputs`（実際のタグ名）|
   |fruit|`strawberry`|
   |config|`configs/prototype.yaml`（既定値：6秒の試作）|
   |audio_profile|`glass-bright` または元音の `original`|

3. 完了した実行の **Summary** を開く。取り込んだ本数、足りない素材、ダウンロード案内が表示される。
   **Artifacts → strawberry-6s-実行番号** をダウンロードし、`STRAWBERRY-6S.mp4` を再生する。
   検査レポートも必要なら `glass-fruit-edit-実行番号` を取得する。

スマートフォンで添付欄やRun workflowが見えない場合は、ブラウザの「デスクトップ用サイト」を試す。
GitHubの書き込み権限が必要。Artifactsの取得にはログインが必要になる。
**公開リポジトリのReleaseに添付すると素材も公開される。** 公開してよい素材のみ使用する。
Releaseの作成・素材の追加・Actionsの実行は、この実装作業では代行していない。

## 次回から

同じ `fruit-inputs` Releaseを編集してMP4を追加し、同じタグでActionsを再実行する。
ZIPの作り直しやReleaseの新規作成は不要。同名ファイルはGitHub側で重複添付できないので、必要なら名前を変える。

単一の果物なら `fruit` を選ぶだけでファイル名の変更も不要。
複数の果物を一緒に入れるときだけ、次のような先頭名を付ける。

|添付するMP4名の例|自動分類|
|---|---|
|`strawberry-01.mp4` / `いちご-01.mp4`|イチゴ|
|`apple-01.mp4` / `リンゴ-01.mp4`|リンゴ|
|`grapes-01.mp4` / `ブドウ-01.mp4`|ブドウ|
|`watermelon-01.mp4` / `スイカ-01.mp4`|スイカ|

先頭名と番号の区切りは `-`、`_`、半角スペース、`.`。果物名だけのファイル名も可。
判別できない名前はActionsの `fruit` に分類する。判別できる先頭名は `fruit` より優先する。
ファイル名順で読み込み、必要尺を超える最後の素材だけをトリムする。
古い不要素材を使いたくない場合はReleaseからその添付を削除するか、別の素材用Releaseを選ぶ。
取り込みの対応表はArtifacts内の `import-report.json` で確認できる。

## 70秒版

既定値はイチゴだけの6秒版。70秒版は明示的に `config.yaml` を選ぶと、イチゴ15秒・リンゴ17秒・ブドウ17秒・スイカ21秒を順に編集する。
複数の短いMP4を追加してよい。同じ短い素材を自動ループして尺を埋めることはしない。
約10秒のイチゴ素材だけでは70秒版は作れない。不足すると実行を失敗で止め、Summaryと
`asset-report.json` に果物別の不足秒数を残す。追加素材を同じReleaseへ添付して再実行する。

70秒版で `fruit=strawberry` を選んだ場合は、先に元音声の6秒版を独立して作成する。
70秒版が素材不足で失敗しても、作成済みの6秒版は `strawberry-6s-実行番号` に保存される。
6秒未満の素材しかない場合は6秒版も完成しない。音声設定の既定値 `original` は
元動画の音を使用し、差し替え・EQ・音楽追加をしない。最終AACへの再エンコードは行う。

## Actionsの実行画面へ直接添付できない理由

GitHubの `workflow_dispatch` 入力は文字列・選択肢・真偽値などで、ファイルアップロード型がない。
[公式ワークフロー構文](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions#onworkflow_dispatchinputs)
に沿い、標準のRelease添付と公式GitHub CLIを利用する。非公式なブラウザ操作や外部アップロードサービスは使わない。
Artifactsはダウンロード時にGitHub側でZIP化されるが、素材アップロード時にZIPを作る必要はない。

既存のZIP入力・別実行のArtifacts入力・編集コマンドは維持している。
今回は取り込みを簡略化したもので、果物指定だけによるAI映像生成は未実装。有料APIは禁止を維持する。

## 検証範囲

2026-10-23：既存30件を含む38件のテスト成功。スマートフォン形式のファイル名、
英語・日本語の果物分類、元データ保持、ZIP互換、危険なパス拒否、既存出力保護を確認。
MP4直接取り込み → 素材準備 → 6秒・1080×1920の合成テスト編集・全編デコードも成功。
ActionsのYAML・シェル・埋め込みPythonの構文を確認。実際のスマートフォン操作、
Releaseからのリモート取得とGitHub上のActions実行は未検証。ユーザーのイチゴ動画はまだ未受領。

## assets-001 の失敗調査と修正確認

実行39926005954の公開ページで `Prepare and assemble` の終了コード2を確認。
詳細ログはサインインが必要で、今回の環境からのGitHub APIアクセスも403のため取得できなかった。
Release `assets-001` の `default.mp4` は取得できた。旧既定値の `config.yaml` でローカル再現すると
イチゴ5秒、リンゴ17秒、ブドウ17秒、スイカ21秒不足し、同じ終了コード2になった。
MP4の破損や音声欠落ではなく、70秒タイムラインに対する素材不足が再現原因。

同じ実素材で6.0秒・1080×1920・30fps・H.264/AACの編集と全編デコードに成功。
元音声と出力の最初の6秒のモノラルPCM波形相関は0.998978。差し替え・EQは未使用。
既定値を6秒版に変更し、70秒版の不足が独立した6秒成果物を消さない回帰テストを追加した。
ArtifactsのダウンロードはGitHub標準のZIP形式で、中にMP4が入る。
