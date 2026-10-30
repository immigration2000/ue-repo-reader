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

## D-023 회귀의 알려진 실패는 에셋별 정확한 기대값으로만 허용 (2026-10-28, claude/codex)
- 결정: bt의 allow_issues를 제거하고 알려진 issue의 stage/context/message 다중집합, 모든 BP 노드 수,
  모든 Level Blueprint 노드 수/상태를 고정한다. 전역 허용 플래그와 null parse_status는 거부한다(Q7).
- 이유: Codex가 새 BP 오류를 주입해도 기존 bt 검사가 통과함을 재현했다. 실제 Claude Code가 구현했고,
  Codex 검토에서 null 상태 공백도 발견해 같은 세션에 수정 지시했다.
- 영향: 새 오류·변경/중복/사라진 오류·개별 에셋 해석 감소와 합계가 같은 노드 재분배를 실패로 잡는다.
  bt의 기존 26/98과 5개 맵 issue는 지원 완료가 아닌 고정된 알려진 제한이다. 기본 회귀의 프로젝트 수 문서도 4개로 정정한다.
  다른 프로젝트의 기본 엄격 기준·디코더·독립 에디터 정답은 유지한다. 새 의존성 없음.

## D-024 표시 생략과 해석 실패를 구분한다 (2026-10-28, claude/codex)
- 결정: v1.12.0. BP dict/구조체·데이터 구조체의 짧은 표시에도 …(+N)으로 생략 수를 남긴다(Q8).
  추가 CDO 40개 상한 이후 값과 opaque/native 표시 제외·미확장 subobject는 별도 수량/이름 안내를 남긴다.
  선언 변수표에 이미 실린 값과 의도적으로 걸러낸 내부 필드는 유실 수에 섞지 않는다.
- 이유: 작은 요약을 완전한 값 목록으로 읽으면 레포의 동작과 기본값을 잘못 설명할 수 있다. 값 종류를 고려해
  <literal>/AnimNode_ 같은 정상 문자열을 native/opaque로 오인하지 않는다.
- 영향: 생략 표시만으로 parse_status를 partial로 바꾸지 않으며, 해석 실패는 기존 Parse warnings와 별개로 계속 보고한다.
  표시에서 빠진 값은 이 문서로 확인할 수 없고 기본값으로 추정하지 않는다. BP/데이터 전체 값 보존(W2)은 아직 별도 작업이다.
  두 SKILL·INDEX/CATALOG 범례·출력 버전을 동기화한다. 새 의존성 없음.

## D-025 버전 있는 핀 투영 IR과 의미 검증의 한계를 분리 (2026-10-28, codex)
- 결정: v1.13.0. BP summary.graph_ir 및 맵 level_bp_graph_ir에 스키마 1의 노드 정체성·핀 타입/기본값·저장 참조를 보존(Q9).
  저장 소유자/핀 GUID로 그래프 안에서만 대상을 연결하고, 구조용 parent/subpin/pass-through만 같은 노드 관례를 별도 basis로 표시.
  모호함·누락·잘못된 값/객체 경로는 unknown과 issue로 남긴다. 선언된 필드가 디코더에 없으면 조용히 생략하지 않는다.
- 이유: 의사코드/짧은 이름 색인만으로 핀 연결·값 손실을 자동 정답 대조하기 어렵다. 표시용 문자열을 공통 데이터로 재사용하면 정보가 손실된다.
  실제 Claude 교차 검토로 기본 객체 경로/부재 전파와 저장키·파생키 충돌을 보완했다. 객체 경로는 원본 필드와 별도 namespace에 둔다.
- 영향: 식별자는 패키지 스냅샷 안의 export/pin 기준이며 영구 diff 키라고 보증하지 않는다. 핀 GUID는 저장 바이트 순서,
  graph/node GUID는 미정규화 원문임을 구분한다. N/N은 노드에 핀이 하나 이상 있다는 뜻이며 핀 목록 전체·게임플레이 의미를 보증하지 않는다.
  node 속성·CDO·빈 그래프·실행 의미·런타임 값은 범위 밖. INDEX/CATALOG/두 SKILL 및 docs/GRAPH_IR.md에 계약 명시.
  Q1의 5.7/5.8 독립 정답은 현재 pin ID/텍스트 부분만 IR에도 대조하며, 전체 의미/객체 기본값의 에디터 정답 확보는 남겨 둔다.
