# TASK-029 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 驗收結論

- 結論：`changes_requested`
- 下一位角色：Codex
- Branch：`codex/fix-line-login-state-continuity`
- Base commit：`196c2087a1bfdf816f16aafc267c7008aa376f41`
- Implementation commit：`c771961d2f777f9153a41ecef131d3623024c5cf`
- Codex completion commit／驗收前 HEAD：`7764f989a3fb720d0c35310e26d4b487655df902`
- Repository：驗收開始與測試完成後均乾淨

## 通過項目

- 10 分鐘 timed signature、專用 salt、URL encoding 與 invalid signature／expiration fail-closed 行為已實作。
- LINE token/profile requests 具有 10 秒 timeout、status/JSON/key error handling，安全錯誤不含上游 payload。
- 原有會員查詢、未核可頁面、管理者 allowlist 與 demo/deployment routes 未被移除。
- Work 重跑 52 項 Web Portal tests 全數通過；2 項既有 Windows make/sh tests 跳過。
- Compile、Python 3.10 grammar 與 `git diff --check` 通過。
- 未執行真實 LINE、production DB、Secret、部署、push、PR 或 merge。

## Blocking findings

### 1. Signed bearer state 未維持 login-CSRF／session-binding 邊界

目前 callback 只驗證 state 是伺服器在 10 分鐘內簽發，完全不再要求登入發起瀏覽器持有對應 session nonce。任何人都可從公開 `/line/login` 取得合法 state；攻擊者可使用自己的 LINE 帳號完成 authorization，再把尚未使用的 callback URL（code + state）交給另一個瀏覽器。該瀏覽器會建立「攻擊者帳號」的登入 session，形成 login CSRF／session swapping。

簽章只能防止 state 被偽造或修改，不能證明 callback 回到原本的 browser transaction。這與 TASK-029「不得降低 OAuth CSRF／state 邊界」衝突，因此不可接受或部署。

補正要求：不得僅靠可轉交的 signed state 建立登入 session。請提出並實作能把最終 session 建立重新綁回原始 browser transaction 的方案；若需要 shared one-time transaction store、跨瀏覽器確認 UI、LINE Console／callback 調整或其他產品取捨，先停止實作並在 report 中列為 Owner 決策，不得自行擴張 schema 或 production 設定。

### 2. Return-path validation 未涵蓋任務明列的 ambiguous inputs

`safe_return_path()` 目前只拒絕 scheme、netloc、`//` 與非 `/` 開頭字串，尚未拒絕反斜線與 ASCII control characters。瀏覽器／proxy 對 `/\\attacker.example`、encoded/backslash variants 或含控制字元路徑可能進行不同正規化；測試也未涵蓋 TASK-029 明列的這些案例。

補正要求：在 redirect 前以明確 allow contract 拒絕反斜線、控制字元與 ambiguous encoded separator；補上相對應單元與 route tests。

### 3. LINE profile 必要欄位僅檢查 key 存在

`access_token`、`userId` 與 `displayName` 目前可能是空字串或非字串，仍會進入 Authorization header 或 DB lookup。TASK-029 要求必要欄位 shape validation。

補正要求：要求 token 與 user ID 為非空字串；display name 至少必須是字串。無效 payload 應安全回 502，且不呼叫後續 HTTP／DB、不建立登入 session。

## Work 驗證證據

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 52 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
通過

ast.parse(..., feature_version=(3, 10))
通過

git diff --check 196c208..HEAD
通過
```

## 下一步

Codex 先補正 return-path 與 response-shape validation，並針對 login-CSRF blocking finding 提出安全、可離線驗證且不擴張 production/schema 範圍的方案。若無法同時達成「跨 browser continuity」與「原始 transaction binding」，應回報 `blocked` 並交由 Owner 選擇 UX／storage／LINE configuration 方案，不得以 signed bearer state 直接放行。
