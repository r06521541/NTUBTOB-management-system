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

Main hosted acceptance: run34618189006 on8066ea54fbe4fd53bf01b06d46756550271cef57
completed SUCCESS, all16 jobs PASS. PR250 merged5762a89c6e6451ed19f5151da1652312a9f76679.
Both trees exactly2eb7e7893574fd4621e1e2db08ecfa46a692e270. No real credentials,
sign/upload/runtime mutation; platform diagnostic/archive are accepted as those
claims only. Full IOS-TF-01 remains incomplete.

Main2026-09-12 read-only follow-up: Owner login completed; existing App capability,
certificate/profile and ASC upload key visible. Developer Sign-in-purpose Keys
list empty. Owner subsequently approved one App-bound Sign-in-purpose key. Main
prepared the final Register draft; Owner now reported downloaded and portal confirms
the approved key was created/downloaded. Agent did not register/read/download keys.
No real signing/upload or new implementation acceptance.

Security advisor lease3 ACCEPT received/handled: supported discovery route permits
only ephemeral hosted-user temporary search-list insertion with exact preservation,
restoration/readback, unchanged default and own-Keychain cleanup; not global login
or trust-all. Main adopted scoped exception in task under IOS-TF-01 flow adjustment.
Profile uses Xcode26 current UserData location, create-exclusive/owned cleanup.
References verified by Main:
https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications
https://developer.apple.com/forums/thread/812538
Native access compatibility and actual signing remain untested. No native/private
execution during architecture review.

Input source security lease4 ACCEPT received/handled at base/HEAD
5762a89c6e6451ed19f5151da1652312a9f76679 plus the two frozen new source files.
Independent command: py -3.10 -m unittest tools.tests.test_ios_testflight_inputs -q;
9 PASS. No blocking findings. Main matched canonical UTF-8 LF SHA256:
- tools/ios_testflight_inputs.py:
  4a54fb22f67800b215abe44c8bd8a159bb269871341438c33c3b2fe285e8cbe3
- tools/tests/test_ios_testflight_inputs.py:
  6e1826bf9ec1a25939e410da31dc84e0e3dad25b94e19521258552c88cf986cf
Scope: separated memory types/P256 keys, fixed ES256 TTL/signature, RSA pairing,
structural profile binding and non-disclosing error categories; authority false.
Limits: password-required P12 parsing is not proof of all private bag encryption;
CMS/inner DER/Apple chain/revocation, provider/API key metadata and live custody,
native signing/upload remain unverified. Controller must enforce these boundaries,
including distinct keys; repr suppression does not authorize generic logging.
No private reads/native/source/Git/cloud mutation by reviewer; now read-only.
