# GridInventory 프로젝트 정밀 분석 개요

## 분석 기준

- 게임 저장소: `https://github.com/immigration2000/GridInventory`
- 게임 커밋: `f9131d8bc078e25849f7c93f20a4d77f653e6c3d`
- 프로젝트: `GridInventory.uproject`, `EngineAssociation="5.7"`
- 분석기 저장소 커밋: `bf79221df2397d9f2e58b978887c2a7beee6c1fd`
- 분석기: `ue-repo-reader 1.20.0`
- 실행일: 2026-11-08 KST
- 분석 clone: `/workspace/grid-readonly-clone`
- 원시 결과: `/workspace/grid-analysis`

분석은 Unreal Editor 없이 저장된 패키지를 직접 읽었다. `verified`는 저장 패키지 안의 정확한 노드·핀 식별자 또는 연결을 뜻한다. 실제 런타임 호출 여부나 게임 의미까지 검증했다는 뜻은 아니다.

## 프로젝트 규모

| 항목 | 수 | 산정 근거 |
|---|---:|---|
| Git 트리의 `.uasset` | 816 | `git ls-tree` 확장자 집계 |
| Git 트리의 `.umap` | 1 | `git ls-tree` 확장자 집계 |
| 일반 `.uasset` | 752 | external actor/object 경로 제외 |
| World Partition external actor | 63 | `Content/**/__ExternalActors__/**/*.uasset` |
| external object | 1 | `Content/**/__ExternalObjects__/**/*.uasset` |
| 실제 scanner 입력 패키지 | 814 | 일반 UAsset 749 + external actor 63 + external object 1 + map 1 |
| 크기 필터로 materialize하지 않은 UAsset | 3 | 메시 2개, 텍스처 1개; 모두 분석 핵심 Blueprint가 아님 |
| 분류된 일반 UAsset | 749 | `CATALOG.md` 자산 통계 |
| 심층 렌더 Blueprint | 30 | `digest.json.blueprints` |
| 심층 렌더 데이터 에셋 | 25 | `digest.json.data_assets` |
| 심층 렌더 맵 | 1 | `digest.json.maps_detail` |
| Widget Blueprint | 10 | 부모 `UserWidget` 집계 |
| Blueprint Function Library | 3 | 부모 `BlueprintFunctionLibrary` 집계 |
| 이름 있는 함수 그래프 | 64 | 각 Blueprint의 `functions` 합계 |
| 렌더된 실행 entry | 41 | event 24, component-bound `on` 9, input 6, custom event 2 |
| Graph IR 그래프 | 104 | `graph_ir.graphs` 합계 |
| Blueprint decoder 노드 | 1,237 / 1,250 | 각 자산의 `nodes_ok/nodes_total` 합계 |
| Graph IR 표현 노드 | 1,308 | 투영 IR의 노드 합계; decoder 수와 coverage basis가 다름 |
| 핀 | 4,409 | Graph IR의 `nodes[].pins` 합계 |
| 저장 연결 관측 | 2,800 | 출력·입력 양쪽을 각각 센 값 |
| 고유 핀 연결 | 1,400 | 2,800개 관측을 endpoint 쌍으로 정규화; 모두 정확히 2회 관측 |

Git LFS 포인터는 0개였다. 분석기는 Git의 2MB 크기 필터로 다음 아트 파일만 가져오지 않았다.

- `Content/Characters/Mannequins/Meshes/SKM_Manny_Simple.uasset`
- `Content/Characters/Mannequins/Meshes/SKM_Quinn_Simple.uasset`
- `Content/Characters/Mannequins/Textures/Manny/T_Manny_02_BN.uasset`

## 구조 요약

프로젝트의 인벤토리 구현은 하나의 완성된 영속 모델보다 두 데이터 계열과 Widget 기반 배치 프로토타입이 함께 존재하는 형태다.

1. `ST_ItemInstance` 계열은 `AC_InventoryComponent.PickUpedItmes`와 `AC_EquipmentComponent`의 장비 필드에 쓰인다.
2. `ST_ItemDefinitionRow`/`ST_RuntimeItemData` 계열은 `WBP_Viewprot_v1`과 그리드 Widget에서 임시 아이템 목록과 표시를 만든다.
3. `WBP_GridLayout`은 여러 `WBP_GridSlot`을 관리한다.
4. `WBP_GridSlot`은 `WBP_GridCell` 배열의 `bIsPlaceItem`을 점유 상태로 사용한다.
5. `BFL_GridSystemUtil.GetCanPlaceIndexs`와 `GetItemFootprintIndices`가 빈 영역 탐색과 셀 인덱스 생성을 담당한다.
6. `WBP_Tempslot`은 DragDropOperation을 만들지만 `OnDrop`/`OnDragOver` 및 원래 위치 해제·재배치 그래프는 발견되지 않았다.

