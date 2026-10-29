# WORKLOG

새 항목은 **맨 위**에 추가합니다. 다음 에이전트가 이 항목만 읽고 이어받을 수 있게 씁니다.

```
## YYYY-MM-DD HH:MM KST · <claude|codex> · <TASK-ID들>
- 한 일:
- 검증: (regress 결과, 직접 확인한 것)
- 남은 일·주의:
```

---

## 2026-10-29 09:00 KST · codex/claude · Q1/Q12 (독립 에디터 정답 수집·대조)
- 한 일: v1.15.0. Claude가 자체 editor-only RepoReaderOracle C++ 모듈과 Python exporter를 작성하고 Codex가 독립 비교기·회귀를 구현.
  stock Python에서 Blueprint graph/variable 배열과 graph.nodes를 읽을 수 없음을 실제5.8 probe로 확인해 native 공개 API를 직접 읽음.
  캡처는 파서를 공유하지 않으며 숨긴 핀/연결·변수·함수 그래프/메타데이터·위젯 바인딩을 보존. FText는 지역화 display 대신 source.
  파일 SHA-256 전후와 package_dirty=false를 확인해 저장 안 된 메모리 편집을 정답으로 사용하지 않음. 저장/컴파일/dirty 해제 API는 캡처에 없음.
  비교기는 과거 digest를 재사용하지 않고 새로 읽으며, 명시적 all/graph 범위·모든 미확정/제외·native 수량을 보고. 원자 캡처/기존 보고서 보존 포함(D-027).
- 실제 분담/검토: Claude 세션3cc862fa-d3ff-48e2-b981-835ae006755f. 첫 시도 API 한도 종료 뒤 같은 세션에서 재개했고
  Codex가9개 독립 fake-editor 검사·양 엔진 빌드/실행으로 검증. dirty 상태 누락을 지적해 같은 작업자에게 보완 지시.
  작업자는 Codex 비교기를 읽기 전용으로 교차검토했고, 자산별 최소 관측/한 오류가 다른 자산 결과를 버리는 문제를 보완.
  잘못된 tooltip과 다른 필드 unknown이 동시에 보고됨을 반례로 입증해 "unknown이면 메타데이터는 비교 안 됨"이라는 검토 가정도 정정·수용.
  실제 도구는 Read/Glob/Grep/Write/Edit만 관측, 명령/테스트/커밋/통합은 Codex 담당. 작업자7파일을 통합본과 byte 대조함.
- 발견한 실제 오류: 고정 linker의 native import 경로가 /Script/CoreUObject./Script/Engine.Actor처럼 중복됨.
  Ctx.full_name이 실제 outer 체인의 절대 이름에서 끝나도록 수정해 native5.8의 pin/default-object 경로21개 차이를 없앰.
  short-name fallback 유지. 같은 export의 중첩 walk와 진짜 중복 정체성을 구분하고, FName 타입 category 대소문자 차이는 의미대로 정규화.
  opaque 선언 타입을 빈 map terminal로 만들던 초기 비교 어댑터도 unknown으로 수정. 기존 BP/노드/issue 기대값은 완화하지 않음.
- 독립 정답: 실제UE5.7.4/5.8.4로 고정 UE Shed9노드/59핀씩과 eg BFL_Util39노드/109핀/연결 관측82개를 캡처.
  tests/editor_oracles의 JSON3개(합계 약155KB)에 native snapshot·출처commit/패키지 hash·capture code 지문을 보존.
  기본 회귀에서 에디터 없이 그래프 전체와 all의 가용 값을 대조. 미명시 메타데이터3/3/11개는 정확한 known_reader_gaps로만 고정하며 검증된 값으로 세지 않음.
  eg 한국어 tooltip "좌측상단 인덱스"와 category 등 가용 메타데이터도 직접 대조. 리더 결과로 native 정답을 만들지 않음.
- 실제 프로젝트 조사: 원본 eg 고정 캐시를 읽기만 하고 Content 복사본을 별도 호스트에 배치. native AssetRegistry가 찾은
  /Game Blueprint 파생52개(별도 KeyRepairs 제외)를 전부 수집, 로드/캡처 실패0·dirty0. 기존49개 외 ControlRig3개 포함.
  전체 graph 대조는40개 일치·5개 차이·7개 미확정(빈 그래프4/ControlRig 어댑터 범위밖3). all은7개 자산 차이·47개 자산 미확정(중복 가능).
  ErrorTolerance GUID, const/default, category·상태 그래프 소속 차이는 리더 오독이라고 단정하지 않고 Q14에 등록.
  전체25MB 캡처/비교 결과·빌드/바이너리는 ignore 캐시에만 보존. 구조화 변수 타입 등 어댑터 갭은 Q13, CallInEditor=true 실데이터는 Q5 유지.
- 검증: 최종 전체 regress 단위121/121 + 기존 독립 외부 에셋6/6 + 새 native oracle3/3 + 고정 프로젝트4/4 PASS.
  실제5.7/5.8 C++ 빌드·product exporter·graph1251개 관측 일치·같은 파일 바이트로 저장 안 된 변수를 메모리에 추가했을 때 거부 PASS.
  eg cold/warm/disabled101개 Markdown/JSON byte-identical, warm97 hits/0 misses/오류0; BP교체 시 그 BP만 재해석 PASS.
  실제 MCP HTTP6도구·재시작/warm/refresh/일반-탐색 캐시 분리 PASS. 두 skill quick_validate·diff --check PASS.
  초기 UAT BuildPlugin은 설치된 FabToolset rules 오류로 실패했고, 엔진 전역 설정 변경 없이 격리 호스트 플러그인 설정으로 해결.
  재현용 editor_native_smoke.py는 새 임시 프로젝트에서 필요한 플러그인만 활성화한다.
- 남은 일·주의: Q1/Q12는 독립 수집/비교 기반 완료이며 모든 레포 의미 정확도의 완료가 아님. 다음 우선순위 Q13/Q14.
  snapshot은 native loaded state다. 파일이 같아도 엔진 로드 보정이 있을 수 있으며 차이를 없애려 GUID/기본값을 추정하지 않는다.
  native/graph 및 all의 미확정·제외와 정확한 회귀 경계를 docs/EDITOR_ORACLE.md, GRAPH_IR.md, 두 SKILL과 tests/README에 명시.
  개인 스킬과 원래 checkout의1.15.0 동기화·설치 경로 검증은 main 반영 직후 확인한다.

## 2026-10-28 17:35 KST · codex/claude · Q10/Q11 (W0 프로젝트 지원 경계)
- 한 일: v1.14.0. UE 5.7+ 프로젝트를 목표로 숫자 EngineAssociation 5.7/5.8만 기본 분석 허용.
  scripts/project_support.py에 순수 정책을 분리하고 CLI가 선택 descriptor를 한 번 읽어 출력 교체·에셋 캐시·LFS·디코더 전에 판정.
  구버전/미검증 신버전/빌드 ID·선언 부재/모호하거나 잘못된 JSON은 기본 거부하며 --best-effort / MCP best_effort=true로만 탐색.
  INDEX/CATALOG 상단과 digest.source.project_support에 선언 원문·선택 경로·분류·요청/실제 탐색 여부를 보존.
  정책 정보 없는 문서도 미확정이며 탐색 성공을 정상 지원이나 의미 검증으로 승격하지 않음. 오래된 저장 에셋의 호환 리더 유지(D-026).
  MCP 캐시 schema2는 일반/탐색 모드와 정책 버전·지원 창을 identity에 넣고 producer 정책도 확인. 지원 거부만 정확한 MCP 인자를 안내.
  두 SKILL/README/설치·서버 가이드와 역사적 HTML의 현행 상태 안내를 동기화. DataTable 300행 미리보기·없는 필드의 값 미확정 설명도 정정.
- 실제 Claude 분담/검토: Q11 작업자 2b8c7219-b485-4c9e-bffc-ff44d19fcc43가 별도 worktree에서 독립 검사 파일만 작성/수정.
  Codex가 실행·범위 검토·통합하고 재지시해 잘못된 UTF-8/NaN·미래/선언 부재·거짓 clean 문구 반례를 보완.
  Q10 읽기 전용 교차검토 cd4d0016-0fbd-41f5-8a95-cbdc078a5d49 2회로 테스트 descriptor 누락, 정책 변경 캐시 무효화,
  누락 정책의 정상 추정, MCP 거부 안내와 정상 공지 검사를 보완. 중첩 중복 JSON 키도 미확정이라는 엄격한 자체 계약을 명시.
  작업자 도구는 Read/Glob/Grep/Write/Edit, 검토자는 Read/Grep만 관측. 두 실행 모두 manager 검증 후 accepted, 실행 중 없음.
- 검증: 최종 전체 regress 단위 101/101 + 외부 독립 에셋 6/6 + 고정 프로젝트 4/4 PASS.
  실제 MCP HTTP 6도구·재시작/warm/refresh·모드별 별도 키/완료 표식·옵트인한 정상 프로젝트의 requested/used 구분 PASS.
  eg 실제 cache cold/warm/disabled의 101개 Markdown/JSON byte-identical, warm97 hits/0 misses/오류0.
  5.8 임시 프로젝트 안의 4.27 데이터와 BP5.6→5.7 교체 시 변경된 BP만 재해석 PASS. 실제 enum 수정/부재 4단계 캐시 무효화도 PASS.
  두 skill quick_validate·변경 진입점 compile·diff --check PASS. HTML PC/모바일·인쇄·JS-off·검색/정렬·외부 요청/JS 오류0 검사 PASS.
  HTTP smoke의 깊은 Windows 임시 출력 경로가 260자를 넘은 실행은 실패했고 prefix를 줄인 뒤 실제 전체 smoke를 재실행해 통과.
- 기대값 정정: 고정 commit의 descriptor 원문과 git show를 대조해 eg/ar=5.8, ves=5.7, bt=4.19 확인.
  기존 ar5.6/bt4.12는 프로젝트 선언이 아니라 에셋 저장 버전이었다. fixtures/HTML을 정정하고 bt만 명시적 탐색으로 회귀 유지.
  기존 BP/노드/에셋 수와 bt26/98·정확한 기존 90 issue 기준은 완화하지 않음.
- 남은 일·주의: Q10/Q11 done. 선언 일치는 핀 전체·게임플레이 의미 정확도의 보증이 아니다. 현재 검증된 기본 창은 5.7/5.8이며
  소스 빌드 ID/빈 선언은 실제 UE5.7+여도 탐색 모드가 필요하다. 원격 clone은 메타데이터 확인 전에 수행될 수 있다.
  다음 우선순위는 Q1/W1 독립 에디터 의미 정답 확보·자동 대조이며, Q9 IR의 현재 핀 ID/텍스트 정답 범위는 그대로다.
  등록 개인 스킬(C:/Users/user1/.codex/skills/ue-repo-reader)과 원래 main checkout을 1.14.0 main으로 fast-forward 동기화함.
  실제 설치 경로의 5.7/5.8 독립 핀 정답 대조·CLI 구버전/빌드 ID/미검증 미래 선언 3건의 출력 보존 거부·정상/탐색 상태 전파 PASS(17:37 KST).