- 회귀 경계: bt는 26/98 및 원래 5개 issue를 유지하고 새 IR 진단 85개만 정확한 다중집합으로 추가 고정한다.
  구조용 소유자 보완 후에도 bt의 미확정 참조 31개는 해당 그래프의 어떤 핀 GUID와도 일치하지 않음을 확인했으며 구버전 디코더를 확장하지 않음.
  새 오류/중복/사라진 오류/개별 BP·Level BP 노드 수 감소는 계속 실패한다. 전역 허용은 복원하지 않는다.
  graph_ir.py 변경도 캐시 fingerprint에 포함하고 출력 버전으로 서버 캐시를 분리. 새 제품 의존성·외부 구현 복사 없음.

## D-026 프로젝트 지원 선언과 에셋 호환·의미 검증을 분리 (2026-10-28, codex/claude)
- 결정: v1.14.0. 목표는 UE 5.7+ 프로젝트이며, 현재 기본 분석은 선택한 .uproject의 숫자 EngineAssociation 5.7/5.8에 한정(Q10/Q11).
  튜플로 major/minor를 비교하고 patch 원문을 보존한다. 5.7 미만·미검증 미래 버전·GUID/빌드 라벨/선언 부재는 기본 거부한다.
  명시적인 CLI --best-effort / MCP best_effort=true는 탐색만 허용하며 분류를 target으로 바꾸지 않는다.
- 이유: 구버전 프로젝트 확대보다 높은 정확도와 레포 이해에 집중한다. 프로젝트 버전을 에셋 최대/최빈 저장 버전으로 추정하면
  현대 프로젝트에 섞인 오래된 에셋을 잘못 배제하므로 에셋별 기존 호환 리더는 유지한다. 선언 일치와 노드 수는 의미 정확도의 보증이 아니다.
- 경계: 선택한 descriptor를 한 번 읽고 출력 교체·에셋 캐시 생성·LFS 다운로드·디코더 설치 전에 판정한다.
  원격 저장소는 선언 확인을 위해 clone할 수 있다. 소스 빌드 ID/빈 선언의 실제 엔진은 추정하지 않는다.
  UTF-8로 읽을 수 없는 JSON, 비객체/비표준 상수, 중첩을 포함한 중복 키 또는 JSON 읽기 실패는 이 도구의 엄격한 메타데이터 정책상 미확정이다.
  이는 Unreal Editor가 그 파일을 열 수 없다는 주장이 아니다. JSON 오류와 원래 선언/선택 경로를 가능한 범위에서 digest에 보존한다.
- 영향: INDEX/CATALOG 상단에 지원 상태와 의미 검증 한계를 출력하며, 정책 정보가 없는 문서는 미확정이다.
  일반/탐색 모드와 정책 버전·최소/검증 상한을 서버 캐시 identity에 포함(CACHE_SCHEMA=2); producer의 정책·요청 모드도 검증한다.
  MCP의 지원 거부만 별도 표식으로 식별해 도구 인자 best_effort=true를 안내하며 일반 입력 오류와 혼동하지 않는다.
- 고정 사례 정정: 실제 고정 commit의 .uproject는 eg=5.8, ar=5.8, ves=5.7, bt=4.19다. ar=5.6/bt=4.12라는 이전 프로젝트 표기는
  에셋 저장 버전과 혼동한 것이므로 fixtures·HTML 보고서를 정정한다. bt만 명시적 탐색으로 회귀를 유지한다.
  BP/노드/개별 issue 기대값은 완화하지 않으며, 오래된 에셋이 있는 5.8 프로젝트의 실제 캐시 cold/warm 검증을 유지한다.
  새 제품 의존성·외부 구현 복사 없음. Q1의 독립 에디터 의미 정답 확보는 별도 최우선 후속 작업이다.

## D-027 네이티브 에디터 관측과 저장 바이트의 독립 대조 (2026-10-29, codex/claude)
- 결정: v1.15.0. Q1/Q12에 선택적인 개발용 에디터 수집 모듈·Python exporter·새 바이너리 비교기와 독립 정답3개를 추가.
  일반 레포 분석의 Python/Git 요구사항은 유지한다. 선택적 oracle 수집에만 UE5.7+·Python Script Plugin·C++ 빌드 도구가 필요하다.
- 이유: 실제5.8 Python probe에서 Blueprint의 graph/variable 배열과 graph.nodes는 노출되지 않았고,
  stock list_all_pins는 visible K2 핀만 제공했다. 전체 노드/숨긴 핀을 정답으로 삼으려면 별도 native bridge가 필요하다.
  에디터의 공개 API/필드를 직접 읽는 자체 코드를 만들었으며 엔진 구현/다른 디코더 코드를 복사하지 않는다.
- 출처: 캡처는 우리 파서/리더를 import하지 않으며 native FText 원문과 UObject 경로를 반환한다.
  source text와 package_dirty=false를 요구한다. 해시가 같아도 저장 안 된 메모리 편집은 비교 가능한 저장 상태로 인정하지 않는다.
  같은 패키지 SHA-256을 캡처/비교 전후에 확인하며 잘못된/미확정 자산도 기록에서 없애지 않는다.
