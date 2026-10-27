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
| H6 | todo | - | 회귀 세트 확장(버그 재현 픽스처, UE Shed/AssetTools 픽스처 검토) | S–M |
| H7 | todo | - | Windows 실기 점검: LFS `--include` 이스케이프, `<PY>` 자리표시자, PowerShell 5.1 stderr | S |
| T1 | done | claude | `digest.json`을 "전부 읽기" 대상에서 제외, 큰 DataTable 상한 | S |
| T2 | doing | claude | 부분 클론(`--filter=blob:limit` 또는 `blob:none` 후 필요한 것만) — 콜드 실행의 85~90%가 클론 | M |
| T3 | todo | - | 에셋별 blob SHA 캐시(바뀐 것만 재파싱) | S–M |
| T4 | todo | - | INDEX 순위 지도(PageRank, 2~4k 토큰), 파일별 머리말 | M |

## P2 — 기능 격차

| ID | 상태 | 담당 | 내용 | 규모 |
|---|---|---|---|---|
| F1 | done | claude | GameplayTags 레지스트리(ini/DataTable/C++)와 사용처 | S |
| F2 | done | claude | 입력 교차 검사(트리거·모디파이어 값, "BP가 쓰는데 IMC에 없는 IA" 경고) | S |
| F3 | todo | - | 변수·함수 플래그(ExposeOnSpawn, Private, SaveGame, RPC, Pure/Const …) | S |
| F4 | todo | - | BP 클래스 DataAsset 인스턴스 저장값 | S |
| F5 | todo | - | GAS 요약(GE·GA) | S |
| F6 | todo | - | 위젯 슬롯·바인딩·애니메이션 | S / M |
| F7 | todo | - | 타임라인 템플릿(길이, 트랙, 키) | S–M |
| F8 | todo | - | 몽타주·시퀀스 노티파이, 섹션 | S–M |
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
| R1 | todo | - | 문서 정정: HF Docker 신규 생성은 PRO, 서버는 선택 사항, 개발자 모드는 Plugins 안, GPT 경로 미사용 | S |
| R2 | todo | - | Codex Cloud 레시피(환경 + AGENTS.md) 시험 | S |
| R3 | todo | - | 스킬 폴더 표준화(.agents/.claude/.github skills) | S |
| R4 | todo | - | Claude Code 플러그인 마켓플레이스 | S |
| R5 | todo | - | MCP 서버 정리(소수 도구, FTS5 검색, 응답 상한) | S–M |
| R6 | todo | - | MCP Registry 등록(stdio 패키지) | S |
| V1 | todo | - | 사람 PC에서 UE Shed / UAsset Translator와 실측 비교 (이 세션에선 실행 불가) | S |
