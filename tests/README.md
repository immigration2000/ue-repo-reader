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

서버 회귀도 단위 검사에 포함한다(`server_tests.py`). 선택 의존성 MCP SDK의 데코레이터만 대역으로 두고
실제 작업·프로세스를 실행한다. 무출력/줄바꿈 없는 출력/연속 출력/출력 핸들 닫힘의 시간 제한,
부모 종료 뒤 stdout을 상속한 자식의 종료, UTF-8·종료 코드·토큰 마스킹·작업 슬롯 회수를 검사한다.

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
- Store 스텁 거부, `py -3` 선택, Python 없음, native stderr와 종료 코드 7 보존을 검사한다.
- 로컬 Git-LFS 저장소에서 실제 포인터를 만들고, 특수문자 `.uasset/.umap` 두 개를 `git lfs pull --include` 대체 경로로 받는다.
  다운로드된 바이트도 원본과 대조한다.

결과와 stdout/stderr 로그는 `tests/.cache/windows-smoke/`에 남긴다. 관리자 설치·실제 Microsoft Store UI·새 PC의 winget 설치는 검증 범위 밖이다.