## 2026-10-28 16:35 KST · codex · Q9 (W3/W1 공통 핀 구조·정답 비교 기반)
- 한 일: v1.13.0. scripts/graph_ir.py의 스키마 1을 BP graph_ir / 맵 level_bp_graph_ir에 연결.
  원본 노드/export 정체성, 핀 타입·전체 텍스트/기본 객체 경로, 저장 참조와 원래 소유자를 보존.
  미확정/중복/잘못된 필드와 객체 경로는 unknown+issue, 모호한 연결은 후보만 보존하고 대상을 추정하지 않음.
  parent/subpin/pass-through의 같은 노드 관례는 별도 basis이며 linked_to에는 적용하지 않음. 누락 노드 수 교차 검사 포함.
  두 SKILL·INDEX/CATALOG·README·docs/GRAPH_IR.md와 버전을 동기화, graph_ir.py도 캐시 fingerprint에 포함(D-025).
- 실제 Claude 교차검토: 5f30197e-dcde-4e3b-96f0-d322cf04aaae 읽기 전용 3회. Codex가 기본 객체 경로/부재 전파,
  선언 필드의 무고지 생략, 저장키와 파생키 충돌, graph/node GUID 원문과 pin GUID 저장 바이트 순서, 핀 범위 고지를 보완.
  실제 고정 디코더 필드 존재 및 eg GridSlot 참조 1120/1120개의 owning_node_object를 확인해 감사의 가정을 정정했고,
  bt 구조 참조 31개는 로컬 소유자 보완 뒤에도 어떤 그래프 핀 GUID와도 일치하지 않음을 대조. Claude가 정정/최종 수정 수용.
- 검증: 전체 regress 단위 90/90 + 독립 외부 에셋 6/6 + 고정 프로젝트 4/4 PASS. 5.7/5.8 pin ID/텍스트를
  공개 IR에도 에디터 정답 대조하며, 실제 모델의 계약 필드/핀 수를 확인. 올바른 parser/Markdown과 틀린 IR을 섞으면 실패함.
  값/타입/연결 변경·동일 GUID의 다른 소유자·중복/누락/다른 그래프·구조용 연결·정상/미확정 기본 객체/추가 키 반례 PASS.
  bt는 원래 26/98·5개 issue 유지, 새 IR 진단 85개를 정확히 고정. 새 오류/중복/사라짐/개별 해석 수 감소 검사는 계속 실패함.
  두 skill quick_validate·버전 일치·diff --check PASS. 기대값 확장 사유는 D-025이며 구버전 디코더 기능을 넓히지 않음.
- 캐시/크기: 최신 eg fresh/warm/disabled의 101개 출력 byte-identical. warm 97 hits/0 misses·오류0.
  digest.json은 Q8 655468 → 9755602 bytes, 전체 값/구조를 보존해 증가함. 캐시 97개 압축 합계635048 bytes,
  최대 비압축 entry2497867 bytes(상한32000000 미만). 이 사례에서 상한 누락/조기 퇴출 없음. 보통 독해는 Markdown을 우선함.
- 남은 일·주의: Q9 done, 관리 실행 accepted/실행 중 없음. complete는 디코더가 노출한 핀의 투영 범위이며
  N/N은 노드에 핀이 하나 이상 있다는 뜻. 핀 전체/게임플레이 의미/기본 객체의 독립 정답 보증이 아님.
  node 속성·CDO·빈 그래프·영구 diff 식별자·런타임 값은 범위 밖. Q1 전체 의미/객체 기본값의 정답 확보와 W2 전체 값 보존은 남음.
  다음 우선순위는 Q10(UE 5.7+ 프로젝트 지원 경계); 실제 버전 제한은 아직 미적용. 캐시 초대형 entry 무고지 skip은 기존 후속 성능 항목.
  등록된 개인 스킬(C:/Users/user1/.codex/skills/ue-repo-reader)의 깨끗한 동일 origin main을 1.3.0→1.13.0으로 fast-forward 업데이트함.
  실제 설치 경로에서 모듈 import/CLI와 5.7·5.8 독립 핀 정답/IR 필드 대조 PASS(16:38 KST). 원래 개발 checkout도 최신 main으로 동기화.

## 2026-10-28 16:02 KST · claude/codex · Q8 (W0의 무고지 표시 생략 제거)
- 한 일: 실제 Claude Code가 BP dict 6개/구조체 8개·데이터 구조체 10개 표시 상한에 정확한 …(+N)을 추가.
  추가 CDO 40개 뒤의 값, native/opaque·미확정 참조와 미확장 subobject는 수량/제한된 이름 안내를 출력.
  선언 변수표에 있는 값과 의도적인 내부 키는 누락 수에 포함하지 않으며, 안내만 있는 CDO도 섹션을 남김.
- Codex 검토: 초기 diff가 <literal>/AnimNode_ 정상 문자열도 opaque로 오인해 새 안내에 포함하는 것을 발견.
  같은 Claude 세션(968a0a4b-dbef-4470-91be-e720582e6262)에 수정 지시해 값 종류로 구분하고 회귀를 추가.
  해석 실패와 표시 상한을 구분하며, 표시 안내만으로 parse_status를 partial로 만들지 않음. D-024·두 SKILL·범례와 v1.12.0 동기화.
- 검증: Codex가 새 경계/중첩/스칼라/제외 수량/문자열/Markdown 전파 7개 직접 실행 PASS.
  전체 regress 단위 83/83 + 외부 에셋 6/6 + 프로젝트 4/4 PASS(공용 고정 클론 재사용), 기대값 완화 없음.
  두 skill quick_validate·diff --check PASS. PyYAML은 검사 도구용 gitignore 캐시에만 설치했고 제품 의존성은 추가하지 않음.
- 남은 일·주의: Q8 done. 작업자 실행은 파일 도구만 사용했고 커밋/문서/검사/통합은 Codex 담당.
  W0의 지원 경계/다른 표시 상한과 W2 전체 값 보존은 별도 작업. Q9 공통 IR/의미 비교 기반은 Codex가 이어서 통합 중.

## 2026-10-28 15:07 KST · codex · A8 (UE 5.7+ 정확도·레포 이해 우선 HTML 개정)
- 한 일: docs/reports/skill-audit-2026-10-28.html을 같은 경로의 개정 2로 재작성. 사용자가 제시한 UE 5.7+ 프로젝트 목표와
  높은 정확도/레포 이해를 우선하는 개발 계획으로 변경. 프로젝트 엔진과 에셋 저장 버전을 분리하고, eg의 5.3/5.6 혼재 에셋에
  필요한 호환은 유지하는 안을 명시. 미확정 엔진·미검증 미래 포맷은 보증하지 않으며 실제 지원 제한/구버전 코드 삭제는 적용하지 않음.
- 우선순위: W0 지원/누락 계약, W1 독립 의미 정답, W2 전체 저장값·상속/컴포넌트 맥락, W3 공통 IR·타입별 관계,
  W4 질문 중심 독해/근거 설명, W5 레포 질문 평가의 6개 미착수 워크스트림. 최소 W3/정답 공통 형식을 W1 비교기보다 먼저 맞추도록 명시.
  기본 표는 기존 todo 19개 중 Q6을 제외한 18개, 품질 우선순위순. Q6은 계획 외/배정 없음으로 보되 TASKS의 todo는 유지.
  배포/마켓플레이스는 보류하며 토큰 추정은 겹치는 범위여서 합산/정확도·절약률로 제시하지 않음.
- 교차검토: 실제 Claude Code 읽기 전용 2회(3ca94faf-ae4b-4b9b-b026-b99814a07d23)와 Codex 원문 대조.
  CDO 40개 외에 BP dict 6개/구조체 8개·데이터 구조체 10개 무고지 표시 상한을 W0에 명시, 기본값/관계 해석의 소스 근거 보강.
  에셋 최대/최빈 저장 버전으로 프로젝트 엔진을 단정하는 제안은 채택하지 않음. 감사는 accepted로 마감, 실행 중 작업 없음.
- 검증: 단일 HTML PC 1440px/모바일 390px 렌더·넘침·검색/필터/정렬/초기화·Q6 토글·상세·인쇄/복원·JS-off 표시 수 PASS.
  인쇄에는 19개, 기본 화면에는 18개라는 표시를 실제 행 수와 일치시킴. 외부 요청/JS 오류 0, anchor/ID 및 고정 소스 27개/행 범위 PASS.
  전체 regress 단위 76/76 + 외부 에셋 6/6 + 고정 프로젝트 4/4 PASS(기존 checkout의 로컬 캐시를 --repo로 재사용).
- 남은 일·주의: A8 done. 스킬·파서·서버·테스트 기대값은 변경하지 않음. 5.7+ 정책과 W0~W5는 개발 계획이며 구현/검증 완료가 아님.
  정식 실행 때 TASK를 나누어 선점하고 필요한 에디터 정답을 확보해야 함. Q6/구형 참고 테스트를 삭제하거나 완료 처리하지 않음.

## 2026-10-28 14:38 KST · codex · A7 (스킬 중간 점검 HTML)
- 한 일: docs/reports/skill-audit-2026-10-28.html 작성. 코드 기준 8deeb6a/v1.11.0의 지원/부분 지원/전용 해석 없음,
  등록된 todo 19개를 기능별·토큰 추정 순으로 정리. 과제별 이유·완료 조건·선행 조건, 추가 미등록 제안 4개, 추천 분담안과 검증 범위를 포함.
  외부 CSS/폰트/스크립트 없이 동작하는 단일 HTML. 검색·기능/우선순위 필터·정렬·상세 펼침·인쇄와 반응형 레이아웃 제공.
  근거는 고정 커밋의 22개 소스 링크로 연결했고, 토큰은 추정이며 전체 정확도 %는 아직 산정할 수 없음을 명시.
- 검토: 실제 Claude Code 읽기 전용 독립 감사(32cbc625-d90b-4236-8fd3-f5ce90374ac2)와 Codex 대조.
  추가 CDO 섹션의 무고지 40개 상한/opaque 제외를 45개 합성 값으로 직접 재현. 일반 SCS 컴포넌트 템플릿 설정·BP/데이터의 전체 값 보존과
  MCP 필드 조회 공백, DataTable 300행 표시/애니메이션/JSON 안내 문서 불일치를 보고서에 반영.
  감사 초안의 "5.8 외부 정답 0"은 pins-5.8 근거로 정정했고, JSON 접근 불가·CDO 전체 변수 상한이라는 과도한 해석도 좁혀 Claude 재확인 수용.
- 검증: HTML 브라우저 실제 렌더 PC 1440px/모바일 390px·가로 넘침·19개 행/5분류·검색/필터/초기화/토큰 정렬·상세·인쇄 PASS.
  외부 요청 0·JS 오류 0, 정적 anchor/ID 중복 없음, 고정 Git 소스 링크/행 범위 검사 PASS. 생성 전후 스크린샷 직접 확인.
  전체 regress 단위 76/76 + 외부 에셋 6/6 + 프로젝트 4/4 PASS(원래 checkout의 고정 로컬 클론을 --repo로 재사용), diff --check PASS.
