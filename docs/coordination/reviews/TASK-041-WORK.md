# TASK-041 Work 驗收報告

驗收日期：2026-08-06（Asia/Taipei）

## 結論

- 結論：`accepted`
- Branch：`codex/deploy-task-040`
- Task base：`62d2de4`
- Planning／document map：`9085a4e`
- Implementation：`5f9211f`
- Fail-closed follow-up：`880f063`
- Codex handoff：`a00078c`
- Repository：乾淨
- 下一位角色：Owner

## 實際驗收

- `role_policy.py` 集中定義 member、officer、admin 與唯讀 capability mapping；capability sets 亦不可變。
- Production resolver 只會產生 linked member 或既有allowlist admin；沒有任何production officer來源。
- `member_required`與`admin_required`改經集中policy，既有匿名redirect、非admin 403、mutation前拒絕與CSRF契約保持通過。
- Demo member不能看見或進入幹部功能；officer與admin透過同一`manage_events` capability同時控制UI與server routes。
- 初驗發現的可變mapping、畸形unhashable policy輸入及缺失Demo member id均已補正並新增回歸測試。
- Route access matrix與Web Portal README和目前程式行為一致；沒有宣稱production已具officer persistence。
- 沒有schema、model、environment、dependency、OAuth、deployment或跨服務變更。

## 驗收條件

1. 集中且不可變的role/capability mapping：通過。
2. Production只解析member或allowlist admin：通過。
3. 既有member/admin guards接到集中policy並保持相容：通過。
4. 非管理員在Member配對查詢／mutation前被拒絕且CSRF保留：通過。
5. Demo三角色能力差異與admin繼承officer能力：通過。
6. 未知角色、畸形session、無效allowlist及畸形policy輸入fail closed：通過。
7. Route access matrix與README一致：通過。
8. 離線測試無外部副作用：通過。

## Work獨立驗證

```text
python -m unittest discover -s apps/web_portal/tests -v
Ran 81 tests — OK (skipped=2)

python -m compileall -q apps/web_portal
OK

Python 3.10 AST grammar check
18 files — OK

git diff --check 9085a4e..HEAD
OK

git status --short
clean
```

兩項skip是Windows缺少Unix `make`／`sh`的既有deployment contract coverage，與本次role policy無關。

## 未驗證與後續限制

- 尚未取得hosted Python 3.10 CI；依Owner規劃，將和下一項實質成果一起建立PR時補齊。
- 尚未做三角色Demo瀏覽器視覺驗收；route與navigation契約已有Flask tests。
- Production仍無officer persistence、角色指派UI或audit log，且不應在沒有schema設計前假設已支援。
- 本驗收不包含PR、merge、deployment或production存取。

## Blocking問題

無。
