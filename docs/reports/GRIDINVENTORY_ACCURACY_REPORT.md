# GridInventory 분석 정확도 보고서

## 결과 상태

| 항목 | 결과 |
|---|---:|
| Blueprint 렌더 성공 | 30/30 |
| 데이터 에셋 렌더 성공 | 25/25 |
| 맵 렌더 성공 | 1/1 |
| 실패 | 0 |
| partial 자산 | 1 |
| Blueprint decoder 노드 | 1,237/1,250 |
| Graph IR 저장 핀 연결 관측 | 2,800 |
| 고유 연결 | 1,400 |
| Unified relations | 3,672 |
| verified | 2,840 |
| candidate | 233 |
| ambiguous | 0 |
| unavailable | 599 |
| cross-language verified | 0 |

`verified` 2,840건은 저장된 pin link와 exact MacroGraph object path 같은 정체성이다. 함수 target의 런타임 dispatch가 검증됐다는 뜻이 아니다. Blueprint 함수 참조는 저장 owner path와 이름이 있어도 함수 그래프 GUID와 공유되는 식별자가 없어 이 프로젝트에서 `verified`로 승격된 것이 0건이며, 프로젝트 내부 target은 `candidate`로 유지했다.

## 구조화 IR 교차 검사

- Graph IR: complete 30, partial 1.
- Declaration IR: partial 30. `NewVariables` 또는 일부 terminal type이 저장되지 않은 경우 unknown을 유지한다.
- semantic reference 원시 관측: 840개.
  - complete 42: MacroGraph 40, CustomEvent 2.
  - partial 798: function 404, variable 342, event 47, interface function 4, delegate 1.
- Native semantic reference validation: `unavailable`. 이 GridInventory 패키지에 대해 UE Editor oracle을 새로 실행하지 않았다.

핵심 함수의 의사코드를 Graph IR과 대조해 실제 graph ID, node GUID, entry/result pin, exec/data link가 존재하는지 확인했다. 확인 대상은 `PickUpItem`, `GetCanPlaceIndexs`, `GetItemFootprintIndices`, `GetPlaceSlotIndex`, `InitSlot`, `GetCellState`, `DrawCells`, `DrawItems`, `DrawLayout`, `OnDragDetected`, `BP_TempItem.EventGraph`, `WBP_Viewprot_v1.EventGraph`다.

## partial 자산

`/Game/FirstPerson/Anims/CtrlRig_FPWarp`만 partial이다.

- 저장 버전: UE 5.6.0
- decoder 노드: 11/24
- issue 14개
- `RigVMModel` graph object path를 얻지 못했고 ordinal 0~12의 export identity가 없다.

이 자산은 인벤토리 핵심 경로에 포함되지 않는다. 그래도 전체 프로젝트를 100% 완전 파싱했다고 보고하지 않는다.

## 다운로드하지 않은 파일

2MB를 넘는 아트 자산 3개를 Git 크기 필터로 제외했다. Blueprint·구조체·DataTable은 제외되지 않았고 LFS 실패도 0건이다. 제외 자산을 정상 파싱한 것으로 세지 않았다.

## 저장 그래프로 입증된 주의 항목

### 1. `PickUpItem`은 입력 item을 배열 원소에 연결하지 않는다

Graph `/Game/Blueprints/AC_InventoryComponent.AC_InventoryComponent.PickUpItem`에서 `K2Node_CallArrayFunction_0`의 `TargetArray`는 `PickUpedItmes`에 연결돼 있지만 `NewItem`과 split member pin은 연결이 없다. 저장 기본값은 빈 `ST_ItemInstance`, `SlotIndex=0`, `TopLeftCellIndex=0`, `bIsRotation=False`다. 입력 `Target`은 `ItemCategory` split pin만 switch selection에 연결된다.

