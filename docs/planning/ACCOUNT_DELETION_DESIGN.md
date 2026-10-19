# 帳號刪除與隊務資料分離草案

TASK-202｜2026-09-17｜**提案，未實作、未核准發布，不保證 App Review 結果**。
Source：`2b8e93e9029ac9be924967696b9be544f377c456`。只讀 source 與官方文件，未查真實資料。
本稿細化 [隱私草稿](../releases/MOBILE_PRIVACY_DRAFT.md)；方案A的30／90日等期限仍待決，
本稿不批准大規模定期清理、不變更一般使用者預設、不要求重建所有Person或重綁登入。

## 1. 結論與 Apple 邊界

推薦「**兩個清楚分開的功能，加一條僅針對申請者的刪除履行流程**」：

- **管理登入方式／解除Apple綁定**：保留NTUBTOB服務帳號與Person；不是帳號刪除。
- **刪除NTUBTOB服務帳號**：涵蓋同一服務的Apple／Google／LINE登入及其帳號資料，
  不能只停iOS登入、卻讓同一帳號透過Portal／LINE恢復全部功能。
- 刪除App帳號**不自動替球隊決定退隊**，但也**不保證具名隊員資料完全保留**。
  現實會員資格和資訊系統保存個資是不同問題；後者仍須有可說明的依據及範圍。

Apple規範基準（2026-09-17查閱）：

