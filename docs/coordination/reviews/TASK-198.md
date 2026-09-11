# TASK-198 review

Security architecture lease1 ACCEPT received/handled by Main at
3b1be6a607c565fa4184aec3493ef527995fbf19. Advisor source/public documentation only;
no tests/native/private inputs. Real execution remains subject to source review
and actual private intake, not another generic approval from Owner.

Accepted supported path: Xcode manual signed archive -> manual export -> private
artifact inspection -> separate ASC upload/processing -> exact Owner-only group.
Apple manual-distribution and archive guidance:
https://help.apple.com/xcode/mac/current/en.lproj/devcac6ab5b3.html
https://help.apple.com/xcode/mac/current/en.lproj/devff5ececf8.html
No dependency on arbitrary unsigned archive export or fictional codesign success.
Reviewed build phases execute within key window; dependency setup precedes it.
No auto-provisioning/new certificate/global key ACL; no public raw logs/artifacts.
Only platform processing proves Apple receipt, and only device evidence proves
installation/core flow. Keep source/public-ready and device claims separate.

Readiness advisor confirms existing profile controller accepts only certificate
and profile, not signing/upload keys. Existing lifecycle pipeline is simulation.
Staging build already bypasses public marker after external-signing checks;
artifact-only inspection can support internal delivery without fake marker PASS.
Actual internal release controller and credential custody still need implementation.

First slice security lease2 ACCEPT received/handled. Independently28 tests27PASS/
1platform skip, diff PASS. CLI nonzero still fails; no continue-on-error or true
signing flags. DEC-109/task limits faithful to Owner scope. Marker/public gate
unchanged; private profile presence not validity; no live controller claim.
Main repeated28 tests27PASS1skip and changed-Python quality PASS.
Native/hosted validation pending for this delta; real signing/TF not complete.
