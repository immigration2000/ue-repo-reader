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

## D-005 5.8 FText 추가 필드 = DevNotes FString, 커스텀 버전으로 게이트 (2026-10-27, claude)
- 결정: Base 히스토리 FText 뒤의 필드를 FString(DevNotes)으로 읽는다. 게이트는 "저장 엔진 ≥ 5.8" 대신
  `FFortniteMainBranchObjectVersion >= 260 && !PKG_FilterEditorOnly` (요약 정보의 커스텀 버전 표). 표를 못 읽으면 기존 엔진 버전 기준.
- 이유: int32 0과 빈 FString은 같은 4바이트라 지금 데이터로는 구분 불가였지만, 개발 노트가 있는 텍스트에서 int32로 읽으면 핀 전체가 어긋난다.
  포맷 사실은 UE 동작과 공개 고지(UAsset Translator THIRD-PARTY-NOTICES의 "FText DevNotes")에서 확인. 무라이선스 코드는 보지 않고 직접 구현.
- 영향: 고정 커밋 3개 출력은 바이트 단위로 동일. 노트가 있으면 BP 헤더에 "N text dev notes (editor-only) not shown".

## D-006 출력 폴더는 입력과 분리하고 식별된 요약본만 교체 (2026-10-27, codex)
- 결정: `--out`을 resolve해 입력 저장소/선택한 프로젝트와 같거나 이를 포함하는 경로는 삭제 전에 거부한다.
  입력 저장소와의 관계는 클론 전에도 검증한다.
  심볼릭 링크/정션 출력도 거부한다. 기존 비어 있지 않은 폴더는 `digest.json`의 `tool`이 ue-repo-reader이고,
  최상위 항목이 생성 결과(INDEX/분할 INDEX/digest.json, blueprints/cpp/data/maps/config)일 때만 교체한다.
  프로젝트 선택을 삭제 전에 끝내고, 클론/체크아웃 뒤 출력 경로를 다시 검증한다.
- 이유: 기존에는 `--out` 경로를 무조건 재귀 삭제해 입력 프로젝트나 사용자의 일반 파일을 잃을 수 있었다(A2).
- 영향: 정상 요약본 재생성과 입력 내부의 전용 출력 하위 폴더는 계속 지원한다. 중단된 실행 결과나 최상위 메모가 있는
  출력은 새 경로를 지정해야 한다. 생성 폴더 내부는 교체되므로 개인 파일을 보관하지 않는다. 요약본 출력 포맷은 바뀌지 않는다.

## D-007 파서 캐시는 프로세스 잠금과 임시 설치 후 게시 (2026-10-27, codex)
- 결정: 부모가 파서를 준비한 뒤 Pool을 시작한다. 최초 설치는 캐시별 OS 파일 잠금(msvcrt/fcntl)을 잡고,
  임시 폴더에서 고정 커밋을 체크아웃·검증한 뒤 최종 경로로 rename한다. 불완전한 기존 설치는 교체한다.
- 이유: 워커/별도 CLI가 공용 Git 캐시에 동시에 init/fetch/checkout해 잠금 충돌과 반쯤 설치된 모듈이 발생했다.
- 영향: 새 의존성 없음. 잠금 파일은 남겨 두되 잠금 자체는 프로세스 종료 시 OS가 해제한다. 대기는 최대 600초,
  Git 단계는 각 120초. 기존 정상 캐시는 그대로 사용하며 출력 포맷은 바뀌지 않는다.

## D-008 부분 실패는 구조화된 issues로 전파 (2026-10-27, codex)
- 결정: VERSION 1.6.0. BP/data/map summary에 `issues: [{stage, context, message}]`와 `parse_status: ok|partial`을 저장한다.
  문서의 Parse warnings와 INDEX Parse report에도 같은 문제를 표시한다. 맵의 `level_bp_status`는 ok/partial/error,
  실패한 `level_bp_nodes`는 null로 정상 빈 그래프의 [0,0]과 구분한다. WorldSettings를 못 읽으면 게임모드는 unknown.
- 이유: 핀 N/N만으로는 속성·그래프 렌더·외부 액터·레벨 BP의 실패가 가려져 INDEX와 회귀가 거짓 성공을 보고했다(A4).
- 영향: 회귀는 digest.json의 세 종류 에셋·전체 실패·부분 실패·레벨 BP·외부 액터·LFS 다운로드 실패를 검사한다.
  기존 서버 영속 캐시는 refresh=true로 갱신해야 한다(A6는 별도). 의사코드의 정상 실행 흐름 표기는 바뀌지 않는다.

## D-009 회귀에 독립 에디터 정답과 비-BP 수량 포함 (2026-10-27, codex)
- 결정: 기본 regress에 UE Shed 고정 커밋의 작은 자체 생성 에셋 6개를 추가한다. 파일별 Git blob 해시와 라이선스를
  검증/보존하며 바이너리는 캐시에만 받는다. BP 핀과 StringTable은 에디터가 만든 JSON 정답과 비교한다.
  기존 3개 프로젝트는 데이터·맵·외부 액터 수도 고정한다. `--only assets`로 외부 에셋만 실행할 수 있다.
- 이유: BP 수/핀 N/N만으로는 잘못된 텍스트와 데이터/맵 전체 누락을 잡을 수 없었다(H6).
- 영향: 첫 전체 회귀는 추가로 약 210KB의 에셋/정답/라이선스를 다운로드한다. 이후 해시가 맞는 캐시를 재사용한다.
  새 의존성 없음. 출처·검토했지만 미채택한 AssetTools 자료·Windows 격리 검증 절차는 tests/README.md에 기록한다.
