# GridInventory 핵심 기능과 함수

## 상태 표기

- `IMPLEMENTED`: 저장 exec/data 연결로 본문을 확인했다.
- `PARTIAL`: 일부 단계만 있고 완전한 기능 흐름은 없다.
- `NOT_IMPLEMENTED`: 이름 있는 함수가 있으나 연결된 본문이 없다.
- `NOT_FOUND`: 전체 함수·이벤트 목록과 그래프 검색에서 발견하지 못했다.

## A. 아이템 추가

### 1. 월드/테스트 아이템을 InventoryComponent에 추가

```text
BP_FirstPersonPlayerController.EventGraph [F Pressed]
  → GetDataTableRowNames(DT_ItemInstance)
  → Array_Random
  → GetDataTableRow
  → BFL_Util.GetInventoryComp
  → AC_InventoryComponent.PickUpItem
```

`PickUpItem(Target: ST_ItemInstance)`은 `Target.ItemCategory`를 switch하고 `NewEnumerator5`(`Collectible`)에서 `PickUpedItmes`에 `Array_Add`한다. 다만 `Array_Add.NewItem`은 입력 Target과 연결되지 않고 기본 `ST_InventoryItems` 상태다. 그래서 함수 이름과 exec flow는 구현돼 있지만 저장 데이터 반영은 `PARTIAL`로 분류한다.

장비 카테고리 처리를 암시하는 `GetEquipmentComp`, `GetEquippedIArmor`, `GetEquippedIContainer` pure node가 있으나 결과가 소비되지 않는다.

### 2. UI runtime 목록에 추가하고 그리기

```text
WBP_Viewprot_v1.Button_Add*.OnClicked
  → DT_ItemDefinition에서 random ST_ItemDefinitionRow
  → NearItem/ChestRigItem/BagItem.Collectible Array_Add
  → WBP_GridLayout.DrawItems
```

Stash와 ChestRig 경로는 방금 변경한 같은 구조체를 `DrawItems`에 넘긴다. Bag 경로는 `BagItem.Collectible`을 변경하고도 `ChestRigItem`을 넘기는 저장 연결이다.

### 3. 빈 공간 탐색과 배치

실제 연결된 주 경로는 다음과 같다.

```text
WBP_GridLayout.DrawItems(NearItem)
  → ClearSlots
  → for each NearItem.Collectible
    → for each WBP_GridSlot
      → WBP_GridSlot.GetCellState
      → BFL_GridSystemUtil.GetCanPlaceIndexs
        → CompareIntPointGreater
        → 후보 시작 인덱스 생성
        → GetItemFootprintIndices
        → 점유 bool 검사
      → Success이면 WBP_GridSlot.DrawCells
```

`GetCanPlaceIndexs`가 첫 번째 배치 가능한 footprint를 반환하고, `DrawCells`가 해당 cell의 색과 `bIsPlaceItem=true`를 설정한 뒤 `WBP_Tempslot`을 만든다. 이 경로는 `IMPLEMENTED`다. 아이템의 top-left/occupied indices를 영속 구조체에 쓰는 연결은 없다.

### 대안/끊긴 배치 경로

- `CanPlaceSlot`: 일부 연결된 구현과 큰 disconnected chain이 함께 존재한다.
- `CheckPlaceItem`: 연결된 본문은 `GetCanPlaceIndexs` 호출·반환뿐이고 이전 loop 구현은 disconnected다.
- `GetPlaceSlotIndex`: 호출되는 위치가 있지만 현재 주 배치 경로에는 `GetItemFootprintIndices`가 사용된다. loop bound가 모두 `ItemSize.Y`인 저장 연결을 확인했다.

## B. 아이템 삭제

| 요구 단계 | 상태 | 근거 |
|---|---|---|
| `RemoveItem` | NOT_FOUND | 64개 함수 목록과 semantic refs에 없음 |
| 저장 배열에서 제거 | NOT_FOUND | item 배열 대상 Array_Remove 계열 호출 없음 |
| 점유 셀 해제 | PARTIAL | `WBP_GridSlot.ClearCells`가 모든 cell을 false로 만들 뿐 특정 item 삭제가 아님 |
| Widget 제거 | PARTIAL | `ClearLayout`이 slot Widget 전체를 RemoveFromParent |
| 삭제 실패 조건 | NOT_FOUND | 관련 branch 없음 |

## C. 아이템 이동과 Drag & Drop

