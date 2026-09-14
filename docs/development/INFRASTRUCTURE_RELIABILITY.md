# 重要基礎建設：可靠性實作指引

本頁供 signing、CI/CD、credential transport、operator、migration/recovery 等工具的下一位實作者使用。
規範與授權只見 [COLLABORATION 8.1](../coordination/COLLABORATION.md)；本頁是操作配方與教訓索引，
不是新規章、平台成功證據或真實執行批准。Windows已知陷阱另見 [AGENT_ENVIRONMENT](AGENT_ENVIRONMENT.md)。

## 先辨識我們在建什麼

Staging App不是production，但可以簽署App、使用上傳金鑰或改變發布狀態的控制程式仍是重要基礎建設。
把「失敗不洩漏」當唯一成功條件，會得到安全停止卻不可診斷的工具；只測mock正向，也不能證明平台相容。
Main對這個取捨及完整交付負責，獨立reviewer須挑戰證據缺口，而非只檢查規章是否被引用。

## 下次動手前的一張小卡（放原task，不另建文件）

沿用五行checkpoint，明列：

1. 成果與風險：要交付哪一層？誰／哪些credential、外部狀態或費用受影響？
2. 基準與範圍：官方／原生最小路徑、exact source/toolchain、已有證據／尚未驗證；哪些自訂層先不加入？
3. Invariant與復原：最低必要權限、暫存清理、部分成功如何查證；沒有新證據不重送。
4. 實驗與測試：一個可否證假說、成功／失敗觀察、負向fixture、fixture不能代表的live層。
5. Owner與停止點：只列真正必要操作、預期次數、停止條件；新custody／服務／費用才新增授權決策。

例如「本人TestFlight」分為：未簽署編譯→真實signed archive/IPA→Apple processing→本人安裝→功能驗收。
只完成前一層就只報前一層。Browser手動觸發仍執行workflow；不是遠端Xcode GUI，也不自動消除自訂程式缺陷。
先評估既有標準工具能否承載，不預設再寫一個parser/controller；也不因一次失敗就直接換服務商。

## 每一層應保留什麼

| 邊界 | 可以保留的診斷 | 不可以用來冒充的證據 |
| --- | --- | --- |
| 本機輸入／驗證 | 固定stage/check、不符欄位名稱、match布林 | 私鑰、密碼、原值／prefix／hash |
| CLI／HTTP | timeout／exit分類、HTTP status、已審查provider code | 完整stderr、URL query、response dump |
| 遠端state | 白名單status、已綁定operation、觀察時間語意 | 從目前state倒推已遺失的原始回應 |
| 失敗與cleanup | 原始failure、secondary failure、known effects、未解決範圍 | cleanup成功等同upload成功；未執行等同遠端absence已查證 |
| final output | 以上資訊不被default覆蓋、下一個唯讀動作 | 空cause加NONE，或由UNKNOWN推定可重試 |

Unexpected exception允許固定unknown分類，但必須指出觀察中斷位置並保留先前安全事實。無法保證所有外部故障
都有精確根因；能保證的驗收目標是：已取得的安全資訊不在內部鏈路消失。修正不靠輸出raw secret-bearing logs。

## TASK-198 教訓到回歸的對照

| 已證實的缺口 | 防堵／本次直接回歸 |
| --- | --- |
| run合法等待狀態被當作拒絕 | `test_raw_run_states_keep_binding_and_wait_without_mutation`；raw假API→真bound/advance，只等待、不延長deadline |
| 綁定檢查通過後仍沿用舊check | `test_raw_run_rejection_reports_the_check_that_actually_failed`；未知／錯型別狀態與真正binding mismatch分開 |
| recover遺漏cause/effect；取消503、result寫入或close遮掉原因 | `test_real_recovery_chain_keeps_failure_and_known_effect_state`；記憶體journal→真Session/recover/emit；保留primary、secondary與保守unknown |
| 未解決輸出卻指示NONE | `test_unresolved_output_always_directs_readonly_review`；只指示read-only，不賦予retry權限 |

命令（全虛構；不輸入真實資產，不聯網）：

```powershell
py -3.10 -B -m unittest tools.tests.test_ios_testflight_dispatch tools.tests.test_ios_testflight_operator -q
```

這些回歸不是整條release已完成。仍待處理：底層transport分類可能合併原因、binding仍未逐欄位報check、
非零傳送後的完整artifact/Apple recovery與私密資料處理仍需更廣證據；不能宣稱全庫診斷已治理完。
原始run首個拒絕回應未保存，不能以可重現等待狀態缺陷宣稱已證明該次根因。

## 下一次實質行動的限制

先完成source review／required CI，然後提出一個精簡、經審查、使用既有資產的GitHub-hosted macOS手動基準。
交代Secret保管、日誌／IPA可見性、成本與清理，再交Owner必要操作；本頁不提供可立即執行的live命令。
已取消的operation與原日誌保留；不改nonce／新建日誌／新增successor來規避既有重試限制。
若需改現有one-successor政策、credential保管方式或服務商，先做範圍明確的設計／批准，不默默擴張。

參考：[GitHub macOS簽署指南](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications)、
[GitHub workflow run狀態](https://docs.github.com/en/rest/actions/workflow-runs)、
[Flutter先跑通本機再自動化](https://docs.flutter.dev/deployment/cd)。官方範例是起點，仍須審查權限、版本與secret輸出，
不是逐字照搬寬鬆設定或把範例成功當成本專案成功。
