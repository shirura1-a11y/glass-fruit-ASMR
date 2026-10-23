# 動画生成サービス・TikTok条件の一次情報調査

調査日: **2026-10-23（日本時間）**。生成APIの呼び出し、契約、購入、無料枠の消費は行っていない。
取得した公式ページの記述と公開SDKを比較した。単価はUSD、税・為替・再生成・入力料金等は別。
取得状況と参照ファイルのSHA-256は [research-sources.json](research-sources.json) に記録。

## 現時点の判断

- **有料APIは使わない。** この段階で完成させるのはローカル編集・プロンプト・技術検査・手動CIの土台。
- 公式の現在の案内では **Gemini APIのVeo 3.1 Previewは2026-10-22に終了** [G1]。
  `veo-3.1-generate-preview` などを使う古いサンプルは採用しない。
  Googleは `gemini-omni-1.1-flash` または別のCloud経由GAモデルへの移行を案内している。
  SDKに旧モデルの例が残っていてもサービス提供の証明にはしない。
- ネイティブな効果音付きの候補はGoogleの現行動画モデルやRunway経由のVeo。
  実際のガラス切断の物理表現・音の一致は未評価。モデルやプロンプトだけで品質を保証できない。
- **Kling直販の仕様・商用条件と、Creator Rewardsの最新の参加要件は確認が残る。**
  通信制限、または本文を返さないページがあり、調査全体が完了したとは扱わない。
  数値や利用権を推測してAPIを選定しない。

## API・費用・音声の比較

| 候補/経路 | 確認できた仕様 | 公式表示価格 | 無料枠・制約 | このプロジェクトとの関係 |
|---|---|---|---|---|
| Runway `gen4.5` [R1,R2] | text-to-video。2〜10秒の整数。`720:1280` / `1280:720`。公開型定義に音声生成の切替はない | 12 credits/秒、1 credit = $0.01 → $0.12/秒 | APIの無料生成枠は今回の料金資料から確認できず。WebアプリのFreeプランとは別に扱う | 6秒の映像で名目$0.72。1080×1920への拡大は可能だが、元の解像度や切断音の品質は別問題 |
| Runway経由 `veo3.1` / `veo3.1_fast` [R1,R2] | 公開型定義は4/6/8秒。縦 `720:1280` / `1080:1920`。`audio` あり | 通常: 音あり$0.40/秒、なし$0.20/秒。Fast: 音あり$0.15/秒、なし$0.10/秒 | 有料。エンドポイントの実稼働・アカウントごとのアクセスは未検証 | 6秒の音ありは通常$2.40 / Fast $0.90。Google直販とは別の経路・料金・提供状況 |
| Kling直販 [K1,K2] | 公式ドキュメントへの接続が403で拒否され、現行モデル・認証・尺・解像度を未確認 | **未確認** | Webの無料ポイントがAPIに使えるとは確認できない | 採用保留。公式条件が確認できるまでAPIキーの要求や連携をしない |
| KlingモデルをRunway経由で使う場合 [R1] | Runwayの料金表に `kling3.0_standard` / `kling3.0_pro` の音あり/なしが掲載 | standard: $0.09/秒（なし）/$0.13/秒（あり）。pro: $0.12/$0.17 | **Kling直販の料金・無料枠ではない**。詳細API仕様・権利条件は別途確認 | 比較の参考のみ。値段が分かることだけで採用しない |
| Google Gemini API Veo 3.1 Preview [G1] | 2026-10-22に終了した旨が公式ガイドに記載 | 現行のGemini APIの選択肢として旧価格を案内しない | 旧モデルを新規実装に固定しない | Cloud経由GAと混同しない |
| Google Gemini API `gemini-omni-1.1-flash` [G1,G2,G3] | Interactions API。9:16指定、既定720p、1080p/4Kはアップスケール。動画と音声を生成。SynthIDあり。アップロード音声参照は未対応 | 入力$1.50/100万token。動画出力$17.50/100万token。720pは5,792 token/秒 ≒ **$0.10136/秒** | 動画のFree TierはNot available。AI Studioでの試用案内をAPI無料枠と解釈しない | 6秒相当の720p出力だけなら約$0.61。ただし初回生成の実際の尺・入力料・高解像度料は別。音楽・声を出さない指示が必要 |

名目70秒に単価を掛けると、Runway gen4.5は$8.40、Runway経由Veo Fast音ありは$10.50、
Google Omni 720p動画出力は約$7.10。**これは見積りの下限に近い単純計算で、70秒制作の請求額ではない。**
モデルの生成尺単位、カットの余白、失敗・品質不合格の再生成、入力素材、税金等を含まない。
4シーンを同じ短い動画のループで埋めないため、使える異なるショットを複数用意する必要がある。
今回の生成API使用料金は **$0（呼び出しゼロ）**。

Google Cloud側の料金ページ [G5] は取得できたが、取得した表ではVeoの単位が
`/ 1 count` と表示され、モデル仕様ページ [G6] は接続拒否。
この表示だけを「1秒」と読み替えてCloud経由の試算を断定しない。
Googleの経路間で価格・認証・利用条件を混同しない。

## 商用利用・権利

