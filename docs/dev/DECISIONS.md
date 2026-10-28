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

## D-010 MCP 분석은 프로세스 트리와 독립 타이머로 관리 (2026-10-27, codex)
- 결정: Windows는 stdlib ctypes Job Object(KILL_ON_JOB_CLOSE)와 stdin 게이트, POSIX는 새 세션/그룹을 사용.
  stdout은 별도 스레드에서 UTF-8로 읽고, 실행/EOF 대기는 monotonic 제한시간을 공유한다.
- 이유: readline에 시간 검사를 붙이면 무출력에서 멈추고, 부모 kill만으로는 Git/LFS/파서 자식이 남는다(A5).
- 영향: 추가 의존성 없음. Windows Job 할당 실패 시 분석 시작 전에 오류로 종료. 4096자 초과 로그 행은 생략.

## D-011 MCP 캐시는 버전 포함 전체 식별자 + 완료 표식으로 게시 (2026-10-27, codex)
- 결정: canonical JSON(schema, tool VERSION, host, owner, repo, full commit, project 원문)의 SHA-256 전체를
  URL-safe base64 43자 digest_id로 사용. 성공/producer 버전·커밋 확인 뒤 cache.json을 원자적으로 게시하며
  완료 표식이 없는 INDEX나 예전 버전은 사용하지 않는다. source label도 브랜치 대신 커밋으로 고정.
- 이유: 프로젝트 경로 치환/40자 잘라내기와 커밋 12자 절단은 충돌하며 출력 버전도 키에 없었다(A6).
  이름 접두사+64자 hex는 실제 Windows eg 분석에서 MAX_PATH를 넘어 compact encoding을 선택했다.
- 영향: 이전 digest_id는 analyze_repo로 재생성. MCP의 미광고 짧은 SHA는 전체 40자 SHA를 요구한다;
  브랜치/태그와 CLI의 짧은 SHA 지원은 유지. 캐시 의미 변경 시 CACHE_SCHEMA, 출력 변경 시 기존 VERSION을 올린다.
  추가 의존성·요약본 포맷 변경 없음. tests/server_smoke.py는 선택 SDK 검증이며 기본 회귀에는 SDK가 필요 없다.

## D-012 로컬 스킬은 단일 원본에서 표준 탐색 폴더로 복사 (2026-10-27, codex)
- 결정: 루트 SKILL.md + scripts/를 원본으로 유지. install_skill.py가 codex/claude/copilot과 user/project를
  명시적으로 받아 표준 경로에 독립 실행 가능한 스냅샷을 복사한다. 프로젝트는 .agents/.claude/.github,
  개인은 .agents(Codex·Copilot)/.claude(Claude Code). LICENSE/NOTICE가 있으면 함께 보존한다.
- 이유: 지침만 있는 별칭이나 저장소를 가리키는 링크는 Windows Git 설정/권한에 따라 깨지고 원본 밖의 설치에서
  scripts를 찾지 못한다. 도구별 소스 복제본을 저장소 안에서 유지하면 파서·사용 지침이 서로 어긋난다(R3).
- 영향: 새 의존성·출력 포맷 변화 없음. 기존 Git 클론 설치/업데이트 유지. 복사본은 자동 갱신되지 않으며
  재설치 전 기존 폴더를 옮겨야 한다. 설치기는 기존 폴더·탐색 경로 링크/정션을 교체하지 않고 사용자 설정도 수정하지 않는다.
  chatgpt-plugin/skills의 MCP 전용 지침은 별도 배포이며 로컬 설치에 섞지 않는다. 경로 공식 출처는 README에 기록.

## D-013 기존 클론도 선택 materialize로 전환 (2026-10-27, codex)
- 결정: 재사용에서도 checkout ref 대신 commit 해석→필터 fetch→필요 blob 일괄 fetch→변경 경로만 checkout.
  이전 index의 삭제 경로를 정리하고 .git/ue-repo-reader-paths로 부분 index의 의도된 생략을 구분한다.
- 이유: 전체 checkout은 처음 건너뛴 큰 아트 blob을 다시 받고, 경로만 checkout하면 삭제된 파일이 분석에 남는다(X4).
- 영향: 로컬/스테이징 변경·미추적 충돌은 보존하고 실패, 링크된 Git worktree는 캐시로 거부. ref 없음은 현재 HEAD 유지.
  Git stdin은 UTF-8 바이트로 전달해 Windows CRLF가 fetch refspec을 깨지 않게 한다. 새 의존성/출력 포맷 변경 없음.

