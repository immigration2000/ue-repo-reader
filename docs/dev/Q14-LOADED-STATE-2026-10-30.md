# Q14 — 저장 바이트와 에디터 로드 상태 차이

2026-10-30 · Codex + 실제 Claude Code 교차 검토 · 도구 1.17.0

고정 eg 저장소의 native 비교 차이 7개 에셋을 재조사했다. 실제 리더 오류 2종(텍스트 원문 누락, 그래프 밖 export 포함)을
고쳤다. 나머지는 저장값과 로드된 관측을 구분해 계속 보고한다. 비교 결과를 맞추기 위해 GUID·const·기본값을 바꾸지 않았다.

## 독립 관측과 범위

- 원본 eg commit `f7335adbb7a896457127303fe4eb30a5292ead8f`, 같은 패키지 SHA-256 및 Git blob.
- 설치된 UE `5.8.4-58902052+++UE5+Release-5.8`, 기존 RepoReaderOracle native bridge 소스 지문 유지.
- 임시 프로젝트에 Content를 복사하고 no-PCH 모듈을 빌드했다. 사용자 프로젝트·엔진 전역 설정은 변경하지 않았다.
- 프로세스1에서 두 번, 새 프로세스2에서 반대 로드 순서로 두 번 수집. 각 요청7개 모두 수집 오류0·dirty=false·전후/원본 해시 동일.
- 각 프로세스 내부는 기존 all 정규화 비교 범위의73318개 관측이 동일했다. 프로세스 사이에는72961개 가용 관측과 GUID 정체성 차이34개를 보고했다.
  배열 순서·레이아웃·기존 제외 항목은 이 비교에 포함되지 않는다. 관측 수는 정확도 점수가 아니다.
- 새 BP_Knife 전체 native 정답과 선택된 원본 관측/바이트 증거만 커밋한다. 큰 전체 캡처·프로젝트 복사본·바이너리는 캐시에 둔다.

재수집 첫 실행은 임시 호스트에서 AnimationData 플러그인을 끈 상태라 애니메이션 의존 에셋 로드가 실패했다.
그 실행은 증거로 쓰지 않았다. 해당 호스트에만 필요한 AnimationData를 켜고 두 프로세스 수집을 다시 성공시켰다.

## 결과

| 차이 | 독립 증거 | 판정과 처리 |
|---|---|---|
| 변수 카테고리8개, 에셋3개 | 원본 History=None FText에 `InnerFunctions`/`Control` 저장. 두 native 프로세스의 원문과 일치. 기존 리더만 빈 문자열 | **리더 오류 수정.** Editor custom version>=32의 scalar tagged 문화권 독립 텍스트를 경계 검사해 읽고 선언 IR·변수 표에 반영 |
| eg ABP_Hands 추가 Entry export109 | 저장 Nodes에는39개, native도 같은39개. 기존 파서의 Outer 그룹에만 추가 export가 섞임 | **멤버십 오류 수정.** 목록 밖 export의 노드·핀은 별도 IR에 보존하고 그래프에서는 제외 |
| ar GideonManny 추가 Entry export155 | 독립 native 캡처를 주장하지 않는다. 원본 Nodes 배열 바이트는6개 멤버이며155가 없음 | 같은 저장 목록 기준으로 제외·별도 보존. 전체 회귀에서 발견한 같은 종류의 오류 |
| 숨긴 ErrorTolerance17개 | 같은 프로세스에서는 동일, 새 프로세스에서만 GUID가 달라짐. 선택된 native 핀의 나머지 필드는 동일. 저장 GUID는 원본 바이트와 리더에 그대로 있음 | **native 세션 의존 ID 관측.** 정확한 재생성 호출 경로까지 추적한 것은 아니다. 이름으로 ID를 맞추거나 비교에서 숨기지 않음 |
| UI_Thumbstick WorldContextObject const | 동일 GUID, 원본 type payload의 bool은false. 두 프로세스 native는true | **안정적인 저장/로드 값 차이.** 리더는 원본false를 유지. 특정 엔진 보정 함수나 런타임 의미는 단정하지 않음 |
| BP_FirstPersonGameMode 입력 B 기본값 | 원본 FString은 `020000003000` 즉 문자열 `0`, 두 프로세스 native는 빈 문자열 | **안정적인 저장/로드 표기 차이.** 리더가 원본값을 빈 문자열로 고치지 않음. 실행상 동등성도 추정하지 않음 |

기존52개 캡처와 최종 리더를 대조하면 차이 에셋은7→5, 차이 항목은45→36이다. 남은36개는 GUID 정체성34개와
const/default2개다. 이들은 계속 mismatch로 출력한다. 모든52개에는 여전히 부재 태그/non-map terminal 등 미확정도 있다.
전체 의미 정확도 완료나 게임플레이 검증을 뜻하지 않는다.

## 그래프 export를 보존하는 방법

`graph_ir.saved_membership`는 exact export/태그와 바이트 개수를 검증한 Nodes 배열을 기준으로 한다.
누락/형식 미지원/참조 미해결/디코딩된 멤버 부족이면 삭제하지 않고 기존 view와 unknown 이유를 남긴다.
잘못된 원본 경계·개수와 실제 읽기 실패는 parse report에도 전달한다. 파서가 돌려준 빈 배열만으로는 판단하지 않는다.
원본 태그에 명시적인 count0이 있으면 그것은 확인된 빈 목록이며, 남은 export를 그래프에 임의로 넣지 않는다.
`membership_basis`에도 집계 근거를 남긴다. 이 새 검증은 UE5 저장 패키지 범위이며, UE4 저장 패키지는 기존 decoded view와
범위 밖 unknown 이유를 유지한다. 구버전 형식 지원을 확대하지 않고 bt의 기존26/98·정확한90개 issue 기준도 유지한다.