## 핵심 Blueprint

| Blueprint | 경로 | 역할 | 관측 상태 |
|---|---|---|---|
| `AC_InventoryComponent` | `/Game/Blueprints/AC_InventoryComponent` | `PickUpedItmes` 배열과 `PickUpItem` | 존재, 12/12 노드 |
| `AC_EquipmentComponent` | `/Game/Blueprints/AC_EquipmentComponent` | armor/container 필드와 조회 함수 | 존재, 장착/해제/스왑 본문은 비어 있거나 인터페이스 호출만 있음 |
| `BFL_GridSystemUtil` | `/Game/Blueprints/BFL_GridSystemUtil` | 셀 배치 가능성·footprint 계산 | 존재, 209/209 노드 |
| `BFL_Util` | `/Game/Blueprints/BFL_Util` | 컴포넌트·UI 설정·색상 접근 | 존재, 38/38 노드 |
| `WBP_GridCell` | `/Game/Blueprints/UI/Grid/WBP_GridCell` | 개별 셀 점유 bool과 표시 | 존재, 26/26 노드 |
| `WBP_GridSlot` | `/Game/Blueprints/UI/Grid/WBP_GridSlot` | 셀 배열 생성·점유·아이템 Widget 표시 | 존재, 88/88 노드 |
| `WBP_GridLayout` | `/Game/Blueprints/UI/Grid/WBP_GridLayout` | 슬롯 목록, 레이아웃, 아이템 배치 | 존재, 169/169 노드 |
| `BP_TempItem` | `/Game/Blueprints/BP_TempItem` | DataTable row 로드와 월드 텍스트 표시 | 존재, 12/12 노드 |

## 데이터 자산

25개 렌더 결과는 UserDefinedStruct 11, DataTable 4, InputAction 4, InputMappingContext 2, UserDefinedEnum 2, AnimMontage 1, `PDA_UISetting_C` 인스턴스 1개다. 인벤토리에 직접 관련된 주요 구조는 다음과 같다.

- `ST_ItemInstance`: 이름, 표시 이름, 카테고리, 크기, 무게, 레벨, 아이콘.
- `ST_InventoryItems`: `Instance`, `SlotIndex`, `TopLeftCellIndex`, `bIsRotation`.
- `ST_ItemDefinitionRow`: 표시·설명·카테고리·레벨·`GridWidth/Height`·스택·무게·아이콘·월드 메시.
- `ST_RuntimeItemData`: `Gear`, `HealthKit`, `Collectible` 배열.
- `ST_GridSlotInfo`: section size, grid position, half-row/column offset.
- `ST_ContainerItemInstance`: item instance와 grid slot 배열.
- `ST_ArmorItemInstance`: item instance와 durability 값.

## C++ 범위

저장소에는 `.cpp`와 `.h`가 0개이며 `.uproject`의 게임 모듈도 없다. 따라서 C++ 타입·함수·필드·호출 그래프는 모두 0개다. 이번 결과는 Blueprint와 데이터 패키지 분석이며, 빈 C++ 결과를 C++ 분석 성공 사례로 해석하지 않는다.

## 빠른 결론

- 실제 배치 경로는 `WBP_Viewprot_v1` → `WBP_GridLayout.DrawItems` → `WBP_GridSlot.GetCellState` → `BFL_GridSystemUtil.GetCanPlaceIndexs` → `GetItemFootprintIndices` → `WBP_GridSlot.DrawCells`이다.
- 점유 정보는 `WBP_GridCell.bIsPlaceItem` 배열에서 생성되고 UI에 반영된다.
- 배치 좌표를 영속 아이템 모델에 다시 기록하는 연결은 발견되지 않았다.
- 삭제, 이동 완료, Drop, 스왑, 실패 롤백은 `NOT_IMPLEMENTED` 또는 `NOT_FOUND`다.
- 저장 그래프에서 확인되는 데이터 연결 이상은 [정확도 보고서](GRIDINVENTORY_ACCURACY_REPORT.md)에 근거와 함께 기록했다.
