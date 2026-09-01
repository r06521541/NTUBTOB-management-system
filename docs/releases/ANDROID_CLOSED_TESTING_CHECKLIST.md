# Android Basic-only Closed Testing checklist

狀態日期：2026-08-31
範圍：`tw.org.ntubtob.portal` 的 `android-closed`、`staging:real`、Basic-only candidate。

本文件是去識別化 evidence contract，不是 Play Console 操作授權，也不證明外部事實。Repository tool 只讀一份由
外部受控流程準備的 JSON，驗證欄位完整性與互相綁定；它不登入、不連網、不建 key、不build/sign/upload、不操作
Console/store/cloud/device/production。任何未知、缺欄、`BLOCKED`、production/open/public 混入或 artifact drift 都停止。

## Operator boundary

1. 只從已接受且合併的 exact 40-character commit 產生 candidate；hosted gates、獨立 Release/Security review 與 strict AAB
   inspection 必須先完成。重建後視為新 artifact，重新檢查所有 hash、version 與 device/track 綁定。
2. Signing key 的建立／備份與 Play Console 操作必須在 repository 外的 Owner-gated surface 完成。候選包 build 則只能使用
   `tools.android_candidate_operator`：先 read-only preflight，再單次文字批准，所有 runtime/signing input 經隱藏輸入及
   nonce-authenticated one-use loopback memory channel交給 Gradle。不得把 keystore、password、private key、
   Console account/session、provider/client ID、backend endpoint、token、Secret 或個人／裝置識別資料寫入 JSON、Git、報告、
   command line 或 retained artifact。
3. Evidence record 只保留 exact package/version/artifact SHA、signer fingerprint comparison input、布林／enum 結果與 `EV-*`
   去識別化 reference。Validator 的輸出會省略 signer fingerprints 和所有 evidence refs；輸入檔仍須按外部 evidence
   retention policy 保護。
4. Validator 不查證 `EV-*` 指向的證據，也不讀 AAB 或 Console；`validated` 只表示 supplied record 符合此 schema。
   外部 observer、Main 與 reviewer 仍須檢查原始受控證據及 exact artifact。
5. 只允許 Closed Testing。不得切到 open testing／production rollout，不通知 testers；若 Console 要求 billing、公開發布、
   destructive signing rotation、未知聲明或 package ownership 有衝突，mutation 前停止並回 Owner。
6. Operator 只接受 clean exact `main == refs/remotes/origin/main`。目前 Play app 已建立；首次 track history 若經 Owner 可見
   read-only頁面確認為空，`previous-version-code=0` 才成立。Operator 不會替代這項外部事實判讀。

## Completion checklist

- Identity/artifact：package 精確為 `tw.org.ntubtob.portal`；semantic version 非 `0.0.0`；version code 為 positive
  integer 且大於受觀察的 prior track version code；exact AAB SHA-256 與 repository strict inspection `passed`。
- Signing：repository-external upload certificate 的 expected/observed SHA-256 完全一致，comparison 為 `match`；不保存
  key/password/certificate payload。
- Runtime：`staging + real + isolated-test-data`，明確 `production_access: false`；reference 只表示去識別化 scope review。
- Product scope：`basic-only`；Officer/Admin、push delivery、deep-link delivery、anonymous crash reporting 全為 `false`。
- Compliance：Data Safety、privacy、support、account-deletion 與 tester notes 均為 `verified`，且五個 `EV-*`
  references 必須 pairwise distinct；同一 reference（例如 `EV-SAME`）不得重複支撐多個 gate。`verified` 必須由 exact
  candidate 的外部 review 產生，不能由文件存在或 repository test 推論。
- Tester notes：明示 staging、Basic-only、無 push、無 deep-link delivery、無 crash reporting，並逐一列出 device matrix 中
  安全上無法執行的 LINE／Google provider login；不可加入自由文字或實際 provider/account 資料。
- Device matrix：同一 artifact SHA；去識別化 Android phone／Android 15、fictional data、無 device identifier。install、upgrade、
  cold start、refresh、logout、schedule/Event/attendance、offline 必須 `passed`；LINE／Google login 僅能 `passed` 或
  `unavailable`，後者必須和 tester notes 精確一致。
- Track：package/version/artifact SHA 與 candidate 完全一致；track 為 `closed`，state 為
  `available-to-closed-testers`；open testing、production rollout 均 `false`，tester notification 為 `not-performed`。
- Blockers：`remaining_blockers` 必須是空 list。processing/unknown/rejected 狀態不可先填 PASS；保留 blocker 並停止。

## Evidence JSON template

以下值全為 fictional。`EV-*` 只能是由受控 evidence index 解析的去識別化 reference，不能放 URL、email、路徑、
帳號或秘密值。

