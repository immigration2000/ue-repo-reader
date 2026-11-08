# GridInventory 호출 관계와 역추적

## 정확성 계약

- `verified`: exact stored identity로 관계를 확인. 이 프로젝트에서는 주로 pin-to-pin link와 MacroGraph path다.
- `candidate`: 저장된 owner object path와 member name이 특정 프로젝트 graph를 가리키지만 공유 GUID로 독립 검증하지 못함.
- `ambiguous`: 복수 target. 이번 unified 결과는 0건.
- `unavailable`: target identity 부족 또는 engine/runtime dispatch.

Blueprint 함수 target 관계는 short name만으로 확정하지 않았다. 아래 프로젝트 함수 call edge는 모두 `candidate`다. 각 call node에서 해당 저장 FunctionReference 자체와 호출 pin은 관측됐지만 함수 graph GUID와 동일성을 증명하는 UHT/Editor identity가 없다.

## 핵심 forward graph

```text
BP_FirstPersonPlayerController.EventGraph
  ├─ candidate → BFL_Util.GetInventoryComp
  └─ candidate → AC_InventoryComponent.PickUpItem

AC_InventoryComponent.PickUpItem
  ├─ candidate → BFL_Util.GetEquipmentComp
  ├─ candidate → AC_EquipmentComponent.GetEquippedIArmor
  └─ candidate → AC_EquipmentComponent.GetEquippedIContainer

WBP_Viewprot_v1.EventGraph
  ├─ candidate → WBP_GridLayout.DrawOneSlotLayout
  ├─ candidate → WBP_GridLayout.DrawLayout
  └─ candidate → WBP_GridLayout.DrawItems

WBP_GridLayout.DrawItems
  ├─ candidate → WBP_GridLayout.ClearSlots
  ├─ candidate → WBP_GridSlot.GetCellState
  ├─ candidate → BFL_GridSystemUtil.GetCanPlaceIndexs
  ├─ candidate → WBP_GridSlot.DrawCells
  ├─ candidate → BFL_GridSystemUtil.CanPlaceSlot          [disconnected chain]
  ├─ candidate → BFL_GridSystemUtil.GetPlaceSlotIndex    [disconnected chain]
  └─ candidate → WBP_GridCell.SetBrushColor/SetLevel2BrushColor [disconnected chain]

BFL_GridSystemUtil.GetCanPlaceIndexs
  ├─ candidate → BPF_Math.CompareIntPointGreater
  └─ candidate → BFL_GridSystemUtil.GetItemFootprintIndices

WBP_GridSlot.DrawCells
  ├─ candidate → WBP_GridCell.SetLevel2BrushColor
  └─ candidate → BFL_Util.GetUISetting
```

Disconnected node에 FunctionReference가 있어도 entry에서 실행되는 forward call과 합치지 않았다.

## 프로젝트 함수 edge 목록

| Source graph | Target candidate | Status | 저장 근거 |
|---|---|---|---|
| PlayerController.EventGraph | `BFL_Util.GetInventoryComp` | candidate | exact owner path + member name, no shared graph GUID |
| PlayerController.EventGraph | `AC_InventoryComponent.PickUpItem` | candidate | same |
| Inventory.PickUpItem | `BFL_Util.GetEquipmentComp` | candidate | same; pure result 일부만 equipment getter self에 연결 |
| Inventory.PickUpItem | `Equipment.GetEquippedIArmor` | candidate | same; 2 call nodes |
| Inventory.PickUpItem | `Equipment.GetEquippedIContainer` | candidate | same |
| GridUtil.CanPlaceSlot | `BPF_Math.CompareIntPointGreater` | candidate | same |
| GridUtil.CanPlaceSlot | `GridUtil.GetPlaceSlotIndex` | candidate | same |
| GridUtil.CheckPlaceItem | `GridUtil.GetCanPlaceIndexs` | candidate | same; 연결된 주 본문 |
| GridUtil.GetCanPlaceIndexs | `BPF_Math.CompareIntPointGreater` | candidate | same |
| GridUtil.GetCanPlaceIndexs | `GridUtil.GetItemFootprintIndices` | candidate | same |
| GridUtil.GetPlaceSlotIndex | `BFL_Util.ArrayPrintString` | candidate | same |
| GridCell.EventGraph | `GridCell.SetSize` | candidate | Construct/PreConstruct shared exec target |
| GridCell.SetLevel2BrushColor | `BFL_Util.GetLevel2Color` | candidate | saved owner/name |
| GridLayout.EventGraph | `GridLayout.InitGrid` | candidate | Construct/PreConstruct shared exec target |
| GridLayout.ClearSlots | `GridSlot.ClearCells` | candidate | saved owner/name |
| GridLayout.DrawItems | `GridSlot.GetCellState` | candidate | saved owner/name + verified data pin chain |
| GridLayout.DrawItems | `GridUtil.GetCanPlaceIndexs` | candidate | saved owner/name + verified data pin chain |
| GridLayout.DrawItems | `GridSlot.DrawCells` | candidate | saved owner/name + verified exec/data chain |
| GridLayout.DrawLayout | `GridLayout.ClearLayout` | candidate | saved self-context/name |
| GridLayout.DrawLayout | `GridLayout.ToMatrix` | candidate | 2 pure calls |
| GridLayout.DrawOneSlotLayout | `GridLayout.ClearLayout/ToMatrix` | candidate | saved self-context/name |
| GridSlot.EventGraph | `GridSlot.InitSlot` | candidate | Construct exec edge |
| GridSlot.ClearCells | `GridCell.SetBrushColor` | candidate | owner/name |
| GridSlot.DrawCells | `GridCell.SetLevel2BrushColor` | candidate | owner/name + exec edge |
| GridSlot.DrawCells | `BFL_Util.GetUISetting` | candidate | owner/name + data edge |
| GridSlot.InitSlot | `GridSlot.SetSize`, `BFL_Util.GetUISetting` | candidate | owner/name |
| WBP_EquippedSection.EquippedItem | `WBP_ItemSlot.AddItem`, `GridLayout.DrawLayout` | candidate | owner/name |
| Viewport.EventGraph | `GridLayout.DrawLayout/DrawOneSlotLayout/DrawItems` | candidate | owner/name + component target data links |

