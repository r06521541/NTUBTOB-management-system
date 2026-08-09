# TASK-037 Work 驗收報告

驗收時間：2026-08-06（Asia/Taipei）

## 結論

- 結果：`accepted`
- Branch：`codex/task-036-deploy-roster`
- Base：`5187b89`
- Implementation：`bfa5494`
- Codex completion：`0d9e367`
- 下一位角色：Owner（決定是否批准 PR 工作包）

## 驗收結果

- LINE callback仍驗證LINE profile payload與LineUser／Member配對，但成功session只保存`user_id`與`member_id`。
- 一般request的legacy cleanup只移除精確`member`與`display_name`，沒有使用`session.clear()`；既有identity、OAuth nonce、return path、CSRF與demo keys均保留。
- `/attendance`沿用`member_required`，再以session中的正整數`member_id`取得fresh Member，不再依賴cookie內Member snapshot。
- Member不存在時只清除`user_id`／`member_id`並回403等待核可頁；Game、attendance與HTTP均未呼叫，不會redirect loop。
- 畸形session在Member lookup前fail closed；roster、admin allowlist、CSRF、OAuth state、versioned cookie與demo suites沒有退化。
- TASK-038 auto-login／manual fallback議題未混入本次diff。

## Work獨立驗證

```text
Web Portal tests: 65 passed, 2 existing Windows make/sh skips
compileall apps/web_portal: passed
Web Portal deployment dry-run: passed; no cloud or HTTP
git diff --check 5187b89..HEAD: passed
working tree before review docs: clean
bundled runtime used by Work: Python 3.12.13
Codex Python 3.10 AST grammar check: passed
```

## 尚未驗證與風險

- 尚未以實際Python 3.10 interpreter執行完整suite；須由PR hosted Python 3.10 CI補證據。
- Signed cookie內容仍不是加密；本任務只移除Member姓名與LINE display name，必要identity IDs仍可由browser持有者讀取。
- Attendance現在每個request增加一次Member lookup；未以production DB量測延遲，但相較既有Game與attendance查詢影響預期有限。
- `member_required`在其他protected route只驗證session shape，不做每次DB revalidation；正式停用／approval lifecycle留待RBAC任務。
- 未使用真實瀏覽器、LINE、production DB或Cloud Run；未部署、push、PR、修改Secret／IAM／schema或發送通知。

## 建議

接受TASK-037。Owner若批准PR工作包，可push目前branch、建立Draft PR並以hosted Python 3.10 CI補齊runtime證據；Work再查驗PR diff與CI。Merge與production deployment仍須分別批准。

## PR與merge結果

- Owner批准PR工作包，Draft PR #45建立成功。
- Hosted Python 3.10 CI run `31064853601`／job `92500338092`成功。
- Owner授權驗收通過後直接merge；PR #45已squash merge為`4b9ddd483a197d00a41403858efd36ff964e6e10`。
- 尚未部署production；TASK-037只完成repository merge。
