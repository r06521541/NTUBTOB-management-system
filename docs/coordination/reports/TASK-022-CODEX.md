# TASK-022 Codex Report

狀態：`ready_for_review`

## Git 與 PR

- Branch：`codex/harden-web-portal-build-boundary`
- Base commit：`a7f801b44e07d1d8518b9f8675e99b4743a98e00`
- Head commit：`ea61d20921db51941b9c6331d16d43168c9caca3`
- Draft PR：[#36](https://github.com/r06521541/NTUBTOB-management-system/pull/36)
- PR 狀態：open、draft、mergeable

## 實際修改

- 新增 Web Portal `.dockerignore`，排除 env、credential、cache、tests、coverage、virtualenv 與 local artifacts；保留 `dist/shared_lib-0.0.1.tar.gz`。
- `deploy-web-portal` 改為只產生過濾後的非機密 env file，排除 `DSN_PASSWORD`、`LINE_LOGIN_CHANNEL_SECRET` 與 `SECRET_KEY`，包含前置空白 key；shell trap 在成功或失敗後清理 temporary file。
- Make entry point 要求兩個明確 Secret resource/version references 與 40 字元 Git SHA；Cloud Build 另做 fail-closed 驗證。
- Cloud Run deploy 綁定三項 runtime Secret variables。DB reference 沿用已確認設定；LINE Login 與 session reference 只由必填 substitutions 提供，未猜測正式名稱。
- Docker build、push、deploy 與 Make substitution 統一使用 `${_IMAGE_TAG}`；Web Portal 維持 public，未加入任何 demo production gate。
- 新增六項 mutation-style deployment contract tests，並更新 Web Portal README 與 deployment runbook。

## 變更檔案

- `apps/web_portal/.dockerignore`
- `apps/web_portal/cloudbuild.yaml`
- `apps/web_portal/tests/test_deployment_contract.py`
- `apps/web_portal/README.md`
- `makes/deploy_apps.mk`
- `docs/operations/DEPLOYMENT_RUNBOOK.md`
- `docs/coordination/reports/TASK-022-CODEX.md`
- `docs/coordination/HANDOFF.yaml`

## 驗證證據

Python 3.10 GitHub Actions run `30991502368`、job `92258478858` 成功：

- CPython 3.10.20。
- Web Portal：25/25（含新增 contract tests）。
- Game broadcast：28/28。
- Notify cronjob：9/9。
- Scheduled deployment wrapper：11/11。
- Update game schedule：5/5。
- LINE webhook ingress：10/10。
- `git diff --check`：通過。

首次 CI run `30991398178` 因測試把允許的 DB Secret version `:latest` 誤判為 image `:latest` 而失敗；commit `ea61d20` 將 assertion 收窄至 image reference 後，最終完整 CI 通過。這不是部署設定失敗。

## 未執行與限制

- 本機沒有可用的 Python executable，因此本輪完整 unittest 證據來自 GitHub-hosted Python 3.10 runner。
- 未執行 Docker build、Cloud Build、`gcloud`、Cloud Run deploy 或 production request。
- 未讀取、列出、建立、修改或驗證 Secret／IAM／Scheduler；未接觸 production DB，未發送通知。
- 未驗證兩個待提供 Secret references 是否存在、runtime IAM 是否可存取、production callback/public boundary、目前 revision 或 rollback revision。
- 不涉及 application runtime code、shared library、schema、migration 或 dependencies。

## 待 Work 驗收

請 Work 查驗實際 diff、fail-closed substitutions、Docker ignore 語意、temporary env cleanup、public/demo boundary，以及最終 Python 3.10 CI。合併與任何 production deployment 仍需 Owner 另行批准。
