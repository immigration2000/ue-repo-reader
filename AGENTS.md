# AGENTS.md — 이 저장소에서 일하는 AI 공용 규칙

이 저장소는 **Claude(Claude Code)와 Codex가 번갈아(핸드오프) 작업**합니다. 이 파일이 규칙의 원본이고,
`CLAUDE.md`는 이 파일을 불러오기만 합니다. 규칙을 바꿀 때는 이 파일만 고치고 `docs/dev/DECISIONS.md`에 이유를 남깁니다.

## 0. 프로젝트 한 줄 요약

언리얼 프로젝트 **git URL(또는 로컬 폴더)** 만으로 블루프린트·맵·데이터 에셋·C++을 AI가 읽을 수 있는 Markdown 요약본으로
만드는 도구. 에디터·엔진 없이 바이너리 `.uasset/.umap`을 직접 디코딩합니다. 저장소 루트가 그대로 스킬 폴더입니다(`SKILL.md`).

| 경로 | 내용 |
|---|---|
| `scripts/ue_repo_digest.py` | 진입점: 클론, LFS 선택 다운로드, 분류, 병렬 렌더, INDEX.md |
| `scripts/bp_reader.py` | 블루프린트 → 의사코드, uasset_read 런타임 패치 |
| `scripts/data_reader.py` | 데이터 에셋(DataTable, 구조체, 열거형, BT, StateTree, 입력 …) |
| `scripts/map_reader.py` | 맵: 레벨 BP, 배치 액터, World Partition |
| `server/` | 원격 MCP 서버 (선택 사항) |
| `tests/` | 회귀 테스트 (`tests/regress.py`, 기대값 `tests/fixtures.json`) |
| `docs/dev/` | 핸드오프 문서: `TASKS.md`, `WORKLOG.md`, `DECISIONS.md` |

## 1. 작업 시작할 때 (매번)

1. `git pull --rebase` — 다른 AI가 올린 작업을 먼저 받는다.
2. 처음 클론한 기기라면 한 번: `git config core.hooksPath .githooks` (커밋 메시지 태그 검사 훅).
3. `docs/dev/WORKLOG.md` 맨 위 항목 2~3개와 `docs/dev/TASKS.md`를 읽는다. 이어받을 일·주의사항이 거기 있다.
4. 할 일을 하나 고르고 `TASKS.md`에서 상태를 `doing`, 담당을 자기 태그(`claude` / `codex`)로 바꾼다.
   이미 다른 에이전트가 `doing`인 항목은 건드리지 않는다.

## 2. 작업 끝낼 때 (매번)

1. 회귀 테스트 통과: `python tests/regress.py` (아래 4절). 실패하면 push하지 않는다.
2. `TASKS.md` 상태를 `done`(또는 `blocked` + 이유)으로 바꾼다.
3. `WORKLOG.md` **맨 위에** 항목을 추가한다(형식은 파일 안 템플릿). 다음 에이전트가 이것만 읽고 이어받을 수 있게
   "한 일 / 검증 / 남은 일·주의"를 쓴다.
4. 되돌리기 어려운 결정(포맷 변경, 의존성, 규칙 변경)은 `DECISIONS.md`에 한 항목으로 남긴다.
5. 커밋 후 `git push`. 작업을 push하지 않은 채 끝내지 않는다.

## 3. 커밋·브랜치

- 커밋 메시지 첫 줄은 **에이전트 태그로 시작**: `[claude] …`, `[codex] …`, 사람이 직접 하면 `[human] …`.
  훅(`.githooks/commit-msg`)이 검사한다.
- 형식: `[태그] <TASK-ID>: <무엇을 왜>` — 예: `[codex] B3: print goto targets that were never labelled`.
- 작은 작업(한 TASK, 회귀 통과)은 `main`에 바로 커밋한다. 여러 TASK에 걸치거나 출력 포맷을 크게 바꾸는 작업은
  `<태그>/<TASK-ID>-<짧은설명>` 브랜치에서 하고, 끝나면 `main`에 fast-forward 또는 PR로 합친다.
