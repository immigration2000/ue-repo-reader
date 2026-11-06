# 정확도 개선 결과

2026-11-07 · `codex/accuracy-p0-p1` · ue-repo-reader 1.18.0

## 변경한 동작

| 변경 | 이전 | 이후 |
|---|---|---|
| 의사코드 핀 연결 | owner가 없거나 틀려도 graph-wide unique GUID면 연결 | exact owner name/path가 한 핀을 식별할 때만 연결; 그 외 unresolved |
| decoded object reference | full path가 실패하면 같은 short name의 첫 export 선택 | exact path 또는 class-filtered unique short name만 허용 |
| 호출·변수 identity | Markdown의 축약 이름만 남고 graph IR에서 소실 | saved property, package index, exact path, GUID components, self-context와 presence 보존 |
| 불완전 member reference | 구조화 상태 없음 | 레코드별 `partial`과 필드별 `unknown` 사유 표시 |
| 캐시/서버 identity | 1.17.0 결과와 공유 가능 | 버전 1.18.0 및 decoder fingerprint로 분리 |

## 수정한 파일과 함수

- `scripts/bp_reader.py`
  - `Ctx.export_by_ref`: 잘못된 full path와 중복 short name을 거부한다.
  - `GraphRenderer.__init__/resolve`: owner별 후보를 모두 보존하고 full path index를 사용한다. 임의 GUID fallback을 제거한다.
- `scripts/graph_ir.py`
  - 노드별 `semantic_references`를 추가했다.
  - function/event/variable/delegate member reference, macro graph, create-delegate/custom-event 이름을 보존한다.
  - package index가 풀리지 않거나 saved field가 없으면 추정하지 않는다.
- `tests/graph_ir_tests.py`, `tests/editor_compare_tests.py`, `tests/unit_tests.py`
  - 정상 exact path, 잘못된 package index, 누락 필드, invalid GUID component, 중복 owner, 잘못된 owner,
    short-name 충돌과 structural-reference 경계를 검사한다.
- `SKILL.md`, MCP용 `SKILL.md`, `docs/GRAPH_IR.md`, digest 범례
  - 새 필드와 독립 검증 경계를 명시했다.

## 실제 결과

새 `eg` digest에서 `semantic_references` 1,195개를 보존했다. exact parent object path까지 해석된 레코드는
613개다. 전체 중 53개는 필요한 저장 필드가 모두 있어 `complete`, 1,142개는 UE 저장에서 생략됐거나 리더가
확인하지 못한 필드 때문에 `partial`이다. partial을 이름으로 보충하거나 complete로 승격하지 않았다.

실제 UE 5.8 `BP_Knife`에서는 인터페이스 이벤트 `ReciveBeginNotify`의 saved `MemberParent=-2`,
`MemberName`, GUID 네 component와 `/Game/.../BPI_Weapon.BPI_Weapon_C`를 함께 보존했다. self-context 변수처럼
`MemberParent`가 저장되지 않은 경우에는 이름만 남기고 parent를 unknown으로 유지했다.

## 추가·실행한 테스트

최종 기록:

- 새 합성 반례 4개: 통과
- 전체 단위 테스트: 통과
- 외부 에셋 6개: 통과
- Native Oracle 8개와 loaded-state/saved-membership evidence: 통과
- 고정 프로젝트 4개: `eg` 49 BP / 1,778 nodes, `ar`, `ves`, `bt` 모두 통과
- MCP HTTP smoke: 6 tools, response limit, warm/restart/refresh와 strict/opt-in cache 분리 통과
- 실패: 없음
- 미실행: 실제 UE 5.7/5.8 에디터의 새 member-reference 캡처, Windows smoke

기존 Native Oracle 통과는 기존 node/pin/declaration 범위가 퇴행하지 않았다는 뜻이다. 새 member reference 필드는
Oracle producer가 아직 수집하지 않으므로 독립 검증 완료로 분류하지 않는다. UE 에디터 실행은 이번 Linux Cloud에서
수행하지 않았다.

## 남은 정확도 문제

- member reference를 Native Oracle C++ 모듈과 비교기에 추가하고 실제 UE 5.7/5.8에서 재수집해야 한다.
- 의사코드의 개별 node-class 의미는 저장 연결과 별개다. Branch/Loop/Switch/async/delegate의 런타임 의미를
  이번 변경이 독립 검증한 것은 아니다.
- C++ index는 여전히 정규식 기반이다. 함수 본문, 일반 선언, overload-resolved 호출 그래프는 제공하지 않는다.
- empty graph, Control Rig/RigVM, collection FText, map Level Blueprint declaration, effective inherited/CDO 값은 남아 있다.
- 고정 프로젝트가 이 버그의 잘못된 GUID fallback을 실제로 트리거하지는 않았다. 오류는 코드 경로와 재현 가능한
  합성 반례로 확인했으며, 기존 출력의 문자열을 임의로 변경하지 않았다.
