# TASK-084：Phase C identity maintenance 正式啟用與完整收尾

## 目標

以單一任務完成 Phase C 尚餘工作：建立可重現的 identity-maintenance readiness／execution／rollback 工具與文件，取得 production 唯讀證據，啟用 Web Portal identity maintenance，執行一組不影響最後管理者、Member 關係、有效球員資格或通知的可恢復受控 mutation，驗證 audit／idempotency／cross-model consistency，最後留下正式 Phase C closeout。

本任務採「單一 TASK、多個明確 gate」。不得為 readiness、inventory、flag activation、mutation smoke 或 closeout 再拆新 TASK；遇到需要 Owner 精確批准的 production boundary 時，在 TASK-084 內停下取得批准後繼續。

## 已確認基準

- Base commit：`611fb38e13f45c68acdf7a14ce9064bd36d931eb`。
- Production schema：`0004_phase_c_identity_lifecycle`。
- Phase B 已完成：197 People、56 LINE identities、56 active `team_player`、309 append-only audits；此為歷史驗證基準，執行時須 fresh inventory，不可硬編為當下事實。
- TASK-082 已完成三服務 Phase C activation：Web Portal、LINE webhook、notify cron 均 Phase C=true、freeze=false、100% traffic；Web Portal identity maintenance=false。
- TASK-083 已修正 regional scheduled-service build resume；本任務不需重新部署 notify 或其他 Phase C source。
- 目前可執行 identity mutation 的正式入口只允許 active allowlisted admin，並受 LINE session、CSRF、reason、request ID、last-admin、audit 與 maintenance gate 約束。

## 完成定義

只有同時達成下列事項，才可宣告 Phase C 完成：

1. 三個 Phase C services 維持一致的 all-on／all-unfrozen 狀態，maintenance 啟用前後均無 runtime drift。
2. 至少一位可登入、active、linked 且仍受 admin allowlist 保護的管理 principal 經唯讀證據確認；不得在 smoke 中修改該 principal。
3. Production identity drift、schema revision、audit uniqueness、qualification 關係與 legacy mapping gates 通過。
4. Web Portal identity maintenance 已在精確 candidate revision 上啟用、核對後才承接 100% traffic；其他服務不部署。
5. 一組 Owner 核准的受控 mutation 與其恢復動作成功，最終業務狀態回到原值；append-only audit 保留且精確符合預期。
6. 同一 request ID 重試不重複寫入；不同 request ID 的恢復操作可稽核。
7. 沒有最後 admin 失效、Member remap、有效 `team_player` 撤銷／暗中恢復、通知副作用、重複 audit、cross-model drift 或敏感 log。
8. 自然 Scheduler／真實被動流量若存在則記錄聚合證據；沒有流量時不得以空等時間冒充成功。不得人工 invoke Scheduler、webhook 或通知補證。
9. Phase C closeout 文件明確記錄 final revisions、flags、受控 mutation 類型、去識別化 before／after classification、audit counts、rollback boundary 與未驗證事項。

## Stage A：repository／local readiness

Codex 先完成 repository-only 工作，不接觸 production：

1. 盤點 identity maintenance route、repository/domain、templates、drift detector、deployment wrapper、flag state machine、audit／idempotency與 last-admin tests。
2. 建立或補強一個 fail-closed Phase C closeout verifier／manifest，固定且只接受去識別化欄位：
   - schema revision與 Phase C vector；
   - admin principal count／candidate classification，不保存 LINE user ID、Member ID、Person ID、姓名或頭像；
   - identity status分類與 counts；
   - Member／Person／identity／qualification drift counts；
   - audit count、request-ID uniqueness與目標 action counts；
   - serving revisions、traffic、IAM classification與 maintenance flag；
   - mutation candidate capability flags，不保存候選真實識別資料。
3. 固定 production 唯讀 inventory SQL／metadata commands、checksum、strict validator 與 before／after compare contract。優先重用 `TASK-068-identity-drift-inventory.sql`；若需新 SQL，只能 SELECT，不得建立 temp／function／table 或修改 session 外狀態。
4. 建立 execution runbook，包含 exact pre-check → maintenance candidate → verify/promote → bounded mutation → idempotent retry → recovery mutation → post-check → closeout 流程。
5. 建立 offline fake PostgreSQL／HTTP／gcloud tests，涵蓋成功與 fail-closed cases。

## Stage B：production 唯讀 readiness

Stage A 經 Work review、唯一 ready PR 與 hosted CI 合併後，Work 才提出精確唯讀 inventory package給 Owner。唯讀盤點至少確認：

- gcloud account／project／region guard；
- 三服務 final revisions、Ready、100% traffic、Phase C=true、freeze=false；
- Web Portal maintenance=false、public IAM與 exact Secret binding metadata；不讀值；
- production revision `0004_phase_c_identity_lifecycle`；
- active／linked allowlisted admin principal count至少1，並確認 smoke不會觸碰最後 admin；
- drift detector與 audit／qualification invariants通過；
- 最近一次自然 Scheduler execution及其聚合 error classification；若 activation後尚無執行，記為 unavailable，不人工觸發；
- 安全 mutation候選的去識別化分類。

