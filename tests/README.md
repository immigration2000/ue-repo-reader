# 회귀 테스트

```powershell
python tests/regress.py                 # 단위 검사 + 외부 에셋 6개 + 고정 프로젝트 3개
python tests/regress.py --only assets   # 단위 검사 + 작은 에셋/에디터 정답 대조
python tests/regress.py --only eg ar    # 지정 프로젝트만 (단위 검사는 항상 실행)
python tests/windows_smoke.py           # 실제 Windows PowerShell 5.1 설치 가이드·LFS 검증
```

Python 3.10+와 Git이 필요하다. `python`이 WindowsApps 스텁이면 설치 가이드의 선택 함수를 쓰거나 실제 Python 경로를 지정한다.
Windows smoke는 이미 있는 Python/Git/git-lfs를 사용하며 소프트웨어를 설치하지 않는다.
생성 결과·외부 바이너리·클론·실행 로그는 모두 gitignore된 `tests/.cache/`에 둔다.

T3 에셋 캐시: 기본 단위 검사에서 실제 Git blob SHA, 같은 크기/mtime의 내용 변경, 도구/디코더/콘텐츠 경로,
외부 액터 추가·변경·순서, 부분 실패 재시도, 손상/체크섬, 변경분만 워커 실행, 정션 밖 파일 보존을 확인한다.
실제 프로젝트에서 cold/warm/캐시 끄기의 모든 Markdown/JSON 바이트와 시간·hit 수를 비교하려면:

```bash
python tests/cache_smoke.py tests/.cache/eg
```

스킬 설치 검사(`skill_install_tests.py`)는 세 도구의 개인/프로젝트 경로 6개에 실제 파일을 복사한다.
한글·공백·대괄호·쉼표 경로에서 다른 작업 폴더를 cwd로 설치본의 CLI 도움말과 네 리더의 로컬 import를 실행하고,
기존 파일 보존·존재하지 않는 프로젝트·탐색 경로의 symlink/Windows junction 거부를 확인한다.
사용자 홈은 임시 경로로 대체하며 실제 개인 스킬 폴더·설정은 바꾸지 않는다.

`clone_tests.py`는 필터를 지원하는 로컬 Git 원본에서 두 커밋을 만든다. 초기/재사용/짧은 SHA/ref 없음에서
대형 텍스처 blob이 계속 없는지 실제 object DB를 검사하고, 필요한 대형 BP·특수문자 경로·삭제 파일 정리,
변경 없는 파일 mtime 유지, 로컬/스테이징 수정·미추적 파일 보존을 확인한다. 외부 다운로드나 바이너리 커밋은 없다.

서버 회귀도 단위 검사에 포함한다(`server_tests.py`). 선택 의존성 MCP SDK의 데코레이터만 대역으로 두고
실제 작업·프로세스를 실행한다. 무출력/줄바꿈 없는 출력/연속 출력/출력 핸들 닫힘의 시간 제한,
부모 종료 뒤 stdout을 상속한 자식의 종료, UTF-8·종료 코드·토큰 마스킹·작업 슬롯 회수를 검사한다.
캐시 검사는 유사·긴·한글 프로젝트 경로, 전체 커밋, 버전/스키마 변경, 중단된 출력·손상된 완료 표식,
재사용·refresh·중복 요청과 실제 자식 출력의 producer 버전/커밋 불일치를 다룬다.

`search_tests.py`는 실제 SQLite FTS5에서 리터럴 부분 문자열(한글/짧은 단어/따옴표/기호), 소스 포함 여부와 `.git` 제외,
warm 인덱스 무재탐색·동시 요청·새 완료 세대/손상 인덱스 재생성을 검사한다. FTS5 없음과 검색 용량 초과도 주입한다.
모든 도구의 20,000자 제한, 문자/항목 페이지의 무손실 연결, 큰 파일의 부분 읽기, glob의 정션 이탈 방지와
열린 reader가 있는 동안 refresh 삭제가 대기하는지도 실제 파일 핸들로 확인한다.

실제 SDK의 Streamable HTTP 검증은 선택 실행이다(서버 의존성 설치와 eg 고정 클론 필요).

```powershell
python -m pip install -r server/requirements.txt
python tests/server_smoke.py
# SDK를 전역에 설치하지 않으려면 별도 venv 또는 pip --target 디렉터리 사용
python -m pip install --target tests/.cache/server-deps -r server/requirements.txt
python tests/server_smoke.py --deps tests/.cache/server-deps
```

`server_smoke.py`는 loopback에만 서버를 열고 기존 eg를 실제 CLI로 분석한다. 원격 커밋 조회/클론만 로컬 픽스처로
대체하며 원본 파일 읽기용 `.uproject`를 임시 repo에 복사한다. 도구 6개·1779/1779 노드·경로 이탈 거부·캐시 재사용·
강제 재분석·서버 재시작 후 디스크 캐시 재사용을 확인한다. 임시 데이터는 `tests/.cache/` 아래에 만들고 종료 시 정리한다.

## 기본 프로젝트