## D-014 MCP는 6도구 유지, 영속 리터럴 검색과 공통 응답 예산 적용 (2026-10-27, codex)
- 결정: 기존 도구 이름/기본 인자를 유지하고 목록에 item offset만 추가. 모든 텍스트 응답은 20,000자 이내,
  목록은 200개/호출·전체 10,000개, 읽기는 문자 offset과 bounded streaming을 사용한다.
  완료된 digest 세대마다 search.sqlite를 원자 게시하고 schema/SQLite 버전/캐시 키/완료 표식 mtime으로 재사용한다.
  FTS5 trigram으로 Python lower() 기준 리터럴 부분 문자열을 검색한다. 1~2자 또는 FTS5 없는 SQLite는 같은 캐시의 instr 사용.
  인덱스는 파일당 2MB·전체 64MB·후보 10,000파일·200,000줄까지이며 생략/상한은 응답에 명시. 검색 SQL은 5초로 제한.
- 이유: 매 검색마다 모든 파일을 다시 읽고, 목록/검색/오류 응답은 기존 PAGE 상한을 넘을 수 있었다(R5).
  MATCH 표현식을 직접 노출하면 기존 부분 문자열·기호 검색의 의미가 바뀌므로 검색어를 인용한 literal phrase로 사용한다.
  형식 사실: https://www.sqlite.org/fts5.html#the_trigram_tokenizer (코드 복사 없이 직접 구현).
- 영향: 새 패키지 의존성·digest 포맷 변경 없음. 검색어는 1–256자, 결과는 1–100개로 제한. 큰 파일 읽기는 계속 지원.
  read/search/list의 핸들과 refresh/prune 삭제를 짧은 READ_LOCK으로 조정해 Windows 열린 SQLite/파일 삭제 충돌 방지.
  .git·심볼릭 링크·정션은 검색/glob 목록에서 제외. 검색 schema/범위 의미가 바뀌면 search_index.VERSION을 올린다.
  MCP 스킬과 CHATGPT 가이드에 offset 종류·예산·검색 커버리지 한계를 반영. 공개 배포/인증 설정은 변경하지 않음.

## D-015 에셋별 캐시는 실제 바이트와 디코더를 식별 (2026-10-28, codex)
- 결정: Git blob SHA-1(필터 없이 실제 바이트) + 도구/Python/디코더 소스/고정 파서 버전 + 콘텐츠 경로/클래스로 키를 만든다.
  맵은 외부 액터의 상대 경로·순서·blob도 포함. 정상 결과만 저장하고 교차 사용처/배치/최종 색인은 매번 다시 계산한다.
- 이유: HEAD SHA/mtime/크기만 확인하면 로컬 수정과 LFS pointer→실물 전환을 놓치며, 맵 본체가 같아도 배치 액터는 바뀐다(T3).
  Git 형식 참고: https://git-scm.com/docs/git-hash-object (--no-filters), 공개 포맷을 직접 구현.
- 영향: 새 의존성 없음. JSON/gzip + checksum + atomic replace, 한 항목 32MB·완료 시 LRU 256MB/10,000개.
  실패/부분 결과는 재시도, 손상/권한 오류는 정상 해석으로 복귀. --no-asset-cache로 끄고 --asset-cache-dir로 이동 가능.
  읽기·쓰기·정리에 링크/정션을 허용하지 않으며 캐시와 출력의 겹침은 기존 출력 삭제 전 거부. 포맷/VERSION 유지.
- 통합 실측 후 보완: 분류 헤더는 기존 병렬 스캔으로 매번 읽고 BP/data/map 본문만 캐시한다. 헤더 수백 개를 대신해
  미지원 아트 전체 바이트를 해시/개별 캐시 파일로 읽으면 eg warm 11.16s가 캐시 끈 9.58s보다 느려졌다.
  본문만 캐시하면 같은 PC의 격리된 실측 cold 10.28s/warm 5.09s/disabled 9.62s, 97 hits/0 misses/0 writes/0 errors.
  원시 내용 SHA 검증은 유지한다. OS 캐시·프로젝트 크기에 따라 속도는 달라지며 보편적인 성능 보장은 아니다.

## D-016 INDEX는 읽기 지도, 완전한 목록은 CATALOG로 보존 (2026-10-28, codex)
- 결정: v1.7.0. 기존 전체 INDEX 내용은 CATALOG.md, 새 INDEX는 진입점·커버리지/경고·PageRank 링크·짧은 범례를 담는다.
  최대 30개 링크/9KB를 목표로 보통 2~4k 토큰, 작은 프로젝트는 더 짧다. 실제 토큰 수는 언어/토크나이저에 따라 다르다.
  에셋/C++ 문서 머리말에 순위/해석 상태/인접 문서 링크, JSON navigation에 모든 순위/방향/연결 근거를 저장한다.