| 公式情報 | 確認した内容と未確認事項 |
|---|---|
| Runway Help Center [R3] | Runway側から非商用限定の制限を課さず、作成物の権利を利用者が保持し、クレジット表記を要求しないと説明。詳細は利用規約参照。入力素材・音声の第三者権利や、他社モデルをAPI経由で使う条件の追加確認は必要 |
| Google Gemini API追加規約 [G4] | Googleは生成物の所有権を主張しない。生成物が他人と類似する可能性、法令遵守、使用に対する利用者の責任を明記。これを独占的な著作権や第三者権利非侵害の保証とは解釈しない |
| Googleのデータ利用 [G4] | Unpaid Servicesの入出力はサービス改善等に使われ得る。Paid Servicesの取扱いと区別する。非公開素材を無条件に無料サービスへ送らない |
| Kling直販 [K1,K2] | 本文を取得できず、出力の商用利用、透かし、再配布、プラン差は未確認。未確認を許諾済みと扱わない |

この段階ではサービス契約も素材のアップロードも行わない。第三者の既存動画・効果音をダウンロードして
本作の素材に流用する処理もない。合成テストの色・文字・正弦波は自前の動作確認用。

## TikTokのAI表示・Creator Rewards

現行の公式Community Guidelines本文 [T1] を取得できた。リアルに見える場面や人物を含む
AI生成・大幅編集コンテンツにはラベルを求める旨を確認。
写実的なガラス果物映像も、投稿時にAI生成であることを明示する前提で制作する。
ラベルは収益化資格や権利処理を保証しない。再利用素材に新しい要素がない場合のFYF不適格の説明もある。

AI生成ヘルプ [T2] とCreator Rewardsヘルプ [T3] はHTTP 200だったが、
実体はTikTok SupportのJavaScriptシェルで記事本文が含まれていなかった。
Creator Academyへのリンクもトップページへ転送された [T4]。
**HTTP 200だけをもって参加要件の確認済みとはしない。**

公開・収益化の前に以下を公式本文とアカウント内の表示で確認する必要がある。

- 日本での対象地域・年齢・アカウント種別・良好な状態の条件
- フォロワー数、直近の再生数、申請時点、対象動画の最低時間・適格再生
- オリジナルで高品質なコンテンツの定義、ループ・静止画・再利用素材の扱い
- AI生成コンテンツの対象可否、AIラベルの操作、報酬算定に関する除外

本作を70秒にすることだけでCreator Rewardsの対象になるとは断言しない。
参加条件の具体的な数値を、取得できない現行ページの代わりに古い記憶から埋めない。
自動投稿・アカウント接続・収益化申請は実装も実行もしない。

## 次の判断

1. 公式資料の未確認項目を解消する。必要ドメインは環境設定の下書きに追加済み。
   保存・公開と通信の再確認が必要。特にKling直販とCreator Rewardsは未完了。
2. 利用許諾のある手持ち素材で、無料のローカル編集と音の位置調整を試せる。
3. 実写風のイチゴ5〜10秒の生成試作は**未制作**。有料APIの使用禁止は継続する。
   無料で使える適法な実素材がなければ、ここで実写風の生成動画を作ったとは報告しない。
4. 将来、ユーザーが方針を変更して費用と品質を承認した場合に限り、別の開発で生成APIを導入する。
   その際も1試作の予算・最大試行回数を先に定める。現コードには再試行もAPIクライアントもない。
5. 実素材の70秒制作とGitHub上でのartifact取得は、その後に検証する。
   今回確認した70秒ファイルは常時ラベル付きの**合成テスト**であり、完成作品ではない。

## 一次情報リンク

- [R1: Runway API Pricing](https://docs.dev.runwayml.com/guides/pricing/)
- [R2: Runway公式Python SDKのtext-to-video入力型](https://github.com/runwayml/sdk-python/blob/main/src/runwayml/types/text_to_video_create_params.py)
- [R3: Runway商用利用の公式FAQ](https://help.runwayml.com/hc/en-us/articles/21668707517587-Can-I-use-the-content-I-made-in-Runway-for-commercial-purposes)
- [G1: Gemini API Videoガイド・Veo終了案内](https://ai.google.dev/gemini-api/docs/video)
- [G2: Gemini API料金](https://ai.google.dev/gemini-api/docs/pricing)
- [G3: Gemini Omni Flashの仕様](https://ai.google.dev/gemini-api/docs/omni)
- [G4: Gemini API追加規約](https://ai.google.dev/gemini-api/terms)
- [G5: Google Cloud生成AI料金](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing)
- [G6: Cloud側Veo 3.1モデル仕様・接続拒否](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate)
- [K1: Kling公式APIドキュメント・接続拒否](https://app.klingai.com/global/dev/document-api/quickStart/productIntroduction/overview)
- [K2: Kling公式API料金案内・接続拒否](https://app.klingai.com/global/dev/document-api/productBilling/prePaidResourcePackage)
- [T1: TikTok Integrity and Authenticity](https://www.tiktok.com/safety/en/policies-and-engagement/integrity-authenticity)
- [T2: TikTok AI生成コンテンツのヘルプ・本文未取得](https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content)
- [T3: Creator Rewardsヘルプ・本文未取得](https://support.tiktok.com/en/business-and-creator/creator-rewards-program/creator-rewards-program)
- [T4: Creator Portalの旧リンク・トップページへ転送](https://www.tiktok.com/creators/creator-portal/en-us/getting-paid-to-create/creator-rewards-program/)
