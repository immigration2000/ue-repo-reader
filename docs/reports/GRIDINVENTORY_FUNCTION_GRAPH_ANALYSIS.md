# GridInventory 핵심 함수 Graph IR 분석

## 읽는 법

각 ID는 `/workspace/grid-analysis/digest.json`의 `blueprints[asset].graph_ir`에서 그대로 보존한 값이다. `guid_raw`는 저장 바이트에서 읽은 표현을 임의로 UUID 문자열로 바꾸지 않았다. 아래 edge는 저장 pin link다. Pure node의 런타임 평가 순서는 이 연결만으로 확정하지 않는다.

## `AC_InventoryComponent.PickUpItem`

- Graph ID: `/Game/Blueprints/AC_InventoryComponent.AC_InventoryComponent.PickUpItem`
- Graph GUID raw: `3e99f13dd5768bc0714ffd695832`
- nodes/pins: 10/53
- Entry: `K2Node_FunctionEntry_0`, export 14, GUID `a3604a4bca20164ca41c061c9fc3e1bd`
- input: `Target`, output pin, `struct ST_ItemInstance`, pin GUID `e85895005cf99c4cbadc95deef397fa8`
- Result node: 없음; 반환값 없는 함수.

주요 노드:

| Node | Class | GUID raw | 저장 참조 |
|---|---|---|---|
| `K2Node_SwitchEnum_0` | K2Node_SwitchEnum | `3ba1eb6a120dfc4d9b1827f1e018ec2f` | E_ItemCategory switch |
| `K2Node_CallArrayFunction_0` | K2Node_CallArrayFunction | `1d77720c7e7b754ca434bd57a8cfefed` | `/Script/Engine.KismetArrayLibrary::Array_Add` |
| `K2Node_CallFunction_0` | K2Node_CallFunction | `a2dab96f1baf534cab99ffe00f3e2b5b` | `BFL_Util_C::GetEquipmentComp` |
| `K2Node_CallFunction_3` | K2Node_CallFunction | `d1d44fdd5647354d98099a9c9190ff59` | `AC_EquipmentComponent_C::GetEquippedIArmor` |
| `K2Node_CallFunction_2` | K2Node_CallFunction | `8a4ee542511a8140a21fd83c51309e6c` | `GetEquippedIContainer` |
| `K2Node_MacroInstance_0` | K2Node_MacroInstance | `b8cf7e0e2be0d04483eba09c8a068c9a` | exact `/Engine/...StandardMacros.IsValid` |

저장 edge:

```text
Entry.then → SwitchEnum.execute
Target.ItemCategory → SwitchEnum.Selection
SwitchEnum.NewEnumerator5 → Array_Add.execute
PickUpedItmes → Array_Add.TargetArray
GetEquipmentComp.AC_EquipmentComponent → GetEquippedIArmor.self
GetEquipmentComp.AC_EquipmentComponent → GetEquippedIContainer.self
```

`Array_Add.NewItem` 및 split members에는 edge가 없다. 저장 기본값은 빈 item instance, slot/top-left 0, rotation false다. `IsValid.exec/InputObject`도 연결되지 않는다. 의사코드의 `Array_Add(TargetArray=PickUpedItmes)` 표기와 Graph IR이 일치하며, NewItem 생략은 unknown이 아니라 실제 unconnected default다.

## `BFL_GridSystemUtil.GetCanPlaceIndexs`

- Graph ID: `/Game/Blueprints/BFL_GridSystemUtil.BFL_GridSystemUtil.GetCanPlaceIndexs`
- Graph GUID raw: `8addd1642feb88a584fc1740c297`
- nodes/pins: 50/154
- Entry: export 41, GUID `c4a98f23ac485d4e9d8a1e6d76a46659`
- inputs: `GridSize:IntPoint`, `ItemSide:IntPoint`, `NewParam:Array<bool>`, `__WorldContext:Object*`
- Result nodes:
  - too-large false: export 53, GUID `e2c49555b637a748bfab6baaa9f1ea0d`
  - success true: export 54, GUID `49c485c809aacb4bbe073aa891f62921`
  - exhausted false: export 52, GUID `e940310533d23a449209e5b2ce5d541c`
- outputs: `Success:bool`, `Startindex:Array<int>`.

Exec flow:

```text
Entry → Sequence
then_0 → CompareIntPointGreater → false이면 Result(false)
then_1 → ForLoop(0..GridSize.X*GridSize.Y-1)
  → X/Y bounds를 모두 만족하는 start index를 TempStartIndex에 추가
then_2 → ForEach TempStartIndex
  → GetItemFootprintIndices
  → ForEach footprint index
    → NewParam[index]가 true이면 bCanPlace=false
  → bCanPlace이면 Result(true, footprint)
  → 아니면 bCanPlace=true로 복구
Completed → Result(false)
```

중요 노드 GUID:

- `CompareIntPointGreater`: `72e043613f93cf41900770d52a1b7dd0`
- `GetItemFootprintIndices`: `491ef726b8010e459675c0069f058a10`
- outer ForLoop macro: `75a9bbb654e23c468751393a09e269ea`
- candidate ForEach: `237062b52dc11e4883683f75ab522eb7`
- footprint ForEach: `9328635f2b93634aa472ff2ee6f376eb`
- `bCanPlace=false` set: `fc4a7209688e4741a016e17e087e24af`
- `bCanPlace=true` reset: `d4e64525b5c30f45a94ea7a923711e5c`

세 macro reference는 StandardMacros의 `ForLoop`, `ForEachLoop`, `ForEachLoop` object path로 complete다. 함수 target 연결은 owner/name 기반 candidate다.

## `BFL_GridSystemUtil.GetItemFootprintIndices`

- Graph ID: `/Game/Blueprints/BFL_GridSystemUtil.BFL_GridSystemUtil.GetItemFootprintIndices`
- Graph GUID raw: `7d979520048f87b6c8c4b4e8c6a7`
- nodes/pins: 17/54
- Entry: export 42, GUID `aa6dac8d434993479a4bae119026a80e`
- Result: export 55, GUID `81ef88f589793a4da15f071cac01cd37`
- inputs: `StartIndex:int`, `GridSize:IntPoint`, `ItemSize:IntPoint`.
- output: `Indices:Array<int>`.

저장 exec edge:

```text
Entry → outer ForLoop
outer.LoopBody → inner ForLoop
inner.LoopBody → Array_Add(TempIndices, inner.Index)
outer.Completed → Result(TempIndices)
```

계산 pin은 inner first index에 `outer.Index * GridSize.X + StartIndex`, last index에 `first + ItemSize.X - 1`을 공급한다. outer last는 `ItemSize.Y - 1`이다. 따라서 row-major rectangle footprint를 생성한다.

주요 GUID: outer ForLoop `f17f15601ad8894fb986888da61974a2`, inner ForLoop `56184f50b3b32c4e9f3083406a953ebc`, Array_Add `6a1c491cc48ab04d9d9538d9f4ebf815`.

## `BFL_GridSystemUtil.GetPlaceSlotIndex`

- Graph ID: `/Game/Blueprints/BFL_GridSystemUtil.BFL_GridSystemUtil.GetPlaceSlotIndex`
- Graph GUID raw: `b36e012782d29030777b3920b26a`
- nodes/pins: 19/64
- Entry: export 43, GUID `5d04a617df8cab4095f02ca8d85a3831`
- Result: export 56, GUID `96edb727eb6e7545bc2099144949e656`
- output pin 이름은 저장 그대로 `Vlaue:Array<int>`.

확인된 edge:

```text
Entry.Selectindex → NowIndex set
outer ForLoop FirstIndex=1, LastIndex=ItemSize.Y
inner ForLoop FirstIndex=1, LastIndex=ItemSize.Y
inner.LoopBody → Array_Add(NewLocalVar, NowIndex) → IncrementInt(NowIndex)
inner.Completed → NowIndex = Selectindex + GridSize.X
outer.Completed → ArrayPrintString → Result(NewLocalVar)
```

outer macro GUID `1df8aa7a6a2ead4b9155f3825b447a93`, inner `e06d40cc7de5704a88a2f4d1fed0fd22`, row set `20c85f03d818e94db0314ed0e930fb7e`, add operator `030ed19c5022254daf2a53ff5ca9e095`다. 두 loop에 `ItemSize.X` 연결이 없다는 점을 의사코드와 raw pin에서 모두 확인했다.

## `WBP_GridSlot.InitSlot`

- Graph ID: `/Game/Blueprints/UI/Grid/WBP_GridSlot.WBP_GridSlot.InitSlot`
- Graph GUID raw: `6d504ef098778ac9630fe9e0f311`
- nodes/pins: 25/81
- Entry GUID: `3989231b29b7384194a3f27eef6b455a`