- 이유: 전체 목록부터 읽으면 질문과 무관한 에셋에 토큰을 쓴다. 저장 참조와 이름 언급을 탐색 링크로 사용하되
  실제 런타임 호출·의존성·게임플레이 중요도를 확정하지 않는다. 동명 에셋/모르는 명시 경로는 추측 연결하지 않는다(T4).
  PageRank는 공개 알고리즘을 직접 구현(.85 damping, 설정 진입점 seed 5배, dangling 질량 재분배); 코드 복사 없음.
  알고리즘 근거: https://snap.stanford.edu/class/cs224w-readings/Brin98Anatomy.pdf §2.1.1.
- 영향: 기존 BP/노드 수량·의사코드 유지. 전체 데이터/실패/입력/태그 검사는 CATALOG로 이동, INDEX는 경고 수량과 report 링크를 유지.
  CATALOG.partN도 생성 출력으로만 허용하며 report/legend 링크는 실제 분할 파일로 보정한다. 두 SKILL 2절/범례/MCP 지침 갱신.
  VERSION 변화로 MCP 완성 캐시는 자동 무효화. 원시 에셋 캐시에는 순위/머리말을 저장하지 않아 교차 맥락은 매번 계산.
  새 실행 의존성 없음; 개발용 tiktoken은 gitignore 캐시에만 설치해 토큰 수를 비교했다.

## D-017 Map의 값 타입과 저장된 미지정 타입 구분 (2026-10-28, codex)
- 결정: UE PinValueType을 Map 값 타입으로 출력한다. 고정 파서의 map_key_terminal_*는 이름과 달리 그 값 타입이다.
  Category=None은 구체 타입으로 출력하지 않고 ?로 표시하며, 잘린 선언은 variable_type issue로 보고한다(v1.7.1).
- 이유: NewVar의 terminal은 실제로 None/None/object=0으로 저장됐다. 이를 다른 타입으로 추측하면 잘못된 사실이 된다(X2).
  반면 그래프 핀은 파서가 읽어 둔 정상 값 타입을 출력기에 전달하지 않아 항상 ?가 되던 경로가 있었다.
- 영향: 타입 ?의 의미를 INDEX/CATALOG와 두 SKILL에 명시. 변수의 의도된 미지정은 파싱 실패와 구분한다.
  새 의존성/상위 파서 코드 복사 없음. 공식 필드 의미:
  https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/FEdGraphPinType
  https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/FEdGraphTerminalType

## D-018 enum 배열은 저장 FName부터 읽고 이름 연결은 캐시 뒤에서 수행 (2026-10-28, codex)
- 결정: v1.8.0. 명시적 enum 타입이 있는 tagged 배열은 payload/count와 FName 범위·enum 이름을 검증해 직접 읽는다.
  compact byte는 정확히 count 바이트인 ByteProperty만 허용. 알 수 없는 배치는 properties issue로 보고한다.
  UEnum의 실제 (FName,int64) 값 표와 DisplayNameMap을 연결해 Enum::Enumerator(number, display="Label")로 표시한다.
- 이유: DA_PlayerData.Stashinfo는 n=5/size=44, 즉 5개의 FName이었으나 고정 파서가 첫 이름 인덱스의 바이트를
  [7,0,0,0,0]으로 읽었다. 이것에 숫자→이름 치환만 하면 잘못된 사실을 확정한다. 저장 이름의 실제 enum 값은
  [5,6,8,10,11]이며 DataTable의 같은 오독도 확인했다(X1). 레이아웃은 고정 eg 에셋/NameMap 대조로 검증하고 직접 구현.
- 영향: enum 정의는 순번이 아닌 실제 int64 값만 신뢰한다. 동명·잘못된 명시 경로·누락 enum·unknown 값은 저장 이름/숫자를
  보존하고 미해결 수를 INDEX/CATALOG에 표시한다. plain byte/타입 없는 legacy 배열은 enum으로 추측하지 않는다.
  지연 EnumArray와 렌더 span만 후처리해 일반 문자열/숫자를 바꾸지 않는다. 원시 캐시는 이름/숫자와 span을 저장하고,
  이름 연결은 매 실행 수행하므로 enum만 변경/삭제해도 의존 데이터의 재파싱 없이 새 상태를 반영한다.
  새 실행 의존성·상위/타 제품 코드 복사 없음. 필드 의미 참고:
  https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/CoreUObject/FByteProperty

## D-019 FName 번호는 UE 표기(Name_{N-1})로 출력 (2026-10-28, claude)
- 결정: VERSION 1.9.0. 고정 파서의 `FArchive.read_name`을 감싸 저장 번호 N(>0)을 `Name_{N-1}`로 표시한다
  (UE `FName::ToString`: 0 = 접미사 없음, 저장값은 표시 번호+1). 우리 `Ctx.fname`은 원래 이 규칙이었다.