## 受控 mutation 候選規則

候選只可依下列順序選擇：

1. 既有 pending／unlinked、非目前登入、非 allowlisted admin、未連 Member、沒有 active qualification 的 identity，可做具明確恢復動作的狀態往返。
2. 其他由 inventory 證明「不影響 admin、Member link、team_player、attendance、通知」且 repository 支援完整恢復的既有對象。
3. 找不到安全候選時，停在 maintenance enabled 或未啟用的最後已驗證狀態，交由 Owner 指定候選或決定不做 smoke；不得自行建立假 production Person／identity，不得拿 Owner 自己的登入、任一 admin、已連 Member 或 active team／guest qualification 測試。

禁止把 remap／unlink 已連 Member、blocked admin、last-admin access、`team_player` revoke／restore 或真實通知作為首個 smoke。

## Stage C：唯一精確 Owner production approval

Work 根據 Stage B 證據整理單一 execution package，至少鎖定：

- merged source commit與 Web Portal current／candidate／rollback revision；
- exact maintenance flag mutation、candidate digest、Secret binding metadata、IAM與 traffic promotion／rollback；
- 去識別化 mutation 類型及候選分類；實際 target ID只能由 Owner 在安全執行環境提供，不得寫入 repository、PR、log或聊天摘要；
- exact action、reason分類、兩個 request IDs（mutation／recovery）、預期 audit actions／count delta與 idempotent retry方式；
- pre/post-check checksums與 stop conditions；
- maintenance flag rollback、traffic rollback及 forward data recovery。

只有 Owner 明確批准此 exact package 後才可執行 Stage D。PR工作包或本任務核准不等於 production批准。

## Stage D：maintenance activation 與受控 smoke

1. 重跑 fresh guards與pre-check；任何 drift停止。
2. 只更新 Web Portal maintenance=true，建立 candidate revision；先核對 Ready、原 image digest、Phase C=true、freeze=false、maintenance=true、Secret bindings與public IAM，再切100% traffic。失敗回切鎖定 revision。
3. 做無副作用 GET與ERROR log檢查；不得把真實 mutation 當health check。
4. 執行唯一核准 mutation；核對before／after與一筆預期audit。
5. 以相同request ID重試，確認不新增audit且狀態不漂移。
6. 以另一request ID執行核准恢復動作；最終業務狀態回到原值，新增精確recovery audit。
7. 執行strict post-check／compare；確認admin、Member links、qualifications、attendance與notification counts無非預期差異。
8. 以實際 metadata／logs／controller／validator做 final gate；沒有流量時不空等，也不人工製造流量。

## Rollback／recovery

- Flag／revision問題：maintenance立即設false或將100% traffic回切執行包鎖定的maintenance-off revision；不關閉Phase C、不改其他服務。
- Mutation失敗但transaction未commit：確認無audit／狀態delta後停止。
- Mutation已commit：不得刪audit或直接SQL回滾；只使用核准的domain recovery action與新request ID做forward recovery。
- Recovery失敗、audit不一致、last-admin／qualification／Member drift：maintenance設false、保留Phase C runtime、停止所有identity mutation並交回Owner；不得ad-hoc SQL修補。
- 不downgrade schema 0004、不restore backup、不刪Person／identity／qualification／audit rows。

## 必要離線／hosted驗證

- `tests/portal_data`完整 suite（PostgreSQL 15／16 hosted matrix，因涉及production verifier／受控SQL contract）。
- Web Portal完整 suite。
- Phase C runtime／controller／artifact／closeout verifier tests。
- deployment tooling targeted tests。
- compileall、isort、Black 24.4.2 formatter API／hosted Black、`git diff --check`、`git status --short`。
- 所有外部HTTP、GCP、LINE、Discord、DB production calls在local tests中mock；不得讀真實env。

## 非目標

- 不新增schema 0005，不做DDL、migration、backfill、delete、restore或ad-hoc SQL repair。
- 不啟用Event／Activity production CRUD、角色指派產品化、allowlist退場、Google／Apple OAuth或Flutter。
- 不部署LINE webhook、notify cron或其他服務。
- 不人工invoke Scheduler、webhook、attendance、identity callback或通知。
- 不發送真實LINE／Discord訊息。
- 不修改Secret、IAM、Scheduler、RLS、grants或production schema。

## 需要 Owner 決策／批准

1. Stage B production唯讀 inventory package。
2. Stage C 精確 Web Portal flag／candidate／traffic／rollback與受控 mutation execution package。
3. 若無安全候選：是否由Owner指定一個既有pending identity，或接受「maintenance已啟用但不以真人mutation smoke」作為Phase C closeout例外。

## PR／協作

- Owner已批准以「單一TASK完成Phase C收尾」為任務方向；Stage A可進行repository/local實作。
- Codex完成Stage A後commit、push、report與`ready_for_review/work` handoff，不先建立PR。
- Work驗收後建立唯一ready PR；required CI通過依standing Git authorization squash merge。
- Stage B／D的production讀取與mutation仍須上述精確批准，不因Git授權而自動成立。
