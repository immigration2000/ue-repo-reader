# P6 Semantic Reference 미확정 원인 분석

## 결론

P5의 `unavailable=61`은 61개의 서로 다른 Blueprint 참조가 아니라 23개 참조에 대한 필드 단위 진단 61개다. 원본 패키지의 tagged property를 다시 읽고 P5 Native Oracle의 loaded-editor 관측과 대조한 결과는 다음과 같다.

| 분류 | 원래 관측 수 | 판정 |
|---|---:|---|
| A. Unreal 직렬화에서 정상적으로 생략된 필드 | 47 | member record `partial` 집계 19, `MemberGuid` 생략 15, `bSelfContext` 생략 13 |
| D. 비교기가 과도하게 미확정 처리 | 13 | exact `MemberParent`가 있는데도 `bSelfContext` 부재 때문에 owner 전체를 거부 |
| F. 원본에 식별 정보가 없어 검증 불가능 | 1 | `K2Node_CreateDelegate.SelectedFunctionName`에는 owner identity가 없음 |
| B/C/E/G | 0 | 이 고정 증거에서는 입증된 사례 없음 |

A의 19개 `status` 진단은 각각의 missing field와 별개의 원본 손실이 아니다. member record 안에 unknown이 하나라도 있어 `status=partial`이 된 것을 비교기가 보수적으로 한 번 더 보고한 집계 진단이다. 따라서 원래 61개를 고유한 저장 정보 누락 61개로 해석하면 안 된다.

입증된 오류는 D뿐이다. 비교기는 이제 exact saved `MemberParent.object_path`가 있으면 external owner를 비교한다. `bSelfContext` 자체는 계속 unknown이며, 생략된 값을 `false`로 만들지 않는다. 같은 이름의 다른 owner path는 여전히 mismatch다. 같은 P5 입력 재실행 결과는 `checked 85 → 111`, `mismatches 0 → 0`, `unavailable 61 → 48`이다. 종료 상태는 의도대로 `incomplete`다.

## 증거와 무결성

- 입력 ZIP SHA-256: `d744d6f1a5351f6c78b233b68003b0e595d7d3f487169a28a03b68b3ae4cff7e`
- 입력 보고서 SHA-256: `604aa0637ff5d0f6343154e850b18d4a6c1ef041b6d3b5e97f8aca6e939df565`
- ZIP CRC 검사: 21개 member 모두 통과, 중복 이름 및 경로 이탈 없음
- Native JSON SHA-256: `95c7dd5bd3c67fc517cc8e1890c3efaa3b46adefa8764a16a7ab500425674f12`
- 원래 compare JSON SHA-256: `bcef90e8240369ee74ec0691a534fc6a3d972a0e6712c7355c2e339bb551f3e0`
- 프로젝트: `tomlooman/ActionRoguelike` commit `31bd38491d9dcec99460d85f3084c79441c5ce8b`
- asset: `/Game/ActionRoguelike/UI/PlayerHealth_Widget`
- package SHA-256: `2687fa1435cf25e493bf05c2d1e4ddff79cb991dc9c4d43411e6beea4e2cb37e`
- P5 package before/after SHA-256: 동일
- engine: Unreal Engine 5.8.4, changelist `58902052`, compatible changelist `55116800`
- build/editor/compare process exit: `0`, `0`, `1`; compare의 `1`은 mismatch가 아니라 incomplete를 포함한다.

ZIP의 빌드 로그와 `UE-Build.version`을 직접 확인했다. RepoReaderOracle 빌드는 성공했고 Native capture는 `package_dirty=false`, root/asset/snapshot issue가 모두 0이다. P5 JSON에서 직접 다시 센 값은 Native semantic reference 23개, complete 22개/partial 1개, saved reader complete 4개/partial 19개, checked 85개, mismatch 0개, unavailable 61개다. 원본 증거는 저장소에 복사하지 않았고 개인 PC 절대 경로와 환경 메타데이터도 보고서에 옮기지 않았다.

## 원본 저장 표현 확인

고정 package를 현재 binary reader로 다시 열어 각 reference node의 원시 tagged struct를 조사했다. `scripts/graph_ir.py`의 `member_reference()`가 받기 전 원본 property에서 다음 패턴을 확인했다.

1. external member 13개는 `MemberParent`와 `MemberName`을 저장한다. `MemberGuid`와 `bSelfContext` tag는 없다.
2. self member 6개는 `MemberName`과 `bSelfContext=true`를 저장한다. 이 중 Blueprint member 4개는 `MemberGuid`도 저장하고, engine 함수 2개는 GUID tag가 없다. `MemberParent`는 없다.
3. macro 2개는 `MacroGraph`, `GraphBlueprint`, `GraphGuid`를 저장한다.
4. custom event 1개는 `CustomFunctionName`, create delegate 1개는 `SelectedFunctionName`만 저장한다.