- 남은 일·주의: A7 done. 추가 제안은 아직 TASK 등록/구현하지 않았으며 todo는 19개 그대로. 선언 변수표 전체가 40개 제한이라는 뜻이 아님.
  실제 프로젝트의 CDO 생략 건수는 미측정. 다음 후보는 제안 A의 작은 생략/unknown 고지와 Q1 독립 정답 확장.
  이번 변경은 보고서/핸드오프 기록만이며 스킬·파서 기능은 수정하지 않음. 감사 실행은 accepted로 마감했고 실행 중 작업 없음.

## 2026-10-28 14:15 KST · codex · O1 Q4 Q7 (실제 Claude Code와 공동 작업)
- 한 일: 사용자 요청에 따라 Codex는 Q4 구현·전체 관리, 실제 Claude Code CLI는 별도 worktree에서 Q7 구현을 담당.
  tools/claude_delegate.py와 CLAUDE_COORDINATION.md 추가: 파일 도구만 허용하는 작업/읽기 전용 검토, 세션 재개·재지시,
  상태/전체 도구 감사·중단·시간 제한·명시적 stale 잠금 복구·관리자 승인 기록. 성공 응답은 awaiting_review이며 자동 병합하지 않음.
  Windows stdin이 막혀도 timeout이 적용되고, 초기 기록 저장 실패도 잠금을 정리. 복구는 관리자/작업자 생존 또는 불명확한 신원이면 거부.
  AGENTS 8절·D-021에 관리 모드 예외를 기록했으며 인증은 사용자가 직접 완료. 새 의존성·권한 우회·전역 설정 변경 없음.
- Q4: v1.11.0. 표 미리보기와 별도로 maps_detail[map_path].actors에 액터·루트 컴포넌트의 디코딩된 저장 프로퍼티 전체를 보존.
  package/export index로 외부 액터를 구분하고 문자열/중첩 값/네이티브 필드/opaque bytes를 JSON으로 보존(D-022).
  미지원/순환/과도한 깊이는 unknown+issue. properties_status=partial은 누락 값도 unknown이라는 뜻을 두 SKILL·모든 범례에 명시.
  잘못된 ActorLabel은 경고/partial로 남기고 object name으로 식별하며 원래 디코딩 값은 별도로 보존. 클래스 기본값·다른 컴포넌트 export는 확장하지 않음.
- Q7: 실제 Claude 세션 48ab5c35-6bda-4172-abfa-72307aaffd43이 구현. bt의 전역 allow_issues를 제거하고 정확한 issue 다중집합,
  모든 BP 노드 수와 Level BP 노드 수/상태를 고정(D-023). Codex 검토에서 null parse_status 공백을 찾아 같은 세션에 수정 지시함.
  기존에 통과하던 새 BP 오류 주입이 이제 실패하는 것을 직접 재확인. bt의 26/98과 맵 issue 5개는 그대로 알려진 제한임.
- 교차 검토: Claude가 Q4/O1을 읽기 전용으로 검토하고 partial 안내·잘못된 라벨·전체 도구 감사·stale 복구 네 항목을 지적.
  Codex가 수정하고 같은 Claude 세션에서 네 항목 모두 수용 확인(총 4회 실행: 구현/재작업/교차 검토/수정 확인).
  실제 관찰 도구도 구현은 Read/Grep/Edit, 검토는 Read/Grep뿐임을 확인. 마지막 비차단 지적의 신원 불명·잠금 불일치 검사도 보완.
- 검증: 최종 순차 전체 regress 단위 76/76 + 외부 에셋 6/6 + 프로젝트 eg/ar/ves/bt 4/4 PASS.
  맵 13개/액터 856개 전체 기록 수와 식별자 유일성, 엄격 JSON 읽기 확인. eg cold/warm/disabled 101개 출력 byte-identical,
  warm 97 hits/0 misses, 실제 BP 교체 시 해당 본문만 재해석. 실제 MCP HTTP 6도구·응답 제한·재시작/refresh PASS.
  두 skill quick_validate·버전 일치·문서 링크·diff --check PASS. symlink 생성 권한 하위 검사만 기존대로 skip, 실제 junction PASS.
- 남은 일·주의: 병렬 검증 도중 테스트용 파서 설치 rename에서 WinError 5가 한 번 발생함. 원인은 확정하지 않았고,
  해당 검사 단독 재실행과 최종 전체 순차 실행은 모두 PASS. 기대값을 완화하지 않음. 캐시 32MB 상한의 로그와 전역 JSON writer 엄격화는 별도 검토 사항.
  다음 정확도 과제는 Q1(정답 비교에는 연결/기본값/입출력도 포함), Q2/Q3/Q5/Q6. 턴 종료 뒤 자동 감시는 없음.
  관리 실행 기록은 원래 checkout의 .ue-repo-reader/claude-jobs/Q7-1e187f4c에만 보존; accepted로 마감했고 실행 중 작업 없음.
  main 4a48004 push 완료. 앱의 archive_worktree는 이 채팅의 primary checkout이라며 정리를 거부함(수동 삭제하지 않음).
  현재 worktree를 codex/O1-managed-workspace(origin/main 추적)로 전환해 최신 main 내용으로 맞춤. 후속 턴은 이 경로에서도 최신 도구를 사용 가능.

## 2026-10-28 11:30 KST · claude · Q1–Q6 (등록만)
- 한 일: TASKS.md에 "정확도 — 빈칸과 검증" 절과 Q1~Q6 추가(코드 변경 없음). 근거: REVIEW-2026-10-27의 `노드 N/N` 한계,
  F6/F7·X6 WORKLOG의 미표시 항목, 캐시된 eg/ar/ves/bt 요약본의 "not decoded"/"unreadable" 표시 점검.
- 검증: regress 단위 + 외부 에셋 6/6 + 프로젝트 4/4 PASS(캐시 클론).
- 남은 일·주의: 추천 순서 Q1(5.8 에디터 정답 비교, 실행은 사람 PC) → Q2(StateTree 설정값) → Q3(위젯 애니메이션 키).
  Q1 스크립트는 사용자 에디터에서 돌아가므로 읽기 전용으로 만들고 프로젝트 파일을 저장·수정하지 않게 할 것.

## 2026-10-28 11:19 KST · codex · X5
- 한 일: v1.10.0. K2Node_FunctionEntry.MetaData의 ToolTip/Category/bCallInEditor를 실제 저장 값으로 읽어
  `// Function metadata` / `// Function tooltip` 설명 주석과 BP summary.function_metadata에 출력(그래프 경로/진입점 이름 포함).
  필드 없음과 명시 false를 구분하고 문자열을 bool로 추측하지 않음. Opaque 구조체는 해당 export index만 TaggedReader로 재읽고,
  복구 실패/잘못된 필드는 function_metadata issue와 unknown 주석으로 표시. author text는 구조체 GUID 이름 정리에서 제외해 보존.
  한글·개행·따옴표·fence·Unicode 구분자는 JSON 리터럴로 표현하며 실제 실행 흐름/함수 플래그는 유지.
  두 SKILL 2절/INDEX/CATALOG 범례·README·테스트 안내·플러그인 버전 갱신, D-020 기록.
- 검증: 최종 전체 regress 단위 66/66 + 외부 에셋 6/6 + 프로젝트 4/4 PASS. bt는 기존 UE 4.12 부분 해석 기대값(26/98) 포함.
  기존 3개 프로젝트의 BP/노드 수량 동일. 실제 BFL_Util 한글 툴팁과 WBP_GridSlot Slot 카테고리 문자열 회귀 추가.
  X5 단위 5개: 합성 bool true/false·필드 생략·명시 빈 문자열, 한글/긴 문구/개행/fence/GUID 원문 보존,
  동명 노드의 정확한 export index/Reader 정리, opaque fallback/필드 실패·summary/Parse report 전파 PASS.
  eg/ar/ves에서 저장된 CallInEditor 예는 없어 true/false는 합성 값으로 검증. 실제 metadata 14개(eg) 출력 확인.
  최종 실제 MCP HTTP 6도구/한글 툴팁 읽기/캐시·검색·refresh·재시작 PASS. eg cold/warm/disabled 출력 101개 byte-identical,
  warm 97 hits/0 misses/0 writes/0 errors. 두 skill quick_validate·plugin/tool 버전 일치·문서/생성 링크·fence·diff --check PASS.
- 남은 일·주의: X5 done. 원격 X6/X3/X7/X8/B9·신규 clone 수정까지 보존해 통합 검증함. B9의 진입점 이름 _0 표기를 반영했고,
  이미 게시된 v1.9.0과 캐시가 섞이지 않도록 v1.10.0 사용. X8 상태 done 보존. 다음 X 후보는 X9, 기능 후보 F5/F9/F10.
  main fast-forward/push 예정. 배포 대상·공개/인증 설정은 변경하지 않음.

## 2026-10-28 12:30 KST · claude · X8 B9 (+X4 회귀 수정)
- X8: 바인딩 쓰는 공개 저장소 탐색 → `UnrealCourse/04_BattleTank`(HealthBar, PlayerUI_BP), `05_TestingGrounds`(WBP_Score)에서
  `DelegateEditorBinding` 발견. 출력 확인: `ProgressBar_0.Percent ← GetPercent_0`, `AimPoint.ColorAndOpacity ← Get_AimPoint_ColorAndOpacity_0`.
  회귀에 `bt`(BattleTank `19ffc19`) 추가 — UE 4.12라 그래프는 26/98만 디코딩(지원 범위 4.25 미만), `nodes_ok`·`allow_issues`로 고정.
  regress.py가 `expect.nodes_ok`/`allow_issues`를 지원하게 확장(기본값은 기존과 같은 엄격 검사).
- B9(발견): 바인딩의 FString `ObjectName`(ProgressBar_0)과 위젯 트리(ProgressBar_1)가 1 차이 → uasset_read가 FName 번호를 `_{N}`으로 표시하는 버그.
  `read_name` 래핑으로 `_{N-1}`(UE 규칙). 시퀀스 첫 분기 `then_0`, 타임라인 `NewTrack_0`, `SizeBox`→`SizeBox_1` 등 이제 에디터와 일치.
  VERSION 1.9.0, D-019. F7 기대값 `NewTrack_1`→`NewTrack_0`(의도된 변경).
- X4 회귀 수정: 새 클론에서 필요한 큰 blob을 `fetch --filter=blob:none origin --stdin`으로 받다가 git 2.43 + GitHub에서
  "did not send all necessary objects"로 실패(기존 캐시 클론만 쓰던 회귀는 못 잡음). git의 lazy fetch와 같은
  `-c fetch.negotiationAlgorithm=noop fetch --no-write-fetch-head --recurse-submodules=no --filter=blob:none`로 교체 → BattleTank·TestingGrounds 새 클론 성공.
