# /report 統一 GEO 評分設計

**日期：** 2026-07-22
**狀態：** 已核准

## 最終決策

GEO Dashboard（第一個網站）與 GEO Scorecard Web（第二個網站）的五個共同指標，全部改用 `/geo report` 定義的評分標準。兩個網站各自抓取與分析目標網站，不互相呼叫、不讀取對方結果。

第一個網站保留獨有的「AI 實際能見度」實測。第二個網站不執行 AI 實際能見度查詢。

## 共同評分標準

兩個網站必須用相同資料快照、相同檢核項目、相同計分函式產生以下原始分數：

1. **AI 平台準備度（0-100）**：依 `geo-platform-optimizer` 的 Google AI Overviews、ChatGPT、Perplexity、Gemini、Bing Copilot 明細評分後取平均。只採用可驗證的網站、Crawler、Schema、內容與外部來源訊號；無法驗證的項目不得猜分。
2. **內容品質 E-E-A-T（0-100）**：Experience、Expertise、Authoritativeness、Trustworthiness 各 25 分，逐項依 `geo-content` 表格加總，最後套用 topical-authority `-5` 至 `+10` 修正並封頂 100。
3. **技術基礎（0-100）**：依 `geo-technical` 八類計分：Crawlability 15、Indexability 12、Security 10、URL Structure 8、Mobile 10、Core Web Vitals 15、SSR 15、Page Speed 15。
4. **Schema（0-100）**：依 `geo-schema` 的 12 項檢核加總，包括 Organization/Person、sameAs、Article author、業務類型、WebSite/SearchAction、BreadcrumbList、JSON-LD、SSR、speakable、合法 Schema、knowsAbout、deprecated schema。
5. **品牌權威度（0-100）**：使用真實台灣市場搜尋證據，不由模型依訓練記憶估分。維持現有卡片四格：台灣媒體報導 40、外部內容深度 20、台灣社群口碑 20、實體辨識度 20。

## 台灣品牌權威資料

品牌搜尋使用繁體中文與台灣地區條件，品牌名稱及別名都要查詢：

- 台灣媒體：中央社、聯合新聞網、科技新報、數位時代、工商時報、經濟日報、天下、商業周刊、VOGUE Taiwan、ELLE Taiwan、POP Daily、GQ Taiwan、ETtoday、自由時報、Yahoo 奇摩新聞及產業媒體。
- 台灣社群：PTT、Dcard、Threads、Instagram、YouTube、Facebook。
- 本地實體：Google 商家與可驗證的第三方品牌資料。

媒體分數必須考慮來源層級、獨立報導篇數、日期與是否只是新聞稿轉載。內容深度只評外部報導的實質內容，不得拿品牌官網長度代替。社群只計第三方提及或可驗證互動，不因存在官方帳號就給滿分。實體辨識度比較官網、Schema 與外部來源中的名稱、業務、地址與聯絡資料是否一致。

搜尋服務失敗時必須標示資料不足並以已取得證據計分，不得要求 AI 補猜。搜尋結果須在單次分析內快取，四個品牌子分數使用同一份證據。

## 總分公式

第二個網站完全採 `/report`：

```text
GEO Score =
  AI 平台準備度 * 25% +
  內容品質 E-E-A-T * 25% +
  技術基礎 * 20% +
  Schema * 15% +
  品牌權威度 * 15%
```

第一個網站保留 AI 實際能見度 20%，其餘 `/report` 權重等比例縮為總計 80%：

```text
Dashboard GEO Score =
  AI 實際能見度 * 20% +
  AI 平台準備度 * 20% +
  內容品質 E-E-A-T * 20% +
  技術基礎 * 16% +
  Schema * 12% +
  品牌權威度 * 12%
```

## 架構與資料流

建立一份無網站框架依賴的 `report_scoring.py`，包含抓取快照、五項評分與台灣品牌搜尋。兩個 repository 各自包含完全相同的模組，以便獨立部署；跨 repository parity test 會防止兩份規則漂移。

每次分析流程：

1. 正規化網址與品牌名稱。
2. 抓首頁、robots.txt、llms.txt、sitemap 與最多 10 個代表性內頁。
3. 建立不可變的網站證據快照。
4. 執行 `/report` 五項評分及台灣品牌搜尋。
5. 第一個網站另行執行原有 AI 實際能見度。
6. 將同一份結果供網頁、PNG 與 PDF 使用，不重複評分。

## 不修改項目

- 第一個網站的 AI 實際能見度查詢、SOV 與引用來源功能。
- 兩個網站現有視覺設計、卡片版型、下載流程與公開操作方式。
- 兩個網站維持獨立部署，不建立站對站 API 依賴。

## 驗收標準

以 `https://www.moreson.com.tw/moreson/` 驗收：

- 兩個網站的五個共同原始分數完全一致。
- 每個分數均可回溯到 `/report` 的明確檢核項目與真實證據。
- Schema 必須識別原始 JSON-LD，也必須對錯誤大小寫、缺漏欄位與無效值扣分。
- 品牌權威必須有台灣媒體與社群搜尋結果；外部服務失敗不得改成 AI 猜分。
- 第一個網站仍能完成 AI 實際能見度分析。
- 第二個網站不呼叫 AI 實際能見度，也不需要 Claude API 才能評分。
- 第二個網站總分可由 `25/25/20/15/15` 精確重算；第一個可由六項權重精確重算。
- 兩個網站測試、PNG/PDF 產生與公開部署 smoke test 全部通過。

## 前提與要避的坑

- `/report` 有部分需要判斷的項目；實作時只能依已抓取證據套用明確區間，不能讓模型直接回傳總分。
- robots.txt 未列出特定 AI Bot 不等於主動允許，評分要區分「明確允許」與「未封鎖」。
- llms.txt 回傳結構、Schema `@type` 大小寫與 JSON-LD `@graph` 都要正確處理。
- 搜尋筆數不能直接當權威；同篇轉載、官方新聞稿及品牌自述要去重或降權。
