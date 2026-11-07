# P0~P6 최종 통합 감사

Date: 2026-11-08

Branch: `codex/p6-semantic-root-cause`

## 판정

P6 브랜치는 P0/P1, P2, P3, P4, P5를 모두 조상으로 포함한다. P4는 P2와 P3의 exact head commit을 merge commit으로
이미 포함한다. 따라서 PR #2와 #3을 별도로 병합하면 코드와 기록을 중복 적용하는 경로가 된다. 현재 안전한 통합 체인은
P6→P5→P4→P0/P1→main이다. 이번 작업에서는 어떤 PR도 병합하지 않았고 main은 `57fc7e3`으로 유지했다.

## 실제 브랜치와 포함 관계

2026-11-08에 GitHub refs를 다시 조회하고 `git merge-base --is-ancestor`로 확인했다.

| 단계 | 브랜치 | phase head | 직접/논리 기준 | 포함 확인 |
|---|---|---|---|---|
| main | `main` | `57fc7e3` | - | P0/P1의 조상 |
| P0/P1 | `codex/accuracy-p0-p1` | `dcb99dc` | main | main 이후 2 commits |
| P2 | `codex/p2-native-reference-validation` | `d4012f9` | P0/P1 | P4의 조상 |
| P3 | `codex/p3-cpp-precision` | `0c945e6` | P0/P1 | P4의 조상 |
| P4 | `codex/p4-unified-analysis` | `ad85408` | P0/P1 + P2 + P3 | P2/P3 exact heads 포함 |
| P5 | `codex/p5-windows-native-validation` | `8c2ec09` | P4 | P4 이후 문서 4개만 추가 |
| P6 | `codex/p6-semantic-root-cause` | `a4872c8` | P5 | P0~P5 전부 포함; 이후 통합 감사 문서 commits 추가 |

P4 merge graph의 `c66da40`은 P2, `6511059`는 P3를 통합한다. P2와 P3는 서로 병렬로 P0/P1에서 출발하지만 둘 다
P4의 조상이다. P5는 P4보다 2 commits, P6 phase 결과는 P5보다 2 commits 앞선다. 최종 통합 감사 기록은 P6 위에만
추가되며 제품 분석 로직을 바꾸지 않는다.

## 단계별 기능 상태

| 단계 | 실제 포함 기능 | 최종 P6 상태 |
|---|---|---|
| P0/P1 | 잘못된 graph-wide pin GUID 추정 제거, exact/unique 연결 규칙, saved semantic reference IR | 유지 |
| P2 | loaded-editor Native Oracle semantic reference 수집기, saved-package/loaded-editor 비교 profile | 유지 |
| P3 | pinned tree-sitter-cpp syntax IR, 함수 본문·source span·호출 spelling 후보, unresolved 계약 | 유지 |
| P4 | 원본 IR 위 additive unified analysis, forward/reverse index, candidate/ambiguous/unavailable 전파 | 유지 |
| P5 | Windows 검증 준비, 고정 ActionRoguelike package/hash, Linux 미실행 경계 보고 | 유지 |
| P6 | exact saved `MemberParent` owner 비교, omitted self/GUID unknown 유지, 61개 원인 매트릭스 | 유지 |

P6 전체 회귀의 실제 ActionRoguelike digest에서 다음 파일 생성을 확인했다.

- `cpp/FUNCTIONS.md`, `cpp/CALL_GRAPH.md`, `cpp/UNRESOLVED.md`, `cpp/CXX_INDEX.json`
- `analysis/OVERVIEW.md`, `analysis/UNRESOLVED.md`, `analysis/UNIFIED_ANALYSIS.json`
- `digest.json.cpp.precision`, `digest.json.unified_analysis`

precision parser는 `tree-sitter 0.25.2`, `tree-sitter-cpp 0.23.4`이고 semantic engine은 없다. 실제 결과 상태가
`partial`인 것은 미확정 호출·전처리·cross-language identity가 남았기 때문이며 실패를 숨긴 것이 아니다.

## P6 코드 검토

`tools/compare_editor_oracle.py:_semantic_owner()`는 다음 긍정 증거만 사용한다.

1. `self_context is True`이면 self owner.
2. exact saved parent object path가 있으면 external owner와 그 exact path.
3. 둘 다 없거나 타입/path가 잘못되면 unknown.

`bSelfContext`가 생략된 13개 external reference의 owner만 exact `MemberParent`로 비교한다. 생략된 self field 자체는
unavailable이고 GUID 15개도 unknown이다. 같은 member name에 잘못된 parent path를 넣은 반례는
`/owner/object_path` mismatch를 요구한다. parser output, Native producer, fixture, Oracle JSON은 바뀌지 않았다.

고정 P5 evidence 재생 결과는 `status=incomplete`, checked 111, mismatch 0, unavailable 48이다. 48개는 정상 저장 생략과
그 aggregate partial 47개, `SelectedFunctionName`만으로 owner를 알 수 없는 CreateDelegate 1개다. complete/pass 수치를
높이기 위해 검사를 제거하거나 loaded default를 saved value로 합성하지 않았다.

## Windows 실측 증거의 범위

저장소의 P5 보고서는 Linux Cloud에서 Windows/UE 접근이 없어 실제 빌드가 차단됐다고 정확히 기록한다. 이후 사용자가 제공한
비공개 P5 Windows evidence ZIP과 보고서를 P6에서 열어 CRC, JSON, 로그, package hash를 검산했다. 그 증거는 UE 5.8.4
plugin build/capture 성공과 P5 85/0/61, P6 replay 111/0/48을 뒷받침한다.

이번 Cloud 작업은 그 동일 JSON/package를 재생했으며 Unreal Editor를 새로 실행하지 않았다. evidence ZIP, Native JSON,
게임 UAsset, Windows 개인 경로/환경 로그는 Git에 추가하지 않았다. UE 5.7, 다른 Blueprint/node class, GridInventorySystem의
새 Native capture는 아직 검증되지 않았다.

## 중복과 충돌 가능성

- 모든 열린 PR #1~#6은 확인 시점에 GitHub `CLEAN`/`MERGEABLE`이었다.
- 각 통합 단계의 base는 head의 조상이다. 현재 순서대로라면 content conflict 없이 merge commit으로 전달할 수 있다.
- PR #2/P2와 #3/P3의 exact commits는 P4에 이미 있으므로 별도 병합하지 않는다.
- P5→P4 PR은 문서 4개만 추가한다. P6→P5는 comparator/test/report 변경을 추가한다.
- 아래 단계의 base branch가 갱신되면 상위 PR diff가 자동 확대된다. 각 merge 직전에 mergeability와 checks를 다시 확인해야 한다.

PR별 상태와 사용자 작업 순서는 [SAFE_MERGE_PLAN.md](SAFE_MERGE_PLAN.md)에 있다.