- 검증: regress 단위 61 + 외부 에셋 6/6(에디터 정답 핀 비교 포함) + 프로젝트 4/4(eg, ar, ves, bt) PASS.
- 남은 일·주의: **회귀가 캐시된 클론만 쓰면 클론 경로 버그를 놓친다** — 가끔 `tests/.cache/<name>`을 지우고 새 클론으로 돌릴 것.

## 2026-10-28 11:45 KST · claude · X3 X7
- X3 (버그 아님): AR `AM_Spider_Hit` 등 UE 4.25 몽타주의 NameMap에 `"0"`, `"1"`이 실제 이름으로 들어 있음 → 섹션 이름이 정말 `0`, `1`.
  FName 해석 문제 아님. 회귀 검사로 고정.
- X7: InputAction 문서에 `## Input action` — 값 타입(없으면 Boolean), 트리거·모디파이어를 서브오브젝트로 펼쳐 설정값 표시
  (IMC와 같은 `_input_obj`; 이름만 = 기본 설정), 트리거가 없으면 "fires on any actuation — Down", bConsumeInput 등 비기본 옵션.
  기존 "Properties"의 원시 `Triggers = [InputTriggerPressed]` 중복 제거. SKILL.md 데이터 목록 갱신.
- 검증: regress 단위 전체 + 외부 에셋 6/6 + 프로젝트 3/3 PASS, X3 1개·X7 2개 검사 추가. 분포: Pressed 10, 트리거 없음 11, Hold 1 …
- 남은 일·주의: 남은 X는 X5(함수 MetaData)·X8(위젯 바인딩 실데이터)·X9(AnimSequence 노티파이).

## 2026-10-28 11:20 KST · claude · X6
- 조사: AR TestLevel의 TreasureChest 두 인스턴스는 `RequiredKeyCard`를 저장하지 않음(= 클래스 기본값 None), LeverBP는 어느 맵에도
  배치되지 않음 → `KeyCard.*` "미사용"은 오판이 아니라 사실. 맵 인스턴스 오버라이드 자체는 정상 출력됨(예: BP_ApplyEffectZone
  `EffectClassToApply=Effect_Stunned_C`).
- 한 일: 그래도 F1이 Markdown 정규식에만 의존하면 오버라이드 120자 절단·액터당 8개 표시 한도, 표시하지 않는 내부 데이터에 있는 태그를 놓침
  → `bp_reader.collect_gameplay_tags()`로 디코딩된 전체 값을 재귀 탐색해 summary `gameplay_tags`에 저장(BP: CDO 값, data: 모든 프로퍼티,
  map: 액터 오버라이드 전체). `gameplay_tags()`가 이 값을 Markdown 검색과 합침.
- 결과: AR에서 새로 `Directors.Events.KillQuestA ← ST_CombatDirector`(StateTree 내부 데이터) 발견 — ini·C++ 어디에도 정의 없음(⚠ 표시).
  사용 태그 12 → 13. 기대값 갱신(의도된 변경), X6 검사 추가, 단위 테스트(긴 값·컨테이너·None) 추가.
- 검증: regress 단위 전체 + 외부 에셋 6/6 + 프로젝트 3/3 PASS.
- 남은 일·주의: 맵 Markdown의 오버라이드 표시 한도(120자·8개)는 그대로 — 표 가독성 때문. 값 전체는 digest.json actor 정보엔 없음(필요하면 별도 과제).
## 2026-10-28 10:52 KST · codex · X1 / X2 완료
- 한 일: v1.8.0. X1은 표시만의 문제가 아니라 enum FName 배열을 uint8로 읽던 오독이었다. Stashinfo의 size=44/count=5,
  4+8×5 바이트와 NameMap을 직접 대조해 저장 이름을 확인. 실제 값은 [5,6,8,10,11]이며 기존 [7,0,0,0,0]은 잘못된 출력.
  TaggedReader에 명시 타입/정확한 payload 폭/이름 범위를 검증하는 enum 배열 디코더 추가. 일반 byte 배열은 그대로.
  실제 UEnum Names(int64 값) + DisplayNameMap을 summary.enum_values로 제공해 내부 이름/실제 숫자/표시 이름을 함께 출력.
  같은 이름/명시 경로 불일치/unknown 값/부분 실패 enum은 추측하지 않고 저장 이름·숫자 및 INDEX/CATALOG 한계를 유지.
  enum_values.py의 지연 원소/정확한 렌더 span으로 일반 텍스트·숫자를 치환하지 않으며, 원시 캐시 이후 이름을 연결한다.
  enum 수정/삭제가 의존 데이터 캐시 hit에도 반영됨. 두 SKILL 2절/범례/README/테스트 안내, D-018 갱신.
- 검증: 최종 전체 regress 단위 60/60 + 외부 에셋 6/6 + 프로젝트 3/3 PASS; BP/노드/데이터/맵 수량 동일.
  실제 DA_PlayerData 5개 + DT_GridLayoutData 138개 enum 값 모두 이름/숫자 연결, 미해결 0. 실제 문자열 회귀 추가.
  FName 인덱스≠enum 값(1→42), compact byte, sparse/alias/동명/경로/잘린 배열/일반 값 보존/20만 원소 지연 처리 검사 PASS.
  실제 eg 3에셋을 공백·한글·대괄호·쉼표 임시 경로로 복사해 cold/warm byte-identical, enum만 수정하면 2 hit/1 miss,
  enum 삭제하면 2 hit/0 miss 및 미해결 5개 표시 PASS. 원본 fixture 파일은 변경하지 않음.
  전체 eg cold/warm/disabled 101개 Markdown/JSON byte-identical(97 warm hits), 실제 MCP HTTP의 수정 데이터 읽기/
  6도구/캐시·검색·refresh·재시작 PASS. 두 skill quick_validate·문서/생성 링크·내부 토큰 미노출·diff --check PASS.
- 남은 일·주의: X1/X2 모두 done. 타입 없는 legacy byte 배열에 enum을 추측하지 않는다. 숫자 값은 저장 FName을 enum 정의에
  대응해 확인하며, enum 정의 없이 숫자를 지어내지 않는다. 새 의존성/상위 파서 코드 복사 없음.
  원격 X6 담당 변경(claude doing)은 보존해 합친 뒤 main push 예정. 후속 후보 X3/X5/X7/F5; X6는 다른 담당 작업 중.

## 2026-10-28 10:34 KST · codex · X2
- 한 일: PDA_PlayerData.NewVar의 101바이트 VarType 확인. container=3, offset 21의 terminal category/subcategory가
  실제 FName None/None이고 object=0이었다. 구체적인 값 타입을 추측하지 않고 Map<E_Crates, ?> + 미지정 설명으로 표시.
  그래프 핀은 고정 파서의 map_key_terminal_*가 실제 UE PinValueType(값 타입)임을 반영해 primitive/struct/object 값을 전달.
  잘린 VarType은 variable_type issue로 보고. 두 SKILL/INDEX/CATALOG 범례와 v1.7.1, D-017 기록.
- 검증: 전체 regress 단위 53/53 + 외부 에셋 6/6 + 프로젝트 3/3 PASS. 합성 byte map의 int/double/struct/object/None,
  배열/Set/스칼라 보존, 잘린 terminal의 구조화 경고, 구조체 기술자/그래프 핀/툴팁 유무 검사. 실제 NewVar 문자열 회귀 추가.
  최초 단위 실행의 서버 시간 제한 검사 3개는 시작 지연으로 실패했으나 독립 전체 재실행에서 모두 통과.
  BP/노드/데이터/맵 수량 변경 없음, git diff --check PASS.
- 남은 일·주의: X2 done, X1 doing. None은 저장된 미지정 타입이며 None 객체 타입으로 단정하지 않는다.
  X1은 DA_PlayerData.Stashinfo의 ArrayProperty(ByteProperty(E_Crates, 정확한 /Game 경로))와 실제 UEnum 값 표를 연결 예정.
  양 작업 완료 후 main 통합/push 예정.

## 2026-10-28 09:25 KST · codex · T3 통합 성능 보완 / T4 완료
- 한 일: 분류 캐시 제거. 분류는 기존 작은 헤더 병렬 스캔, BP/data/map 본문만 실제 SHA 캐시로 재사용한다.
  미지원 아트 전체 해시·개별 캐시 I/O를 없애고 분류 코드도 단순화. 본문 내용·버전·경로·외부 액터 무효화와
  실패 재시도/손상 복구/경로 보호는 유지. README/테스트 안내/D-015에 실측과 선택 이유 기록. T3/T4 모두 done.
- 검증: 최종 전체 regress 단위 50/50 + 외부 에셋 6/6 + 프로젝트 3/3 PASS. BP/노드/데이터/맵/외부 액터 수량 동일.
  격리된 실제 eg cold 10.28s / warm 5.09s / disabled 9.62s; warm 97 hits/0 misses/0 writes/0 errors.
  모든 Markdown/JSON 101개 byte-identical, 실제 BP 5.6→5.7 교체 시 본문 1개만 재파싱(불변 데이터 hit) PASS.
  최종 실제 PowerShell 5.1 설치·복사 스킬 eg 49 BP/1779 nodes·LFS 2경로·사용자 Git 설정 보존 PASS.
  최종 실제 MCP 1.30.0 HTTP 6도구/INDEX/CATALOG/캐시·검색·refresh·서버 재시작 PASS.
  두 skill quick_validate, 문서 링크/fence, 모든 생성 Markdown 링크/섹션, git diff --check PASS.
- 남은 일·주의: v1.7.0. INDEX 약 2~4k 토큰은 목표이며 토크나이저/언어에 따라 다르고 작은 ves는 약 1.1k.
  원시 캐시는 파서 캐시 아래에 남고 상한 내에서 정리된다. 전체 분류 헤더와 C++/사용처/배치/순위는 매번 갱신.
  단일 PC 속도 수치는 일반 성능 보장이 아니다. 기존 symlink 권한 하위 검사만 skip, 실제 junction 검사는 PASS.
  main fast-forward 통합/push 예정; 다음 후보 X1/X2/X6 또는 F5/F9/F10. 사용자 배포/공개 설정은 변경하지 않음.

## 2026-10-28 09:20 KST · codex · T4
- 한 일: v1.7.0. 짧은 INDEX + 전체 CATALOG 분리. 저장 참조/고유 이름 언급의 결정적 PageRank(damping .85,
  설정 진입점 seed 5배)로 읽기 링크 최대 30개/9KB. 실제 호출·의존성·게임 중요도의 증거가 아닌 탐색 힌트라고 명시.
  중복 이름·알 수 없는 명시 경로는 추측하지 않음. 에셋/C++ 문서 머리말에 경로·해석 상태·순위·인접 링크,
  digest.json.navigation에 전체 순위/연결 근거. 경고는 INDEX에 요약하고 CATALOG에 전부 유지. 분할된 report 링크도 보정.
  두 SKILL 2절·범례·README·MCP 지침/가이드 갱신, CATALOG/part 파일만 출력 교체 허용, D-016 기록.