`fixtures.json`의 고정 커밋을 대상으로 BP/노드뿐 아니라 데이터·맵·외부 액터 수도 검사한다.
개별 summary 필드와 문서 문자열, 전체 실패 및 `issues`/`parse_status`도 확인한다.

| 프로젝트 | BP / 노드 | 데이터 | 맵 | 외부 액터 |
|---|---:|---:|---:|---:|
| eg | 49 / 1779 | 43 | 5 | 64 |
| ar | 69 / 1271 | 50 | 3 | 0 |
| ves | 2 / 7 | 4 | 1 | 138 |

ves는 World Partition 맵의 액터 139개와 외부 패키지 138개를 별도로 고정한다.
테스트 러너 자체에도 데이터/맵 누락, 잘못된 텍스트, 손상된 다운로드를 잡는 검사를 둔다.

## 독립 에디터 정답이 있는 외부 에셋

출처: [UE Shed, 고정 커밋 73f7c701](https://github.com/ue-shed/ue-shed/tree/73f7c7015e1a5d688c7d3c69abf92d1e4e28ba78/fixtures).
`asset_fixtures.json`에 전체 커밋과 파일별 Git blob 해시를 고정한다. 라이선스도 캐시에 함께 받는다.
선택한 파일만 다운로드하며 외부 코드나 바이너리를 이 저장소에 복사/커밋하지 않는다. 새 의존성은 없다.

- BP_Keys 4개: UE 4.27.2, 5.6.1, 5.7.4, 5.8.3. [픽스처 설명](https://github.com/ue-shed/ue-shed/blob/73f7c7015e1a5d688c7d3c69abf92d1e4e28ba78/fixtures/graph-pin-text/README.md)에 따라,
  `expected.json`의 노드·핀 위치·핀 GUID·텍스트 원문을 실제 파싱 값과 대조하고 Markdown에도 원문이 나오는지 검사한다.
  GUID는 에디터의 uint32 네 단어 표기와 고정 파서의 직렬화 바이트 순서를 구분한다.
- StringTable 2개: UE 4.27, 5.3의 `ST_LegacyText`. [생성 프로젝트](https://github.com/ue-shed/ue-shed/tree/73f7c7015e1a5d688c7d3c69abf92d1e4e28ba78/fixtures/legacy-unreal-project)의
  `evidence.json`에서 네임스페이스·키·문자열을 읽어 결과와 대조한다.

에디터에서 생성된 기존 정답을 사용한다. 이 테스트가 Unreal Editor를 실행하거나 픽스처를 재생성하는 것은 아니다.
정답 JSON을 우리 리더 출력으로 덮어쓰면 안 된다. UE Shed 라이선스는 고정 커밋의 [MIT LICENSE](https://github.com/ue-shed/ue-shed/blob/73f7c7015e1a5d688c7d3c69abf92d1e4e28ba78/LICENSE)다.

[AssetTools 9f29146b](https://github.com/PedroMartinsMenezes/AssetTools/tree/9f29146b2f58b326af86b94432a30bd1a39e2035)도 검토했다.
코드의 MIT 고지와 별개로 `Data/Input/EditorMeshes`, 엔진/샘플 콘텐츠와 cooked 게임 자료가 섞여 있고,
`Data/Output`은 변환기 출력이다. 이번 기본 회귀는 출처가 명시된 자체 생성 에셋과 독립 에디터 정답이 있는 UE Shed 자료를 채택했다.
AssetTools 바이너리나 코드는 가져오지 않았다.

## Windows PowerShell 5.1 smoke

`windows_smoke.py`는 설치 가이드의 PowerShell 블록 7개를 5.1 파서로 확인하고, 이미 설치된 의존성을 사용해
진단·Python 선택·Git 설정·스킬 설치·실제 분석을 실행한다. 설치가 불필요하므로 winget 단계는 실행하지 않는다.

- 사용자 경로 대신 임시 경로를 쓰고, 분석 대상은 eg의 고정 커밋으로 재현한다.
- `GIT_CONFIG_GLOBAL`/Git 검색 상한을 격리해 사용자 Git 설정과 저장소 훅을 건드리지 않는다. 사용자 Git 설정 해시도 전후 비교한다.
- 한글·공백·대괄호·쉼표 경로에서 가이드가 Coverage를 실제 출력하는지 확인한다.
- 가이드의 Git 클론 설치를 확인한 뒤, 최소 파일만 복사한 `.agents/skills/ue-repo-reader` 설치본으로 실제 eg를 분석한다.
- Store 스텁 거부, `py -3` 선택, Python 없음, native stderr와 종료 코드 7 보존을 검사한다.
- 로컬 Git-LFS 저장소에서 실제 포인터를 만들고, 특수문자 `.uasset/.umap` 두 개를 `git lfs pull --include` 대체 경로로 받는다.
  다운로드된 바이트도 원본과 대조한다.

결과와 stdout/stderr 로그는 `tests/.cache/windows-smoke/`에 남긴다. 관리자 설치·실제 Microsoft Store UI·새 PC의 winget 설치는 검증 범위 밖이다.
