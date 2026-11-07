# P2 Blueprint semantic reference 독립 검증 확대

2026-11-07 · 기준 `dcb99dc` · 작업 브랜치 `codex/p2-native-reference-validation`

## 판정

Linux Cloud에서 native producer 소스, saved/loaded 전용 비교 profile, fail-closed 합성 검사를 구현했다. 실제 Unreal
Editor 5.7/5.8에서 새 producer를 빌드하고 캡처하지 못했으므로 **새 semantic reference의 독립 검증 완료로 판정하지 않는다**.
기존 8개 native 정답 JSON은 변경하지 않았고 새 profile에서는 capability 부재로 `incomplete`가 된다.

## 기존에 검증되지 않았던 필드

1.18.0 graph IR은 다음 saved-package 관측을 보존하지만 기준 커밋의 Native Oracle producer는 수집하지 않았다.

- `FunctionReference`, `EventReference`, `VariableReference`, `DelegateReference`
- FMemberReference의 `MemberParent`, `MemberName`, `MemberGuid`, `bSelfContext`
- `MacroGraphReference.MacroGraph`
- `K2Node_CreateDelegate.SelectedFunctionName`, `K2Node_CustomEvent.CustomFunctionName`
- 위 참조가 속한 graph/node exact object path와 node GUID에 결합된 target identity

따라서 기존 all/graph profile의 통과는 pin/declaration 회귀만 증명하며 이 필드의 정확성을 증명하지 않았다.

## 새롭게 검증 가능한 필드

`RepoReaderOracle`은 node마다 `semantic_references`를 기록한다. FMemberReference UPROPERTY와 그 struct field를 Unreal
reflection으로 읽어 loaded parent object/class path, name, GUID, SelfContext를 보존하고, effective owner class에서 실제
UFunction/FProperty가 해석되면 resolved member/owner path를 기록한다. MacroInstance는 `GetMacroGraph()`의 exact path를
기록한다. 모든 레코드는 `state=loaded-editor`이며 snapshot도 `semantic_reference_state=loaded-editor`로 표시된다.

새 `semantic-references` profile은 같은 SHA-256 package를 새로 읽은 graph IR의 `saved-package` 관측과 다음을 비교한다.

- exact graph object path
- exact node object path, node class와 node GUID
- reference kind와 source property
- self 또는 exact external parent object path
- member name과 GUID
- exact macro graph path, custom event name

중복 graph/node/reference identity는 덮어쓰지 않고 거부한다. 같은 short name, unknown parent/GUID, partial record는 성공이
아니다. editor가 exact target을 resolve하지 못한 native record도 unavailable이다. CreateDelegate는 1.18.0 saved field가
function name만 제공하므로 이름이 같아도 owner identity가 없어 incomplete로 남긴다.

## 변경된 소스 코드

- `tools/RepoReaderOracle/.../RepoReaderOracleLibrary.cpp`
  - loaded member/macro/name reference read-only capture와 target resolution 추가
  - 저장·컴파일·node reconstruction·dirty 변경 API는 호출하지 않음
- `tools/export_editor_oracle.py`
  - 새 producer capability key를 exporter/plugin 일치 조건에 추가
- `tools/compare_editor_oracle.py`
  - `semantic-references` profile, saved/display GUID 변환, exact identity와 saved/loaded provenance 보고 추가
- `tests/editor_compare_tests.py`, `tests/editor_export_tests.py`, `tests/unit_tests.py`
  - 정상 함수, 동명 타 class, wrong GUID, missing parent/reference, duplicate node, partial/unknown, saved/load 차이,
    member/macro/custom-event 종류와 old capability/hash 거부 반례 추가
- `docs/EDITOR_ORACLE.md`, `tests/README.md`
  - profile 계약과 Windows UE 5.7/5.8 수집·비교 절차 추가

## 테스트 결과

- 변경 전 전체 `python tests/regress.py`: 통과
  - unit 전체, 외부 asset 6/6, 기존 Native Oracle 8/8
  - `eg` 49 BP / 1,778 nodes, `ar`, `ves`, `bt` 통과
- 변경 후 semantic 합성 반례와 전체 unit suite: 통과
- 변경 후 최종 전체 `python tests/regress.py`: 통과. 기존 Native Oracle 8개와 `eg/ar/ves/bt` 기준 변화 없음
- 실패: 없음
- 미실행: UE 5.7/5.8 C++ plugin 실제 build, 새 native capture, Windows smoke

첫 기준선 실행은 기존 `tests/.cache/eg` clone의 LFS materialization 변경을 clean-workdir guard가 거부했다. clone을 reset하거나
수정하지 않고 `eg-p2-baseline-preserved`로 보존한 뒤 새 고정 clone에서 전체 기준선을 통과했다.

## 실제 engine 검증이 필요한 항목

1. UE 5.8에서 plugin이 현재 public header/API로 compile되는지 확인한다.
2. function/variable/event/delegate/macro가 실제로 있는 Blueprint를 새 JSON으로 캡처한다.
3. capture 전후 package SHA-256, `package_dirty=false`, root/asset/snapshot issues 없음과 target count를 확인한다.
4. semantic profile을 실행해 saved/loaded 차이를 그대로 분류한다.
5. UE 5.7에서 별도 build/capture/report를 반복한다.
6. 검토를 통과한 새 정답은 기존 JSON을 덮어쓰지 말고 source commit, Git blob, engine build와 함께 별도 추가한다.

## 남아 있는 정확도 위험

- FMemberReference의 loaded state는 저장값이 아니다. engine load fixup으로 owner/GUID가 달라질 수 있으며 비교기는 이를 숨기지 않는다.
- 현재 Cloud에는 Unreal headers/toolchain이 없어 C++ compile 여부를 검증하지 못했다.
- node GUID도 load session에서 바뀔 수 있다. 이름으로 재매칭하지 않으므로 mismatch 또는 unavailable로 남을 수 있다.
- self-context target은 loaded Blueprint skeleton/generated class에서 resolve하지만 saved identity 비교는 `self` token과 name/GUID에 한한다.
- CreateDelegate owner, runtime virtual/interface dispatch, compiled expansion과 gameplay behavior는 이 profile의 검증 범위가 아니다.
- 실제 capture가 추가되기 전까지 Linux 합성 통과는 비교기 동작 검증이며 semantic reference 정확성의 독립 정답이 아니다.
