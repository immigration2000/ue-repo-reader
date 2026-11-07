# GridInventorySystem 분석 준비 상태

Date: 2026-11-08

Recommended branch before approved merges: `codex/p6-semantic-root-cause`

## 준비 판정

GridInventorySystem을 변경하지 않는 정적 읽기 분석에는 준비됐다. UE 5.7/5.8 project declaration, C++ source,
Blueprint/data/map saved package를 digest로 만들고 C++↔Blueprint 후보를 양방향 탐색할 수 있다. 다음 의미는 아직 증명할 수 없다.

- compiler/UHT가 선택한 exact C++ overload 또는 generated function identity
- virtual/interface/RPC/delegate의 runtime dispatch target
- 저장되지 않은 Blueprint 기본값과 editor load fixup의 일반 규칙
- GridInventorySystem package에 대한 새 UE 5.8 Native Oracle 일치

이 관계들은 candidate, ambiguous 또는 unavailable로 유지해야 한다. 이름 하나만 같다는 이유로 verified로 승격하지 않는다.

## 요구 사항

| 항목 | 요구 |
|---|---|
| Python | 3.10+ |
| source access | Git, private repo이면 사용자의 정상 Git credential |
| binary assets | Git LFS 설치; 고정 full commit 사용 |
| C++ precision | `requirements-cxx.txt`: tree-sitter 0.25.2, tree-sitter-cpp 0.23.4 |
| parser cache | `UE_REPO_READER_CACHE`를 writable 별도 위치로 지정 |
| input | 개발 중 원본이 아닌 깨끗한 분석 전용 clone |
| output/cache | project 밖의 서로 다른 전용 디렉터리 |

분석기는 source를 저장하거나 Blueprint를 컴파일하지 않는다. 다만 LFS materialization과 clone checkout은 분석 clone의 working
files를 바꿀 수 있으므로 개발자가 쓰는 원본 checkout을 입력으로 사용하지 않는다.

## Linux Cloud 실행

```bash
cd /workspace/ue-repo-reader
python -m venv /workspace/grid-reader-venv
/workspace/grid-reader-venv/bin/pip install -r requirements-cxx.txt
export UE_REPO_READER_CACHE=/workspace/grid-reader-cache

/workspace/grid-reader-venv/bin/python scripts/ue_repo_digest.py \
  <GRID_REPOSITORY_URL> \
  --ref <FULL_40_CHAR_COMMIT> \
  --workdir /workspace/grid-readonly-clone \
  --out /workspace/grid-analysis \
  --asset-cache-dir /workspace/grid-asset-cache
```

여러 `.uproject`가 있으면 `--project <relative-path-or-name>`을 추가한다. 정상 범위 밖 선언을 탐색할 때만
`--best-effort`를 명시하고 결과의 unconfirmed 상태를 유지한다.

## Windows 실행

```powershell
cd C:\work\ue-repo-reader
py -3 -m venv C:\work\grid-reader-venv
C:\work\grid-reader-venv\Scripts\python.exe -m pip install -r requirements-cxx.txt
$env:UE_REPO_READER_CACHE = "C:\work\grid-reader-cache"

C:\work\grid-reader-venv\Scripts\python.exe scripts\ue_repo_digest.py `
  <GRID_REPOSITORY_URL> `
  --ref <FULL_40_CHAR_COMMIT> `
  --workdir C:\work\grid-readonly-clone `
  --out C:\work\grid-analysis `
  --asset-cache-dir C:\work\grid-asset-cache
```

Unreal Editor는 digest 생성에 필요 없다. GridInventorySystem의 semantic reference를 editor-loaded 값과 독립 대조할 때만
원본이 아닌 별도 검증 clone에 `RepoReaderOracle`을 설치하고 package pre/post SHA-256과 dirty=false를 확인한다.

## 결과 읽기 순서

1. `INDEX.md`: project support, coverage, Parse warnings, 읽기 우선순위
2. `CATALOG.md`: 전체 asset/type 목록과 Parse report
3. 질문과 관련된 `blueprints/`, `cpp/`, `data/`, `maps/` 문서
4. `cpp/UNRESOLVED.md`와 `analysis/UNRESOLVED.md`
5. 구조화 탐색은 `cpp/CXX_INDEX.json`, `analysis/UNIFIED_ANALYSIS.json`, `digest.json`

Blueprint 결과는 class/parent, function/event graph, node/pin/link, semantic references와 unknown 사유를 보존한다. C++ 결과는
class/struct/inheritance, UFUNCTION/UPROPERTY raw annotations, declaration/definition/body/source span, call spelling 후보를 보존한다.
통합 결과는 `relation_index.by_source`와 `by_target_or_candidate`로 정방향/역방향을 찾는다.

## 증분 분석과 캐시

`--asset-cache-dir`은 파일 bytes, parser/tool version, map external actor identity로 cache를 식별한다. 바뀐 asset만 본문 decode를
재사용하거나 다시 읽지만 사용처·navigation·통합 index는 매번 계산한다. 실패·partial 결과는 성공 cache로 고정하지 않는다.
검증 재실행에는 `--no-asset-cache`를 사용해 fresh decode와 결과를 비교할 수 있다.

## MCP 접근

선택 MCP 서버는 읽기 전용 6도구를 제공한다.

- `analyze_repo`, `wait_for_analysis`
- `list_digest_files`, `read_digest_file`
- `search_digest`, `read_source_file`

`server/requirements.txt`를 격리 환경에 설치하고 `python server/server.py`로 loopback/host 설정에 맞게 실행한다. 실제 공개
호스트에서는 secret path와 owner allowlist를 설정하고 GitHub token은 필요한 private repository에 read-only Contents 권한만
준다. 40자 commit SHA를 사용하며 `refresh=true`는 명시적인 재분석에만 쓴다.

## Parse warning과 confidence 처리

- asset의 `parse_status`, `issues`, graph/declaration IR status를 먼저 확인한다.
- unified relation의 `verified`, `candidate`, `ambiguous`, `unavailable`을 그대로 답변에 표시한다.
- saved pin/MacroGraph의 verified는 저장 identity이며 runtime order가 아니다.
- C++ tree-sitter 관측은 `syntax_observed`; `semantic_resolved`는 현재 비어 있다.
- LFS pointer/size skip, partial graph, missing external actor를 정상 빈 값으로 해석하지 않는다.

## 권장 읽기 전용 분석 프롬프트

> `codex/p6-semantic-root-cause`의 ue-repo-reader로 GridInventorySystem의 고정 commit을 새 전용 clone에서 분석하라.
> 원본 프로젝트를 수정하지 말고 출력과 cache는 프로젝트 밖에 둔다. INDEX/CATALOG의 support·coverage·Parse warnings를 먼저
> 확인한 뒤, 질문 관련 Blueprint graph/node/pin과 C++ source span을 양방향으로 추적하라. verified/candidate/ambiguous/
> unavailable과 saved-package/loaded-editor/syntax provenance를 구분하고, 이름만 같은 관계를 확정하지 말라.

승인된 통합이 끝나면 같은 절차의 branch를 `main`의 승인된 release commit으로 바꾼다.