Native loaded-editor 관측에서 저장 GUID가 생략된 15개는 모두 zero GUID (`00000000000000000000000000000000`)였고, 저장 `bSelfContext`가 생략된 13개는 모두 `false`였다. 이것은 저장 tag가 없다는 관측과 editor가 로드한 default 값을 구분하는 근거다. reader는 이 default를 저장값이라고 주장하지 않고 unknown을 유지해야 한다.

저장된 4개 nonzero GUID는 Native loaded GUID와 모두 일치했고 원래 비교의 mismatch도 0이었다. 따라서 이 package에서 GUID word 변환 오류(C)는 관측되지 않았다. 모든 19개 member struct의 raw fields가 reader IR에 대응하므로 parser 정보 누락(B)도 관측되지 않았다.

## 61개 진단의 원인

### A — 정상적인 저장 생략 47개

- `/status` 19개: `scripts/graph_ir.py:member_reference()`가 field absence를 unknown으로 보존하므로 record가 partial이다. 정확한 owner/name 등 다른 필드까지 무효라는 뜻은 아니다.
- `/guid` 15개: 원본 struct에 `MemberGuid` tag가 없다. Native는 로드 후 zero GUID를 관측했다. zero GUID를 saved value로 합성하지 않는다.
- `/self_context` 13개: external reference에서 원본 struct에 `bSelfContext` tag가 없다. Native는 로드 후 `false`를 관측했다. reader는 tag 부재를 unknown으로 유지한다.

tag 부재는 원시 `Ctx.props(export)`와 `graph_ir.semantic_references[].saved_fields` 양쪽에서 확인했다. A를 complete로 만들기 위한 parser 변경은 하지 않았다.

### D — 비교기 owner 판정 13개

수정 전 `tools/compare_editor_oracle.py:_semantic_owner()`는 `self_context` unknown을 먼저 반환했다. 그 결과 `/Script/...` exact `MemberParent`가 저장된 external reference 13개도 owner가 unknown이 되었다. 이는 검증 가능한 긍정 증거를 버린 비교기 오류다.

수정 후 규칙은 다음과 같다.

- `self_context is True`: self owner
- exact parent string: external owner와 exact object path
- 둘 다 없거나 잘못된 경우: unknown

이 규칙은 external이라는 값을 추측하지 않는다. exact parent object path가 저장된 경우에만 external owner를 구성하며, 별도의 `/self_context` 비교는 계속 unavailable이다. 수정 전 같은 이름만 맞아도 통과하는지 확인하는 반례에 wrong parent path를 넣었고 mismatch가 발생함을 검증했다.

### F — CreateDelegate owner 1개

`EventGraph/K2Node_CreateDelegate_1`은 저장 package와 Native Oracle 모두 `SelectedFunctionName=OnPlayerHealthChanged`를 제공한다. 이 값에는 declaring/owning class, member GUID 또는 exact function object path가 없다. 이름 일치는 owner identity가 아니므로 기존 partial 판정을 유지했다.

## 코드 근거

- 저장 tagged fields 투영: `scripts/graph_ir.py`의 `saved_guid()`, `member_reference()`, `semantic_references()`
- loaded-editor 독립 관측: `tools/RepoReaderOracle/Source/RepoReaderOracle/Private/RepoReaderOracleLibrary.cpp`의 `WriteLoadedMemberReference()`, `WriteSemanticReferences()`
- saved/native canonicalization: `tools/compare_editor_oracle.py`의 `_reader_semantic_reference()`, `_native_semantic_reference()`
- owner 판정과 수정: `tools/compare_editor_oracle.py`의 `_semantic_owner()`
- exact graph/node identity와 비교: `tools/compare_editor_oracle.py`의 `_semantic_snapshot()` 및 semantic profile 경로
- 반례: `tests/editor_compare_tests.py::test_semantic_reference_profile_uses_exact_parent_without_inventing_omitted_self_context`

전체 노드·필드·원본/reader/native 값과 각 진단의 분류는 [P6_REFERENCE_FIELD_MATRIX.md](P6_REFERENCE_FIELD_MATRIX.md)에 있다.

## 검증 경계

이번 작업은 기존 P5의 실제 UE 5.8.4 capture를 독립 입력으로 재생했다. Unreal Editor를 새로 실행하거나 UE 5.7에서 재검증하지 않았다. loaded `false`/zero GUID가 모든 Unreal 버전과 모든 node class에서 같은 저장 규칙을 뜻한다고 일반화하지 않는다. E(로드 과정에서 값이 계산되거나 변경됨)는 이 asset에서 saved nonzero 값이 다른 loaded 값으로 바뀐 사례가 없어 0으로 분류했으며, tag 부재 후 default materialization은 A의 근거로만 사용했다.
