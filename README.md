# ue-repo-reader

언리얼 프로젝트 **깃 주소(또는 로컬 폴더)** 만 주면, AI가 블루프린트까지 포함해 프로젝트 전체를 읽을 수 있는 텍스트 요약본(digest)을 만드는 스킬입니다.
**언리얼 에디터를 켜지 않고, 엔진 설치도 필요 없습니다.** 블루프린트는 바이너리 `.uasset`을 직접 디코딩해서 실행 흐름 의사코드로 바꿉니다.

Claude Code와 Codex가 같은 `SKILL.md` 형식을 쓰기 때문에 둘 다에서 그대로 동작합니다.

## 쓰는 방법

| 어디서 | 방법 |
|---|---|
| **ChatGPT 데스크톱 앱 (Codex)** — Free·Plus 포함 모든 요금제 | 이 저장소를 스킬 폴더에 클론 → 주소만 주면 내 PC에서 분석. 안내: [docs/CHATGPT.ko.md](docs/CHATGPT.ko.md) 맨 앞 · Codex에게 설치 맡기기: [docs/CODEX_SETUP.ko.md](docs/CODEX_SETUP.ko.md) |
| **ChatGPT 웹 채팅** — Pro·Business·Enterprise | MCP 서버를 한 번 띄우고 플러그인으로 연결. 안내: [docs/CHATGPT.ko.md](docs/CHATGPT.ko.md) |
| **Claude 채팅** | Claude 계정 스킬(`ue-repo-reader`) 사용, 또는 같은 MCP 서버를 커스텀 커넥터로 연결 |
| **Claude Code / Codex CLI** (PC) | 이 폴더를 스킬로 설치(아래) |

```
ue-repo-reader/
├─ scripts/            분석 도구 본체 (ue_repo_digest.py, bp/data/map_reader.py)
├─ server/             MCP 서버 (ChatGPT·Claude 채팅용), run_local.bat
├─ chatgpt-plugin/     ChatGPT 플러그인 패키지 (plugin.json, skills/, mcp.json)
├─ deploy/huggingface/ 무료 호스팅용 Dockerfile + Space 설정
├─ Dockerfile          일반 컨테이너 호스팅용
└─ SKILL.md            Claude Code / Codex 스킬
```

## 설치

