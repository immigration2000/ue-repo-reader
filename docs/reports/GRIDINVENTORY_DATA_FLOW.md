# GridInventory 데이터 흐름

## 데이터 모델은 두 계열로 나뉜다

### Instance/Equipment 계열

```text
DT_ItemInstance (19 rows)
  row: ST_ItemInstance
    ├─ ItemName, DisplayName
    ├─ ItemCategory, Size, Weight, Level, Icon
    └─ wrapped by
       ├─ ST_InventoryItems { Instance, SlotIndex, TopLeftCellIndex, bIsRotation }
       ├─ ST_ArmorItemInstance { Instance, MaxDurability, CurrentDurability }
       └─ ST_ContainerItemInstance { Instance, GridSlots[] }
```

- `AC_InventoryComponent.PickUpedItmes`는 `Array<ST_InventoryItems>`다.
- `AC_EquipmentComponent`는 armor/container wrapper 네 개를 직접 멤버로 가진다.
- `BP_TempItem`은 `LoadItemName`으로 `DT_ItemInstance` row를 찾아 `Out Row:ST_ItemInstance`에 저장한다.

### Grid UI runtime 계열

```text
DT_ItemDefinition (270 rows)
  row: ST_ItemDefinitionRow
    ├─ DisplayName, Description, Category, Level
    ├─ GridWidth, GridHeight, MaxStack, Weight
    └─ Icon, WorldMesh

WBP_Viewprot_v1
  ├─ NearItem: ST_RuntimeItemData
  ├─ ChestRigItem: ST_RuntimeItemData
  └─ BagItem: ST_RuntimeItemData
        └─ Collectible: Array<ST_ItemDefinitionRow>
```

두 계열 사이를 변환하거나 동기화하는 함수는 발견되지 않았다. `ST_ItemInstance.Size:IntPoint`와 `ST_ItemDefinitionRow.GridWidth/GridHeight`는 비슷한 정보를 표현하지만 동일 item identity를 증명하는 저장 참조가 없다.

## 아이템 pickup 흐름

1. PlayerController의 F 입력이 `DT_ItemInstance` row name을 무작위 선택한다.
2. `GetDataTableRow`가 `ST_ItemInstance`를 반환한다.
3. `BFL_Util.GetInventoryComp`가 player character의 `AC_InventoryComponent`를 반환하는 후보 호출이다.
4. `PickUpItem(Target)`의 switch가 `Target.ItemCategory`를 읽는다.
5. `Collectible` 분기에서 `PickUpedItmes` 배열에 add한다.

중요한 단절: 5단계의 `Array_Add.NewItem`에는 2단계의 Target이나 이를 감싼 `ST_InventoryItems`가 연결되지 않았다. 저장 기본 struct가 들어간다. 따라서 item 데이터 보존을 확인할 수 없다.

## 그리드 배치 흐름

```text
WBP_Viewprot_v1 runtime item array
  → WBP_GridLayout.DrawItems(NearItem)
  → NearItem.Collectible[]
  → each WBP_GridSlot
  → GetCellState(): Array<bool>
  → GetCanPlaceIndexs(GridSize, ItemSide, occupancy)
  → GetItemFootprintIndices(): Array<int>
  → WBP_GridSlot.DrawCells(indices, item row)
```

### 점유 데이터의 생성과 저장 위치

- 실제 점유 source of truth는 각 `WBP_GridCell.bIsPlaceItem` bool이다.
- `WBP_GridSlot.GetCellState`가 `Cells` 순서로 bool 배열을 매번 새로 만든다.
- `GetCanPlaceIndexs`는 전달된 bool 배열을 읽기만 한다.
- `DrawCells`가 footprint index에 해당하는 cell의 bool을 true로 쓴다.
- `ClearCells`는 전체 cell을 false로 쓴다.

`OccupiedCoordinates`라는 변수는 없다. footprint array는 함수 local `TempIndices`, `Startindex`, `DrawCells`로 전달되며 영속 item 구조체에 저장되지 않는다.

### 좌표 계산

- 선형 index의 row: `index / GridDimensions.X`.
- column: `index % GridDimensions.X`.
- footprint index: `StartIndex + row*GridSize.X + column`.
- layout 좌표: `ToMatrix(Target, HalfRow, HalfColumn)`이 `Y*2+HalfRow`, `X*2+HalfColumn`을 반환한다.
- `ST_InventoryItems.TopLeftCellIndex`와 `SlotIndex` 필드는 존재하지만 현재 배치 UI에서 쓰는 node/pin 연결은 발견되지 않았다.

