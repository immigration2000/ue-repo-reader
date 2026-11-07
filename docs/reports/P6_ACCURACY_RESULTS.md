# P6 정확도 개선 및 재검증 결과

## 변경 결과

P6는 parser output을 바꾸지 않았다. 입증된 비교기 오류 한 건만 수정했다.

| 파일 | 변경 |
|---|---|
| `tools/compare_editor_oracle.py` | exact saved `MemberParent`가 있으면 unknown `bSelfContext`와 독립적으로 external owner를 구성하고 비교 |
| `tests/editor_compare_tests.py` | omitted self-context + exact parent는 owner를 비교하며, same-name/wrong-parent는 mismatch인지 검증 |
| `tests/unit_tests.py` | 새 반례를 명시적 단위 회귀 목록에 추가 |
| `docs/EDITOR_ORACLE.md` | exact parent와 omitted self-context의 비교 경계를 명시 |
| `docs/reports/P6_*.md` | P5 증거 검산, 61건 전수 매트릭스, 재검증 결과 기록 |

`scripts/graph_ir.py`, Native Oracle producer, 원본 `.uasset`, P5 Native/compare JSON은 변경하지 않았다.

## 수정 전후

동일한 `semantic-native.json`, 동일 package SHA-256, 동일 `semantic-references` profile을 사용했다.

| 항목 | P5 원본 비교 | P6 수정 비교 | 차이 |
|---|---:|---:|---:|
| status | incomplete | incomplete | 없음 |
| checked observations | 85 | 111 | +26 |
| mismatches | 0 | 0 | 0 |
| unavailable | 61 | 48 | -13 |
| exact-parent owner 미확정 | 13 | 0 | -13 |
| 저장 생략/identity 부족 미확정 | 48 | 48 | 0 |

26개의 추가 checked observation은 13개 external owner 각각의 owner mode와 exact object path다. 기존 85개 관측은 유지했고 필드 검사를 삭제하거나 비교 범위를 줄이지 않았다. comparator 종료 코드는 계속 1이며, 남은 unknown을 pass로 바꾸지 않았다.

## 해결된 항목과 남은 항목

- 실제 parser 오류 수정: 0건. 원본 tagged fields가 모두 reader projection에 있었다.
- 비교기 오류 수정: 13건. exact `MemberParent` owner를 과도하게 unavailable 처리하던 진단이다.
- Unreal 저장 형식 때문에 남은 미확정: 47건. aggregate partial status 19, GUID tag absence 15, self-context tag absence 13이다.
- 원본 identity 부족으로 남은 미확정: 1건. CreateDelegate selected function owner다.
- 원인을 모르는 항목: 0건, 이 고정 evidence의 61건 범위에서만 해당한다.
- 새 mismatch: 0건.

저장 tag가 없는 28개 field에 loaded default를 복사하지 않았다. `unknown`, `saved-package`, `loaded-editor` 경계는 그대로다.

## 실행한 검증

최종 실행 결과는 아래 표에 기록한다. P6 커밋 시점의 실제 명령 결과만 수치로 쓴다.

| 검증 | 결과 |
|---|---|
| 업로드 ZIP CRC·경로 안전성·member 중복 검사 | PASS — 21개 |
| P5 보고서/JSON/로그 수치 독립 재계산 | PASS — 23 refs, native 22 complete/1 partial, saved 4 complete/19 partial, 85/0/61 |
| package before/after/current SHA-256 | PASS — 모두 `2687fa1435cf25e493bf05c2d1e4ddff79cb991dc9c4d43411e6beea4e2cb37e` |
| 원본 raw tagged fields ↔ reader IR 전수 대조 | PASS — 23 refs, member 19개 |
| 수정 전 P5 compare report 재현 | PASS — incomplete, checked 85, mismatch 0, unavailable 61 |
| 수정 후 같은 evidence replay | PASS — incomplete, checked 111, mismatch 0, unavailable 48 |
| exact parent / unknown self-context 반례 | PASS |
| same member name / wrong exact parent 반례 | PASS — mismatch |
| Python compile 및 `git diff --check` | PASS |
| 전체 `tests/unit_tests.py` | PASS — pinned C++ parser 의존성 설치 후 174/174 |
| 고정 external assets | PASS — 6/6 |
| 기존 Native Oracle 그룹 | PASS — pins 2개 + eg 6개 = 8개 |
| 별도 saved/loaded evidence 검사 | PASS — ar saved Nodes, eg loaded-state |
| 고정 프로젝트 | PASS — eg, ar, ves, bt 4/4 |

첫 system-Python 단위 실행은 `requirements-cxx.txt`가 설치되지 않아 P3 C++ precision 4개가 실패했고 나머지 170개는
통과했다. 저장소가 고정한 `tree-sitter==0.25.2`, `tree-sitter-cpp==0.23.4`를 `/tmp` 격리 venv에 설치한 뒤 174/174가
통과했다. 제품 코드 실패로 숨기지 않고 환경 의존성 실패와 최종 결과를 모두 기록한다.

첫 전체 regress는 단위174, assets6, native pins2, ar/ves/bt를 통과한 뒤 기존 `tests/.cache/eg` clone의 local/staged
change를 청결성 검사에서 발견해 exit2로 중단했다. 그 cache를 reset하거나 fixture를 수정하지 않았다. 별도 깨끗한
`/tmp/p6-regress-cache`에서 eg를 다시 clone해 실행했고 eg digest, eg Native Oracle 6개 그룹, loaded-state evidence가 모두
통과했다. 두 실행을 합쳐 고정 프로젝트 4개와 전체 고정 검사를 모두 실행했다.

## 실제 UE 검증과 미실행 항목

실제 UE 5.8.4 빌드/capture는 P5 증거로 검증했다. 이번 Linux Cloud 세션에서는 Unreal Editor를 다시 실행하지 않았다. 아래 항목은 미실행이다.

- UE 5.7에서 같은 plugin/API 빌드 및 capture
- UE 5.8.4에서 수정된 comparator를 Windows에서 직접 실행
- 다른 Blueprint/node class에서 omitted/default 패턴이 같은지 확대 검증
- runtime delegate binding target, UHT/Clang AST 의미 검증

comparator는 플랫폼 독립 Python이며 동일 P5 Native JSON과 동일 package bytes를 재생했지만, 이를 새 Windows capture로 표현하지 않는다.

## 보존과 공개 범위

원본 P5 evidence ZIP은 작업용 첨부 디렉터리와 임시 추출 위치에서만 읽었다. ZIP, 원본 Native JSON, Windows 로그, 개인 PC 절대 경로 및 하드웨어 메타데이터는 Git 변경 목록에 포함하지 않는다. 저장소에는 재현 가능한 코드·합성 반례·민감정보를 제거한 집계와 node identity만 기록한다.

이 결과는 `PlayerHealth_Widget`의 23개 reference와 P5의 UE 5.8.4 capture에 한정된다. unavailable 감소는 의미 정확도 점수가 아니라, 이미 저장된 exact owner 증거를 비교기가 사용하게 된 결과다.