따라서 저장 그래프 기준으로 `NewEnumerator5` 분기는 입력 item 자체가 아니라 기본 `ST_InventoryItems`를 추가한다. 이는 노드·핀 연결 관측이다. 실제 게임 실행 결과는 Editor/runtime에서 별도 확인해야 한다.

### 2. `PickUpItem`의 장비 조회 pure node 결과는 사용되지 않는다

`GetEquipmentComp`, `GetEquippedIArmor`, `GetEquippedIContainer` 노드는 존재하지만 반환 구조체가 다른 핀으로 이어지지 않는다. 한 `GetEquippedIArmor` 노드는 `self`도 연결되지 않았다. 의사코드에서 보이지 않는 pure data island를 Graph IR로 확인했다.

### 3. `GetPlaceSlotIndex`의 두 loop bound가 모두 `ItemSize.Y`다

Graph `/Game/Blueprints/BFL_GridSystemUtil.BFL_GridSystemUtil.GetPlaceSlotIndex`에서:

- outer `K2Node_MacroInstance_5.LastIndex` ← `K2Node_VariableGet_4.ItemSize_Y`
- inner `K2Node_MacroInstance_4.LastIndex` ← `K2Node_VariableGet_15.ItemSize_Y`
- inner 완료 후 `NowIndex` ← `Selectindex + GridSize.X`

폭 `ItemSize.X`가 loop bound에 연결되지 않고, 다음 행 시작값도 현재 행에서 누적되지 않는다. 이것이 의도인지 오류인지는 기획 정보 없이 확정하지 않지만, 비정사각 item footprint 계산에는 명백한 검토 대상이다. 현재 실제 배치 경로는 이 함수가 아니라 `GetCanPlaceIndexs` → `GetItemFootprintIndices`를 사용한다.

### 4. Backpack 버튼은 `BagItem`에 추가한 뒤 `ChestRigItem`을 그린다

`WBP_Viewprot_v1.EventGraph`에서 `Button_AddBag` 경로는 `BagItem.Collectible`을 `Array_Add` target으로 사용한 뒤, `K2Node_CallFunction_18.DrawItems.NearItem`에는 `K2Node_VariableGet_21.ChestRigItem`이 연결돼 있다. `BagItem`을 넘기는 연결은 없다. 이 역시 저장 data link 관측이며, UI에서 잘못된 목록을 다시 그릴 가능성이 있다.

### 5. 장비 변경 함수가 비어 있다

- `SwapEquipItem`: entry 1노드, 연결된 logic 없음.
- `UnEquipItem`: entry 1노드, 연결된 logic 없음.
- `EquipItem`: `UpdateEquipment()` 호출 하나. 해당 target은 interface/runtime dispatch라 unified relation은 unavailable이다.

## 확인하지 못한 사항

- UE 5.7/5.8 Editor가 로드한 MemberReference와 저장 패키지 값의 독립 대조.
- 런타임 pure node 평가 순서와 Widget lifecycle.
- Blueprint compiler가 끊긴/죽은 노드를 제거하거나 경고하는지.
- Drag/drop 수신 target, 이동·삭제·스왑·롤백의 외부 구현. 저장소 그래프 검색에서는 발견되지 않았다.
- 영속 저장, 네트워크 복제, save game, 서버 권한 처리.
- C++ 의미 분석. 소스 자체가 없다.

## 재현 명령

```bash
UE_REPO_READER_CACHE=/workspace/grid-reader-cache \
/tmp/p6-venv/bin/python scripts/ue_repo_digest.py \
  https://github.com/immigration2000/GridInventory \
  --ref f9131d8bc078e25849f7c93f20a4d77f653e6c3d \
  --project GridInventory.uproject \
  --workdir /workspace/grid-readonly-clone \
  --out /workspace/grid-analysis \
  --asset-cache-dir /workspace/grid-asset-cache
```

tree-sitter 의존성은 `tree-sitter==0.25.2`, `tree-sitter-cpp==0.23.4`로 고정했다. 이번 저장소에는 C++가 없어 precision parser의 의미 결과는 비어 있다.