- 검증: 전체 regress 단위 50/50 + 외부 에셋 6/6 + 프로젝트 3/3 PASS; BP/노드 수량 변경 없음.
  우선순위·정규화·고립/빈 그래프·결정성·중복 이름·300문서/긴 한글 설정·모든 문서/링크·부분 실패·분할/재실행 검사 PASS.
  실제 Windows 5.1 설치본 eg 49 BP/1779 nodes·LFS 특수경로 2개, 실제 MCP HTTP 6도구/INDEX/CATALOG/재사용/재시작/refresh PASS.
  실제 Markdown 링크/섹션 타깃 모두 유효. 개발 캐시 tiktoken 0.14.0으로 cl100k_base/o200k_base 실측:
  eg 2119/2139, ar 2216/2220, 작은 ves 1141/1139 tokens. 실행 의존성은 추가하지 않음. 두 skill quick_validate PASS.
  통합 cold/warm/disabled 101개 Markdown/JSON byte-identical, 실제 BP 5.6→5.7 교체 시 해당 분류/본문만 재생성 PASS.
- 남은 일·주의: T4 done. T3 통합 eg 실측 cold 13.42s/warm 11.16s/disabled 9.58s에서 분류 캐시의 비용을 확인해
  T3를 doing으로 되돌림. 작은 분류 헤더는 병렬로 새로 읽고 본문 캐시만 유지하는 조정 후 재검증·통합 push 예정.

## 2026-10-28 09:15 KST · codex · T3
- 한 일: 실제 바이트의 Git blob SHA + 디코더 소스/고정 파서/Python/도구 버전/콘텐츠 경로로 분류·BP·data·map 결과 캐시.
  맵은 외부 액터 경로·순서·내용도 포함. 정상 결과만 JSON/gzip + 체크섬/atomic replace로 저장하며 Used by/Placed in은 매번 계산.
  --no-asset-cache/--asset-cache-dir, 256MB/10,000개 LRU 정리, 손상·쓰기 실패 시 재해석. 캐시/출력 겹침은 삭제 전 거부,
  링크/정션은 캐시 읽기·쓰기·정리에서 제외. 문서와 D-015 추가. 출력 포맷/VERSION은 유지.
- 검증: 전체 regress 단위 46/46 + 외부 에셋 6/6 + 프로젝트 3/3 PASS. 같은 크기/mtime 변경, 버전/경로/외부 액터 무효화,
  실패·부분 결과 비저장, 손상/체크섬, 변경분만 워커 실행, 캐시 정션 밖 파일 보존, 기존 digest 삭제 전 검증 PASS.
  실제 eg cold/warm/disabled 100개 Markdown/JSON 전부 byte-identical; warm 1,123 hits/4 misses/0 writes/0 errors.
  4개 미분류 에셋은 재분류. 동시 회귀와 OS 캐시 영향으로 단일 실행 시간의 속도 비교는 결론 내리지 않음.
- 남은 일·주의: T3 done, T4 doing. 캐시는 사용자의 파서 캐시 아래에 저장되며 새 버전/디코더 수정 시 무효화된다.
  정리 예산은 실행 완료 시 적용; 입력 파일 해시는 매번 읽어 로컬 수정/LFS 실물을 확인한다. T4 통합 후 main push 예정.

## 2026-10-27 17:41 KST · codex · R5
- 한 일: 도구 6개 유지. search_index.py의 SQLite FTS5 trigram 영속 인덱스 추가(완료 세대·schema·SQLite 버전 확인,
  원자 게시/손상 재생성). 대소문자 무시 리터럴 부분 문자열·기호·한글 유지; 1~2자/FTS5 없음은 캐시 instr 검색.
  검색어 1–256자·결과 1–100, 인덱스 파일당 2MB/총 64MB/후보 10,000파일/200,000줄·SQL 5초 제한과 커버리지 표시.
  6도구 공통 텍스트 응답 20,000자 제한, 목록 200개 + item offset, 큰 파일은 bounded streaming + character offset.
  glob/search는 .git/링크/정션 제외. READ_LOCK으로 열린 파일/SQLite와 refresh/prune 삭제 충돌 방지.
  MCP 지침/스킬·CHATGPT 가이드·테스트 안내 갱신, D-014 기록. 기존 digest 캐시/출력 포맷/의존성은 유지.
- 검증: cp949 환경 전체 regress 단위 42/42 + 외부 에셋 6/6 + 프로젝트 3/3 PASS. 신규 R5 단위 5개.
  리터럴·짧은 검색·한글·따옴표/기호·소스 범위·warm 무재탐색/동시 호출·세대 교체/손상 복구·FTS fallback·용량/행 상한·
  SQL timeout, 한글/이모지 문자 페이지 무손실 연결·목록 무중복·응답 상한·대형 파일 부분 읽기·정션 차단·열린 reader/refresh 확인.
  실제 mcp 1.30.0 Streamable HTTP: 6도구/offset 스키마/실제 eg 49 BP·1779/1779, 20k 응답, warm 및 서버 재시작 후
  검색 DB mtime 동일 재사용, refresh 실제 재분석 PASS. Windows 5.1 설치/LFS 검증은 앞 X4에서 PASS.
  MCP skill quick_validate, 문서 링크/fence·git diff --check PASS. 기본 회귀에는 선택 MCP SDK 불필요.
- 남은 일·주의: X4/R5 모두 done. 첫 검색은 인덱스를 만들며, 검색 커버리지 경고가 있으면 list/read로 보완.
  목록 offset은 항목 수, 읽기 offset은 디코딩한 문자 수. 실제 외부 서버 배포·인증/공개 설정 변경은 하지 않음.
  기존 symlink 생성 권한 하위 검사는 skip, 실제 junction 검사는 PASS. main 통합/push 후 후속 후보 T3/T4 또는 X1/X2/X6.

## 2026-10-27 17:22 KST · codex · X4
- 한 일: 기존 클론도 ref를 먼저 해석/필터 fetch한 뒤 공통 materialize 사용. 변경된 필요 파일만 checkout하고
  빠진 필요 blob은 SHA 목록으로 일괄 fetch; 대형 아트 blob은 생략. 삭제된 추적 파일은 index/작업 트리에서 정리.
  로컬·스테이징 변경/미추적 충돌은 변경 전에 거부, 일반 clone만 지원. UTF-8 raw stdin으로 Windows LF/NUL 보존.
  README에 재사용/무 ref/변경 보존 규칙 추가. 정상 digest 포맷/수량 기대값은 그대로.
- 검증: 단위 37/37 + 외부 에셋 6/6 + 프로젝트 3/3 PASS. 로컬 실제 부분 클론 두 커밋에서 대형 텍스처 2개가
  object DB에 없는 채 유지, 대형 BP만 취득, 태그/짧은 SHA/무 ref/이전 커밋 복귀, 파일 삭제/수정 보존/mtime 확인.
  실제 PowerShell 5.1 설치 가이드·복사 설치본 eg 49 BP·1779/1779, LFS 2개 경로 PASS; 사용자 Git 설정 동일.
- 남은 일·주의: X4 done, R5 진행 중. 재사용 클론의 HEAD는 요청 커밋으로 detach. 기존 작업 내용이 있으면 새 --workdir 사용.
  파서나 출력 VERSION 변화 없음. 후속 R5 완료 시 통합 회귀 후 함께 main에 반영 예정.

## 2026-10-27 14:49 KST · codex · R3
- 한 일: scripts/install_skill.py 추가. --client codex/claude/copilot + --user/--project를 명시하면 루트 SKILL.md와
  Python scripts만 도구별 표준 탐색 폴더에 복사(원본 LICENSE/NOTICE가 있으면 동반). 프로젝트 .agents/.claude/.github,
  개인 .agents(Codex·Copilot)/.claude(Claude Code). 기존 폴더·링크/정션은 교체하지 않음. .git/개발 규칙/캐시/MCP 패키지 제외.
  SKILL의 실행 경로를 자신의 폴더 기준으로 명시하고 공백 경로 인용. README의 개인/프로젝트 설치·중복 방지·스냅샷/클론
  업데이트 방법과 공식 경로 출처 정리. CODEX_SETUP의 기존 Git 클론 절차는 유지하고 복사 설치 경로 안내 추가. D-012 기록.
- 검증: cp949 환경 전체 regress 단위 36/36 + 외부 에셋 6/6 + 프로젝트 3/3 PASS. 새 단위 2개에서 개인/프로젝트 경로 6개,
  한글·공백·대괄호·쉼표 경로, 다른 cwd에서 설치본 4리더 import/CLI 도움말, 기존 파일 바이트 보존·정션 거부 확인.
  실제 PowerShell 5.1.19041.6456에서 가이드 7블록 검사와 Git 클론 설치 후 최소 복사 설치본으로 eg 49 BP·1779/1779 분석 PASS.
  Python 선택/종료 코드 7/LFS 특수문자 2파일도 PASS, 사용자 Git 설정 해시 동일. skill-creator quick_validate PASS
  (검증용 PyYAML은 tests/.cache/skill-validation에만 설치), 문서 로컬 링크/fence/UTF-8 및 git diff --check PASS.
- 남은 일·주의: R3 done. 복사 설치본은 스냅샷이므로 기존 폴더를 옮긴 뒤 재설치; Git 클론은 git pull로 갱신.
  사용자 개인 스킬 폴더·설정과 공개 배포 대상은 변경하지 않음. 도구별 앱 UI 탐색 자체는 검증하지 않았고 파일 구조·실행을 검증.
  기존 output symlink 생성 하위 검사는 Windows 권한 부족으로 skip(실제 junction 검사는 PASS). 파서·출력 포맷/버전 변화 없음.

## 2026-10-27 14:11 KST · codex · R1
- 한 일: README·CHATGPT.ko·HF Space README를 공식 문서(2026-10-27 확인)에 맞춰 정정.
  로컬 스킬은 서버/HF 불필요, 원격 MCP는 선택 사항으로 구분. 검증한 CODEX_SETUP으로 Windows 설치를 통합.
  HF CPU Basic Docker 신규 생성은 개인 PRO/조직 Team·Enterprise, 유료 하드웨어는 별도 결제 조건임을 구분.
  잘못된 요금제 단정 표·무료 호스팅 보장·Security and login 경로를 제거. Plugins → + → Add custom MCP server →
  설치 → @ 호출로 갱신하고 GPT Actions 불필요 명시. 공개 범위는 사용자가 결정하며 실제 배포/설정 변경 없음.
  낡은 로컬 marketplace JSON 예시는 현재 공식 패키지 안내로 교체. 서버 시간 제한·캐시/전체 SHA 사용법도 기록.
- 검증: OpenAI Plugins quickstart/custom MCP/skills/package/tunnel, HF Spaces 생성·CPU Basic 조건·Docker 안내 직접 확인 및 링크.
  Markdown 로컬 링크·코드 fence·UTF-8/BOM 검사 PASS. 최종 코드 전체 회귀 단위 34/34 + 외부 에셋 6/6 + 프로젝트 3/3,
  실제 MCP HTTP 6도구·캐시/refresh/재시작 검사 PASS(앞 A6 항목). git diff --check PASS.