| 도구 | 위치 |
|---|---|
| Claude Code (개인) | `~/.claude/skills/ue-repo-reader/` |
| Claude Code (프로젝트) | `<프로젝트>/.claude/skills/ue-repo-reader/` |
| Codex · ChatGPT 데스크톱 앱 | `~/.agents/skills/ue-repo-reader/` (Windows: `%USERPROFILE%\.agents\skills\ue-repo-reader\`) |

이 폴더(`SKILL.md`, `scripts/`)를 통째로 복사하거나, 그 위치에 이 저장소를 `git clone` 하면 됩니다(업데이트는 `git pull`). 필요한 것은 **Python 3.10+, git, git-lfs**뿐이에요(Git for Windows에는 git-lfs가 포함되어 있습니다).
첫 실행 때 파서([soatori/uasset_read](https://github.com/soatori/uasset_read), 검증한 커밋으로 고정)를 `~/.cache/ue-repo-reader`에 자동으로 받습니다.

## 사용법

AI에게 그냥 이렇게 말하면 스킬이 동작합니다.

> 이 저장소 리뷰해줘: https://github.com/내계정/MySoulsLike

직접 실행할 수도 있습니다.

```bash
python scripts/ue_repo_digest.py https://github.com/owner/Project --out Project_digest
python scripts/ue_repo_digest.py D:/Work/MySoulsLike              # 로컬 체크아웃도 OK
python scripts/ue_repo_digest.py <url> --ref dev --project Chapter03/Game   # 브랜치 / 멀티 프로젝트
```

## 결과물

```
Project_digest/
├─ INDEX.md          ← AI가 가장 먼저 읽는 파일
├─ blueprints/Game/…/BP_X.md   BP 하나당 파일 하나 (콘텐츠 경로 그대로)
├─ data/Game/…/DT_X.md         데이터 에셋 하나당 파일 하나
├─ maps/Game/…/L_X.md          맵 하나당 파일 하나 (레벨 BP + 배치된 액터)
├─ cpp/CLASSES.md    C++ UCLASS/USTRUCT/UENUM + 블루프린트 노출 함수·프로퍼티
└─ digest.json       위 내용 전체를 기계가 읽는 형태로
```

**INDEX.md**에 들어가는 것:
- 프로젝트 정보: 엔진 버전, 모듈, 플러그인, 기본 맵·게임모드·GameInstance, 입력 설정
- 블루프린트 목록: 종류(일반/위젯/애님), 부모 클래스, 진입점(BeginPlay, 입력, 컴포넌트 이벤트…)
- **C++ ↔ BP 매핑**: 어떤 C++ 클래스를 어떤 BP가 상속하는지, 어떤 C++ 함수를 어떤 BP가 호출하는지
- 데이터 에셋 목록: 요약(행 수, 필드 수, 태스크 수 등)과 **어떤 BP·에셋이 쓰는지(Used by)**
- 파싱 리포트: 부분 디코딩, 실패, LFS 누락 항목

**BP 파일** 예시(ActionRoguelike의 실제 출력):

```text
on Box.OnComponentBeginOverlap(OverlappedComponent: PrimitiveComponent*, OtherActor: Actor*, ...)
  // Basic check to filter only he player and skip bots.
  cast OtherActor to RoguePlayerCharacter
    [cast ok]:
      OtherActor.GetComponentByClass(ComponentClass=RogueActionComponent).AddAction(Instigator=self, ActionClass=EffectClassToApply)
```

```text
states: Locomotion, EnterStun, Stunned, ExitStun, EnterDead
entry → Locomotion
Locomotion → EnterStun   when bStunned
Stunned → ExitStun   when !bStunned
```

컴포넌트 트리(트랜스폼 포함), 변수(타입·카테고리·Replicated/RepNotify·기본값), CDO 기본값, 이벤트 디스패처, 위젯 트리(텍스트 포함), 코멘트 박스와 노드 코멘트, 끊어진 실행 체인(죽은 코드)까지 표시됩니다.

**맵 파일**에서 읽는 것:
- 게임모드 오버라이드, 월드 파티션 여부, 스트리밍 서브레벨, 주요 월드 설정
- **레벨 블루프린트** 그래프(BP와 같은 의사코드)
- **배치된 게임플레이 액터**: 라벨, 오브젝트 이름, 클래스, 위치, 회전, **인스턴스별로 바꾼 값**(예: 같은 BP 두 개가 서로 다른 효과로 설정된 것)
- 환경 액터 요약: 스태틱·스켈레탈 메시별 개수, 라이트·포그·랜드스케이프·HLOD 등
- 월드 파티션 맵은 `__ExternalActors__`의 액터 파일을 모아 같은 목록에 합침
- 각 BP 파일 끝에 "어느 맵에 몇 개 배치됐는지(Placed in levels)"

```text
| BP_ApplyEffectZone (`BP_ApplyEffectZone_3`) | BP_ApplyEffectZone_C | (-760, -470, 120) | yaw -90 | EffectClassToApply=Effect_Stunned_C; OverheadText="" |
| BP_ApplyEffectZone2 | BP_ApplyEffectZone_C | (-450, -470, 120) | yaw -90 | EffectClassToApply=Effect_Burning_C; OverheadText="" |
```

**데이터 에셋 파일**에서 읽는 것:

| 종류 | 내용 |
|---|---|
| DataTable / CompositeDataTable | 모든 행을 표로 (행 구조체가 C++에 있으면 표시) |
| UserDefinedStruct | 필드 이름·타입·기본값·툴팁 |
| UserDefinedEnum | 값·열거자·표시 이름 |
| StringTable | 네임스페이스와 키 → 문자열 |
| Behavior Tree | 셀렉터/시퀀스 트리, 데코레이터 조건, 서비스, 태스크 인자(블랙보드 키, 대기 시간, EQS 쿼리…) |
| Blackboard | 키·타입·BaseClass |
| StateTree | 상태 계층(태스크·전이·진입 조건 개수, 링크된 트리) |
| EQS | 제너레이터와 테스트 설정 |
| Input Mapping Context / Input Action | 액션 ↔ 키 ↔ 모디파이어 표 |
| Curve | 키 값 |
| 프로젝트 C++ 타입의 DataAsset | 저장된 속성 전체(중첩 구조체·하위 오브젝트 펼침) |

```text
| Row | MonsterId | Weight | SpawnCost | KillReward |
| MinionRanged | Monsters:Monster_MinionRanged | 3 | 15 | 20 |
| MinionRanged_Elite | Monsters:Monster_MinionRanged_Elite | 1 | 20 | 100 |
```

```text
Selector
  ⚙ service DefaultFocus(BlackboardKey=bb:TargetActor)
  ◆ if Cooldown(CoolDownTime=15)
  ◆ if RogueBTDecorator_CheckHealth "Is low Health?"(FlowAbortMode=LowerPriority)
  Sequence "Flee & Heal Sequence"
    - RunEQSQuery "Find Hiding Spot"(… QueryTemplate=Query_FindHidingSpot …, BlackboardKey=bb:MoveToLocation)
    - MoveTo "Move To Cover"(BlackboardKey=bb:MoveToLocation)
```

## 검증 결과

- **UE 5.8 실제 프로젝트**(ExtractionGame, 에셋 3,412개, 5.3~5.8.3에서 저장된 파일 혼재): 블루프린트 79개 **노드 7,311개 100%**, 데이터 에셋 33개, 맵 6개 전부 성공, 약 40초

- [tomlooman/ActionRoguelike](https://github.com/tomlooman/ActionRoguelike) (UE 5.6, 에셋 1,764개): 블루프린트 69개 **그래프 노드 100% 디코딩**, 데이터 에셋 38개 전부 성공, 전체 약 10초
  - UE 4.25 / 4.26 / 5.1 / 5.3에서 저장된 채 남아 있는 에셋도 전부 포함
- UE 5.7 포맷 에셋 459개(OpenBPX 테스트 픽스처): 노드 1,590개 100%
- [MarcelKrawczyk/UE5-character-input-framework](https://github.com/MarcelKrawczyk/UE5-character-input-framework) (**UE 5.7.2**, 월드 파티션): 외부 액터 138개를 맵에 합쳐 읽음, BP·입력 매핑 포함 전부 성공, 약 5초
- UE 5.6/5.7 데이터 에셋 픽스처 94개(DataTable·구조체·열거형·StringTable): 전부 성공. 픽스처에 딸린 정답 JSON과 대조했고, "수정 전/후" 픽스처에서는 수정한 칸만 정확히 바뀌어 나오는 것까지 확인
- Git LFS 저장소: 작은 `.uasset`만 골라 받고 텍스처·메시는 건너뜀. 공백·대괄호가 들어간 경로도 확인

## 원리와 제가 고친 부분

`uasset_read`는 UE 5.7 포맷만 가정하고 있어서, 구버전·신버전에서 저장된 에셋은 핀 정보가 통째로 깨졌습니다. `bp_reader.py`가 런타임에 다음을 보정합니다.
1. UE 5.4 이전 포맷에는 export 테이블에 `ScriptSerializationEndOffset`이 없어서, 태그 속성의 끝(`None` 종료자)을 직접 찾아 핀 배열 위치를 계산합니다.
2. 엔진 버전마다 있고 없는 핀 필드(`SourceIndex`, `bSerializeAsSinglePrecisionFloat`, `bIsUObjectWrapper`)의 조합을 파일마다 탐지합니다.
3. **UE 5.8**은 FText(기본 히스토리) 뒤에 int32 하나를 더 저장합니다. 파일 헤더의 저장 엔진 버전이 5.8 이상이면 읽고, 결과가 불완전하면 반대 설정도 시도합니다.
4. Map 타입 핀의 값 타입(`FEdGraphTerminalType`)에 있는 bool 3개를 파서가 건너뛰지 않아서 이후가 어긋나던 버그를 수정했습니다(모든 버전 공통).

데이터 에셋은 `data_reader.py`의 자체 태그 속성 리더가 읽습니다. uasset_read가 놓치는 부분 세 가지를 보완해요.
- 구조체 배열(스키마를 모르는 구조체, 구버전의 내부 태그 포함) → 필드·행·블랙보드 키·BT 자식 목록이 여기서 나옵니다. 같은 리더로 UE4 BP의 변수 선언도 복원해요.
- DataTable 행 데이터 → 파서는 행 이름만 세고 내용을 버려서, 행마다 태그 스트림을 직접 읽습니다.
- 네이티브 페이로드(StringTable 항목, 열거형 값, 커브 키) → 바이너리 레이아웃을 직접 디코딩합니다.

그 외 렌더링 단계에서:
- 핀 GUID는 노드 안에서만 고유하므로 (소유 노드, GUID) 쌍으로 연결을 해석합니다. 초기에 GUID만 썼을 때 `Yaw` 자리에 `Pitch`가 들어가는 오류가 있었어요.
- 하위 그래프 중복 목록을 제거하고, 전이 규칙을 상태 머신 줄에 인라인합니다.

## 한계

- 저장된 에셋을 정적으로 읽는 것이라 런타임 값은 알 수 없습니다. 노드 이름은 내부 함수 이름(`K2_GetActorLocation`)이라 에디터 표시 이름과 다를 수 있어요.
- UE 5.8에서 바뀐 FText 포맷은 파일 헤더의 저장 엔진 버전을 보고 자동 처리합니다. 더 새 엔진에서 포맷이 또 바뀌면 일부만 디코딩될 수 있고, 파일마다 `노드 N/M`과 파싱 리포트에 정확히 표시됩니다.
- 데이터 에셋은 저장된 값만 보입니다(비어 있는 필드는 구조체/클래스 기본값). StateTree의 태스크·조건 인스턴스 값과 Control Rig 그래프는 아직 읽지 않습니다.
- 머티리얼, 나이아가라, 메타사운드, 애니메이션, 메시, 텍스처는 개수만 셉니다.
- 맵의 액터 위치는 루트 컴포넌트 기준(부착된 액터는 부모 기준 상대 위치)입니다.
- "Used by"는 이름 참조로 찾기 때문에 C++ 코드나 ini 설정에서만 참조하는 경우는 잡히지 않습니다.
- LFS 객체를 받을 권한이 없는 환경에서는 LFS에 올라간 BP를 읽을 수 없습니다(리포트에 원인이 표시됨). 본인 PC의 Claude Code나 Codex에서 돌리면 평소 쓰는 git 인증으로 받습니다.