- 이유: uasset_read는 `Name_{N}`으로 찍어 번호 붙은 모든 이름(export·import·FName 값)이 1씩 컸다(B9). 근거:
  FString으로 저장되는 UMG 바인딩 `ObjectName`=`ProgressBar_0` vs 트리 `ProgressBar_1`, 위젯 이름이 `SizeBox`→`SizeBox_2`로
  `_1`을 건너뜀, 시퀀스 첫 핀이 `then_1`, 타임라인 첫 트랙이 `NewTrack_1`(에디터 기본은 `NewTrack_0`). 수정 후 모두 UE 표기와 일치.
- 영향: 번호 붙은 컴포넌트·위젯·액터·핀 이름이 바뀐다(노드 수·디코딩 결과는 동일). 이전 요약본과 텍스트 diff 발생, 에셋 캐시는
  디코더 소스 해시로 자동 무효화. 회귀에 UE 4.12 BattleTank(`bt`, 바인딩 실데이터)를 `nodes_ok`·`allow_issues`로 추가.

## D-020 함수 메타데이터는 저장된 진입점 설명으로 출력 (2026-10-28, codex)
- 결정: v1.10.0. K2Node_FunctionEntry.MetaData의 Category/ToolTip(FText)과 bCallInEditor(bool)를 주석 및
  BP summary.function_metadata에 그래프 경로/진입점 이름과 함께 저장한다. 실행문·함수 플래그와 구분한다(X5).
- 이유: 함수 설명과 분류·에디터 호출 설정이 기존 요약에서 빠졌다. 반면 저장되지 않은 값을 false/빈 설명으로 추정하거나,
  생성된 PinToolTip을 작성자가 저장한 함수 설명으로 사용하면 의미가 달라진다. 실제 eg의 한글 툴팁/Slot 분류로 확인했다.
- 영향: 명시 false/빈 문자열은 보존하고 없는 필드는 생략한다. Opaque 값은 정확한 export index로 재읽으며 읽기 실패는
  function_metadata issue와 unknown 표시로 전파한다. 주석 문자열은 JSON escaping으로 원문을 보존하고 구조체 이름 정리에서 제외.
  두 SKILL 2절/범례/README/플러그인 버전 갱신. v1.9.0(B9) 이후의 새 버전으로 기존 MCP/에셋 캐시를 무효화한다.
  새 의존성·상위/타 제품 코드 복사 없음. 필드 의미 근거:
  https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Editor/BlueprintGraph/FKismetUserDeclaredFunctionMetad-
  https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Editor/BlueprintGraph/UK2Node_FunctionEntry

## D-021 사용자 요청에 따른 Codex 관리·Claude Code 작업자 모드 (2026-10-28, codex)
- 결정: 실제 Claude Code CLI를 별도 worktree에서 실행하고 Codex가 작업 배정·재지시·검토·테스트·커밋·통합·push를 맡는다.
  관리 실행은 파일 읽기·편집 도구만 허용하며, 작업자 성공 응답은 검토 대기 상태로 기록한다.
- 이유: 사용자가 두 도구 사이의 작업 전달까지 직접 관리하도록 요청했다. 같은 checkout의 동시 수정과 검증 전 main 반영을 피하고,
  새 Codex 에이전트를 Claude Code로 오인하지 않도록 AGENTS.md에 관리 모드의 절차 예외와 역할을 명시한다.
- 영향: 단독 Claude/Codex 작업 절차는 유지한다. 세션·프롬프트·로그는 로컬 ignore 경로에만 저장하고 인증 정보는 다루지 않는다.
  새 의존성·전역 권한 변경·전체 권한 우회 없음. Codex 턴 종료 후 지속 감시는 별도 요청이 있어야 한다.
  CLI 실행/재개 방식: https://code.claude.com/docs/en/headless

## D-022 맵 표와 전체 저장 프로퍼티 분리 (2026-10-28, codex)
- 결정: v1.11.0. 기존 맵 표의 짧은 미리보기와 별도로 maps_detail[map_path].actors에 모든 디코딩된 액터·루트 컴포넌트
  저장 프로퍼티를 JSON으로 보존한다. source_package/export_index로 같은 이름의 외부 액터도 구분한다.
- 이유: 길이 120자·8개 표시뿐 아니라 중첩 값 렌더러 자체도 원소/깊이를 제한하므로, 표시 문자열을 저장하면 원래 값을 잃는다(Q4).
- 영향: 문자열·배열·딕셔너리·네이티브 dataclass 필드를 표시용 정리 없이 보존한다. 바이너리는 base64, 비문자열 키는 entries,
  미지원 객체/순환/깊이 64 초과는 unavailable과 actor_values issue로 보고한다. 실패한 프로퍼티는 partial이며 기본값으로 추측하지 않는다.
  별도 컴포넌트 export 추가 해석과 클래스 기본값 복원은 범위 밖이다. INDEX/CATALOG/두 SKILL과 MCP 캐시 버전을 함께 갱신한다.
  새 의존성·외부 코드 복사 없음.

