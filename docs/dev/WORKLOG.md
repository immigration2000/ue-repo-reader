# WORKLOG

새 항목은 **맨 위**에 추가합니다. 다음 에이전트가 이 항목만 읽고 이어받을 수 있게 씁니다.

```
## YYYY-MM-DD HH:MM KST · <claude|codex> · <TASK-ID들>
- 한 일:
- 검증: (regress 결과, 직접 확인한 것)
- 남은 일·주의:
```

---

## 2026-10-27 09:30 KST · claude · (규칙 도입)
- 한 일: AGENTS.md(공용 규칙 원본), CLAUDE.md, `.githooks/commit-msg`(태그 검사), docs/dev/TASKS·WORKLOG·DECISIONS,
  회귀 테스트 `tests/regress.py` + `tests/fixtures.json`(고정 커밋 3개) 추가. TASKS는 2026-10-26 조사 로드맵을 옮긴 것.
- 검증: 현재 코드로 regress 3/3 PASS (eg 49 BP·1779 노드, ar 69·1271, ves 2·7).
- 남은 일·주의: 새 기기에서는 `git config core.hooksPath .githooks` 한 번. 이어서 claude가 P0 버그(B1~B6) 수정 진행.