- 한 커밋에 한 가지 일. 포맷만 바꾸는 정리(공백, 리네임)는 기능 변경과 섞지 않는다.
- 각 도구가 요구하는 attribution 줄(예: Claude의 `Co-Authored-By`)은 그대로 붙인다.

## 4. 테스트 (변경마다 필수)

```bash
python tests/regress.py                 # 고정 커밋 3개를 클론해 요약본을 만들고 기대값과 비교
python tests/regress.py --only eg       # 하나만
python tests/regress.py --repo eg=/path/to/local/clone   # 이미 받아 둔 클론 재사용
```

- `tests/unit_tests.py`(클론 없이 도는 빠른 검사)가 regress 시작 때 먼저 돈다. 저장소로 재현할 수 없는 포맷 경우(예: 비어 있지 않은
  DevNotes)는 여기에 합성 바이트로 검사를 넣는다.
- 기대값(`tests/fixtures.json`): BP 수, 노드 수 `N/N`, 실패 0, 그리고 버그 재발 방지용 문자열 검사
  (`must_contain` / `must_not_contain`). 버그를 고치면 **그 버그를 잡는 검사를 반드시 추가**한다.
- 노드 수나 BP 수가 바뀌는 것이 의도된 변경이면 기대값을 고치고 WORKLOG에 이유를 쓴다.
- Windows 경로·인코딩에 영향을 주는 변경이면 `docs/CODEX_SETUP.ko.md` 절차가 여전히 맞는지 확인한다.

## 5. 코드 규칙

- Python 3.10+, 표준 라이브러리 우선. 새 의존성은 DECISIONS에 기록하고 `SKILL.md` 요구사항에 반영.
- 파일 I/O와 subprocess는 항상 `encoding="utf-8"` (Windows 기본 cp949 대비). `shell=True` 금지. 경로는 `pathlib`.
- 멀티프로세싱은 `spawn` 컨텍스트, 워커 초기화 함수는 예외를 던지지 않는다(풀이 무한 재생성됨).
- 디코딩 실패는 조용히 넘기지 말고 요약본의 parse report에 남긴다. **AI가 사실로 읽으므로, 모르면 모른다고 출력**하고
  추측한 값을 출력하지 않는다.
- 출력 표기(의사코드 문법, 범례)를 바꾸면 `INDEX.md` 범례와 `SKILL.md` 2절을 같이 고친다.

## 6. 파서·라이선스 (중요)

- `soatori/uasset_read`는 **v0.5.4.44 (`b10a83a`, MIT)로 고정**한다. 이후 버전(v0.5.4.45, `dev-0.6.0` 브랜치)은
  LICENSE가 없으므로 **코드를 복사하지 않는다.** 포맷 "사실"(필드 순서, 버전 게이트)만 UE 동작 기준으로 직접 구현한다.
- 독점 제품(UAsset Translator, StraySpark Lucid 등)은 공개 문서의 개념만 참고하고 리버스 엔지니어링하지 않는다.
- MIT/BSD/Apache 코드(UAssetAPI, unreal-asset-mcp, UE Shed, CUE4Parse …)를 옮길 때는 출처와 라이선스 고지를 남긴다
  (Apache-2.0은 NOTICE 유지). GPL(FModel) 코드는 가져오지 않는다.
- 새 디코딩 로직은 uasset_read를 더 패치하기보다 우리 리더(`data_reader.TaggedReader` 등)에 넣는다.

## 7. 하지 말 것

- 토큰·비밀번호·`GITHUB_TOKEN`을 커밋하거나 출력에 남기기.
- 큰 바이너리(.uasset, 요약본 결과물, 클론)를 커밋하기. 테스트 캐시는 `tests/.cache/`(gitignore).
- 다른 에이전트가 `doing`인 작업을 덮어쓰기, `main`에 force-push.
- 사용자에게 확인 없이 공개 범위·배포 대상(Space, 마켓플레이스 등)을 바꾸기.
