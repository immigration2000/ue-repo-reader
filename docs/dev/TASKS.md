# TASKS

상태: `todo` · `doing` · `done` · `blocked`. 담당: `claude` / `codex` / `-`.
작업을 시작할 때 상태와 담당을 바꾸고 커밋하세요(다른 에이전트와 겹치지 않게). ID는 커밋 메시지에 씁니다.
근거와 상세는 2026-10-26 조사 보고서(로드맵 절)를 요약한 것입니다. 규모: S(하루 이내) · M(며칠) · L(1주 이상).

## P0 — 요약본이 사실과 다르게 말하는 버그

| ID | 상태 | 담당 | 내용 | 규모 |
|---|---|---|---|---|
| B1 | done | claude | 함수 반환값·출력 파라미터 누락: `return` → `return true`, 헤더에 `-> bool` (WBP_GridSlot.CanPlaceItem) | S |
| B2 | done | claude | 자동 전환(`bAutomaticRuleBasedOnSequencePlayerInState`)이 `when False`로 표시 (ABP_Hands) | S |
| B3 | done | claude | `→ goto #N`인데 `[#N]` 대상이 출력되지 않음 (BP_FirstPersonCharacter IA_Move, AR A_FootstepFoleyComponent) | S–M |
| B4 | done | claude | 연결 안 된 필수 입력이 안 보임: `Possess()` → `Possess(InPawn=∅)` (BP_NullPointPC) | S |
| B5 | done | claude | `--ref`에 짧은 SHA를 주면 CalledProcessError로 종료 | S |
| B6 | done | claude | 색인 잡음: Used by 자기 참조, `/Script/CoreUObject.Vector_1476395008` 같은 분류 라벨, Niagara 라벨 분리 | S |
| B7 | done | claude | 구조체 기본값 원시 출력(GUID 붙은 멤버명, `=-143` 객체 인덱스, 벡터 문자열) | S–M |
| B8 | done | claude | 순수 노드 반복 인라인(SnapDragAxis 8회) → `let` 한 번 | S |

## P1 — 5.8 포맷 견고화, 토큰, 실행 시간

| ID | 상태 | 담당 | 내용 | 규모 |
|---|---|---|---|---|
| H1 | done | claude | FText 5.8 추가 필드를 DevNotes FString으로 읽기, 게이트 `FFortniteMainBranchObjectVersion >= 260 && !PKG_FilterEditorOnly`, 0이 아니면 경고 | S |
| H2 | done | claude | 맵 핀 세 번째 bool을 `FReleaseObjectVersion >= 31`일 때만 | S |
| H3 | done | claude | 단정밀도 플로트 플래그를 `FUE5ReleaseStreamObjectVersion >= 36` 게이트로 | S |
| H5 | done | claude | 모르는 `FileVersionUE5`(>1018)·커스텀 버전이면 경고 후 부분 출력 (5.9 대비) | S |
| H6 | done | codex | 회귀 세트 확장: UE Shed 에셋 6개/에디터 정답, 데이터·맵·외부 액터 수량 검사; AssetTools 검토(D-009) | S–M |
| H7 | done | claude | Windows 점검: LFS 패턴·Python 선택·UTF-8 처리; codex가 실제 PowerShell 5.1/LFS/설치 가이드 추가 검증 완료(V2) | S |
| T1 | done | claude | `digest.json`을 "전부 읽기" 대상에서 제외, 큰 DataTable 상한 | S |
| T2 | done | claude | 부분 클론(`--filter=blob:limit` 또는 `blob:none` 후 필요한 것만) — 콜드 실행의 85~90%가 클론 | M |
| T3 | doing | codex | 에셋별 blob SHA 캐시(바뀐 것만 재파싱); 통합 실측 후 분류 캐시 비용 조정 중 | S–M |
| T4 | done | codex | INDEX 순위 지도(PageRank, 2~4k 토큰), 파일별 머리말 | M |

## P2 — 기능 격차

| ID | 상태 | 담당 | 내용 | 규모 |
|---|---|---|---|---|
| F1 | done | claude | GameplayTags 레지스트리(ini/DataTable/C++)와 사용처 | S |
| F2 | done | claude | 입력 교차 검사(트리거·모디파이어 값, "BP가 쓰는데 IMC에 없는 IA" 경고) | S |
| F3 | done | claude | 변수·함수 플래그(ExposeOnSpawn, Private, SaveGame, RPC, Pure/Const …) | S |
| F4 | done | claude | BP 클래스 DataAsset 인스턴스 저장값 | S |
| F5 | todo | - | GAS 요약(GE·GA) | S |
| F6 | done | claude | 위젯 슬롯·바인딩·애니메이션 | S / M |
| F7 | done | claude | 타임라인 템플릿(길이, 트랙, 키) | S–M |
| F8 | done | claude | 몽타주·시퀀스 노티파이, 섹션 | S–M |
| F9 | todo | - | 머티리얼 인스턴스 파라미터(S), 머티리얼 표현식 트리(M) | S / M |
| F10 | todo | - | C++ 색인(tree-sitter)과 BP↔C++ 링크 | M |
| F11 | todo | - | Kismet 바이트코드 대체 섹션 | S / M |
| F12 | todo | - | Niagara, MetaSound, PCG, LevelSequence | M–L |

