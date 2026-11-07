# P0~P6 최종 회귀 결과

Date: 2026-11-08

Source: `codex/p6-semantic-root-cause`, P6 phase commit `a4872c8`

## 환경과 의존성

- Linux Cloud, Python 3.12
- parser cache: workspace의 별도 writable cache
- C++ precision: `tree-sitter==0.25.2`, `tree-sitter-cpp==0.23.4`
- 전체 프로젝트 회귀: 기존 dirty cache를 reset하지 않고 새 `/tmp` cache에서 clone/build
- MCP SDK: `server/requirements.txt`의 기존 격리 target 사용

fixture, Oracle JSON, 원본 package, 외부 프로젝트는 수정하지 않았다.

## 최종 결과

| 검사 | 결과 |
|---|---|
| Python 단위 테스트 | PASS — 174/174 |
| Blueprint Graph IR | PASS — 단위 반례 + 고정 프로젝트 |
| Declaration IR | PASS — 단위 반례 + 기존 Native replay |
| C++ Precision Index | PASS — pinned parser 사용, syntax/partial 경계 유지 |
| Unified Analysis | PASS — forward/reverse index와 status propagation |
| Semantic Reference 비교 반례 | PASS — exact/wrong/missing/duplicate/unknown |
| 외부 독립 에셋 | PASS — 6/6 |
| 기존 Native Oracle 그룹 | PASS — 8/8 |
| saved/loaded evidence 검사 | PASS — 2/2 |
| 고정 프로젝트 | PASS — eg, ar, ves, bt 4/4 |
| MCP 실제 HTTP smoke | PASS — 6 tools |
| Python compile / diff whitespace | PASS |

고정 프로젝트 결과는 eg 23초, ar 59초, ves 8초, bt 7초였다. 시간은 Cloud 실행의 관측값이며 성능 보증이 아니다.
ActionRoguelike 결과에는 Blueprint 69개와 C++ precision/unified output이 함께 생성됐다.

## P6 동일 증거 재생

실행 profile은 `semantic-references`이며 P5의 동일 Native JSON과 동일 package bytes를 사용했다.

| 항목 | 결과 |
|---|---:|
| status | incomplete |
| checked | 111 |
| mismatch | 0 |
| unavailable | 48 |
| aggregate partial | 19 |
| saved GUID absent | 15 |
| saved self-context absent | 13 |
| CreateDelegate owner unavailable | 1 |

comparator exit code 1은 이 profile의 incomplete를 뜻한다. mismatch나 실행 실패가 아니다. 48개를 제거하거나 unknown을
default로 바꾸지 않았다.

## 실제 실행 명령

```bash
export UE_REPO_READER_CACHE=/workspace/shared/ue-repo-reader-cache
/tmp/p6-venv/bin/python tests/unit_tests.py
```

전체 회귀는 source를 바꾸지 않고 `tests.regress.CACHE`만 새 `/tmp/p6-github-regress-cache-20261108`로 지정하여
`tests/regress.py`의 같은 `main()`을 실행했다. 이는 이전 LFS materialization이 남은 cache clone을 reset하지 않기 위한
격리이며 fixture/check 범위를 바꾸지 않는다.

```bash
python tests/server_smoke.py --deps tests/.cache/server-deps --repo tests/.cache/eg
```

MCP smoke는 `analyze_repo`, `wait_for_analysis`, `list_digest_files`, `read_digest_file`, `search_digest`,
`read_source_file`의 6개 Streamable HTTP 도구, 20k response limit, warm/restart/refresh, strict/best-effort cache 분리를 통과했다.

## 미실행·검증 경계

- 이 최종 Linux 실행에서 Unreal Editor/UBT/MSVC를 새로 실행하지 않았다.
- UE 5.7 plugin build와 semantic capture는 미실행이다.
- GridInventorySystem 자체의 digest와 Native capture는 미실행이다.
- Clang AST, UHT symbol identity, runtime virtual/interface/delegate target은 미실행이다.

실제 UE 5.8.4 성공은 사용자가 제공한 P5 Windows evidence의 로그/JSON/hash를 P6에서 검산한 결과다. 이번 Cloud 회귀의
독립 엔진 실행 결과로 바꾸어 표현하지 않는다.