Exec flow는 `Sequence`의 첫 분기에서 `SetSize`, 둘째 분기에서 Y/X 중첩 ForLoop를 실행한다. `CreateWidget<WBP_GridCell_C>`에는 `GetUISetting().CellSize`와 현재 `Cells.Array_Length`가 전달된다. 반환 Widget을 `Cells`에 add한 뒤 `GridPanel.AddChildToGrid`에 outer index를 row, inner index를 column으로 전달한다.

주요 GUID: outer loop `9778f9bf6424f14b94b5ed235b91e56e`, inner loop `8a03fcbe5b8faf42a2e000c461c0ad53`, cell add `ef252d1836520e4eb95077a0e05dbe22`, AddChildToGrid `b2a252fe28bbba45b510df71816064ce`.

## `WBP_GridSlot.GetCellState`

- Graph ID: `/Game/Blueprints/UI/Grid/WBP_GridSlot.WBP_GridSlot.GetCellState`
- Graph GUID raw: `91932ab547d690972a66a0b0ff57`
- nodes/pins: 8/21
- Entry GUID: `e3ff6ff87cb146439a11f4b785fb3ebc`
- Result GUID: `728bd7e92e22af4b90e4de5d2ab142d0`
- output: 저장 이름 `CellStae:Array<bool>`.

`Cells`를 ForEach하고 각 element의 `bIsPlaceItem`을 local bool array에 add한 후 반환한다. ForEach macro GUID는 `69be9af8ee9bf84cb27da4c020a54966`, Array_Add GUID는 `c074a8ea1f1f114d91348ec1f76b2385`다.

## `WBP_GridSlot.DrawCells`

- Graph ID: `/Game/Blueprints/UI/Grid/WBP_GridSlot.WBP_GridSlot.DrawCells`
- Graph GUID raw: `5f33465b8fd7879ef1c1361b8b80`
- nodes/pins: 22/88
- Entry GUID: `387e6efef7aa3749ab5ceef1e7853918`
- inputs: `TargetCells:Array<int>`, `NewParam:ST_ItemDefinitionRow`.

Exec flow:

```text
ForEach TargetCells
  → Cells[index].SetLevel2BrushColor(NewParam.Level)
  → Cells[index].bIsPlaceItem=true
Completed
  → CreateWidget<WBP_Tempslot>(CellSize=UISetting.CellSize, St=NewParam)
  → GridPanel.AddChildToGrid(row=TargetCells[0]/GridDimensions.X,
                             column=TargetCells[0]%GridDimensions.X)
  → layer=99, row span=GridHeight, column span=GridWidth
```

주요 GUID: color call `85dab26a772c854d96461f4916ff8af4`, occupancy set `099f511a1ce37a468fc5df30f6e1ddea`, AddChildToGrid `e3b3f9df2daa174e86acfacdeb4fdc66`, SetLayer `f79bd81f172ab949bea7489e3bfe7eeb`, SetRowSpan `1e23da2588e03c43a31cb73ffd12557a`, SetColumnSpan `8769803dc35f5c47a6d117100c356b7f`.

## `WBP_GridLayout.DrawItems`

- Graph ID: `/Game/Blueprints/UI/Grid/WBP_GridLayout.WBP_GridLayout.DrawItems`
- Graph GUID raw: `181e18afdab5853622ad5adb2839`
- nodes/pins: 76/283
- Entry: export 79, GUID `d4c33d51387bf34f84fd1733b540f726`
- input: `NearItem:ST_RuntimeItemData`.

연결된 주 chain의 핵심 노드:

| Node | GUID raw | 역할 |
|---|---|---|
| `K2Node_CallFunction_8` | `bce0ee7b17b15844be2424f0583eb867` | ClearSlots |
| `K2Node_MacroInstance_8` | `9466ee98d436e74a9afaf6480913c7ea` | NearItem.Collectible ForEach |
| `K2Node_CallArrayFunction_0` | `8628ccd430df2c4b9f8b02d7f43141c4` | DrawCells local array clear |
| `K2Node_MacroInstance_9` | `ff328577fd644247b78241e006cb7ae2` | SlotList ForEachWithBreak |
| `K2Node_CallFunction_20` | `2043a6050b871b4e83dd55ce4536f8e9` | GetCellState |
| `K2Node_CallFunction_11` | `a2089faa7efe604d94e4752ae0caa91f` | GetCanPlaceIndexs |
| `K2Node_VariableSet_6` | `899f583506bf8d46aa1c77234a4e0623` | local DrawCells = Startindex |
| `K2Node_CallFunction_17` | `2467882781de0944bbad8d2f9016c744` | WBP_GridSlot.DrawCells |
| `K2Node_CallFunction_25` | `9dee8fcf6aa31146a7f1e51d73db903b` | 실패 PrintString |