- 남은 일·주의: A5/A6/R1 모두 done. 서비스 요금제·UI는 바뀔 수 있어 확인 날짜와 공식 출처를 남김.
  Windows Job Object 실기 검증 완료, Linux/Docker 배포 실기는 이번 범위에서 실행하지 않음. 후속 후보 T3/T4 또는 R5.

## 2026-10-27 14:11 KST · codex · A6
- 한 일: 도구 VERSION·캐시 schema·호스트/소유자/저장소·전체 커밋·프로젝트 원문을 canonical JSON으로 해시.
  SHA-256 전체 256비트를 URL-safe base64 43자로 표현해 Windows 경로 예산 유지(식별자 길이로 실제 eg 쓰기 실패도 재현/해결).
  정상 종료와 producer 버전/커밋 확인 뒤에만 cache.json을 atomic replace로 게시. INDEX만 남은 중단 결과·예전 버전·손상 표식은
  재사용/파일 읽기에서 거부. refresh/실행 중 중복 요청 보존, 만료된 done 작업도 오류 응답. source label은 커밋으로 고정.
- 검증: cp949 환경 전체 regress 단위 34/34 + 외부 에셋 6/6 + 프로젝트 3/3 PASS. 신규 캐시 검사 4개 포함.
  격리 설치한 실제 mcp 1.30.0의 Streamable HTTP에서 도구 6개와 실제 eg 1779/1779 분석, 파일 읽기/검색/경로 이탈 거부,
  재사용·refresh(실제 CLI 재실행)·서버 재시작 후 디스크 캐시 재사용 PASS. git diff --check PASS.
- 남은 일·주의: 이전 digest_id는 재분석 필요. MCP의 미광고 짧은 SHA는 전체 40자를 요청하도록 바꿈(불변 캐시 식별 보장);
  CLI의 짧은 SHA 동작은 그대로. 도구 출력 포맷/VERSION 변화 없음. R1 문서 정정은 다음 커밋.

## 2026-10-27 14:01 KST · codex · A5
- 한 일: stdout reader와 독립된 monotonic 제한시간 적용. Windows는 게이트를 Job Object에 먼저 넣은 뒤
  분석을 시작해 자식 생성 경쟁을 없애고, POSIX는 새 세션/프로세스 그룹을 사용. 성공·실패·초과 시 트리 종료와
  부모 wait/파이프 수거. UTF-8 고정, 40줄 로그 유지, 4096자 초과 행은 토큰이 분할 노출되지 않게 생략.
- 검증: 신규 서버 단위 4개 포함 30/30 PASS, 외부 에셋 6/6, 프로젝트 3/3 PASS.
  무출력·미완성 행·연속 출력·stdout 닫힘과, 부모 실행/종료 뒤 자식 stdout 상속을 실제 Windows 프로세스로 검증.
  비정상 종료 코드 7, 한글 로그, 토큰 마스킹, done_event·슬롯 반환 확인. git diff --check PASS.
  첫 전체 실행의 기존 parser_concurrent_install에서 WinError 5가 1회 발생; 단독 재검사와 전체 재실행은 PASS.
- 남은 일·주의: A6/R1 계속 진행 중. POSIX 경로는 구현했으나 이번 실기는 Windows이며 외부 배포는 하지 않음.

## 2026-10-27 13:50 KST · codex · H7 V2
- 한 일: tests/windows_smoke.py로 실제 Windows PowerShell 5.1.19041.6456에서 가이드 블록 7개 구문 검사 및
  진단→Python 선택→Git 설정→스킬 클론→eg 고정 커밋 분석을 실행. 작업 경로·Git 전역 설정/검색 상한은 임시 경로에 격리.
  실제 검증에서 발견한 가이드 문제 수정: 없는 python/py 버전 명령은 건너뛰고, 대괄호 경로의 결과 확인은 -LiteralPath 사용.
  H7의 남은 실제 5.1 검증(V2)을 done으로 전환. 검증 방법/범위는 tests/README에 기록.
- 검증: eg 49 BP·1779/1779·실패 0, 한글/공백/[ ]/쉼표 출력 경로에서 가이드의 Coverage 표시 확인.
  Store 스텁(exit 9009) 거부·py -3 대체 선택·Python 없음 거부, native stderr 출력과 종료 코드 7 보존 확인.
  로컬 실제 Git-LFS 포인터 2개(.uasset/.umap)를 특수문자 경로의 git lfs pull 대체 경로로 받아 원본 바이트 대조: 실패 0.
  사용자 Git 전역 설정 해시 전후 동일. 동일 5.1/cp949 환경 전체 regress: 단위 26/26 + 외부 에셋 6/6 + 프로젝트 3/3 PASS.
  로그/결과는 tests/.cache/windows-smoke/(gitignore). 기존 symlink 실생성 하위 검사만 권한 부족 skip. git diff --check PASS.
- 남은 일·주의: 이미 설치된 Python/Git/LFS를 사용해 winget/UAC/Store UI는 실행하지 않음. 사용자 스킬 폴더나 전역 설정도
  변경하지 않음. H6/H7 완료 후 다음 후보 A5/A6 또는 T3. 프로덕션 파서·출력 포맷 변화 없음.

## 2026-10-27 13:50 KST · codex · H6
- 한 일: UE Shed 73f7c701 고정 커밋의 BP_Keys 4개(4.27/5.6/5.7/5.8, 각 9노드)와 StringTable 2개(4.27/5.3)를
  에디터 정답 JSON과 대조하는 asset_regress 추가. 노드·핀 위치/GUID·텍스트와 네임스페이스/키/문자열을 검사.
  파일별 Git blob 해시 검증, 라이선스 동반 캐시, --only assets 지원. 외부 바이너리/코드 복사·커밋 없음.
  기존 3개 프로젝트의 데이터(43/50/4)·맵(5/3/1)·외부 액터(64/0/138) 수량과 ves 배치 액터 139개 고정.
  잘못된 --only도 오류 처리. AssetTools는 엔진/게임 자료 혼재·변환기 출력 정답이어서 기본 세트에는 미채택.
  D-009와 tests/README에 출처·검증 범위 기록.
- 검증: 실제 Windows PowerShell 5.1 + PYTHONIOENCODING=cp949에서 단위 26/26, 외부 에셋 6/6, 프로젝트 3/3 PASS.
  프로젝트 노드 3057/3057, 기존 BP/노드 기대값 변화 없음. 새 누락 검사·오라클/손상 다운로드 검사 3개 추가.
  누락 검사를 수정 전 회귀 러너에 적용하면 실패 확인. 기존 symlink 생성 하위 검사만 권한 부족 skip.
- 남은 일·주의: 외부 코퍼스는 첫 실행 약 210KB 다운로드 후 해시가 맞는 캐시 재사용. 엔진 자체를 실행한 검증은 아님.
  V2/추가 H7 실제 PowerShell 검증도 통과했고 별도 커밋으로 기록 예정. 프로덕션 파서/출력 포맷 변경 없음.

## 2026-10-27 13:27 KST · codex · A3 A4 (통합 검증)
- 한 일: 원격 main의 H7(UTF-8/LFS/설치 가이드) 변경 위로 A3/A4를 rebase. WORKLOG와 단위 테스트 충돌에서 양쪽 변경을 보존.
- 검증: PYTHONIOENCODING=cp949 환경에서 최종 단위 23/23 PASS + regress 3/3 PASS(eg 13s, ar 14s, ves 13s).
  A3 병렬 설치·복구 검사와 A4 실패 주입 검사, H7 LFS 패턴 검사 모두 포함. 기존 symlink 생성 하위 검사만 권한 부족 skip.
  git diff --check PASS. 코드/픽스처의 추가 변경 없이 main에 fast-forward 후 push.
- 남은 일·주의: A3/A4와 H7은 done. H6 또는 A5/A6 진행 권장. 예전 서버 캐시는 refresh=true로 재생성.

