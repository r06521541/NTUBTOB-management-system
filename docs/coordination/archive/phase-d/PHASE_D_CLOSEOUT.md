# Phase D closeout and retention index

本目錄保存已完成 repository delivery 的原始 task／report／review。Archive只證明當時事實，不授權現在的產品、
provider、Secret、cloud、store、database、deployment、runtime或production操作；現行authority仍只看
`HANDOFF.yaml`、`PROJECT_STATE.md`、`DECISIONS.md`與active task。

## Retention basis

下列每個群組均有current repository state或merged Git ancestry證明；列出的SHA已驗證為建立本closeout時exact HEAD
`b658ed02b8b535a5af321b7db9929be6e1119642`的ancestor：

| Task | Merged／incorporated evidence SHA |
| --- | --- |
| TASK-142 | `a196a91699374ee020457afa7caa2c63ce4e7f65` |
| TASK-143 | `c3baebddd08a100efafac47b641c129d956f68c7` |
| TASK-144 | `9cd006cf93c61185c868d5d571230953b4e72b35` |
| TASK-145 | `c4016dce924a1fa3e1edfaab7b9581ec968e04eb` |
| TASK-146 | `4c6993ed5dbbde3919643ffa56bd5ae419e7f0fc` |
| TASK-147 | `9b1c52eeb9445887ad2ff9ab3b37b650e6fe8dd1` |
| TASK-148 | `598f522475bfb9102ff21bb697eb5cc4ea9eb03b` |
| TASK-149 | `a46ce2e59a86eb29ecf35779bc6a2be5f7974bba` |
| TASK-150 | `aecfcb6fa822a998cfe7594a28064c20baf1c319` |
| TASK-151 | `710bf371e5616e47ef17e753809c3f5dd165eb3f` |
| TASK-152 | `8f13309d672eb5dfc02d327438c9da4b46c5270a` |
| TASK-153 | `2784293a739972c92b7a82d68d6358d916167cff` |
| TASK-154 | `6e8166a22d28188a44e0e02088c238bc5e400a92` |
| TASK-155 | `9cb52dcc618fb82fcf1bd3f26b209f84ba13fe78` |
| TASK-156 | `ae7371dc337307eefae0cff2f3c1bab2f4358dae` |
| TASK-157 | `e66f05f9920231d6f92cac2523b85f8f8ab7554f` |
| TASK-158 | `3a378aa053ed50a80d857ebe5f860b453b1a6841` |
| TASK-159 | `f59bdf5de26cc88b4e255d9c9f54b8aabb0779bc` |
| TASK-160 | `70d9df4f4479561a9a8da59efd10a56dce1e4105` |
| TASK-161 | `5d389f6c7c293a362551111a5be025ca058d9d60` |
| TASK-162 | `4d4b3502451544f5b9efeb9c2bfd4c605d6385a2` |
| TASK-163 | `aa614ab57423f589d318bc96c627d5f5a1b61bb5` |
| TASK-164 | `6b0aa7e556d25cb906bf12f4ea0c7eed57705f13` |
| TASK-165 | `98687a736d0f910132185c7ac1128ddbb89748b3` |
| TASK-166 | `0d6efacac2f20fe1ff66f1aa9ae84fd888ab0961` |
| TASK-167 | `10d7cee44b6bd6ff2edb456518a129ebb3692443` |
| TASK-168 | `cabdbcd039c9d526adb21fd8b11e145cd48f2574` |
| TASK-171 | `66529e9900e82bc1b7cbea52618469dbc3c0e8eb` |
| TASK-172 | `07fed38243883b95ef4c8371566b6859d9f57b31` |

TASK-142～168涵蓋已整合的Flutter孵化／delivery、mobile auth/staging、Event read/write/attendance與已完成Web／production
rollout群組。TASK-171是已review/merged的Apple repository slice，TASK-172是已review/merged的quality/digest hardening。
各群組仍未授權的外部能力已提升至active`PROJECT_STATE.md`與DEC-103／104；無須靠archive推論。

## Exact moved set

- `tasks/`：29 files，`TASK-142.md`～`TASK-168.md`、`TASK-171.md`、`TASK-172.md`。
- `reports/`：32 files：TASK-142／143／144；TASK-145A／145B／145C；TASK-146／147／148；TASK-149A／149B；
  TASK-150～156；TASK-158～168；TASK-171 Flutter/iOS與Mobile Auth；TASK-172 Tooling。
- `reviews/`：13 files：TASK-146／147／148／149／160／161／162／163／165／167／168／171／172。

共74個歷史檔案只改路徑，內容未重寫。子目錄保留artifact class，並避免report／review同名時互相覆蓋。

## Deliberately retained active groups

- TASK-169：repository readiness已完成，但其Android/iOS store、signing、provider、production backend與public-release
  matrix仍是current gate。
- TASK-170：repository candidate contract已完成，但Google Play developer-account verification、exact candidate、device與
  Closed Testing evidence仍待外部Owner-gated階段。
- TASK-173：本次active governance delivery。

任何完成證據不明確的群組都不得因本index推定完成或封存。
