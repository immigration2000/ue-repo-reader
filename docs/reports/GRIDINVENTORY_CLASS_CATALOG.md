# GridInventory Blueprint 클래스 카탈로그

이 표는 `digest.json.blueprints`와 declaration/graph IR에서 얻은 전체 30개 Blueprint의 변수·함수·활성 entry 목록이다. `—`는 해당 저장 필드 또는 그래프에서 항목을 관측하지 못했다는 뜻이다. 상속 변수와 빈 이벤트는 목록에 자동 보충하지 않았다.

| Blueprint | Asset path | Parent | Interface | 저장 변수 | 함수 | 활성 이벤트·입력 | 노드 |
|---|---|---|---|---|---|---|---:|
| `BP_DragDrop` | `/Game/DeltaForce/BP_DragDrop` | DragDropOperation | — | NewVar | — | — | 0/0 |
| `BFL_GridSystemUtil` | `/Game/Blueprints/BFL_GridSystemUtil` | BlueprintFunctionLibrary | — | — | CanPlaceSlot; CheckPlaceItem; GetCanPlaceIndexs; GetItemFootprintIndices; GetPlaceSlotIndex | — | 209/209 |
| `BFL_Util` | `/Game/Blueprints/BFL_Util` | BlueprintFunctionLibrary | — | — | ArrayPrintString; GetEquipmentComp; GetInventoryComp; GetLevel2Color; GetUISetting | — | 38/38 |
| `BP_TempItem` | `/Game/Blueprints/BP_TempItem` | Actor | — | LoadItemName; Out Row | UserConstructionScript | BeginPlay | 12/12 |
| `BI_Equipment` | `/Game/Blueprints/BI_Equipment` | Interface | — | — | UpdateEquipment | — | 1/1 |
| `BPF_Math` | `/Game/Blueprints/BPF_Math` | BlueprintFunctionLibrary | — | — | CompareIntPointGreater; intpointLength | — | 13/13 |
| `AC_InventoryComponent` | `/Game/Blueprints/AC_InventoryComponent` | ActorComponent | — | PickUpedItmes | PickUpItem | — | 12/12 |
| `AC_EquipmentComponent` | `/Game/Blueprints/AC_EquipmentComponent` | ActorComponent | BI_Equipment_C | EquippedHelmat; EquippedVest; EquippedChestRig; EquippedChestBackpack | EquipItem; GetEquippedIArmor; GetEquippedIContainer; SwapEquipItem; UnEquipItem | — | 26/26 |
| `CtrlRig_FPWarp` | `/Game/FirstPerson/Anims/CtrlRig_FPWarp` | ControlRig | — | — | — | — | 11/24 partial |
| `ABP_FP_Copy` | `/Game/FirstPerson/Anims/ABP_FP_Copy` | AnimInstance | — | — | AnimGraph | — | 5/5 |
| `BP_FirstPersonCameraManager` | `/Game/FirstPerson/Blueprints/BP_FirstPersonCameraManager` | PlayerCameraManager | — | — | UserConstructionScript | — | 1/1 |
| `BP_FirstPersonPlayerController` | `/Game/FirstPerson/Blueprints/BP_FirstPersonPlayerController` | PlayerController | — | Touch Controls Widget Class; Force Touch Controls; NewVar | Should Use Touch Controls; UserConstructionScript | BeginPlay; key Tab; key F | 38/38 |
| `BP_FirstPersonGameMode` | `/Game/FirstPerson/Blueprints/BP_FirstPersonGameMode` | GameModeBase | — | — | UserConstructionScript | — | 1/1 |
| `BP_FirstPersonCharacter` | `/Game/FirstPerson/Blueprints/BP_FirstPersonCharacter` | Character | BPI_TouchInterface_C | Target Touch UI | Aim; Move; UserConstructionScript | IA_Look; IA_Move; IA_Jump; IA_MouseLook; Primary/Secondary Thumbstick; Touch Jump Start/End | 30/30 |
| `BP_JumpPad` | `/Game/LevelPrototyping/Interactable/JumpPad/BP_JumpPad` | Actor | — | Velocity; Color Target; Exclusion Tag | UserConstructionScript | ActorBeginOverlap | 21/21 |
| `BP_WobbleTarget` | `/Game/LevelPrototyping/Interactable/Target/BP_WobbleTarget` | Actor | — | — | UserConstructionScript | — | 7/7 |
| `BP_DoorFrame` | `/Game/LevelPrototyping/Interactable/Door/BP_DoorFrame` | Actor | — | Door Size; Door Frame; Door Frame Scale; Door; Closed Position; Door Detection Adjust; Door Thickness; Split Door; Door Frame Overide Material; Add Door; Door2; Closed Position_0 | Set Mesh; UserConstructionScript | BeginPlay; ActorBeginOverlap; ActorEndOverlap; Open Door; Close Door | 148/148 |
| `ABP_Unarmed` | `/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed` | AnimInstance | — | Character; MovementComponent; Velocity; GroundSpeed; Direction; ShouldMove; IsFalling | AnimGraph | BlueprintUpdateAnimation; BlueprintInitializeAnimation | 95/95 |
| `WBP_EquippedSection` | `/Game/Blueprints/UI/WBP_EquippedSection` | UserWidget | — | — | EquippedItem | — | 13/13 |
| `WBP_Viewprot_v1` | `/Game/Blueprints/UI/WBP_Viewprot_v1` | UserWidget | — | NewVar; NearItem; ChestRigItem; BagItem | — | Construct; Button_51/Button/Button_AddStash/Button_AddChestRig/Button_AddBag.OnClicked | 74/74 |
| `WBP_GridCell` | `/Game/Blueprints/UI/Grid/WBP_GridCell` | UserWidget | — | CellSize; Index; bIsPlaceItem | SetBrushColor; SetLevel2BrushColor; SetSize | PreConstruct; Construct | 26/26 |
| `WBP_GridLayout` | `/Game/Blueprints/UI/Grid/WBP_GridLayout` | UserWidget | — | PreviewData; MaxGrid; SlotList; ItemName | ClearLayout; ClearSlots; DrawItems; DrawLayout; DrawLayout_Preview; DrawOneSlotLayout; InitGrid; ToMatrix | PreConstruct; Construct | 169/169 |
| `WBP_ItemSlot` | `/Game/Blueprints/UI/Grid/WBP_ItemSlot` | UserWidget | — | bIsRotation; CachedItem | AddItem; SetSize | — | 36/36 |
| `WBP_Tempslot` | `/Game/Blueprints/UI/Grid/WBP_Tempslot` | UserWidget | — | CellSize; Index; bIsPlaceItem; St | OnDragDetected; OnMouseButtonDown; SetSize | Construct | 34/34 |
| `WBP_GridSlot` | `/Game/Blueprints/UI/Grid/WBP_GridSlot` | UserWidget | — | GridDimensions; Cells; PreView | ClearCells; DrawCells; GetCellState; InitSlot; SetSize; ToMatrix | PreConstruct; Construct | 88/88 |
| `WBP_ItemSlot1` | `/Game/Blueprints/UI/Grid/WBP_ItemSlot1` | UserWidget | — | bIsRotation; CachedItem; ST | AddItem; SetSize; ToMatrix | Construct | 43/43 |
| `PDA_UISetting` | `/Game/Blueprints/Data/Static/PDA_UISetting` | PrimaryDataAsset | — | NewVar; NewVar_0; CellSize | — | — | 0/0 |
| `UI_Thumbstick` | `/Game/Input/Touch/UI_Thumbstick` | UserWidget | — | TrackInput; Initial Touch Location; Position; Stick Input; Thumbstick Size; Invert X; Invert Y; Scale Output; Touch Target | Touch Input Check | Tick; PreConstruct | 66/66 |
| `UI_TouchSimple` | `/Game/Input/Touch/UI_TouchSimple` | UserWidget | — | In String | — | Construct; Btn_Jump.OnPressed/Released; two thumbstick events | 16/16 |
| `BPI_TouchInterface` | `/Game/Input/Touch/BPI_TouchInterface` | Interface | — | — | Primary Thumbstick; Secondary Thumbstick; Touch Jump End; Touch Jump Start | — | 4/4 |