## Widget 반영

`WBP_GridSlot.DrawCells`는 두 종류의 UI 상태를 함께 변경한다.

1. 각 footprint cell의 brush를 item level 색으로 변경하고 `bIsPlaceItem=true`.
2. `WBP_Tempslot`을 생성해 `St=ST_ItemDefinitionRow`, `CellSize=UISetting.CellSize`를 전달한다.
3. 첫 footprint index를 row/column으로 바꾸어 GridPanel에 추가한다.
4. `GridHeight/GridWidth`를 Widget row/column span에 적용한다.

`WBP_Tempslot.Construct`는 `St.Icon`을 Image에 적용하고 item 크기×cell 크기로 SizeBox를 설정한다.

## 레이아웃 데이터 흐름

```text
DT_GridLayoutData (45 rows, ST_GridLayoutRow)
  → LayoutSections: Array<ST_GridSlotInfo>
  → WBP_GridLayout.DrawLayout
  → CreateWidget<WBP_GridSlot>(GridDimensions=SectionSize)
  → SlotList Array_Add
  → GridPanel row/column/span
```

`ItemName=RowName`은 ChestRig/Backpack layout이 선택됐는지 확인하는 UI 조건에 사용된다. `ST_ContainerItemInstance.GridSlots`도 같은 `ST_GridSlotInfo` 배열을 가지지만, equipment 멤버와 현재 Widget layout 사이의 직접 write/read 연결은 없다.

## 장비 데이터 흐름

- `GetEquippedIArmor(Helmet|Armor)`는 `EquippedHelmat` 또는 `EquippedVest`를 select해 반환한다.
- `GetEquippedIContainer(ChestRig|Backpack)`는 `EquippedChestRig` 또는 `EquippedChestBackpack`을 select해 반환한다.
- 허용 category가 아닌 false branch에는 Result exec 연결이 없다.
- 네 equipment 필드에 값을 쓰는 `VariableSet`은 해당 컴포넌트 그래프에서 발견되지 않았다.
- `PickUpItem`의 equipment 조회 결과도 사용되지 않는다.

따라서 equipment 값의 생성·변경·inventory 이동은 현재 저장 그래프만으로 확인할 수 없다.

## Drag 데이터 흐름

```text
WBP_Tempslot.St
  ├─ CreateWidget<WBP_Tempslot>.St       (drag visual)
  └─ CreateDragDropOperation.NewVar      (BP_DragDrop exposed field)

WBP_Tempslot.CellSize
  └─ drag visual.CellSize
```

generic `CreateDragDropOperation.Payload`는 연결되지 않는다. `BP_DragDrop.NewVar`에 item definition row가 저장되지만, 이를 읽는 Drop handler가 없다. 원래 slot/index/bool array와 drag operation 사이의 연결도 없다.

## 중복 생성 가능 경로

저장 그래프에서 확인되는 사실은 다음과 같다.

- `DrawItems`는 시작할 때 `ClearSlots`로 cell bool을 false로 만들지만 기존 `WBP_Tempslot` child를 제거하는 호출은 없다.
- 이어서 runtime `Collectible` 전체를 다시 순회하며 `CreateWidget<WBP_Tempslot>`을 호출한다.
- `ClearSlots`는 `WBP_GridSlot.ClearCells`만 호출한다.

따라서 같은 `DrawItems`를 반복 호출하면 기존 item Widget과 새 item Widget이 함께 남을 가능성이 있다. GridPanel child lifecycle을 Editor/runtime에서 실행하지 않았으므로 실제 중복 표시 여부는 `candidate risk`로 기록한다.

## 구조체 write-back 검사

| 질문 | 확인 결과 |
|---|---|
| 변경된 item 구조체를 원본 배열에 다시 쓰는가? | 그리드 경로에는 없음. UI cell bool만 변경 |
| top-left/slot index를 기록하는가? | 필드는 있으나 연결 없음 |
| item rotation을 기록하는가? | 필드는 있으나 drag/grid 연결 없음 |
| swap 실패 시 원본 보존/rollback이 있는가? | swap 자체가 미구현 |
| 삭제 실패 시 데이터가 보존되는가? | 삭제 함수 없음 |
| UI와 실제 inventory 배열이 동기화되는가? | 두 데이터 계열 사이 연결 없음 |

## 미확정 경계

Class default, inherited/native behavior, Widget compiler가 생성한 lifecycle, runtime object identity는 저장 그래프만으로 확정하지 않았다. 위 흐름은 저장된 node/pin 연결과 struct declaration에서 직접 확인한 범위다.
