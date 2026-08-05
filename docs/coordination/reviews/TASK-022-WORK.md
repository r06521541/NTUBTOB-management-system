# TASK-022 Work Review

日期：2026-08-05
結論：`changes_requested`
Branch：`codex/harden-web-portal-build-boundary`
驗收HEAD：`ad074c657fe0f187355bb968a623129f213663d7`
Draft PR：[#36](https://github.com/r06521541/NTUBTOB-management-system/pull/36)

## 已通過項目

- Working tree乾淨；PR open／draft／mergeable，Python 3.10 final Codex-head run `30991661459`成功。
- `.dockerignore`排除env、credential、cache、tests與local artifacts，未排除shared library artifact。
- Temporary env使用前置空白相容filter排除`DSN_PASSWORD`、`LINE_LOGIN_CHANNEL_SECRET`與`SECRET_KEY`。
- Cloud Run設定三項runtime Secret bindings；未知LINE Login／session references由substitutions提供，未硬編碼猜測名稱。
- Docker build／push／deploy均使用`${_IMAGE_TAG}`，Web Portal維持public且未開啟production demo gates。
- 修改範圍沒有application runtime code、shared library、schema或其他服務deployment config；沒有build、gcloud、deployment、Secret／IAM或production操作。

## Blocking findings

### 1. Temporary env cleanup在切換目錄後刪除錯誤路徑

`deploy-web-portal`在repository root設定：

```sh
trap 'rm -f apps/${DIR_WEB_PORTAL}/.env.yaml' EXIT
```

但同一shell之後執行`cd apps/${DIR_WEB_PORTAL} && gcloud ...`。Shell在exit trap執行時仍位於`apps/web_portal`，因此trap會嘗試刪除`apps/web_portal/apps/web_portal/.env.yaml`，實際temporary env仍留在原處。這同時違反TASK-022成功／失敗均清理的要求，且現有contract tests沒有捕捉cwd變化。

必須使用不受`cd`影響的已解析absolute path，或把`cd/gcloud`放進會回到原cwd的subshell，再確保成功與失敗都清理正確檔案。新增回歸測試，不能只搜尋`trap`字樣；至少要能辨識cleanup target不受後續`cd`影響。

### 2. Secret reference local preflight不足，畸形值仍會啟動Cloud Build

Make target只執行`test -n`。以下值都會通過local preflight並呼叫`gcloud builds submit`：

- `${_PLACEHOLDER}`
- `:latest`
- `secret:`
- `secret:latest:extra`
- 含空白或`=`的值

Cloud Build內validation雖拒絕部分值，但它只要求「包含冒號」，因此`:latest`、`secret:`與多冒號仍會通過；更重要的是，TASK-022要求repository deployment entry point在Cloud Build前fail closed，不能用已建立remote build作為第一道完整validation。

必須在Make entry point於`make build-shared-lib`與`gcloud`之前，對兩個reference執行一致的保守validation：非placeholder、無空白／`=`、exactly one delimiter colon、resource與version均非空。Cloud Build validation也要保留同等防線。新增mutation／fixture tests證明上述invalid examples都在任何build／gcloud command前被拒絕。

## 必要補測

- Cleanup在gcloud成功與失敗、且command曾切換cwd時，均指向真正`apps/web_portal/.env.yaml`。
- 兩個Secret reference的missing、blank、placeholder、leading／trailing colon、multiple colons、space與equals都fail closed。
- Invalid reference不得到達`make build-shared-lib`、`gcloud builds submit`或任何Cloud Build step。
- 修正後重跑Web Portal完整suite與其餘五個既有suites、compile／diff check及Python 3.10 CI。

## 安全邊界

補正仍只限repository、offline tests與同一Draft PR；不得執行Docker／Cloud Build、gcloud、deployment、Secret／IAM查詢、production request、通知、production DB或schema操作。

## 下一步

交回Codex補正同一PR #36。完成後更新Codex report與HANDOFF為`ready_for_review / work`，再由Work重新驗收。

## 第二輪驗收（HEAD `a180530`）

結論：`accepted`

兩項blocking均已補正：

- `gcloud builds submit`改在subshell內切換目錄，EXIT trap維持repository-root cwd並清除真正的`apps/web_portal/.env.yaml`。
- Make local preflight與Cloud Build defense-in-depth均使用保守`resource:version` grammar，要求resource／version非空、exactly one colon，並拒絕placeholder、空白、`=`及額外colon。
- 新增executable Make fixtures，證明兩個Secret references的invalid examples均在`build-shared-lib`與`gcloud`前停止。
- 新增fake `gcloud`成功／失敗fixtures，實際切換cwd後都確認temporary env被刪除。

Work使用workspace bundled CPython 3.12.13重跑：Web Portal 27項中25項通過、2項因Windows缺少`make`／`sh`而按設計skip；webhook 10/10、game 28/28、notify 9/9、schedule 5/5、wrapper 11/11均通過，完整`git diff --check`通過。Linux GitHub-hosted Python 3.10 final Codex-head run `30992571090`／job `92261893941`成功並實際執行Web Portal 27/27，包含兩項本機skip的executable regressions。

PR #36為open／draft／mergeable，remote head與本機`a180530057abf1bef3b4b71889f5d9c818f875b5`一致；working tree乾淨。沒有執行Docker／Cloud Build、gcloud、deployment、Secret／IAM或production操作。

## 最終結論

`accepted`。等待Work驗收commit的Python 3.10 CI成功後，交由Owner決定是否將PR #36標記ready並merge。Merge不代表Web Portal deployment、Secret reference設定或Secret IAM授權。