## 2026-10-27 13:30 KST · claude · H7
- 한 일:
  - `tests/regress.py`·`tests/unit_tests.py`가 시작할 때 stdout/stderr를 UTF-8(errors=replace)로 재설정, 자식 프로세스에
    `PYTHONIOENCODING=utf-8:replace` 전달. (A1이 재현한 cp949 `UnicodeEncodeError`.)
  - LFS 대체 경로(`git lfs pull --include`) 패턴을 `lfs_include_pattern()`으로: `[ ] * ? , \`를 `?`로 바꿈.
    백슬래시 이스케이프는 Windows git-lfs에서 경로 구분자로 바뀌고, 쉼표는 목록 구분자라서. 과매칭은 같은 길이 형제 파일뿐.
  - `docs/CODEX_SETUP.ko.md`: `<PY>` 자리표시자 제거 → `Invoke-UePython` 함수(`python` → `py -3` → `python3` 중 3.10+인 첫 번째,
    WindowsApps 스텁은 종료 코드로 걸러짐). 5단계에 `PYTHONIOENCODING`, `exit code` 출력, "성공은 종료 코드로만 판단 —
    PS 5.1에서 stderr 진행 로그가 빨간 NativeCommandError로 보여도 정상" 안내.
- 검증: `PYTHONIOENCODING=cp949`로 수정 전 regress는 em dash에서 UnicodeEncodeError 재현, 수정 후 3/3 PASS + unit 14/14(lfs 패턴 검사 추가).
  설치 문서 PowerShell 블록 7개 파싱 OK(pwsh 7.4.6), 파이썬 선택 함수는 가짜 스토어 스텁(exit 9009)·파이썬 없음 두 경우 모두 확인.
- 남은 일·주의: Windows PowerShell 5.1 실기는 못 돌림 → V2로 남김(사람 PC). Codex가 Windows에서 돌릴 때 확인 부탁.

## 2026-10-27 13:24 KST · codex · A4
- 한 일: VERSION 1.6.0. BP/data/map summary의 공통 issues(stage/context/message), parse_status와 문서 Parse warnings 도입.
  속성·변수 메타데이터·위젯·타임라인·전환 규칙·그래프 렌더 실패를 전달. 맵은 외부 액터 실패/상한/LFS 누락과
  레벨 BP 예외·부분 디코딩도 INDEX/JSON에 전달. 실패한 레벨 BP는 nodes=null, status=error로 빈 0/0과 구분.
  읽지 못한 WorldSettings 게임모드/데이터 기본값은 unknown으로 표시. INDEX의 clean 판정은 부분 실패도 확인.
  regress가 JSON의 BP/data/map 전체/부분 실패와 레벨 BP·외부 액터·LFS 실패를 검사하도록 강화.
  새 검사가 발견한 AR 2개 BP의 SavedViewOffset 네이티브(DeprecateSlateVector2D) 오파싱도 수정: 값 추측 없이 opaque 보존.
  INDEX 범례·양쪽 SKILL·README·Windows 가이드와 D-008 갱신.
- 검증: 단위 22/22 PASS(A4 실패 주입/네이티브 검사 7개 추가), regress 3/3 PASS. BP 120개·노드 3057/3057,
  데이터 97개·맵 9개, 전체/부분 실패 0. 맵/그래프/속성/데이터 실패 주입 시 clean이 사라지고 회귀가 실패하는 것 확인.
  새 검사 3개를 수정 전 구현에 적용하면 실패 확인(맵 오류 보고, 비-BP 회귀 검사, 네이티브 보존).
  실제 Windows 정션 검사는 계속 PASS, 기존 symlink 실생성 하위 검사만 권한 부족 skip. git diff --check PASS.
- 남은 일·주의: 서버 영속 캐시의 예전 digest는 analyze_repo(refresh=true)로 재생성(A6는 별도 todo).
  Windows에서 검증; Unix flock 분기는 이 PC에서 미실행. 다음은 H6/H7 또는 A5/A6. A3/A4 브랜치를 main에 FF 후 push.

## 2026-10-27 13:13 KST · codex · A3
- 한 일: 분류/렌더 Pool 생성 전에 부모에서 파서 설치 완료. 설치는 OS 파일 잠금 + 임시 체크아웃 후 rename으로 게시,
  중단된 설치 교체, Git/잠금 대기시간 제한 추가. D-007에 캐시 설치 규칙 기록.
- 검증: 단위 15/15 PASS(병렬 설치·잠금/재시도·부모 준비 3개 추가), regress 3/3 PASS.
  로컬 가짜 파서 저장소로 4개 프로세스 동시 설치, 불완전 설치 복구, 실패한 fetch 후 재시도 확인.
  실제 고정 파서를 새 빈 캐시에 받아 ves를 4워커로 분석: BP 2개·노드 7/7, 실패 0; 맵도 성공.
  기존 symlink 생성 하위 검사는 Windows 권한 부족으로 skip. 출력 포맷/기대값 변화 없음.
- 남은 일·주의: 같은 브랜치에서 A4(부분 실패 보고·회귀) 진행 중. A3/A4 완료 후 main에 fast-forward 예정.

## 2026-10-27 12:38 KST · codex · A2
- 한 일: `validate_output_dir`로 입력 저장소/선택한 프로젝트와 같거나 이를 포함하는 출력 경로를 거부.
  심볼릭 링크·Windows 정션(3.10/3.11도 reparse 속성 사용), 파일 경로, 일반 파일이 있는 폴더도 거부.
  기존 출력은 digest.json 도구 식별자와 최상위 생성 항목을 검증한 뒤 교체. 새/빈 출력과 정상 요약본 재생성은 유지.
  클론 전에 검증하고 체크아웃 뒤 재검증; `--project` 선택을 삭제보다 먼저 수행해 잘못된 선택 시 이전 결과 보존.
  사용 지침(README/SKILL/Windows 설치 문서)과 D-006 갱신.
- 검증: 단위 12/12 PASS(6개 추가), 실제 Windows 정션 검사 PASS. 심볼릭 링크 실생성 하위 검사는 권한 부족으로 skip.
  새 음성 검사 4개를 수정 전 코드에 실행하면 모두 삭제 시도를 잡는 것 확인(삭제 함수 모킹으로 원본 보호).
  최종 regress 3/3 PASS(eg 49 BP·1779/1779, ar 69·1271/1271, ves 2·7/7), git diff --check PASS.
  앱 번들 Python 3.12.14 + PYTHONIOENCODING=utf-8:replace 사용. 생성 결과 포맷/기대값 변화 없음.
- 남은 일·주의: 출력 내부 blueprints/cpp/data/maps/config는 전용 생성 폴더이며 재실행 시 교체됨. 실행이 중단되어
  식별 불가능한 결과 폴더는 새 --out을 사용. A3(최초 파서 설치 경합) → A4(부분 실패 보고/회귀) 순으로 권장.

## 2026-10-27 11:54 KST · codex · A1
- 한 일: 실행 코드 변경 없이 전체 구조와 실패 처리 분석. `REVIEW-2026-10-27.md`에 근거·재현·우선순위 기록.
  A2(입출력 경로 겹침 삭제), A3(최초 파서 설치 경합), A4(맵/그래프 부분 실패 보고), A5(MCP 무출력 timeout),
  A6(버전 누락/프로젝트 충돌 캐시 키)를 todo로 추가. H7에 regress.py cp949 출력 실패 재현 기록.
- 검증: 앱 번들 Python 3.12.14, 단위 6/6 + UTF-8/준비된 캐시로 regress 3/3 PASS.
  BP 120개·노드 3057/3057, 데이터 97개·맵 9개, 데이터/맵 실패 0.
  모킹 검사에서 입력 루트 삭제 시도·맵 실패를 INDEX가 clean으로 판정·회귀도 통과 확인.
  무출력 자식 0.53s가 0.1s timeout을 넘어 done, 프로젝트 경로 캐시 충돌도 확인. MCP 네트워크 E2E는 미실행.
- 남은 일·주의: 최초 빈 파서 캐시는 워커들의 config/shallow 잠금 충돌로 ves BP 1개 실패; warm 재실행 통과.
  첫 eg/ar checkout 255 원인은 미확정. C: 디스크가 0까지 차서 재현 파일 쓰기 실패; 테스트 클론 약 1.3GB,
  자동 승인 검토가 정리 명령을 차단해 사용자에게 직접 정리 요청. 추가 클론/다운로드 전에 여유 공간 확인.
  다음은 A2/A3 → A4·회귀 강화 권장. 기능 구현은 하지 않음.

## 2026-10-27 16:30 KST · claude · F8
- 한 일: AnimMontage를 데이터 에셋으로 렌더(`DATA_CLASSES`에 추가, `data_reader._render_montage`): 길이·블렌드 인/아웃·자동 블렌드아웃,
  슬롯별 세그먼트(재생 시퀀스, 구간, 재생 속도, 반복), 섹션과 다음 섹션 링크, 노티파이를 시간순으로
  (노티파이 객체 클래스·설정, 이름만 있으면 "event → AnimBP `AnimNotify_X`"로 AnimBP 이벤트와 연결). 중복되는 원시 프로퍼티는 생략.
- 검증: regress 3/3 PASS, F8 검사 추가(AR Primary_Attack_A_Medium_Montage).
- 남은 일·주의: AnimSequence 자체의 노티파이는 아직(시퀀스는 크고 LFS 제한에 걸리기 쉬움). UE 4.25 저장 몽타주(AR 스파이더)는 섹션 이름이
  `0`, `1`로 나오는데 실제 이름인지 FName 해석 문제인지 미확인. 다음 추천 T3(캐시) 또는 D1(커밋 간 BP diff).

## 2026-10-27 16:00 KST · claude · F7
- 한 일: BP 문서에 `## Timelines` — TimelineTemplate(TaggedReader)에서 길이(기본 5s)·autoplay·loop·replicated·LengthMode,
  float/vector/color/event 트랙별 외부 커브 에셋 이름 또는 내부 커브 키(최대 8개, `t→v`). 빈 내부 커브는 "no keys (evaluates to 0)".
- 검증: regress 3/3 PASS, F7 검사 2개(EG BP_NullPointGM TempMatching, AR BP_MusicManager).
- 남은 일·주의: 외부 커브 에셋의 키는 그 커브의 data/ 문서에 있음(링크는 안 걸었음). 다음 추천 F8(몽타주·노티파이), T3(캐시).

## 2026-10-27 15:40 KST · claude · F6
- 한 일: 위젯 BP
  - 위젯 트리에 비기본 속성(Visibility, RenderOpacity, Width/HeightOverride, ColorAndOpacity, Brush 리소스 …, `_WIDGET_KEYS`)과
    슬롯 레이아웃 `[slot Padding=…, HorizontalAlignment=…, Size=…]`(슬롯 export의 저장값 전부, 200자 상한).
  - `## Widget animations`: 애니메이션별 트랙 대상 속성(MovieScene 트랙의 PropertyBinding)과 바인딩된 위젯(AnimationBindings.WidgetName,
    TaggedReader로 읽음). `*_INST` 복사본은 건너뜀.
  - `## Property bindings`: `UWidgetBlueprint.Bindings`(ObjectName.PropertyName ← FunctionName/SourcePath). **테스트 저장소 3개에 바인딩이 하나도
    없어 실데이터 미검증** — 바인딩 쓰는 프로젝트를 만나면 출력 확인할 것.
- 검증: regress 3/3 PASS, F6 검사 추가(WBP_NavBtn).
- 남은 일·주의: 애니메이션 길이·키 값(MovieSceneFrameRange, FloatChannel)은 opaque라 미표시. 다음 추천 T3(blob SHA 캐시), F7(타임라인), F8(몽타주 노티파이).

## 2026-10-27 15:10 KST · claude · F4
- 한 일: 이 프로젝트 BP 클래스의 인스턴스로 저장된 에셋(클래스명 `<BP이름>_C`, 예: PDA_PlayerData로 만든 DA_PlayerData)을
  데이터 에셋으로 분류해 저장값을 렌더. EG에서 DA_PlayerData·DA_Stash·DA_UISetting 3개가 새로 `data/`에 생김.
- 검증: regress 3/3 PASS, F4 검사 추가.
- 남은 일·주의: 바이트 열거형 배열은 숫자로 나옴(`Stashinfo = [7, 0, …]`, 타입 Array<E_Crates>) — 열거형 이름 매핑은 교차 에셋 조회가 필요해 보류.
  PDA_PlayerData 변수 표의 `Map<E_Crates, None>` 값 타입 디코딩이 이상함(별도 확인 필요).

## 2026-10-27 14:50 KST · claude · F3
- 한 일: 함수 헤더에 `[pure, const, static, private, protected, RunOnServer, RunOnOwningClient, Multicast, Reliable]`
  (FunctionEntry `ExtraFlags`). 변수 표 Flags에 Transient·Config·SaveGame·ExposeToCinematics(PropertyFlags),
  `Condition=OwnerOnly` 등(ReplicationCondition), ExposeOnSpawn·Private(메타데이터), 툴팁이 있으면 Tooltip 열.
  메타데이터는 uasset_read가 opaque로 남기므로 `data_reader.TaggedReader`로 BP export를 다시 읽어 얻음(`_variable_metadata`).
- 검증: regress 3/3 PASS + unit, F3 검사 3개 추가. 플래그 분포: pure 9, const 8, pure+static 6, pure+const 6.
- 남은 일·주의: 함수 MetaData(툴팁·카테고리·CallInEditor)는 아직 미표시. 다음 추천 T3(blob SHA 캐시) 또는 F6(위젯 슬롯·바인딩), F4(BP 클래스 DataAsset).

## 2026-10-27 14:10 KST · claude · T2
- 추가: MCP 서버도 자체 git fetch 대신 digest 스크립트의 부분 클론을 씀(`--ref <commit> --workdir`). 로그·digest.json의 URL에서 자격 증명 제거.
  서버 E2E(mcp_client_test) 통과, 서버 작업 폴더 .git 137MB.
