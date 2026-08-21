# TASK-101 — Web Portal weather Secret deployment contract

## 目標

補齊 Dashboard 天氣功能的 production deployment contract，讓 Web Portal 只能以 Owner 核准的 exact
Weather API Secret reference 建立 revision，並在 promotion 前驗證 runtime 仍為 Secret-backed。

## 邊界

- 不改 schema、portal product behavior、Secret payload、Secret version、IAM 或 production。
- temporary deployment env 必須移除 `WEATHER_API_KEY` plain value。
- Cloud Build、wrapper CLI 與 revision contract 必須共用同一個 exact weather reference。
- 任一缺值、非法 reference 或 runtime classification drift 都 fail closed。

## 驗證

- Deployment wrapper／Cloud Build contract tests。
- Web Portal weather tests與完整 Web Portal suite。
- Hosted Python 3.10 CI與 final gate。

## Production gate

既有 `WEATHER_API_KEY:2` metadata 為 enabled，runtime service account 已有 Secret accessor；這些唯讀證據不
授權部署。合併後仍須由 Owner 核准 exact commit、rollback revision 與三個 explicit Secret references。