- [5.1.1(v)](https://developer.apple.com/app-store/review/guidelines/#data-collection-and-storage)：支援建立帳號的App需提供App內刪除入口。
- [刪除指引](https://developer.apple.com/support/offering-account-deletion-in-your-app/)：刪除帳號與相關個資，
  包括使用者內容；僅停用不足。可需時或人工履行，但須告知時間並確認完成，非高度監管App不能強制以客服往返代替。
- 同一指引要求Sign in with Apple token撤銷；[revocation API](https://developer.apple.com/documentation/signinwithapplerestapi/revoke-tokens)
  處理供應商授權，不代表已刪本服務資料，亦不刪除使用者的Apple帳號。
- [TN3194](https://developer.apple.com/documentation/technotes/tn3194-handling-account-deletions-and-revoking-tokens-for-sign-in-with-apple)
  明列無可用token/code時仍須履行本服務資料刪除，另指引使用者手動撤銷；亦要求處理撤銷通知後的資料清理。
  [Apple使用者說明](https://support.apple.com/102571)區分停止Apple登入與在App刪帳號。
  兩者共同約束下列intent分流；不是任意忽略撤銷通知或自動抹除所有Person的依據。

**沒有找到「球隊原有名冊」可以一律豁免的Apple規定。** 個資法律允許保存與Apple接受同一服務的
保留設計也非完全相同判斷。具名保留不是預設：未證實獨立紀錄邊界／必要依據，或只是App資料換表存放，
就必須納入刪除，不能把該例外包裝成符合規範的既成事實。

## 2. 現況：可沿用什麼、不可誤用什麼

| Source | 已有能力／重要限制 |
| --- | --- |
| [models.py](../../shared_lib/shared_module/portal_data/models.py) | Person同時有姓名、備註、portal狀態／權限；Member有姓名、學籍／球衣／守位等及Person連結；不是分離的「空帳號」 |
| 同上：AuthIdentity／MobileSession | 多provider連到同一Person；session綁identity及Person。多處FK RESTRICT；直接DELETE Person會失敗或破壞關聯 |
| 同上：Game／Event／Activity | 舊Game回覆可同時連user／member／person；只清person_id不能清掉可識別性。發布邀請快照與audit也可能留下person、actor、文字／JSON |
| [identity_lifecycle.py](../../shared_lib/shared_module/portal_data/identity_lifecycle.py) | `unlink_identity`是管理員LINE路徑，要求legacy LINE row、不能解除當前identity；**不能直接拿來當Apple self-service unlink** |
| [mobile_repository.py](../../shared_lib/shared_module/portal_data/mobile_repository.py) | Apple撤銷通知停用該identity、session與credential；不清Person，也不等於本服務帳號刪除；主動撤銷執行器仍缺 |
| [account_deletion.py](../../shared_lib/shared_module/portal_data/account_deletion.py) | 0013只有requested收據，限active Person／linked identity／active session；不涵蓋pending／restricted、履行與完成 |
| [LINE webhook](../../functions/line_webhook_handler/webhook.py) | Phase C與legacy回覆路徑並存，後者可由member_id寫入；Mobile API單點封鎖不足以涵蓋所有舊入口 |

保留現有Person／Member ID及一般principal resolution；不引入第二套全面帳號系統。
但開始接受真實刪除前，所有可能讀寫該申請者的入口必須能尊重刪除狀態，不能只在Flutter隱藏按鈕。

## 3. 產品操作：不改日常預設

### A. 解除單一登入方式

路徑：個人 → 帳號與安全 → 登入方式 → Apple → 解除綁定。

- 畫面明說「保留隊務帳號與資料；之後使用其他已綁定方式登入」。不是紅色「刪除帳號」的別名。
- 本人重新驗證與站內確認；仍須有另一個**已驗證且可用**的登入方式，僅顯示linked不足。
- 只剩Apple時，可選新增另一方式，或直接走刪除整個帳號；**完整刪除不要求先綁其他provider**。
- 撤銷Apple授權、使Apple來源App sessions失效、清理Apple credential／連結；其他provider sessions與Person不受影響。
  主動撤銷及本機SDK清理分開驗證；中途失敗顯示「解除尚未完成」，不假稱成功。
- Apple通知先驗簽、防重，並核對操作intent、account／identity generation與事件時間：
  若對應明確整帳號刪除申請，收斂該次server／client／Keychain資料清理；重複通知不重做mutation。
  若只是停止使用Apple、或找不到明確刪除receipt，先停止Apple存取並處理provider資料，
  不把它当全Person刪除授權，也不能因此聲稱多provider保留設計已符合所有平台要求。
  舊generation的延遲事件不得刪除新註冊帳號；無法安全歸屬時分開調查，不保留已知失效的Apple存取。
  不為「最後一位管理員」而忽略Apple撤銷，沿用必要的管理權恢復程序。

這是新增self-service能力，不把既有管理員LINE解除綁定改成通用刪除。可獨立安排，不是完整刪除的前置依賴。
**Standalone unlink另有release gate**：多provider保留與TN3194撤銷通知清理範圍須完成平台適用性核對，
未確認時不先上線此功能；不阻擋完整帳號刪除路徑的設計與交付。

### B. 刪除整個服務帳號

路徑：個人 → 帳號與安全 → 刪除NTUBTOB帳號（清楚、可找到，不藏在客服）。
支援App直接完成發起／確認；如有web步驟，deep link直達刪除頁，不回首頁找入口。

確認頁預覽由後端產生、短時效並綁定本人及資料版本：

> 將結束您的NTUBTOB線上帳號，Apple／Google／LINE均不能再存取這個帳號。
> 將移除登入連結及與帳號相關的個人資料；他人的帳號、比賽日期與比分不會因此刪除。
> 球隊會員資格不由此按鈕自動裁定。若有依法須保存的資料，本頁會逐項說明原因、期限及可見範圍。
> 核實後預計於30日內完成線上範圍；備份另列清除期限。這是草案數字，正式文案以已核准且可履行期限為準。

- 按鈕「取消」／「確認刪除帳號」，不預勾保留個資、不導向只解除Apple、不強迫退隊或逐provider登入。
- 新鮮本人驗證即可涵蓋已確認屬於同一服務帳號的所有綁定；不要求使用者再次輸入provider密碼給本服務。
- 有獨立名冊例外時，預覽列**具體欄位、依據、期限與承辦角色**；有疑義可提出權利請求，
  但不因此擱置無爭議的帳號／credential清理。沒有例外則直說不保留具名帳號資料。
- 「本人停用／pending／blocked」也提供有限權限刪除入口：驗證該provider身分或等效安全證明，
  只處理其可證明擁有的帳號／pending identity，不能藉此解封或按姓名挑選Person。

### C. 退隊／變更資格

維持現有幹部資格管理；不因解除Apple而撤銷team_player，不因刪除申請自動取消整場Event。
完整刪除後沒有線上帳號／可識別名冊時，系統不能繼續替其保留活躍個人邀請或代回覆權限。
這是資料與功能的必要結果，不等於替球隊判定現實中是否退隊。

## 4. 資料處置：保留系統結構，不保留假裝已刪的帳號

2026-09-24 DEC-114 補充：本人發布內容與第三方提及分開；本人內容不能只去署名，
共用隊務紀錄的操作人也不等於整筆紀錄的個人作者。歸屬依reviewed欄位契約，不讓
client或管理員臨時勾選「共用」迴避清除。舊自由文字沒有subject標記，不等於沒個資。
有歧義的候選進內部人工例外，綁定record/version後局部處理；不讓使用者逐筆催辦，
不讓未知狀態自動變完成。當前純分類模組尚不會建立review queue或實際移除原文。

新增／調整欄位時：活動名稱、地點／時間與規則避免聯絡資料及私密狀況；聯絡人／
分工採人員關聯；管理原因優先固定代碼、必要補充最小化；通知盡量由模板組合。
提示不等於內容偵測，不以姓名regex自動刪文或承諾可找全。外部已送副本與離線快取
仍須分別驗證，不能用資料庫刪除成功推定。處理期限需上線前訂定，本稿不填虛構天數。

| 資料 | 解除Apple | 完整刪除預設 |
| --- | --- | --- |
| Apple綁定、credential、相關sessions | 撤銷／清理 | 一併撤銷／清理，其他已綁provider亦處理 |
| Google／LINE登入與服務sessions | 不動 | 失效化並清除；不刪其Google／LINE供應商帳號 |
| Person姓名／正式名／備註、Member可識別欄位 | 不動 | 刪除；只有經核實、逐項披露的獨立保留例外才另存受限名冊 |
| Person／Member內部鍵 | 不動 | 可評估最小tombstone，僅供必要FK；不是「原Person保持完整」承諾 |
| 資格、權限、Event manager、邀請與個人出席 | 不動 | 停止帳號權限及個人通知／寫入；移除個人回覆與可識別關聯，不刪整個Event或其他人 |
| 賽程、對戰、比分與其他人的回覆 | 不動 | 保留；必要時移除申請者作者識別／文字中個資 |
| 審核／支援文字、audit／snapshot中個資 | 不動 | 實際刪除或遮除儲存內容與所有可回連欄位；只改UI顯示不算 |
| 通知受眾／已讀、device與待送outbox | 不動其他identity | 撤掉申請者待送／地址映射，保留他人投遞；不能整批取消他人的訊息 |
| 裝置cache／Keychain、服務備份 | 清Apple相關範圍 | 在線本人裝置清理；其他裝置下次連線封鎖並清理。備份／離線限制如實說明 |

### Person可留到哪裡？

可保留**無登入能力、無姓名／備註／學籍／LINE映射等，且無可回連個資的技術支點**；
例如舊audit只需顯示「已刪除帳號」，不讓整場比賽失去資料完整性。
不能留下同一Person跨年個人出席、Member映射或外部可識別連結，卻宣稱匿名。
即使移除直接識別也須檢查小隊人數、時間與角色是否能重識別；做不到就刪該關聯／個人行。
Tombstone是候選實作，不是無條件合法保留；對仍可識別的稽核／備份只用有期限、限權的明示例外。

`immutable`限制的是一般業務編修，不是永久保留個資的法律依據。需另設受控privacy erasure路徑，
留下不含原文的處置證據，不能偷偷改原有快照流程，也不能只增加redaction overlay卻永存原文。

### 若希望刪帳號但仍保留具名球隊名冊

此為**條件式例外／尚未核准方案**，不是為了保留現狀而預設採用：

1. 逐欄證明資料來源、真正管理者、獨立目的及保留依據／期限；「以前就有」與「Owner同意」本身不足。
2. 明確區隔App帳號資料；不把將刪資料先複製到名冊以迴避。由哪個服務提供給哪些幹部也須透明。
3. 該資料不得拿來恢復登入、舊出席、權限、subject配對或行銷；個資權利仍有處理管道。
4. 這條路未完成法務／平台適用性核對前，不對外承諾Person完全不動；正式版本採上面的保守刪除預設。

不需把全部名冊重搬新表；只對實際需要保留的例外設資料邊界。若沒有足夠依據，名冊保留需求不能優先於刪除義務。

## 5. 技術草案：最小增量，而非重造帳號系統

### 生命週期與存取封鎖

沿用0013收據，新增履行資料／append-only step ledger（正式migration設計另review，不先占revision號）。
既有 `Person.portal_status` 不直接新增一串enum去破壞所有caller；以獨立生命週期紀錄控制例外。
對未提出刪除且無生命週期紀錄者，維持既有狀態、權限與登入行為；對有紀錄者由共用guard處理。

候選狀態：`requested → verified → processing → online_completed → completed`，
另有有期限的`needs_attention`；此state表示**本服務資料履行**，最後`completed`須備份清理／合法例外證據完整。
Apple授權另記`revoked_confirmed`／`manual_action_needed`／`unresolved`，不混入本服務完成狀態。
UI可明示「NTUBTOB資料已刪除；Apple端授權仍待手動移除」，不得縮寫為「所有地方全部清除」。
在不可逆步驟開始前可明確取消；登入或provider callback不構成取消。不設強制冷靜期拖延。
舊客戶端只識別requested，不能直接回未知enum；採向後相容投影或明確新contract，發布前測試。

- verified提交成功時原子封鎖帳號一般操作，所有已存在session失效；解除Apple只封鎖該provider。
- 舊access token、Portal cookie、LINE舊按鈕、排程／重試、Officer代操作與manual pairing均覆蓋。
  先前排入queue的通知／寫入在送出或commit前也重查，不只檢查最初請求。
- 身份／Person／管理權／session鎖順序沿用既有契約；刪除與刷新／身份綁定／出席寫入競態須測。
- receipt查詢使用範圍極小、限時的獨立權限或provider proof，不讓已撤銷的一般session繼續讀業務資料。
  不用可猜UUID作公開查詢；不把receipt bearer放log或一般URL。完成通知不強制新增電子郵件。

### 執行與失敗處理

以一個共用domain service及可重入步驟完成，不另造release-style多層controller。
首版可由授權人員監督執行已review的程序，使用者仍在App發起，不必自己寄信催辦。

1. 固定申請ID與account generation，產生唯讀影響清單、保留例外及截止時間；同人重送回同一未結案申請。
2. 先封鎖存取與通知，再分流provider處理：有可用token時撤銷並清理；若**確定無可用refresh/access/code**，
   依TN3194完成本服務資料清理、提供Apple手動撤銷指引，不要求使用者逐provider重登或等待手動完成才刪。
   `credential_missing`不是`timeout/ambiguous`；後者須查證已知效果，不可假裝沒發生或自動重送。
   有限期保存撤銷所需credential時須列明用途／期限，必要時與安全負責人處置；不能無期限持有或卡住全部清理。
3. 外部呼叫不持有長DB transaction。每步記錄stage/check、confirmed效果、失敗原因與下一步，
   timeout不能改判零副作用或直接重送；不留raw token／response／個資快照。
4. 只對本申請批准範圍清理；在transaction內重查scope與generation。移除個資，不抹掉他人回覆／整場Event。
5. 線上post-check、provider結果、cache限制與備份清單獨立記錄；只宣稱已驗證的層級，
   provider手動步驟未做不能阻止本服務刪除，但須持續顯示Apple端未確認的事實。
6. 備份恢復先套刪除抑制資訊再開放服務；抑制資訊本身也限權、有期限，不無限保存provider subject hash。
   其期限至少涵蓋所有仍可恢復舊資料的backup／PITR／export horizon；無法證明舊副本已不可恢復時，
   不先清抑制資訊、也不假稱備份清理完成。實際保留天數須由盤點結果與Owner另行核准。

不可逆刪除後不以恢復整份舊備份作普通rollback。可回退相容程式，但不能復活帳號／個資。
具體資料庫、目標、筆數、dry-run artifact與實際不可逆動作仍須另行精確授權。

### 特殊情況

- **最後管理員**：受理不能永久以「找不到接班人」拒絕。預先建立受控恢復與有期限交接，
  必要時暫停管理寫入，而非繼續讓待刪帳號擁有權限；不自動升權給任意隊員。
- **新註冊**：明確新加入流程，舊帳號刪除完成前不產生新帳號繞過封鎖；完成後不自動依姓名／email／舊LINE row
  恢復舊Person。將來要再次連結合法保留的名冊，需本人明確申請與幹部驗證，不恢復已刪內容或管理權。
- **一個provider對多個app/client audience**：撤銷前核對本服務app grouping；不要猜撤銷只影響單裝置。
- **離線裝置與已送出訊息**：不能保證抹掉離線裝置、接收者截圖或第三方獨立保存；停止未來存取／傳送、
  清理受控副本並據實揭露，不以此免除本方責任。

## 6. 上線順序與驗收

1. Owner先核准功能邊界與具名名冊策略；保存期間另核准，不因本稿新增全庫24月清理。
2. source側建唯讀inventory／虛構fixture，覆蓋legacy Member/LINE、JSON、snapshot與caller graph；獨立安全設計review。
3. 實作共用guard、receipt新contract、step ledger、UI確認／restricted入口及purge adapter；全用假資料與mock provider。
4. 相容性先行：所有讀寫端升到懂guard的版本，再啟用刪除受理／executor；一般未申請帳號無需重綁或重登。
  舊版服務仍可繞過guard時不得啟用。Schema只用additive migration並提供不復活資料的rollback。
5. 隔離staging演練provider成功／失敗與刪後再登入；確認客服能力、logs／備份期限後才公布政策及收真實申請。
6. 對外版本需完整可用的刪除入口與履行，不用source-only/fake畫面冒充；Review notes說明路徑、時間及合法例外，
  提供可測帳號，實際審核結果仍由Apple判斷。

| 必測情境 | 不可退讓的結果 |
| --- | --- |
| 一般人未申請、解除Apple但保留Google/LINE | 既有Person／資格／出席與其他登入不變；無全域登出；unlink另須平台範圍確認 |
| 只有Apple、pending、restricted、最後管理員 | 都有真實可行的刪除受理／完成路徑，不以補綁或幹部回覆永久阻擋 |
| 同時refresh/link/attendance、舊Portal cookie／LINE按鈕 | verified後不得新發可用session或復活業務寫入 |
| provider timeout、主刪除成功但通知失敗、DB回應遺失 | 分開記錄效果與失敗、可查證，不重送未知mutation或回籠統成功 |
| 確定缺Apple refresh/access/code | 本服務資料仍可履行；提供手動撤銷，分開顯示狀態，不強制重登或永久pending |
| Apple callback重複／延遲／無對應receipt／已刪後新generation | 不盲刪Person、不刪新帳號、不保留失效Apple存取；明確刪除intent才收斂該次整帳號清理 |
| 兩人同場賽事／同批通知，申請者是活動建立者 | 他人帳號、回覆與活動不被連帶刪除；申請者個資不能藏在actor／JSON |
| snapshot／多重member-user-person外鍵 | 不靠改名或null單一欄位宣稱匿名；實際儲存內容與關聯均驗證 |
| 刪後註冊／幹部配對／舊備份恢復 | 不自動復活舊帳號、權限或已刪資料 |

## 7. 本輪建議決策

建議批准的是**設計方向**：兩個獨立入口；一般預設不改；只處理明確申請者；Person技術鍵可保留但
帳號個資不能原封不動；具名名冊是證據充分才成立的例外，否則走保守刪除。期限、source實作、
cloud設定、政策發布及真實刪除仍不是本稿已完成事項。
若Owner的硬性需求是「刪帳號後姓名與所有歷史出席必須仍完整」，應先驗證該保留方案能否成立，
而不是先實作再宣稱Apple允許。