## unavailable target

- `AC_EquipmentComponent.EquipItem → UpdateEquipment`: interface/override target을 현재 graph에서 찾지 못했다.
- `WBP_GridLayout.ClearLayout → RemoveFromParent`, `InitGrid → SetVisibility`: native UMG 함수이며 프로젝트 Blueprint target이 없다.
- Kismet, UMG, Engine library 함수는 저장 FunctionReference parent를 보존하지만 프로젝트 함수 reverse index target으로 만들지 않았다.

## 주요 함수 reverse index

| Target | 관측된 caller graph | 상태 | 주의 |
|---|---|---|---|
| `PickUpItem` | `BP_FirstPersonPlayerController.EventGraph` | candidate | F key path |
| `GetInventoryComp` | `BP_FirstPersonPlayerController.EventGraph` | candidate | player character cast 기반 pure 함수 |
| `GetEquipmentComp` | `AC_InventoryComponent.PickUpItem` | candidate | pure result가 장비 getter 일부에만 연결 |
| `GetEquippedIArmor` | `AC_InventoryComponent.PickUpItem` | candidate | 결과 미사용 |
| `GetEquippedIContainer` | `AC_InventoryComponent.PickUpItem` | candidate | 결과 미사용 |
| `DrawItems` | `WBP_Viewprot_v1.EventGraph` 3 call nodes | candidate | Stash/ChestRig/Bag buttons |
| `DrawLayout` | `WBP_Viewprot_v1.EventGraph`, `WBP_EquippedSection.EquippedItem` | candidate | row name source가 다름 |
| `DrawOneSlotLayout` | `WBP_Viewprot_v1.EventGraph` | candidate | stash/name tag 초기화 |
| `ClearSlots` | `WBP_GridLayout.DrawItems` | candidate | main chain |
| `GetCellState` | `WBP_GridLayout.DrawItems` | candidate | main chain |
| `GetCanPlaceIndexs` | `WBP_GridLayout.DrawItems`, `BFL_GridSystemUtil.CheckPlaceItem` | candidate | main + wrapper |
| `GetItemFootprintIndices` | `BFL_GridSystemUtil.GetCanPlaceIndexs` | candidate | main chain |
| `DrawCells` | `WBP_GridLayout.DrawItems` | candidate | success branch |
| `GetPlaceSlotIndex` | `CanPlaceSlot`, `WBP_GridLayout.DrawItems`, `WBP_GridSlot.EventGraph` | candidate | latter 두 위치의 해당 chain은 disconnected |
| `SetLevel2BrushColor` | `WBP_GridSlot.DrawCells`, `WBP_GridLayout.DrawItems` | candidate | DrawItems의 직접 call은 disconnected chain |
| `GetUISetting` | GridSlot DrawCells/InitSlot/SetSize, item slot functions | candidate | global UI DataAsset access |

## variable reverse 흐름

- `WBP_GridCell.bIsPlaceItem`
  - read: `WBP_GridSlot.GetCellState`, legacy `WBP_GridLayout.DrawItems` chain, `BFL_GridSystemUtil.CanPlaceSlot`.
  - write true: `WBP_GridSlot.DrawCells`, disconnected legacy DrawItems chain.
  - write false: `WBP_GridSlot.ClearCells`.
- `WBP_GridLayout.SlotList`
  - add: DrawLayout, DrawLayout_Preview, DrawOneSlotLayout.
  - iterate: ClearLayout, ClearSlots, DrawItems.
- `WBP_Viewprot_v1.NearItem/ChestRigItem/BagItem`
  - 각각 button handler가 collectible array에 add한다.
  - Bag handler의 DrawItems input은 ChestRigItem으로 교차 연결됐다.
- `AC_InventoryComponent.PickUpedItmes`
  - Array_Add target으로만 관측. remove/read/iterate graph는 없음.

## 전체 relation 통계

Unified IR은 3,672개 relation을 만들었다: verified 2,840, candidate 233, ambiguous 0, unavailable 599. reference kind별 주요 수치는 exec pin link 764, data pin link 2,036, Blueprint function reference 102, variable reference 105, variable use 231, MacroGraph reference 40이다. 이 수치는 연결 양끝 관측을 포함한 relation 수이며 고유 gameplay call 수가 아니다.
