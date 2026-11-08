# GridInventory 정밀 분석 문서 색인

## 분석 대상

- GridInventory: `f9131d8bc078e25849f7c93f20a4d77f653e6c3d`
- ue-repo-reader: `bf79221df2397d9f2e58b978887c2a7beee6c1fd`, version 1.20.0
- 분석 결과 root: `/workspace/grid-analysis`
- 범위: 저장 Blueprint·data asset·map의 정적 분석. Unreal Editor/runtime 실행 없음.

## 문서

1. [프로젝트 개요](GRIDINVENTORY_PROJECT_OVERVIEW.md) — 저장소 규모, coverage, 핵심 구조, C++ 부재.
2. [전체 클래스 카탈로그](GRIDINVENTORY_CLASS_CATALOG.md) — Blueprint 30개의 경로·부모·interface·변수·함수·이벤트.
3. [핵심 기능과 함수](GRIDINVENTORY_CORE_FUNCTIONS.md) — 추가·삭제·이동·스왑·그리드·장비 기능의 구현 상태.
4. [함수 Graph IR 분석](GRIDINVENTORY_FUNCTION_GRAPH_ANALYSIS.md) — 핵심 함수의 graph/node GUID, entry/result, exec/data edge.
5. [데이터 흐름](GRIDINVENTORY_DATA_FLOW.md) — item 구조체, 배열, 좌표, 점유 bool, Widget 반영, write-back 경계.
6. [호출 그래프](GRIDINVENTORY_CALL_GRAPH.md) — forward/reverse 관계와 verified/candidate/unavailable 구분.
7. [정확도 보고서](GRIDINVENTORY_ACCURACY_REPORT.md) — 수치 산정, partial/unavailable, 교차 검사, 저장 연결 이상.

## 함수 질문용 빠른 찾기

| 질문 | 먼저 읽을 문서/절 |
|---|---|
| 아이템을 어디에 추가하는가? | 핵심 기능 `A. 아이템 추가`, 데이터 흐름 `pickup 흐름` |
| 빈 셀을 어떻게 찾는가? | Graph IR `GetCanPlaceIndexs`, `GetItemFootprintIndices` |
| 실제 점유 상태는 어디에 있는가? | 데이터 흐름 `점유 데이터의 생성과 저장 위치` |
| item Widget을 어디서 만드는가? | Graph IR `WBP_GridSlot.DrawCells` |
| layout row를 어떻게 그리는가? | Graph IR `WBP_GridLayout.DrawLayout` |
| drag/drop이 완성됐는가? | 핵심 기능 `C. 아이템 이동과 Drag & Drop` |
| 장비 장착/해제가 구현됐는가? | 핵심 기능 `F. 장비 및 컨테이너` |
| 누가 `DrawItems`를 호출하는가? | 호출 그래프 `주요 함수 reverse index` |
| 분석기가 놓친 자산이 있는가? | 정확도 보고서 `partial 자산`, `다운로드하지 않은 파일` |
| 저장 그래프에서 의심되는 연결은? | 정확도 보고서 `저장 그래프로 입증된 주의 항목` |

## 핵심 실제 경로

```text
WBP_Viewprot_v1 button event
  → WBP_GridLayout.DrawItems
  → WBP_GridSlot.GetCellState
  → BFL_GridSystemUtil.GetCanPlaceIndexs
  → BFL_GridSystemUtil.GetItemFootprintIndices
  → WBP_GridSlot.DrawCells
  → WBP_GridCell.bIsPlaceItem + WBP_Tempslot
```

저장 pin links는 verified지만 각 Blueprint 함수 target은 Native/UHT shared identity가 없어서 candidate다.

## 원시 결과 찾기

- 읽기 지도: `/workspace/grid-analysis/INDEX.md`
- 전체 자산 목록·parse report: `/workspace/grid-analysis/CATALOG.md`
- Blueprint 의사코드: `/workspace/grid-analysis/blueprints/`
- 구조화 Graph/Declaration IR: `/workspace/grid-analysis/digest.json`
- 통합 relation: `/workspace/grid-analysis/analysis/UNIFIED_ANALYSIS.json`
- unresolved relation: `/workspace/grid-analysis/analysis/UNRESOLVED.md`

대형 digest와 cache는 Git에 포함하지 않는다. 이 문서들은 고정 commit 분석 결과의 검토 가능한 요약만 보존한다.

## 현재 확인된 구현 경계

- 구현: 빈 영역 탐색, footprint 생성, cell 점유 표시, item Widget 생성, layout 구성, drag operation 시작.
- 부분: pickup 배열 반영, equipment 조회, 전체 clear.
- 미구현/미발견: 특정 item 삭제, drop 확정, grid 이동, swap, rollback, 영속 좌표 write-back, inventory↔grid data model 동기화.

## 다음 심화 분석 추천

1. `WBP_GridLayout.DrawItems`의 connected와 disconnected chain을 Editor에서 시각 대조.
2. `AC_InventoryComponent.PickUpItem.Array_Add.NewItem`의 실제 컴파일 경고와 runtime 값을 확인.
3. `GetPlaceSlotIndex`에 비정사각 item 입력을 넣어 `GetItemFootprintIndices`와 비교.
4. `WBP_Viewprot_v1.Button_AddBag`의 `ChestRigItem` input 연결을 Editor에서 확인.
5. `DrawItems` 반복 호출 후 GridPanel child 수를 확인해 Widget 중복 가능성을 검증.
6. DragDrop operation 수신 graph가 다른 커밋·플러그인·Level Blueprint에 존재하는지 프로젝트 범위를 확장해 조사.
