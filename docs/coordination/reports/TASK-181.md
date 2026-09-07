# TASK-181 工程減摩擦交付

## Delta

- 新增既有quality runner的check-only working-tree selection；無第二套wrapper。
- 校正Mobile revision／maintenance／TASK-180過期描述；分離固定Git證據與未重新查證runtime紀錄。
- 提供流程／CI成本提案，不修改COLLABORATION、DECISIONS、CI選測或Owner gate。
- 安全邊界、格式工具版本、SHA-based CI selection不變；沒有runtime／provider／store／DB操作。

## Verification

- 新tests先確認缺少selector而失敗；實作後quality suite 13 tests通過。
- quality＋classifier＋workflow focused suite：48 tests，47 passed、1既有本機Bash環境skip。
- 臨時Git repository覆蓋clean、staged、unstaged、new、ignored、deleted、renamed與index/disk抵銷。
- Windows pinned Black CLI在兩個owned檔timeout；runner正常返回failure。
  同版本Black API格式化與check/isort check補本機證據；不把CLI失敗稱為PASS。
- reviewer `/root/task181_review` lease 1：ACCEPT，無blocking findings；独立重跑同一48-test suite，
  47 passed、1本機Bash skip；git diff --check通過，交回前dirty diff無漂移，Main已收到並接受。
- Main以相同Black/isort版本API確認兩檔格式通過；hosted CI尚待單一PR執行；未做live runtime inventory。

## Limits / next

--working-tree檢查目前磁碟，不驗證index-only內容；未出生HEAD與Git錯誤fail closed；只供check不供format。
未節省本次CI：quality工具仍依現行classifier走full。流程與CI提案需另外接受及實作，尚未生效。
Main依現行流程完成targeted review後建立單一ready PR；merge不授權部署。
本文件是pre-PR evidence checkpoint，後续merge與required checks結果以本delivery branch的Git／PR證據核對；
不寫入含有自身內容的commit SHA，也不為補merge時間另開PR。