## P3 — 에디터 없는 diff·린트·CI

| ID | 상태 | 담당 | 내용 | 규모 |
|---|---|---|---|---|
| D1 | todo | - | `--diff base..head` 의미 단위 BP diff | M |
| D2 | todo | - | 도달성 기반 린트(Tick 남용, 캐스트 실패 핀, Unbind 누락 …) | M |
| D3 | todo | - | SARIF 2.1.0 출력, PR 코멘트 | S |
| D4 | todo | - | 재사용 GitHub Action(푸시마다 요약본 갱신) | S–M |

## P4 — 배포·문서

| ID | 상태 | 담당 | 내용 | 규모 |
|---|---|---|---|---|
| R1 | done | codex | 문서 정정: HF Docker 신규 생성은 PRO, 서버는 선택 사항, 개발자 모드는 Plugins 안, GPT 경로 미사용 | S |
| R2 | todo | - | Codex Cloud 레시피(환경 + AGENTS.md) 시험 | S |
| R3 | done | codex | 스킬 폴더 표준화(.agents/.claude/.github skills) | S |
| R4 | todo | - | Claude Code 플러그인 마켓플레이스 | S |
| R5 | done | codex | MCP 서버 정리(소수 도구, FTS5 검색, 응답 상한) | S–M |
| R6 | todo | - | MCP Registry 등록(stdio 패키지) | S |
| V1 | todo | - | 사람 PC에서 UE Shed / UAsset Translator와 실측 비교 (이 세션에선 실행 불가) | S |
| V2 | done | codex | 실제 Windows PowerShell 5.1에서 격리된 설치 가이드 E2E·Python 선택·native stderr/종료 코드·특수문자 LFS 다운로드 검증 | S |

## 분석·리뷰

| ID | 상태 | 담당 | 내용 | 규모 |
|---|---|---|---|---|
| A1 | done | codex | 현재 코드 구조·실행 흐름·회귀 상태와 정확성/운영 위험 분석 — REVIEW-2026-10-27.md | S |
| A2 | done | codex | P1: 출력 경로가 입력 프로젝트 또는 그 상위이면 삭제하지 않고 거부; 기존 출력 교체 범위도 검증(D-006) | S |
| A3 | done | codex | P1: 파서 최초 설치를 부모 프로세스에서 완료하고 워커 시작; 공유 캐시 설치 동시성 보호(D-007) | S |
| A4 | done | codex | P1: 맵의 레벨 BP·외부 액터·속성 실패와 그래프 렌더 실패를 summary/INDEX로 전파; 회귀에서 검사(D-008, v1.6.0) | S–M |
| A5 | done | codex | P2: MCP 작업 제한시간을 stdout 수신과 독립적으로 집행; 프로세스 종료·수거 보장 | S |
| A6 | done | codex | P2: MCP 캐시 키에 도구/출력 버전과 충돌 없는 프로젝트 식별자 포함 | S |

## 후속 — 작업 중 발견 (2026-10-27, claude)

| ID | 상태 | 담당 | 내용 | 규모 |
|---|---|---|---|---|
| X1 | todo | - | 바이트 열거형 배열이 숫자로 나옴(`Stashinfo = [7, 0, …]`, Array<E_Crates>) → 같은 저장소의 UserDefinedEnum 문서로 이름 매핑 | S |
| X2 | todo | - | PDA_PlayerData 변수 표 `Map<E_Crates, None>` — Map 값 타입 디코딩 확인 | S |
| X3 | todo | - | UE 4.25 저장 몽타주(AR 스파이더) 섹션 이름이 `0`, `1` — 실제 이름인지 FName 해석 문제인지 확인 | S |
| X4 | done | codex | 기존 클론 재사용 + `--ref`가 `git checkout ref`로 빠진 큰 blob을 lazy fetch → T2의 materialize 재사용 | S |
| X5 | todo | - | 함수 MetaData(툴팁·카테고리·CallInEditor) 표시 | S |
| X6 | todo | - | 맵 배치 인스턴스의 변수·태그 오버라이드가 요약본에 나오는지 확인(AR LeverBP KeyCard → GameplayTags "미사용" 오판 가능) | S–M |
| X7 | todo | - | InputAction 에셋 자체의 트리거·모디파이어(IA 단위 설정) 표시 | S |
| X8 | todo | - | 위젯 Property bindings 출력 실데이터 검증(테스트 3개 저장소엔 바인딩 없음) — 바인딩 쓰는 공개 저장소로 확인 | S |
| X9 | todo | - | AnimSequence 노티파이(시퀀스는 크고 LFS 한도에 걸리기 쉬움 → 헤더/노티파이만 읽는 방법 검토) | M |