- 계약: schema1, 명시적 all/graph profile과 제외 범위. GUID는 uint32 워드별 저장 바이트 순서로 변환하고 소유 노드 안에서 식별.
  타입 category/subcategory만 FName의 대소문자 무관/None 의미를 정규화하며 원문 snapshot은 보존한다.
  opaque 변수 타입이나 미해석 IR 필드를 빈 타입/기본값으로 만들지 않는다. nonempty graph가 없는 graph 비교는 미확정이다.
- 정답/검사: 실제5.7.4/5.8.4로 캡처한 고정 UE Shed 패키지와 eg BFL_Util을 tests/editor_oracles에 JSON으로 보존.
  source commit/패키지 해시와 독립 snapshot은 변경하지 않는다. 리더가 보고하지 않는 메타데이터3/3/11개만 정확한 경계로 별도 고정하며,
  이것은 그 필드가 검증되었다는 허용 목록이 아니다. 그래프는 일치해야 하고 전체 비교의 가용 값도 불일치가 없어야 한다.
  새 갭/변경/중복/누락은 실패한다. 엔진 없이 기본 회귀에서 재생하며 바이너리/빌드/큰 전체 캡처 결과는 캐시에만 둔다.
- 발견/수정: 고정 linker의 Actor→/Script/Engine→/Script/CoreUObject 체인에서 GetFullName이 native 경로를 중복했다.
  Ctx.full_name이 저장된 절대 package/object 이름에서 경로를 종료하도록 고쳐 실제 pin/object default 경로21개 차이를 제거했다.
  버전·캐시 fingerprint로 이전 출력의 재사용을 막으며 기존 BP/노드/issue 기대값은 완화하지 않는다.
- 한계: native loaded state는 저장 바이트와 같지 않을 수 있다. eg52개 전체 캡처는 비교 파이프라인 검증/차이 발견에 사용하며
  전체 게임플레이 의미 정확도의 완료로 보고하지 않는다. 저장 안 된 상태와 별개인 엔진 로드 보정도 Q14에서 조사한다.
  변수 타입/일부 선언값은 어댑터 미확정(Q13), CallInEditor=true 실데이터 정답(Q5), CDO/상속 유효값과 런타임 동작은 남는다.


## D-028 저장 선언 구조를 표시 문자열과 분리 (2026-10-29, codex/claude)
- 결정: v1.16.0. Q13/Q15에서 `blueprints[path].declaration_ir` schema1을 추가하고 native 비교기의 선언 입력으로 사용한다.
  변수 타입은 raw EdGraphPinType, 플래그는 uint64 십진 문자열, category는 FText source, 기본값은 선언에 저장된 문자열이다.
  부모·함수 그래프는 패키지 인덱스로 정확한 객체 경로를 찾는다. 선언 전용 tagged 읽기에서 표시용 짧은 이름 변환을 끈다.
- 부재 계약: 저장되지 않은 NewVariables/FunctionGraphs/Bindings를 빈 배열로 간주하지 않는다. `saved_fields`와 unknown 이유를 남긴다.
  명시적 빈 배열/빈 문자열/0/null을 구분하며, non-map terminal은 저장되지 않아 미확정이다. CDO/상속·실행 값은 추정하지 않는다.
  변수/바인딩 정체성 누락·중복은 컬렉션을 미확정으로 만든다. 맵 Level Blueprint 선언은 이 API 범위 밖이다. tagged 오류와 잘못된 현대 타입 바이트는 parse report에 남긴다.
- 타입 범위: 검증한 현대 저장 게이트(UE4>=518, Framework>=37, Release>=31, UE5 Release Stream>=36)만 새로 디코딩한다.
  구버전 저장 레이아웃의 타입 구조는 raw bytes+unknown으로 남기며 기존 표시용 호환 리더는 유지한다.
  새 디코더는 표준 struct로 직접 작성했고 엔진 구현·고정 버전 이후 uasset_read 소스를 복사하지 않았다.
  필드 순서·게이트는 설치된 UE5.7/5.8의 EdGraphPin/Node 소스와 공개 FEdGraphTerminalType API 사실을 확인했다.
- 비교 범위: 표시 문자열/별도 tagged 재해석 대신 공개 선언 IR의 가용 값을 비교한다. 선언 Map 값 const/weak 플래그도 비교한다.
  graph 핀의 해당 플래그는 기존 제외 범위를 유지한다. projection/stream 문제와 미확정 필드는 완전 일치로 승격하지 않는다.
