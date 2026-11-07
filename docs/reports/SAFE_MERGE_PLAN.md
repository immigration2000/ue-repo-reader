# P0~P6 안전 병합 계획

Date: 2026-11-08

No merge was performed by this task.

## 현재 PR 구조

2026-11-08 GitHub 재조회 결과다. 상태는 병합 직전에 다시 확인해야 한다.

| PR | Head → Base | 포함 내용 | 상태 |
|---|---|---|---|
| [#1](https://github.com/immigration2000/ue-repo-reader/pull/1) | P0/P1 → main | 정확도 P0/P1 | OPEN, CLEAN, MERGEABLE |
| [#2](https://github.com/immigration2000/ue-repo-reader/pull/2) | P2 → P0/P1 | Native semantic validation | OPEN, CLEAN, MERGEABLE; P4에 포함됨 |
| [#3](https://github.com/immigration2000/ue-repo-reader/pull/3) | P3 → P0/P1 | C++ precision | OPEN, CLEAN, MERGEABLE; P4에 포함됨 |
| [#4](https://github.com/immigration2000/ue-repo-reader/pull/4) | P4 → P0/P1 | P2+P3+unified analysis | OPEN, CLEAN, MERGEABLE |
| [#5](https://github.com/immigration2000/ue-repo-reader/pull/5) | P6 → P5 | exact owner fix와 P6 reports | OPEN, CLEAN, MERGEABLE |
| [#6](https://github.com/immigration2000/ue-repo-reader/pull/6) | P5 → P4 | Windows validation boundary reports | OPEN, CLEAN, MERGEABLE |

PR #6은 이번 작업에서 새로 만들었다. P5 diff는 `docs/dev/TASKS.md`, `docs/dev/WORKLOG.md`,
`P5_WINDOWS_NATIVE_VALIDATION.md`, `P5_SEMANTIC_ACCURACY.md`뿐이며 parser/fixture/Oracle code를 바꾸지 않는다.

## 권장 순서

1. **PR #5 검토 후 merge commit으로 P6 → P5 병합**
   - checked111/mismatch0/unavailable48과 unknown 보존을 확인한다.
   - merge 후 P5 head가 P6 commits와 최종 통합 reports를 포함하는지 확인한다.
2. **업데이트된 PR #6으로 P5 → P4 병합**
   - PR #5가 먼저 병합돼야 P6가 P4로 전달된다.
   - PR #6 diff가 P5/P6 전체를 포함하는지 다시 확인한다.
3. **업데이트된 PR #4로 P4 → P0/P1 병합**
   - P4에는 P2 `d4012f9`와 P3 `0c945e6`가 이미 있다.
   - PR #2와 #3은 병합하지 않는다. P4 포함 관계를 재확인한 뒤 사용자가 superseded로 종료한다.
4. **최종 전체 회귀 재실행**
   - 단위174, assets6, Native8, evidence2, projects4, MCP6 tools를 확인한다.
   - branch SHA와 generated output/tool version을 기록한다.
5. **PR #1로 P0/P1 → main 병합**
   - PR #4까지 P0/P1에 들어간 뒤에만 진행한다.
   - main에는 직접 push하지 않는다.

이 bottom-up 순서는 각 하위 base branch를 먼저 완성하여 마지막 PR #1이 P0~P6 전체를 한 번만 main으로 전달하게 한다.

## 각 단계의 사용자 확인 목록

- GitHub base/head SHA가 계획과 같은가
- `mergeable=CLEAN`이며 required checks가 모두 성공했는가
- 예상 밖 binary, ZIP, Oracle JSON, UAsset, 개인 경로/로그가 diff에 없는가
- fixture/expected answer 변경이 없는가
- merge 방식이 history를 보존하는 merge commit인가
- auto-merge, force push, branch history rewrite가 꺼져 있는가

PR #2/#3은 사용자가 P4 ancestry를 확인한 뒤 닫는다. 이번 작업은 기존 PR을 닫거나 merge하지 않았다.

## 충돌 시 처리

현재 graph에서는 모든 통합 base가 head의 조상이고 GitHub가 CLEAN으로 판정한다. 이후 branch가 바뀌어 conflict가 생기면
main이나 기존 phase branch를 rewrite하지 않는다. P6 최종 branch에서 새 통합 branch를 만들고 충돌 파일의 양쪽 의미를 검토한
뒤 전체 회귀를 다시 실행하여 새 PR로 대체한다. fixture 기대값을 바꿔 conflict나 제품 오류를 숨기지 않는다.

## 최종 사용 branch

- 병합 전 GridInventorySystem 분석: `codex/p6-semantic-root-cause`
- 승인된 순서가 끝난 뒤: main의 P0~P6 통합 merge commit

현재 main은 `57fc7e3`이며 이번 작업에서 변경하지 않았다.
