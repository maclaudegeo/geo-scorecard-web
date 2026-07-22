# GEO Scorecard 統一評分設計

**日期：** 2026-07-22
**狀態：** 已核准

## 目標

維持 GEO Dashboard 與 GEO Scorecard Web 現有介面、卡片格式及操作流程不變。Scorecard Web 的五個共同維度改用 Dashboard 現行評分方法，確保同一網址在兩個網站得到相同的維度分數。

驗收網址：`https://www.moreson.com.tw/moreson/`

## 評分範圍

兩個網站必須共用以下五個維度的資料來源與計算方式：

1. AI 平台準備度
2. 內容品質 E-E-A-T
3. 技術基礎
4. 品牌權威度
5. Schema 結構化資料

Dashboard 原有的 AI 實際能見度、AI 平台查詢、SOV 與引用來源分析保持不變，Scorecard Web 不執行這些項目。

## 架構

Dashboard 現行五維度評分邏輯是唯一標準。Scorecard Web 不再要求單一 Claude 呼叫自行產生五維度分數，而是呼叫相同評分函式取得結果，再轉換成現有卡片資料格式。

Scorecard Web 維持既有總分公式：

```text
GEO Score =
  AI 平台準備度 * 25% +
  內容品質 E-E-A-T * 25% +
  技術基礎 * 20% +
  品牌權威度 * 20% +
  Schema 結構化資料 * 10%
```

這個總分不與 Dashboard 含 AI 實際能見度的六維度綜合分數直接比較；驗收重點是五個共同維度逐項一致。

## 資料流程

1. Scorecard Web 接收網址。
2. 使用 Dashboard 相同的網站抓取、robots.txt、llms.txt、Schema、安全標頭與內容檢查。
3. 使用 Dashboard 相同的品牌權威度評分流程。
4. 將五個結果映射到 Scorecard Web 現有欄位。
5. 依既有五維度權重計算 Scorecard GEO Score。
6. 使用現有圖片產生器輸出兩張卡片。

## 一致性與穩定性

品牌權威度包含模型判斷，獨立重跑可能產生小幅差異。一次分析中的五維度結果必須先形成同一份評分快照，再供畫面與圖片共同使用，禁止同一工作重複評分。

若任一必要網站抓取或模型評分失敗，Scorecard Web 必須回報評分失敗，不得用 Claude 猜測值或零分靜默替代。

## 不修改項目

- Dashboard 前端與現有完整分析流程
- Scorecard Web 前端
- Scorecard 與 Analysis Card 視覺設計
- 下載流程與輸出檔名
- Dashboard 的 AI 實際能見度評分

## 驗收標準

以 `https://www.moreson.com.tw/moreson/` 測試時：

- 兩個網站的五個共同維度逐項一致。
- Scorecard Web 不呼叫 AI 實際能見度查詢。
- Scorecard Web 總分可由五個顯示分數依既定權重精確重算。
- 現有 Scorecard Web 測試全部通過。
- 兩張 PNG 可正常生成與下載。
