# WORKLOG

새 항목은 **맨 위**에 추가합니다. 다음 에이전트가 이 항목만 읽고 이어받을 수 있게 씁니다.

```
## YYYY-MM-DD HH:MM KST · <claude|codex> · <TASK-ID들>
- 한 일:
- 검증: (regress 결과, 직접 확인한 것)
- 남은 일·주의:
```

---

## 2026-10-27 12:10 KST · claude · H2 H3 H5 T1
- 한 일 (VERSION 1.5.0 — B7·B8·H5·T1로 출력 표기가 바뀐 것을 묶어 올림):
  - H2 맵 핀 세 번째 bool(`bTerminalIsUObjectWrapper`)을 `FReleaseObjectVersion >= 31`일 때만 읽음.
  - H3 핀 필드 조합을 커스텀 버전으로 먼저 결정(단정밀도 플래그 `FUE5ReleaseStreamObjectVersion >= 36`,
    UObject 래퍼 `FReleaseObjectVersion >= 31`, SourceIndex는 게이트 불명이라 둘 다 시도). 기존 탐색은 대체 경로로 유지.
    요약 정보 읽기는 `_custom_versions()`(경로별 캐시)로 통합.
  - H5 `FileVersionUE5 > 1018` 또는 알려진 커스텀 버전(FNMB 268, Release 44, UE5RS 68)보다 새 패키지면 BP·data·map 헤더와
    parse report에 경고. 값은 `bp_reader._KNOWN_*` — **새 엔진 버전을 검증하면 여기를 올릴 것**.
  - T1 `digest.json` 압축(공백 제거, AR 124KB→97KB) + "읽지 말 것" 안내(INDEX 범례, SKILL.md). 60k자 넘는 Markdown은
    `X.md` + `X.part2.md…`로 자동 분할(코드 펜스 닫고 다시 염, 끝에 이어보기 링크). 서버는 원래 .md만 나열.
  - 단위 테스트 추가: newer_format_note, combo_order, split_md.
- 검증: regress 3/3 PASS + unit 6/6. H2·H3·H5 전후 출력 동일(경고 오탐 0). 분할은 낮은 한도(10k)로 실제 요약본에 돌려 확인.
- 남은 일·주의: 다음 추천 T2(부분 클론, 콜드 실행의 85~90%가 클론) → T3(blob SHA 캐시). 기능은 F1(GameplayTags)·F2(입력 교차 검사)가 싸고 효과 큼.
  H6·H7(Windows 실기)은 사람 PC가 필요할 수 있음.

## 2026-10-27 11:30 KST · claude · B7 B8 H1
- 한 일:
  - B7 구조체 값 읽기 쉽게: `Name_N_<GUID>` 멤버명 → `Name`(BP·data·map 전부), 구조체 안 object 프로퍼티를 에셋 이름으로
    (`ObjRef` = int 하위 클래스, uasset_read의 object/class 핸들러를 감쌈, `Ctx` 생성 시 `_CUR_CTX` 설정),
    핀 기본값 `0.000000,0.000000,80.000000` → `Vector{X=0, Y=0, Z=80}`, `(TagName="A")` → `GameplayTag{TagName=A}`.
  - B8 길고(60자 초과) 두 곳 이상에서 쓰는 순수 식을 그래프 끝 `// where` 블록에 `$N`으로 한 번만 출력(순수 노드는 매번
    재평가되므로 let이 아니라 where로 표기). 여러 출력 핀을 가진 순수 호출도 대상. 범례·SKILL.md 반영.
  - H1 FText DevNotes를 FString으로 읽음, 게이트를 커스텀 버전(FNMB ≥ 260, 에디터 전용 필터 아님)으로 교체(D-005).
  - `tests/unit_tests.py` 추가(regress가 먼저 실행): DevNotes 합성 바이트, 멤버명, 핀 구조체 표기.
- 검증: regress 3/3 PASS + unit 3/3. H1 전후 출력 바이트 동일(노트가 전부 비어 있음). B7·B8 검사를 이전 출력에 돌리면 실패 확인.
- 남은 일·주의: P0 끝. 다음 추천: H2·H3(맵 핀 bool·단정밀도 플로트를 버전 게이트로), H5(5.9 대비 경고), T1(digest.json 분리).
  `$N` 별칭 기준은 `_ALIAS_MIN_LEN = 60` (bp_reader.py).

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
