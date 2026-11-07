# P6 Semantic Reference 필드 매트릭스

## 읽는 법

아래 23행은 P5 Native Oracle에 있던 semantic reference 전부다. graph/node object path와 node GUID로 exact join한 뒤 원본 package tagged fields, binary reader projection, Native loaded-editor target을 비교했다.

`저장 P/N/G/S`는 `MemberParent/MemberName/MemberGuid/bSelfContext`의 tag 상태다. `Y`는 원본 package에 저장됨, `-`는 tag가 없음, `n/a`는 FMemberReference가 아닌 reference다. `원래→수정`은 해당 reference가 만든 unavailable observation 수다.

진단 코드는 다음과 같다.

- `S` — member record가 partial이라는 집계 진단, 분류 A
- `G` — saved `MemberGuid` tag 없음, 분류 A
- `B` — saved `bSelfContext` tag 없음, 분류 A
- `O` — exact saved parent가 있는데 owner를 거부한 비교기 진단, 분류 D, 수정됨
- `D` — `SelectedFunctionName`에 owner identity가 없음, 분류 F

## 노드별 전수 매트릭스

| # | Graph / node / GUID | Node class | 종류·원본 필드 | 저장 P/N/G/S 및 값 | Reader → Native loaded target | 미확정 코드 (원래→수정) |
|---:|---|---|---|---|---|---|
| 1 | `OnPlayerHealthChanged` / `K2Node_CallFunction_2` / `E6663D62410CA54D3BDCC9B891CBFF8C` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/Engine.KismetMathLibrary:Divide_DoubleDouble` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 2 | `OnPlayerHealthChanged` / `K2Node_VariableGet_3` / `0C050D51450C516ED15F65B10BD2E527` | `K2Node_VariableGet` | variable · `VariableReference` | `-/Y/Y/Y`; `PulseHealthAnim`, GUID `A015A793F29239C3BAE38923D9E2A5FD`, self true | saved self/name/GUID → widget skeleton `PulseHealthAnim` | `S` → `S` (1→1) |
| 3 | `OnPlayerHealthChanged` / `K2Node_CallFunction_6` / `21919DA9460B3FA7FC16E6B3F864A1D5` | `K2Node_CallFunction` | function · `FunctionReference` | `-/Y/-/Y`; `PlayAnimation`, self true | self/name, GUID unknown → resolved `/Script/UMG.UserWidget:PlayAnimation`, loaded GUID zero | `S,G` → `S,G` (2→2) |
| 4 | `OnPlayerHealthChanged` / `K2Node_VariableGet_4` / `0B7493824FAED55E5B0C38A18315DDC5` | `K2Node_VariableGet` | variable · `VariableReference` | `-/Y/Y/Y`; `HealthText`, GUID `474A2B0850B938809F33CDFF7C3D86C2`, self true | saved self/name/GUID → widget skeleton `HealthText` | `S` → `S` (1→1) |
| 5 | `OnPlayerHealthChanged` / `K2Node_CallFunction_3` / `87A76436429340F5B6786696AF792CF3` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/UMG.TextBlock:SetText` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 6 | `OnPlayerHealthChanged` / `K2Node_CallFunction_7` / `74EA207843B3E6CA4F813992B417FD0A` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/Engine.KismetTextLibrary:Conv_DoubleToText` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 7 | `OnPlayerHealthChanged` / `K2Node_CallFunction_12` / `D2C19C9C4738F1F12C950F9C6964CC24` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/Engine.KismetMathLibrary:NotEqual_DoubleDouble` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 8 | `OnPlayerHealthChanged` / `K2Node_VariableGet_5` / `99B1E09A48C4B3CD780CF0B2017E082C` | `K2Node_VariableGet` | variable · `VariableReference` | `-/Y/Y/Y`; `HealthBar`, GUID `83E6A9CF41623F1EA6E1FB9FA495E202`, self true | saved self/name/GUID → widget skeleton `HealthBar` | `S` → `S` (1→1) |
| 9 | `OnPlayerHealthChanged` / `K2Node_CallFunction_0` / `0FC3F7664C0A713595DE9CB305A8FAE1` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/UMG.ProgressBar:SetPercent` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 10 | `OnPlayerHealthChanged` / `K2Node_CallFunction_1` / `D719B62C4087DF11D3D6C3BDFD0A5190` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/ActionRoguelike.RogueActionComponent:K2_GetAttribute` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 11 | `EventGraph` / `K2Node_CallFunction_4` / `F29176DF492584F07F7768BF8A98A049` | `K2Node_CallFunction` | function · `FunctionReference` | `-/Y/-/Y`; `GetOwningPlayer`, self true | self/name, GUID unknown → resolved `/Script/UMG.Widget:GetOwningPlayer`, loaded GUID zero | `S,G` → `S,G` (2→2) |
| 12 | `EventGraph` / `K2Node_CustomEvent_2` / `15DE2AD142BA933BF39F8EB9FACE3117` | `K2Node_CustomEvent` | custom event · `CustomFunctionName` | n/a; `OnPossessedPawnChanged_Event` | 같은 loaded name | 없음 (0→0) |
| 13 | `EventGraph` / `K2Node_AssignDelegate_2` / `694C6CC845B2663B987C4AA14DF13AAA` | `K2Node_AssignDelegate` | delegate · `DelegateReference` | `Y/Y/-/-`; `/Script/Engine.Controller.OnPossessedPawnChanged` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 14 | `EventGraph` / `K2Node_CallFunction_1` / `2B41F7E644B8170A5FF6F29A1EA988E4` | `K2Node_CallFunction` | function · `FunctionReference` | `-/Y/Y/Y`; `OnPossessedPawnChanged_Event`, GUID `15DE2AD142BA933BF39F8EB9FACE3117`, self true | saved self/name/GUID → widget skeleton custom event | `S` → `S` (1→1) |
| 15 | `EventGraph` / `K2Node_CallFunction_5` / `E06B8E344F6633756BFB5CB8C7BE8921` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/Engine.Controller:K2_GetPawn` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 16 | `EventGraph` / `K2Node_CallFunction_2` / `314062034A8E178E5A2548B750431771` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/ActionRoguelike.RogueGameplayFunctionLibrary:GetActionComponentFromActor` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 17 | `EventGraph` / `K2Node_Event_1` / `CBC67BF24923920D7460A291C171123D` | `K2Node_Event` | event · `EventReference` | `Y/Y/-/-`; `/Script/UMG.UserWidget:Construct` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 18 | `EventGraph` / `K2Node_MacroInstance_0` / `A55CCA7D46CD43FCAB629F810258B2BA` | `K2Node_MacroInstance` | macro · `MacroGraphReference` | n/a; saved `MacroGraph`, `GraphBlueprint`, `GraphGuid` | exact StandardMacros `IsValid` graph path 일치 | 없음 (0→0) |
| 19 | `EventGraph` / `K2Node_MacroInstance_1` / `7CCD1C9F4C7DF1A3D9E1AA9FB9946E30` | `K2Node_MacroInstance` | macro · `MacroGraphReference` | n/a; saved `MacroGraph`, `GraphBlueprint`, `GraphGuid` | exact StandardMacros `IsValid` graph path 일치 | 없음 (0→0) |
| 20 | `EventGraph` / `K2Node_CallFunction_10` / `C10A988D4CA399E48E7C97A429CB2B7E` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/ActionRoguelike.RogueGameplayFunctionLibrary:GetActionComponentFromActor` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 21 | `EventGraph` / `K2Node_CallFunction_6` / `D09914E349C9EDE5E271EE8523C795BC` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/ActionRoguelike.RogueActionComponent:RemoveDynamicAttributeListener` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |
| 22 | `EventGraph` / `K2Node_CreateDelegate_1` / `04917BEB42ABCA3E5329F0965FC59528` | `K2Node_CreateDelegate` | delegate function · `SelectedFunctionName` | n/a; `OnPlayerHealthChanged` | name 일치, owner identity 없음 | `D` → `D` (1→1) |
| 23 | `EventGraph` / `K2Node_CallFunction_7` / `489BDEDA405B4E1669EE6DBA1B27CC32` | `K2Node_CallFunction` | function · `FunctionReference` | `Y/Y/-/-`; `/Script/ActionRoguelike.RogueActionComponent:AddDynamicAttributeListener` | exact parent/name → 같은 owner/member, GUID zero, self false | `S,G,B,O` → `S,G,B` (4→3) |