```json
{
  "schema": "android-closed-testing-evidence-v1",
  "channel": "android-closed",
  "reviewed_commit_sha": "cccccccccccccccccccccccccccccccccccccccc",
  "artifact": {
    "package_name": "tw.org.ntubtob.portal",
    "version_name": "0.1.0",
    "version_code": 2,
    "previous_version_code": 1,
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "strict_inspection": "passed"
  },
  "signer": {
    "expected_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "observed_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "comparison": "match",
    "evidence_ref": "EV-SIGNER-COMPARE"
  },
  "runtime": {
    "environment": "staging",
    "client_mode": "real",
    "data_scope": "isolated-test-data",
    "production_access": false,
    "evidence_ref": "EV-RUNTIME-SCOPE"
  },
  "scope": {
    "release_scope": "basic-only",
    "officer_admin": false,
    "push_delivery": false,
    "deep_link_delivery": false,
    "anonymous_crash_reporting": false
  },
  "compliance": {
    "data_safety": {"status": "verified", "evidence_ref": "EV-DATA-SAFETY"},
    "privacy": {"status": "verified", "evidence_ref": "EV-PRIVACY"},
    "support": {"status": "verified", "evidence_ref": "EV-SUPPORT"},
    "deletion": {"status": "verified", "evidence_ref": "EV-DELETION"},
    "tester_notes": {
      "status": "verified",
      "evidence_ref": "EV-TESTER-NOTES",
      "declares_staging": true,
      "declares_basic_only": true,
      "declares_no_push": true,
      "declares_no_deep_link_delivery": true,
      "declares_no_crash_reporting": true,
      "unavailable_provider_scenarios": []
    }
  },
  "device_matrix": {
    "artifact_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "device_class": "android-phone",
    "os_major": 15,
    "device_identifier_recorded": false,
    "test_data": "fictional",
    "scenarios": {
      "install": {"result": "passed", "evidence_ref": "EV-DEVICE-INSTALL"},
      "upgrade": {"result": "passed", "evidence_ref": "EV-DEVICE-UPGRADE"},
      "cold_start": {"result": "passed", "evidence_ref": "EV-DEVICE-COLD-START"},
      "line_login": {"result": "passed", "evidence_ref": "EV-DEVICE-LINE-LOGIN"},
      "google_login": {"result": "passed", "evidence_ref": "EV-DEVICE-GOOGLE-LOGIN"},
      "refresh": {"result": "passed", "evidence_ref": "EV-DEVICE-REFRESH"},
      "logout": {"result": "passed", "evidence_ref": "EV-DEVICE-LOGOUT"},
      "schedule_event_attendance": {"result": "passed", "evidence_ref": "EV-DEVICE-SCHEDULE-EVENT-ATTENDANCE"},
      "offline": {"result": "passed", "evidence_ref": "EV-DEVICE-OFFLINE"}
    }
  },
  "track": {
    "name": "closed",
    "processing_state": "available-to-closed-testers",
    "package_name": "tw.org.ntubtob.portal",
    "version_name": "0.1.0",
    "version_code": 2,
    "artifact_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "open_testing": false,
    "production_rollout": false,
    "tester_notification": "not-performed",
    "evidence_ref": "EV-TRACK-STATE"
  },
  "remaining_blockers": []
}
```

## Offline validation

把 JSON 放在 repository 外的受控路徑，只傳入檔案路徑，不把內容或 private input 放進命令列：

```sh
python tools/android_closed_testing.py <deidentified-evidence.json>
```

成功回傳 sanitized JSON summary；失敗在 stderr 回傳不含 caller value 的 `BLOCKED` reason 並 exit 2。輸出中的
`external_truth_attested: false` 是刻意邊界：此工具無法把 self-attested input 升格為 Console、device 或 runtime truth。

## Candidate operator（Owner 在場時）

```powershell
py -3.10 -m tools.android_candidate_operator preflight --previous-version-code 0
py -3.10 -m tools.android_candidate_operator build --previous-version-code 0
```

第二行只在 preflight 顯示 package `tw.org.ntubtob.portal`、`android-closed`、`staging-real`、Basic-only、exact merged commit
與 monotonic version 都正確後執行。依序隱藏輸入 staging API origin、LINE channel ID、Android／Web Google client ID、
repository-external keystore path、alias、store/key passwords 與 expected upload-certificate SHA-256。成功只會產生一份
repository-external候選包及 sanitized JSON；仍未授權／完成實機、Console upload、tester、open或production動作。
Operator 只複製已檢查的immutable snapshot，隨後清除repository-local build outputs；清除失敗即STOP，不能回報成功。
