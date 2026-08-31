# TASK-171 Work Review

- reviewer: `/root/task170_release_security_review`
- verdict: `ACCEPT`
- reviewed_commit: `b720e1cef8e037da1b69d1e746e40d51703d24c3`

## Closed findings

- P1：未知Apple key在fresh cache可重複觸發early refresh。修正後每個cache window只允許一次thread-safe early refresh。
- P1：cold／expired JWK refresh失敗會被每個請求重試。修正後timeout、5xx、malformed與oversized response共用一分鐘backoff，且clock rollback不會重開window。
- P1：warm cache的early rotation refresh暫時失敗後，曾被鎖到正常TTL到期。修正後失敗不消耗early allowance；deadline前零transport，deadline時併發請求最多一個recovery transport，成功後共用rotated key。

## Accepted boundary

- Apple assertion維持RS256、exact issuer／audience／nonce／time及bounded JWK驗證；Apple `sub`是唯一identity key，profile hints不得自動合併Person。
- Apple runtime設定為optional且fail closed；未設定只停用Apple，不影響既有LINE／Google。
- Flutter僅在real iOS composition顯示Apple login／link；native bridge只回傳identity token，不持久化provider credential或profile hint。
- App Store release marker仍為not implemented。Apple帳戶、identifier、key、entitlement/profile、Secret、runtime、deployment、real-device provider smoke與TestFlight不在本次驗收內。
- Review使用immutable Git archive且全程read-only；focused verifier 10/10通過，無provider／cloud／Secret／runtime mutation。