## 인벤토리 핵심 변수의 저장 타입

| Owner | 변수 | 저장 타입 | 용도 |
|---|---|---|---|
| AC_InventoryComponent | `PickUpedItmes` | `Array<ST_InventoryItems>` | pickup 배열 |
| AC_EquipmentComponent | `EquippedHelmat`, `EquippedVest` | `ST_ArmorItemInstance` | armor 상태 |
| AC_EquipmentComponent | `EquippedChestRig`, `EquippedChestBackpack` | `ST_ContainerItemInstance` | container 상태 |
| WBP_GridCell | `CellSize`, `Index`, `bIsPlaceItem` | `IntPoint`, `int`, `bool` | 셀 크기·번호·점유 표시 |
| WBP_GridSlot | `GridDimensions`, `Cells`, `PreView` | `IntPoint`, `Array<WBP_GridCell_C*>`, `ST_ItemDefinitionRow` | slot 격자·셀·미리보기 |
| WBP_GridLayout | `PreviewData`, `MaxGrid`, `SlotList`, `ItemName` | `Array<ST_GridSlotInfo>`, `IntPoint`, `Array<WBP_GridSlot_C*>`, `Name` | layout·slot 집합 |
| WBP_Viewprot_v1 | `NearItem`, `ChestRigItem`, `BagItem` | `ST_RuntimeItemData` | UI 임시 목록 |
| WBP_Tempslot | `CellSize`, `Index`, `bIsPlaceItem`, `St` | `IntPoint`, `int`, `bool`, `ST_ItemDefinitionRow` | 표시와 drag payload |