- 회귀 정답: Q1의 독립 eg52개 native 캡처에서 에셋4개(변수7개)를 변형 없이 선택한다. Map 값/객체·텍스트·구조체 배열을 포함한다.
  기존 정답3개의 native snapshot/출처commit/패키지 해시를 바꾸지 않으며, 부재 NewVariables를 미확정으로 정정한 1개 갭씩만 추가한다.
  각 새 정답의 출처 Git blob도 고정 commit/path와 대조한다. 전체 graph 비교와 all의 가용 값 일치 및 정확한 미확정 다중집합 검사, 기존 BP/노드/issue 기대값을 유지한다.
- 캐시: declaration_ir.py를 fingerprint에 포함하고 출력 버전을 1.16.0으로 올린다. 제품 의존성 추가와 신규 native 빌드는 없다.
  남은 saved/loaded 차이 원인 조사는 Q14, 실데이터 CallInEditor=true는 Q5, 실제 비어 있지 않은 위젯 바인딩의 native 정답은 별도 검증 공백이다.

## D-029 저장 그래프 멤버십·텍스트 원문과 native 세션 관측을 분리 (2026-10-30, codex/claude)
- 결정: v1.17.0. Q14/Q17에서 UE5 저장 그래프의 top-level Nodes 태그/소유 export/타입/경계/원시 개수를 검증한 뒤에만
  Outer로 묶인 목록 밖 노드를 그래프 집계에서 분리한다. 전체 노드·핀은 unlisted_graph_nodes에 보존하고 saved_membership과
  membership_basis로 기준을 공개한다. 잘못된/부재/미해결 목록은 기존 view와 unknown을 유지하며, 명시적 count0은 확인된 빈 목록이다.
- 이유: eg ABP_Hands의39개 저장/native 멤버 밖 export109, ar GideonManny의6개 저장 멤버 밖 export155를 기존 파서가 추가했다.
  eg1779→1778, ar1271→1270은 그래프 집계의 정정이며 데이터를 버리는 변경이 아니다. ar은 원본 바이트 증거로만 주장한다.
  별도 EntryNode가 목록 밖 export를 참조하면 충돌을 보존하고 런타임 entry를 추정하지 않는다. 영역 간 원시 owner/GUID도 유지한다.
- 범위: 새 멤버십 검증은 UE5 저장 패키지에 한한다. UE4 저장 패키지는 범위 밖 unknown과 기존 view로 두고 bt26/98 및
  정확한90개 issue 기준을 유지한다. 잘못된 실제 바이트와 I/O 실패는 parse report로 전파하며 미지원 자체는 새 오류로 만들지 않는다.
- 텍스트: Editor custom version>=32의 scalar tagged FText History=None 원문을 자체 bounded 리더로 디코딩한다.
  ASCII narrow/UTF16 wide를 구분하고 길이·종단·presence를 검증한다. 실제 엔진에서 비정규0xe9의 widening이 U+FFE9임을 관측했으므로
  Latin-1/코드페이지 추측을 하지 않고 비정규 narrow 입력은 unknown으로 둔다. 실패 sentinel과 authored literal을 선언/함수 API에서 구분한다.
  TArray/Map/Set의 FText는 종전 경로이며 후속Q18로 분리한다. 빈 표시를 원문 부재로 보증하지 않는다.
- 독립 관측: 같은 패키지7개를 UE5.8.4의 두 프로세스에서 각각2회 캡처했다. 프로세스 안73318개 관측은 같고,
  프로세스 사이 숨긴 ErrorTolerance17개 GUID가 달라졌다. 저장 const/default와 native 값의 안정적 차이2개도 계속 보고한다.
  정확한 엔진 보정 호출 경로나 실행상 동등성은 단정하지 않는다. 비교기가 이름으로 ID를 추정하거나 차이를 제외하지 않는다.
- 진단 도구: 실제 Claude Code가 native 반복 캡처만 비교하는 도구와 반례9개를 작성하고 Codex가 재지시·독립 실행·통합했다.
  비교 입력 전제 오류는 거부, 유효한 입력의 어떤 갭도 incomplete가 changed보다 우선하며 관측된 차이는 보존한다.
  BP_Knife native 정답1개와 선택된 원본 관측/바이트 증거만 회귀에 추가한다. 큰 전체 캡처·복사본·바이너리는 캐시에 둔다.
- 영향: 두 SKILL·INDEX/CATALOG·Graph IR 문서를 같이 갱신하고 graph_membership.py를 캐시 지문에 포함한다.
  선택적 --no-pch는 소유한 임시 에디터 smoke 호스트에만 적용하며 실제5.8.4 빌드/수집으로 검증했다.
  엔진 구현·고정 버전 이후 uasset_read 코드를 복사하지 않았고 새 제품 의존성은 없다.