`GetCellState.CellStae → GetCanPlaceIndexs.NewParam`, slot `GridDimensions → GridSize`, item `GridWidth/GridHeight → ItemSide`, `Startindex → DrawCells local → DrawCells.TargetCells` 데이터 edge를 확인했다. 성공 branch는 DrawCells를 호출하고 loop break로 이어진다.

같은 그래프에 별도 `CanPlaceSlot/GetPlaceSlotIndex` chain이 있으나 entry에서 도달하지 않는 disconnected chain으로 렌더됐다. 보고서의 주 실행 흐름에 합치지 않았다.

## `WBP_GridLayout.DrawLayout`

- Graph ID: `/Game/Blueprints/UI/Grid/WBP_GridLayout.WBP_GridLayout.DrawLayout`
- Graph GUID raw: `0c76259f157c988d9d81e68240b8`
- nodes/pins: 23/88
- Entry GUID: `156530a6d30e7248b73c339f6bfc0416`
- input: `RowName:Name`.

`ItemName=RowName → ClearLayout → GetDataTableRow(DT_GridLayoutData) → ForEach LayoutSections → CreateWidget<WBP_GridSlot> → SlotList.Array_Add → GridPanel.AddChildToGrid → SetRowSpan → SetColumnSpan` 순서다. `ToMatrix` pure output은 row/column과 span에 각각 연결된다.

주요 GUID: loop `adf811c677193c42b2cd7071b9558c6a`, ToMatrix calls `894db949a514944988972cd4a7a563d8`/`4339105adc8054449b0b88fa37ba1ef2`, Array_Add `f6010eea0a28bb458dfaf5d7220e3d52`, ClearLayout `830f05088d5eed4aab09833f15217e03`.

## `WBP_Tempslot.OnDragDetected`

- Graph ID: `/Game/Blueprints/UI/Grid/WBP_Tempslot.WBP_Tempslot.OnDragDetected`
- Graph GUID raw: `a0c6593347d6a8365ac2c5dac62e`
- nodes/pins: 7/37
- Entry GUID: `7a2f6d00bb620448b6cda6741a9af2fe`
- Result GUID: `76dcbffaaa4f634c94f1527060bcb9b1`
- result: `Operation:DragDropOperation*`.

`PrintString → CreateWidget<WBP_Tempslot> → CreateDragDropOperation<BP_DragDrop_C> → Result` exec edge가 있다. `St`는 drag visual의 `St`와 operation의 exposed `NewVar`에 연결되고, `CellSize`는 visual에 연결된다. generic `Payload`는 unconnected다. CreateWidget GUID `3cde1f9fe743d540ae861b94309f5ce8`, CreateDragDropOperation GUID `5a11e478b49ce7438fdca588c6b6b5eb`.

## `BP_TempItem.EventGraph`

- Graph ID: `/Game/Blueprints/BP_TempItem.BP_TempItem.EventGraph`
- Graph GUID raw: `c808b5b969ef86690c75c41b1ad5`
- BeginPlay GUID: `b412e58d42e634419f5674a0bd68515c`

BeginPlay의 Sequence는 첫 분기에서 `LoadItemName → GetDataTableRow(DT_ItemInstance) → Out Row set`, 둘째 분기에서 `LoadItemName → NameToText → TextRender.K2_SetText`로 이어진다. GetDataTableRow GUID `d5d52a7806b22044bf816d573d3ca711`, Out Row set GUID `286b3435eb969449be051c77320c81b4`다. ActorBeginOverlap과 Tick event node는 저장돼 있지만 exec output이 연결되지 않았다.

## 검증 한계

핵심 그래프는 모두 `graph_ir.status=complete`이고 decoder 노드도 N/N이다. complete는 decoder가 노출한 노드·핀의 투영 완전성을 뜻하며, Unreal Editor의 독립 truth와 의미적으로 대조했다는 뜻은 아니다. 함수 참조 target은 별도 Native Oracle 부재로 candidate를 유지한다.
