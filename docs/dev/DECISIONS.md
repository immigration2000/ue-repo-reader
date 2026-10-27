# DECISIONS

되돌리기 어렵거나 다른 에이전트가 알아야 하는 결정만 남깁니다. 새 항목은 **맨 아래**에 번호를 이어서 추가합니다.
형식: `## D-번호 제목 (날짜, 태그)` → 결정 / 이유 / 영향.

## D-001 파서는 uasset_read v0.5.4.44(MIT)로 고정 (2026-09-30, claude)
- 결정: `UASSET_READ_COMMIT = b10a83a…` 유지. v0.5.4.45 이후와 `dev-0.6.0`은 쓰지 않고 코드도 복사하지 않는다.
- 이유: v0.5.4.45는 코드가 같고 LICENSE만 삭제됨. dev 브랜치도 LICENSE 없음.
- 영향: 5.8 등 새 포맷 대응은 우리 패치·리더에서 직접 구현(포맷 사실만 참고).

## D-002 두 AI 핸드오프 작업 방식 (2026-10-27, claude)
- 결정: 규칙 원본은 `AGENTS.md`(Codex가 읽음), `CLAUDE.md`는 `@AGENTS.md` import만. 핸드오프 문서는
  `docs/dev/TASKS.md`·`WORKLOG.md`·`DECISIONS.md`. 커밋 첫 줄에 `[claude]`/`[codex]`/`[human]` 태그, 훅으로 검사.
  작은 작업은 main 직커밋, 큰 작업은 `<태그>/<ID>-…` 브랜치.
- 이유: 두 AI를 번갈아 순차 작업하므로, 다음 에이전트가 문서와 git만 보고 이어받을 수 있어야 함.
- 영향: 모든 변경은 회귀 테스트(`tests/regress.py`) 통과 후 push.

## D-003 회귀 테스트는 고정 커밋 3개 (2026-10-27, claude)
- 결정: ExtractionGame_Fin `f7335ad`, ActionRoguelike `31bd384`, UE5-character-input-framework `bc6badd`를
  전체 SHA로 고정해 노드 수와 문자열 검사로 비교한다.
- 이유: 5.8 / 4.25~5.6 혼합 / World Partition을 각각 대표. 저장소가 바뀌어도 결과가 흔들리지 않게 SHA 고정.

## D-004 출력 포맷 v1.4.0: 값과 의미를 숨기지 않는다 (2026-10-27, claude)
- 결정: 함수는 `-> Out: T`와 `return <값>`, 연결 안 된 object 입력은 `Pin=∅`, 자동 전환은 `when auto (…)`,
  상수 False 규칙은 `when never (…)`. 포맷이 바뀌면 VERSION을 올리고 범례·SKILL.md를 함께 고친다.
- 이유: AI는 요약본을 사실로 읽는다. 생략(빈 return, when False)이 "값이 없다/절대 안 일어난다"로 오독됐다.
- 영향: 이전 요약본과 텍스트 diff가 생긴다(서버 캐시는 커밋+버전 단위로 다시 만들 것).