확인된 목록 밖 export는 `blueprints[path].unlisted_graph_nodes`에 전체 핀 IR과 함께 보존한다.
Level Blueprint 쪽 결과는 `maps_detail[path].level_bp_unlisted_graph_nodes`로 전달한다. 서로 다른 멤버십 영역으로 향하는
참조는 원래 owner/GUID를 유지한 미해결 상태다. 별도 영역의 노드를 실제 그래프 실행 대상으로 추정하지 않는다.

ABP_Hands의 별도 `EntryNode` 속성은 목록 밖109를 참조하고, 목록 안108은 실제 저장된 링크를 갖는다.
두 사실은 함께 보존된다. Markdown은 listed-node 링크에서 그린 entry가 런타임 entry의 보증이 아니라고 알린다.
원본 포인터·패키지를 저장하거나 고치지 않는다. eg 그래프 노드 총계1779→1778(ABP_Hands170→169), ar1271→1270이다.
없어진 데이터가 아니라 집계 대상이 바뀐 것이며, 각1개 decoded export는 별도 영역에서 계속 확인할 수 있다.

## 텍스트 실패와 인코딩

새 scalar 경로는 FText의 source를 읽는다. 실패한 값은 문자열 모양의 `UnreadableValue` 표시와 별도로
선언/함수 메타데이터에서는 unknown으로 처리한다. 사용자가 실제로 같은 모양의 문자열을 저장한 경우에는 literal로 보존한다.

양수 FString 길이에는 canonical ASCII, 음수 길이에는 UTF16을 허용한다. 별도 소유한 패키지 복사본에서 문자1바이트를0xe9로
바꿔 실제 에디터로 읽자 원문이 U+00E9가 아니라 U+FFE9였다. 복사본은 원상복원했으며 원본 저장소는 건드리지 않았다.
따라서 Latin-1/현재 코드페이지를 추측하지 않고 비정규 narrow 바이트는 unknown으로 거부한다. 이 반례도 byte/hash 증거와 함께 고정한다.

이 변경은 scalar tagged TextProperty에 한한다. TArray/Map/Set 안의 FText는 종전 경로이며 History=None 등에서 원문을
놓칠 수 있다. 빈 표시를 실제 부재로 단정하지 말아야 한다. 컬렉션 지원과 native 정답은 후속 **Q18**로 등록했다.

형식 사실은 설치된 `Text.cpp`, `EditorObjectVersion.h`, `EdGraphPin/Node`와 객체/핀 공개 필드를 확인했다.
엔진 구현이나 고정 버전 이후 파서 코드를 복사하지 않았다. 문화권 독립 텍스트의 의미는
[공식 텍스트 지역화 문서](https://dev.epicgames.com/documentation/unreal-engine/text-localization-in-unreal-engine)도 참고한다.

## 재현과 회귀

- [독립 정답/바이트 증거](../../tests/editor_evidence/eg-loaded-state.json): 패키지 SHA·Git blob, 카테고리8개, 핀17+2개, native 상태 그래프.
- [ar 저장 목록 증거](../../tests/editor_evidence/ar-unlisted-state-node.json): native 관측과 구분한 원본 배열/소스 정체성.
- [비정규 narrow 바이트 반례](../../tests/editor_evidence/ansi-native-probe.json): 별도 복사본 원문·바이트·전후 해시.
- [BP_Knife native 정답](../../tests/editor_oracles/eg-bp-knife.json): 전체 캡처를 변형 없이 선택하고 정확한 unknown 경계 고정.
- `editor_state_evidence.py`는 원본 바이트와 새 리더를 다시 읽어 대조한다. 원문/멤버십 회귀, 저장 const/default 유지, GUID 미변경을 검사한다.
- `compare_native_repeats.py`는 두 native 캡처만 읽는 진단 도구다. 엔진 빌드·프로젝트가 다르거나 schema/producer/정체성 등 입력 전제가 틀리면 exit2로 거부하며 보고서를 쓰지 않는다.
  입력 전제가 성립한 뒤 캡처 오류·에셋 집합·패키지 해시·dirty 상태 등에 갭이 있으면 incomplete(exit1)가 우선하며, 비교 가능한 에셋의 차이 기록은 유지한다. 완전한 비교에서 차이가 있으면 changed(exit1), 차이·갭이 없으면 stable(exit0)이다.
- `editor_native_smoke.py --no-pch`는 임시 호스트의 대형 PCH 생성을 줄이는 선택 옵션이다. 신규 사용자 의존성은 없다.

최종 전체 회귀는 단위154/154·외부 에셋6/6·native 정답8/8·고정 프로젝트4/4 PASS이다.
캐시 cold/warm/disabled의 Markdown/JSON101개 바이트 일치·warm97 hits, 실제 MCP HTTP6도구·캐시 분리도 통과했다.
동시 smoke 실행 때 기존 프로세스 종료 검사의 fixture 준비가1.2초를 넘은 실패1회가 있었고, 검사/제품 코드를 바꾸지 않고
다른 실행이 끝난 뒤 전체 회귀를 단독 재실행해 종료 코드0을 확인했다.
별도 no-PCH smoke는 실제 UE5.8.4 빌드·1251 graph 관측 일치·dirty 거부·원본 해시 보존을 통과했다.
전체 재수집 호스트는0.300GiB·PCH0개이며, 신규5.7 no-PCH 빌드까지 검증했다는 주장은 하지 않는다.
