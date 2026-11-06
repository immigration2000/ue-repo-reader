# ue-repo-reader 정확도 감사

2026-11-07 · 기준 `main` 57fc7e3 · 작업 브랜치 `codex/accuracy-p0-p1`

## 감사 기준과 방법

README의 주장이나 노드 수만으로 지원 여부를 판단하지 않았다. `bp_reader.py`, `graph_ir.py`,
`declaration_ir.py`, `ue_repo_digest.py`, Native Oracle 모듈과 비교기, 테스트 러너와 고정 픽스처를
직접 읽었다. 변경 전 기준선은 단위 검사, 외부 에셋 6개, 기존 Native Oracle 8개, 고정 프로젝트
`eg/ar/ves/bt` 4개가 통과했다. 이 통과는 아래에 적은 비교 범위만 증명하며 전체 Blueprint 의미
정확도를 뜻하지 않는다.

## 현재 코드 구조

1. `ue_repo_digest.py`가 저장소를 부분 클론하고 LFS 대상을 제한한 뒤 C++·에셋을 분류한다.
2. `bp_reader.py`가 고정된 `uasset_read` 커밋을 패치해 그래프·핀과 tagged property를 읽고 Markdown
   의사코드를 만든다. 여러 직렬화 조합 중 읽힌 노드 수가 가장 큰 결과를 선택한다.
3. `graph_membership.py`는 UE5 저장 그래프의 bounded `Nodes` 배열을 별도로 확인해 Outer 기반 결과와
   구분한다. 확인되지 않은 경우 기존 view를 유지하며 `unknown`으로 남긴다.
4. `graph_ir.py`는 노드·핀·저장 링크와 선택된 멤버 참조를 구조화한다. `declaration_ir.py`는 부모,
   변수 선언, 함수 그래프, 위젯 바인딩의 저장 필드를 별도로 보존한다.
5. `RepoReaderOracle`은 UE 5.7/5.8 에디터가 로드한 객체를 C++에서 읽는다. Python 비교기는 같은
   패키지 해시를 확인한 뒤 새 바이너리 리더 결과와 대조한다.
6. C++ 색인은 `ue_repo_digest.py:scan_cpp`의 헤더 정규식이다. 리플렉션 표면의 일부만 수집하며 AST가 아니다.

## 영역별 지원과 검증 수준

| 영역 | 현재 구현 | 검증 수준 | 남은 위험 |
|---|---|---|---|
| Blueprint/부모 클래스 | saved `ParentClass` package reference를 declaration IR에 보존 | UE 5.7/5.8 일부 Native Oracle과 합성 반례 | 태그 부재, map Level Blueprint 선언, 상속된 유효값은 미확정 |
| 함수·이벤트·매크로·중첩 그래프 | parser graph view, 역할 목록, UE5 saved `Nodes` membership | 고정 프로젝트와 saved membership 원시 바이트 증거 | 빈 그래프, UE4 membership, Control Rig/RigVM은 비교 범위 밖 |
| 노드·핀 | object path/export index, 클래스, 핀 순서·GUID·방향·타입·기본값·표시 플래그 | UE 5.7/5.8 Native Oracle 8개와 합성 변이 검사 | N/N은 핀이 하나 이상 읽힌 노드 수이며 핀 목록 완전성 보증이 아님 |
| 저장 연결 | owner path/name + pin GUID를 그래프 내부에서 해석, 모호성 보존 | Native Oracle의 저장 link 관측과 중복·교차 그래프 반례 | 저장 링크는 실행·도달 가능성 증명이 아님 |
| 함수·변수·델리게이트·매크로 참조 | 1.18부터 saved field/package index/exact path/GUID/self-context 보존 | 저장 tagged property와 합성 반례, 실제 BP_Knife에서 확인 | Native Oracle이 아직 이 필드를 독립 캡처하지 않아 부분 검증 |
| 의사코드 실행 흐름 | Branch/Sequence/Loop/Switch, 호출, 반환, delegate 등을 수작업 렌더링 | 고정 문자열·합성 회귀와 전체 digest 회귀 | 엔진 실행 모델이 아니며 노드별 해석 규칙의 누락 가능성 |
| 데이터 흐름 | 입력 링크 추적, pure 표현식, reroute, sub-pin 표시 | 링크·기본값 변이와 실제 digest 회귀 | node property 의미, wildcard 승격, 컴파일 후 확장 결과는 미검증 |
| C++ 리플렉션 표면 | UCLASS/USTRUCT/UENUM/UINTERFACE, 일부 UFUNCTION/UPROPERTY | 정규식 단위의 간접 회귀 | 일반 함수/필드, 본문, 호출 그래프, 오버라이드, 매크로·조건부 컴파일에 취약 |

## 독립 Native Oracle이 실제 비교하는 범위

현재 비교기는 부모 클래스, 변수 선언 일부, 함수 그래프 목록, 위젯 바인딩 일부, 비어 있지 않은 그래프의
노드 클래스, 모든 수집 핀의 이름·방향·타입·기본값·표시 플래그와 저장 링크, 함수 entry metadata 일부를
비교한다. 패키지 SHA-256, dirty 상태, 엔진 버전, 캡처 출처도 확인한다.

다음은 독립 비교 완료로 간주할 수 없다.