| 단계 | 상태 | 실제 함수 |
|---|---|---|
| drag 시작 감지 | IMPLEMENTED | `WBP_Tempslot.OnMouseButtonDown` |
| drag operation/visual 생성 | IMPLEMENTED | `WBP_Tempslot.OnDragDetected` |
| payload 데이터 | PARTIAL | `BP_DragDrop.NewVar: ST_ItemDefinitionRow`; generic `Payload` pin은 unconnected |
| OnDragOver | NOT_FOUND | 함수/이벤트 없음 |
| OnDrop | NOT_FOUND | 함수/이벤트 없음 |
| 원래 점유 셀 해제 | NOT_FOUND | drag 경로와 `ClearCells` 연결 없음 |
| 새 위치 계산·확정 | NOT_FOUND | drop 좌표를 placement 함수에 전달하는 연결 없음 |
| 원래 데이터 배열 갱신 | NOT_FOUND | 저장 구조체 write-back 없음 |

따라서 이 저장 커밋에서 drag visual 생성까지만 구현돼 있다.

## D. 아이템 스왑

- `AC_EquipmentComponent.SwapEquipItem`: 함수 entry만 있고 `(no logic connected)`.
- grid item swap 함수: `NOT_FOUND`.
- 충돌 대상 탐색, 두 좌표 교환, 실패 rollback: `NOT_FOUND`.

## E. 그리드 표시

### Layout 구성

- `DrawLayout(RowName)`: `DT_GridLayoutData`의 `LayoutSections`를 읽어 `WBP_GridSlot` 생성, `SlotList` 추가, GridPanel row/column/span 설정.
- `DrawLayout_Preview(Array)`: 전달된 slot info로 같은 표시.
- `DrawOneSlotLayout(GridSize)`: 기존 slot 제거 후 하나 생성.
- `InitGrid`: design/background cell을 `MaxGrid` 크기로 생성하고 Collapsed 처리.
- `ToMatrix`: `Row=Target.Y*2+HalfRow`, `Column=Target.X*2+HalfColumn`.

### Slot과 Cell 구성

- `WBP_GridSlot.InitSlot`: `GridDimensions.Y × GridDimensions.X` 중첩 loop, `WBP_GridCell` 생성, `Cells` 추가, row/column 배치.
- `SetSize`: UI setting의 CellSize와 grid dimensions를 곱해 SizeBox 설정.
- `GetCellState`: cell 순서대로 `bIsPlaceItem` bool 배열 생성.
- `DrawCells`: footprint index마다 brush color와 점유 bool 설정; 첫 index로 row/column을 계산하고 item Widget span 설정.
- `ClearCells`: 모든 cell brush 초기화 호출과 점유 false.

## F. 장비 및 컨테이너

### 확인된 구조

- `AC_EquipmentComponent`는 `BI_Equipment_C`를 구현한다.
- armor: `EquippedHelmat`, `EquippedVest` (`ST_ArmorItemInstance`).
- container: `EquippedChestRig`, `EquippedChestBackpack` (`ST_ContainerItemInstance`).
- `GetEquippedIArmor`: Helmet/Armor category일 때 select 결과 반환.
- `GetEquippedIContainer`: ChestRig/Backpack category일 때 select 결과 반환.
- `ST_ContainerItemInstance.GridSlots`는 layout 설명 배열이며, 실제 item occupancy 배열은 아니다.

### 미구현/미확정

- `EquipItem`에는 입력이 없고 `UpdateEquipment` interface 호출 하나만 있다.
- `UnEquipItem`, `SwapEquipItem` 본문은 비어 있다.
- `UpdateEquipment` 구현 target은 현재 자산에서 확인되지 않는다.
- `InventoryComponent`의 item을 equipment 필드에 쓰는 variable set이 없다.
- 장비 내부 grid와 `WBP_GridLayout`을 데이터 모델로 동기화하는 write-back은 발견되지 않았다.

## 함수별 탐색 우선순위

1. `WBP_GridLayout.DrawItems` — 현재 배치 orchestration과 disconnected legacy chain이 함께 있다.
2. `BFL_GridSystemUtil.GetCanPlaceIndexs` — 실제 빈 공간 탐색.
3. `BFL_GridSystemUtil.GetItemFootprintIndices` — row-major footprint 생성.
4. `WBP_GridSlot.DrawCells` — 점유와 Widget 표시가 만나는 지점.
5. `AC_InventoryComponent.PickUpItem` — 입력 item 미연결 문제.
6. `WBP_Viewprot_v1.EventGraph` — runtime 목록 source와 Bag/ChestRig 연결.
7. `WBP_Tempslot.OnDragDetected` — 미완성 drag/drop의 구현 경계.