## 기능 카테고리

### 아이템 수집·추가

- `BP_FirstPersonPlayerController.EventGraph`: F key → random `DT_ItemInstance` row → `PickUpItem`.
- `AC_InventoryComponent.PickUpItem`: collectible category에서 배열 add.
- `WBP_Viewprot_v1` button handlers: random `DT_ItemDefinition` row를 runtime list에 add.
- `WBP_GridLayout.DrawItems`: runtime collectible을 slot에 배치.
- `WBP_ItemSlot.AddItem`, `WBP_ItemSlot1.AddItem`: item 정보를 Widget에 표시.

### 공간 계산

- `BPF_Math.CompareIntPointGreater`
- `BFL_GridSystemUtil.GetCanPlaceIndexs`
- `BFL_GridSystemUtil.GetItemFootprintIndices`
- 레거시/대안 경로: `CanPlaceSlot`, `CheckPlaceItem`, `GetPlaceSlotIndex`.

### 그리드 표시

- `WBP_GridLayout.DrawLayout`, `DrawLayout_Preview`, `DrawOneSlotLayout`, `InitGrid`.
- `WBP_GridSlot.InitSlot`, `DrawCells`, `ClearCells`, `GetCellState`.
- `WBP_GridCell.SetSize`, `SetBrushColor`, `SetLevel2BrushColor`.

### Drag & Drop

- `WBP_Tempslot.OnMouseButtonDown`: left mouse drag 감지 reply.
- `WBP_Tempslot.OnDragDetected`: drag visual과 `BP_DragDrop` operation 생성.
- Drop 수신·이동 확정: `NOT_FOUND`.

### 장비

- 조회: `GetEquippedIArmor`, `GetEquippedIContainer`.
- `EquipItem`: interface `UpdateEquipment` 호출 하나.
- `SwapEquipItem`, `UnEquipItem`: `NOT_IMPLEMENTED`.

## 핵심 클래스의 직접 참조

다음은 저장 FunctionReference owner path와 member name에서 얻은 target 후보다. 함수 그래프 GUID와 같은 독립 식별자를 공유하지 않아 모두 `candidate`다.

- `BP_FirstPersonPlayerController.EventGraph` → `BFL_Util.GetInventoryComp` → `AC_InventoryComponent.PickUpItem`.
- `AC_InventoryComponent.PickUpItem` → `BFL_Util.GetEquipmentComp`, `AC_EquipmentComponent.GetEquippedIArmor/GetEquippedIContainer`.
- `WBP_Viewprot_v1.EventGraph` → `WBP_GridLayout.DrawLayout/DrawOneSlotLayout/DrawItems`.
- `WBP_GridLayout.DrawItems` → `ClearSlots`, `WBP_GridSlot.GetCellState/DrawCells`, `BFL_GridSystemUtil.GetCanPlaceIndexs`.
- `GetCanPlaceIndexs` → `BPF_Math.CompareIntPointGreater`, `GetItemFootprintIndices`.
- `WBP_GridSlot.DrawCells` → `WBP_GridCell.SetLevel2BrushColor`, `BFL_Util.GetUISetting`.

상세 forward/reverse status는 [호출 그래프](GRIDINVENTORY_CALL_GRAPH.md)에 있다.