## 합계 검산

| 진단 | 원래 | 수정 후 | 분류 |
|---|---:|---:|---|
| `S` aggregate partial status | 19 | 19 | A |
| `G` saved GUID absent | 15 | 15 | A |
| `B` saved self-context absent | 13 | 13 | A |
| `O` exact parent owner rejected | 13 | 0 | D, 수정 |
| `D` selected function owner unavailable | 1 | 1 | F |
| 합계 | **61** | **48** | |

13개 external reference에서 owner 비교는 mode와 object path 두 값을 추가로 확인하므로 checked observation은 26개 늘었다. 원래 확인된 85개를 제거하거나 비교 범위를 줄이지 않았다.

## 필드별 저장/로드 의미

| 필드 | 이 package의 저장 관측 | Native loaded-editor 관측 | 판정 |
|---|---|---|---|
| `MemberParent` | external 13개에 exact package reference; self 6개에는 tag 없음 | external 13개 exact class path, self는 null parent와 effective/resolved owner | exact saved parent는 검증 가능. self의 parent 부재를 외부 owner로 추측하지 않음 |
| `MemberName` | member 19개 모두 저장 | 19개 모두 같은 loaded name | 19개 모두 일치 |
| `MemberGuid` | nonzero 4개 저장, 15개 tag 없음 | 저장 4개와 일치; 생략 15개는 zero GUID | 4개 검증, 15개 unknown 유지 |
| `bSelfContext` | self 6개에 true 저장, external 13개 tag 없음 | self 6개 true, external 13개 false | true 6개 검증, false 13개는 loaded 관측일 뿐 saved value로 합성하지 않음 |
| `FunctionReference` | 14개 | 14개 loaded reference | 위 행별 owner/name/GUID/self 규칙으로 비교 |
| `VariableReference` | 3개 | 3개 loaded reference | name/nonzero GUID/self true 일치 |
| `EventReference` | 1개 | 1개 loaded reference | exact external parent/name 일치; GUID/self tag 부재 유지 |
| `DelegateReference` | 1개 | 1개 loaded reference | exact external parent/name 일치; GUID/self tag 부재 유지 |
| `MacroGraphReference` | 2개 exact `MacroGraph` object reference | 2개 exact loaded macro graph path | 2개 complete comparison |
| `SelectedFunctionName` | 1개 name만 저장 | 같은 name, owner 미제공 | name equality만으로 target match 처리하지 않음 |

원본 package field는 `scripts/graph_ir.py:member_reference()`가 해석하는 동일한 tagged property에서 직접 확인했다. Native 값은 `RepoReaderOracleLibrary.cpp:WriteLoadedMemberReference()`의 Unreal reflection 관측이다. 비교 사유는 `compare_editor_oracle.py:_reader_semantic_reference()`, `_native_semantic_reference()`, `_semantic_owner()`에서 생성된다.