- 한 일:
  - 클론을 부분 클론으로: `--filter=blob:limit=2m --no-checkout --depth 1` → `ls-tree`(크기 조회 없이)와
    `rev-list --missing=print`로 빠진 큰 blob을 알아낸 뒤 필요한 경로만 `checkout --pathspec-from-file`(한 번에 일괄 fetch).
    빠진 blob 중 `.umap`과 이름이 아트 접두사(T_, SM_, SK_, M_, MI_, S_, A_ …)가 아닌 `.uasset`만 가져옴. 나머지는 parse report에 기록.
  - LFS를 `git lfs pull` 대신 LFS batch API로 직접 받음(`lfs_batch_download`, 8병렬, sha256 검증). 이유: git-lfs가 트리 전체를
    훑으면서 부분 클론의 빠진 blob을 하나씩 lazy fetch함(EG에서 53팩, +500MB). 실패·남은 것은 기존 `git lfs pull`로 대체.
    인증은 URL의 자격 증명(서버의 GITHUB_TOKEN)만 사용, `.lfsconfig`가 있으면 git-lfs에 맡김.
- 검증: 새 클론으로 regress 3/3 PASS. EG 36s→17s, .git 603MB→137MB. AR은 LFS가 없고 작은 파일이 대부분이라 46s 그대로(큰 blob 13개만 추가 fetch).
- 남은 일·주의: git 2.43에는 `GIT_NO_LAZY_FETCH`가 없어 직접 다운로드로 우회. 기존 클론 재사용 + `--ref` 경로는 여전히
  `git checkout ref`(빠진 blob lazy fetch) — 필요하면 materialize 재사용으로 바꿀 것. 비공개 저장소의 로컬 실행(자격 증명 도우미)은 git-lfs 경로로 감.

## 2026-10-27 13:10 KST · claude · F1
- 한 일: `config/GameplayTags.md` 신규 + INDEX에 GameplayTags 절.
  - 정의: `Config/DefaultGameplayTags.ini`, `Config/Tags/*.ini`, 플러그인 Config, GameplayTagTableRow DataTable,
    C++ `UE_DEFINE_GAMEPLAY_TAG(_COMMENT|_STATIC|_TYPED)`. 리다이렉트(`GameplayTagRedirects`)도.
  - 사용: 요약본 Markdown의 `TagName=X`(BP·data·map) + C++의 `RequestGameplayTag("X")`와 네이티브 태그 변수 사용.
  - 경고: 쓰였는데 어디에도 정의 안 된 태그, 옛 이름(리다이렉트)으로 저장된 태그. "정의됐는데 미사용" 목록은 보수적 표현.
- 검증: regress 3/3 PASS + unit 6/6, AR에서 22개 정의(네이티브 12)·12개 사용·리다이렉트 2개 확인. EG는 태그가 없어 절 생략.
- 남은 일·주의: 런타임 문자열로 만든 태그는 못 봄(문서에 명시). 맵 인스턴스의 태그 오버라이드가 요약본에 안 나오면 미사용으로 잡힐 수 있음
  (AR의 KeyCard.* — LeverBP 배치 인스턴스 오버라이드 확인 필요, 별도 조사 거리).

## 2026-10-27 12:40 KST · claude · F2
- 한 일:
  - IMC 표의 모디파이어·트리거를 서브오브젝트로 펼쳐 설정값 표시: `InputModifierNegate_4` → `Negate`,
    `Negate(bX=false, bZ=false)`, `Scalar(Scalar=Vector{X=50, Y=50, Z=1})`. 데이터 요약에 `mapped_actions` 추가.
  - INDEX에 "Input check (Enhanced Input)" 절: BP가 처리하는데 어떤 IMC에도 없는 액션(⚠), 매핑됐지만 BP 이벤트가 없는 액션을
    "프로퍼티에 할당됨(C++ 바인딩 추정)"과 "어디서도 참조 안 됨(C++ 확인 필요)"으로 구분.
  - 사용자 프로젝트에서 실제로 `IA_EnterBlackSite ← BP_NullPointPC` 미매핑 검출, `IA_MouseLook`은 IMC_MouseLook에만 있고 미사용.
- 검증: regress 3/3 PASS + unit 6/6, F2 검사 3개 추가.
- 남은 일·주의: InputAction 에셋 자체의 트리거·모디파이어(IA 단위 설정)는 아직 표시 안 함. 다음 추천 F1(GameplayTags), T2(부분 클론).

## 2026-10-27 12:10 KST · claude · H2 H3 H5 T1
- 한 일 (VERSION 1.5.0 — B7·B8·H5·T1로 출력 표기가 바뀐 것을 묶어 올림):
  - H2 맵 핀 세 번째 bool(`bTerminalIsUObjectWrapper`)을 `FReleaseObjectVersion >= 31`일 때만 읽음.
  - H3 핀 필드 조합을 커스텀 버전으로 먼저 결정(단정밀도 플래그 `FUE5ReleaseStreamObjectVersion >= 36`,
    UObject 래퍼 `FReleaseObjectVersion >= 31`, SourceIndex는 게이트 불명이라 둘 다 시도). 기존 탐색은 대체 경로로 유지.
    요약 정보 읽기는 `_custom_versions()`(경로별 캐시)로 통합.
  - H5 `FileVersionUE5 > 1018` 또는 알려진 커스텀 버전(FNMB 268, Release 44, UE5RS 68)보다 새 패키지면 BP·data·map 헤더와
    parse report에 경고. 값은 `bp_reader._KNOWN_*` — **새 엔진 버전을 검증하면 여기를 올릴 것**.
  - T1 `digest.json` 압축(공백 제거, AR 124KB→97KB) + "읽지 말 것" 안내(INDEX 범례, SKILL.md). 60k자 넘는 Markdown은
    `X.md` + `X.part2.md…`로 자동 분할(코드 펜스 닫고 다시 염, 끝에 이어보기 링크). 서버는 원래 .md만 나열.
  - 단위 테스트 추가: newer_format_note, combo_order, split_md.
- 검증: regress 3/3 PASS + unit 6/6. H2·H3·H5 전후 출력 동일(경고 오탐 0). 분할은 낮은 한도(10k)로 실제 요약본에 돌려 확인.
- 남은 일·주의: 다음 추천 T2(부분 클론, 콜드 실행의 85~90%가 클론) → T3(blob SHA 캐시). 기능은 F1(GameplayTags)·F2(입력 교차 검사)가 싸고 효과 큼.
  H6·H7(Windows 실기)은 사람 PC가 필요할 수 있음.

## 2026-10-27 11:30 KST · claude · B7 B8 H1
- 한 일:
  - B7 구조체 값 읽기 쉽게: `Name_N_<GUID>` 멤버명 → `Name`(BP·data·map 전부), 구조체 안 object 프로퍼티를 에셋 이름으로
    (`ObjRef` = int 하위 클래스, uasset_read의 object/class 핸들러를 감쌈, `Ctx` 생성 시 `_CUR_CTX` 설정),
    핀 기본값 `0.000000,0.000000,80.000000` → `Vector{X=0, Y=0, Z=80}`, `(TagName="A")` → `GameplayTag{TagName=A}`.
  - B8 길고(60자 초과) 두 곳 이상에서 쓰는 순수 식을 그래프 끝 `// where` 블록에 `$N`으로 한 번만 출력(순수 노드는 매번
    재평가되므로 let이 아니라 where로 표기). 여러 출력 핀을 가진 순수 호출도 대상. 범례·SKILL.md 반영.
  - H1 FText DevNotes를 FString으로 읽음, 게이트를 커스텀 버전(FNMB ≥ 260, 에디터 전용 필터 아님)으로 교체(D-005).
  - `tests/unit_tests.py` 추가(regress가 먼저 실행): DevNotes 합성 바이트, 멤버명, 핀 구조체 표기.
- 검증: regress 3/3 PASS + unit 3/3. H1 전후 출력 바이트 동일(노트가 전부 비어 있음). B7·B8 검사를 이전 출력에 돌리면 실패 확인.
- 남은 일·주의: P0 끝. 다음 추천: H2·H3(맵 핀 bool·단정밀도 플로트를 버전 게이트로), H5(5.9 대비 경고), T1(digest.json 분리).
  `$N` 별칭 기준은 `_ALIAS_MIN_LEN = 60` (bp_reader.py).

## 2026-10-27 10:40 KST · claude · B1 B2 B3 B4 B5 B6
- 한 일 (출력 포맷 v1.4.0):
  - B1 함수 결과: `return true/false` 등 값 출력(5.8은 결과 핀 default==auto_default라 기존 필터가 숨김), 헤더에 `-> Out: T`.
  - B2 애님 전환: `bAutomaticRuleBasedOnSequencePlayerInState` → `when auto (…)`, 상수 False 규칙 → `when never (…)`,
    비기본 전환 설정 `[blend Xs, priority N, on start/end/interrupt notify X]`. `state_machine()`이 이제 4-튜플(…, props).
  - B3 goto: exec 진입 수를 reroute knot 너머 실제 대상으로 셈 + 라벨 없는 goto가 남으면 강제 라벨로 한 번 재렌더.
  - B4 연결 안 된 object/class/interface 입력을 `Pin=∅`로 표시(advanced/hidden 핀 제외).
  - B5 `--ref`: 40자 SHA는 그 커밋만 fetch, 짧은 SHA는 blobless 클론으로 해석, 못 찾으면 명확한 error로 종료.
    기존 클론 재사용 시에도 `--ref`로 체크아웃(이전에는 무시됐음).
  - B6 Used by 자기 이름(같은 이름의 다른 에셋) 제외, 깨진 클래스명(`/Script/…_1476395008`) 버림,
    이름 추정 분류를 실제 클래스에 합침(`NiagaraSystem 23`), `other (by name)` → `unknown class`.
  - 범례(INDEX.md), SKILL.md, chatgpt-plugin SKILL.md에 새 표기 반영. VERSION 1.4.0.
- 검증: regress 3/3 PASS, 버그별 검사 7개 추가(fixtures.json). 같은 검사를 수정 전 출력에 돌리면 eg 11·ar 3건 실패 → 검사가 실제로 잡음.
  수정 전후 diff에서 의도하지 않은 변화 없음(라벨 번호 이동만). 짧은 SHA/없는 SHA/전체 SHA 클론 경로 직접 실행 확인.
- 남은 일·주의: P0 중 B7(구조체 기본값 원시 출력)·B8(순수 노드 반복 인라인)은 todo. 다음 추천은 H1(FText DevNotes FString).
  `Pin=∅`는 선택 입력(OwningPlayer 등)에도 붙는다 — 사실이지만 많아지면 F-계열에서 "선택 입력" 구분 검토.

## 2026-10-27 09:30 KST · claude · (규칙 도입)
- 한 일: AGENTS.md(공용 규칙 원본), CLAUDE.md, `.githooks/commit-msg`(태그 검사), docs/dev/TASKS·WORKLOG·DECISIONS,
  회귀 테스트 `tests/regress.py` + `tests/fixtures.json`(고정 커밋 3개) 추가. TASKS는 2026-10-26 조사 로드맵을 옮긴 것.
- 검증: 현재 코드로 regress 3/3 PASS (eg 49 BP·1779 노드, ar 69·1271, ves 2·7).
- 남은 일·주의: 새 기기에서는 `git config core.hooksPath .githooks` 한 번. 이어서 claude가 P0 버그(B1~B6) 수정 진행.
