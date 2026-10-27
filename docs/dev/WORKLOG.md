# WORKLOG

새 항목은 **맨 위**에 추가합니다. 다음 에이전트가 이 항목만 읽고 이어받을 수 있게 씁니다.

```
## YYYY-MM-DD HH:MM KST · <claude|codex> · <TASK-ID들>
- 한 일:
- 검증: (regress 결과, 직접 확인한 것)
- 남은 일·주의:
```

---

## 2026-10-27 10:40 KST · claude · B1 B2 B3 B4 B5 B6
- 한 일 (출력 포맷 v1.4.0):
  - B1 함수 결과: `return true/false` 등 값 출력(5.8은 결과 핀 default==auto_default라 기존 필터가 숨김), 헤더에 `-> Out: T`.
  - B2 애님 전환: `bAutomaticRuleBasedOnSequencePlayerInState` → `when auto (…)`, 상수 False 규칙 → `when never (…)`,
    비기본 전환 설정 `[blend Xs, priority N, on start/end/interrupt notify X]`. `state_machine()`이 이제 4-튜플(…, props).
  - B3 goto: exec 진입 수를 reroute knot 너머 실제 대상으로 셈 + 라벨 없는 goto가 남으면 강제 라벨로 한 번 재렌더.
  - B4 연결 안 된 object/class/interface 입력을 `Pin=∅`로 표시(advanced/hidden 핀 제외).
  - B5 `--ref`: 40자 SHA는 그 커밋만 fetch, 짧은 SHA는 blobless 클론으로 해석, 못 찾으면 명확한 error로 종료.
    기존 클론 재사용 시에도 `--ref`로 체크아웃(이전에는 무시됐음).
  - B6 Used by 자기 이름(같은 이름의 다른 에셋) 제외, 깨진 클래스명(`/Script/…_1476395008`) 버림,
    이름 추정 분류를 실제 클래스에 합침(`NiagaraSystem 23`), `other (by name)` → `unknown class`.
  - 범례(INDEX.md), SKILL.md, chatgpt-plugin SKILL.md에 새 표기 반영. VERSION 1.4.0.
- 검증: regress 3/3 PASS, 버그별 검사 7개 추가(fixtures.json). 같은 검사를 수정 전 출력에 돌리면 eg 11·ar 3건 실패 → 검사가 실제로 잡음.
  수정 전후 diff에서 의도하지 않은 변화 없음(라벨 번호 이동만). 짧은 SHA/없는 SHA/전체 SHA 클론 경로 직접 실행 확인.
- 남은 일·주의: P0 중 B7(구조체 기본값 원시 출력)·B8(순수 노드 반복 인라인)은 todo. 다음 추천은 H1(FText DevNotes FString).
  `Pin=∅`는 선택 입력(OwningPlayer 등)에도 붙는다 — 사실이지만 많아지면 F-계열에서 "선택 입력" 구분 검토.

## 2026-10-27 09:30 KST · claude · (규칙 도입)
- 한 일: AGENTS.md(공용 규칙 원본), CLAUDE.md, `.githooks/commit-msg`(태그 검사), docs/dev/TASKS·WORKLOG·DECISIONS,
  회귀 테스트 `tests/regress.py` + `tests/fixtures.json`(고정 커밋 3개) 추가. TASKS는 2026-10-26 조사 로드맵을 옮긴 것.
- 검증: 현재 코드로 regress 3/3 PASS (eg 49 BP·1779 노드, ar 69·1271, ves 2·7).
- 남은 일·주의: 새 기기에서는 `git config core.hooksPath .githooks` 한 번. 이어서 claude가 P0 버그(B1~B6) 수정 진행.