- 빈 그래프, 그래프/노드/변수 GUID, 에디터 배치
- 함수·변수·델리게이트·매크로의 saved member reference 의미
- 함수 flags/keywords/compact title의 전체 범위
- 위젯 binding SourcePath 전체
- graph pin map terminal의 일부 flags와 FText localization identity
- Control Rig/RigVM, 런타임 실행·도달성, CDO/상속 후 유효 기본값
- 저장 바이트와 에디터 load fixup 결과가 다른 필드의 원인 판정

Oracle 생산자는 바이너리 리더 코드를 사용하지 않지만, 비교 adapter는 리더가 만든 IR을 입력으로 사용한다.
따라서 생산자와 리더가 독립이라는 사실만으로 비교기의 필드 선택·정규화 오류까지 배제할 수는 없다.

## 실제 확인한 오류

### P0: 의사코드가 소유자 없는 핀 링크를 GUID만으로 연결

`GraphRenderer.resolve`는 저장 참조의 owner가 없거나 틀려도 그래프 전체에서 같은 GUID가 하나뿐이면 그 핀을
대상으로 선택했다. 구조화 `graph_ir`는 이미 이 경우를 `unresolved`로 처리했기 때문에 Markdown과 IR이 서로 다른
사실을 말할 수 있었다. 잘못된 owner, owner 부재, 중복 owner 반례로 이전 동작을 재현했고 1.18에서 제거했다.

### P0: tagged object reference가 같은 이름의 첫 export로 축약

`Ctx.export_by_ref`는 `full_name`이 일치하지 않아도 같은 short name의 첫 export를 반환했다. full path가 틀린 참조와
중복 short name 반례에서 잘못된 객체를 선택할 수 있었다. 이제 package index는 정확한 객체와 class를 확인하고,
full path는 정확히 하나가 일치해야 하며, short-name-only 참조도 class 필터 뒤 유일할 때만 사용한다.

### P1: 저장된 호출·변수 대상이 구조화 결과에서 소실

기존 `graph_ir`는 핀 연결만 보존하고 `FunctionReference`, `EventReference`, `VariableReference`,
`DelegateReference`, `MacroGraphReference`를 버렸다. Markdown에는 축약된 이름만 남아 동명 멤버와 owner class를
후속 분석기가 구분할 근거가 없었다. 1.18은 원본 saved field와 exact package identity를 추가한다.

## 잠재적인 정확도 위험

- parser 조합 선택 기준이 해석된 노드 수다. 같은 노드 수를 내는 잘못된 필드 정렬은 의미 오류를 숨길 수 있다.
- `Ctx.obj_name`, 의사코드 함수명과 C++↔Blueprint 매핑에는 여전히 표시용 short name이 쓰인다. 구조화 identity와
  대조하지 않고 이름만으로 결론을 내리면 안 된다.
- `graph_ir.status=complete`는 기존 pin projection 계약을 유지한다. 각 `semantic_references.status`가 partial이면
  멤버 identity는 부분 결과다.
- 기본값은 saved pin/declaration/CDO 관측을 구분해 읽어야 한다. auto-default와 동일하다는 사실은 상속 후 유효값을
  증명하지 않는다.
- collection FText, StateTree instanced data, 위젯 binding 실데이터, CallInEditor=true 실데이터에는 기존 TASKS의
  Q18/Q2/Q16/Q5 공백이 남아 있다.
- C++ 정규식 색인은 함수 본문과 호출 관계를 제공하지 않는다. 현재 C++↔Blueprint 연결은 이름 기반 후보 이상으로
  해석하면 안 된다.

## C++ AST 접근 평가

| 접근 | 정확도 장점 | 비용·한계 | 판단 |
|---|---|---|---|
| 현재 정규식 | 의존성 없음, UMACRO 표면을 빠르게 표시 | 전처리, 복잡한 선언, 본문·호출·오버라이드 분석 불가 | 보조 fallback으로 유지 |
| tree-sitter-cpp | 오류 복원, 함수/필드/호출 syntax tree, Linux에서 엔진 없이 실행 가능 | UE 매크로·조건부 컴파일 의미와 실제 overload resolution 불가; 새 고정 의존성 필요 | F10의 첫 구현 후보. `syntax-only/unresolved` provenance 필수 |
| Clang AST | type/overload/상속/호출 target 정확도가 가장 높음 | UE 헤더, generated headers, 정확한 compile commands와 target flags 필요; 현재 Cloud에 clang/libclang도 없음 | Windows/정식 빌드 환경의 선택적 정답·보강 경로 |

tree-sitter 결과를 확정된 C++ 의미로 표시하면 안 된다. 선언·호출마다 `parser`, source span, resolution status를
보존하고, Clang 결과가 있을 때만 overload-resolved 관계로 승격하는 단계적 구조가 적합하다.

## 개선 우선순위

1. 완료: P0 핀 연결과 object reference의 추정 제거.
2. 부분 완료: P1 saved member identity 보존. Native Oracle 독립 비교가 추가되기 전까지 partial.
3. P2: Oracle에 FMemberReference 원본 parent/name/GUID/self-context와 macro graph path를 추가하고 UE 5.7/5.8에서
   실제 캡처한다. 기존 JSON을 리더 출력으로 갱신하지 않는다.
4. P3: F10으로 tree-sitter 기반 syntax index를 별도 schema로 추가한 뒤 Clang 선택 검증을 설계한다.
5. P4: C++↔Blueprint 연결은 exact object path/GUID 또는 AST-resolved symbol이 있을 때만 확정하고 이름 매치는 후보로 남긴다.
