# ue-repo-reader

언리얼 프로젝트 **깃 주소(또는 로컬 폴더)** 만 주면, AI가 블루프린트까지 포함해 프로젝트 전체를 읽을 수 있는 텍스트 요약본(digest)을 만드는 스킬입니다.
**언리얼 에디터를 켜지 않고, 엔진 설치도 필요 없습니다.** 블루프린트는 바이너리 `.uasset`을 직접 디코딩해서 실행 흐름 의사코드로 바꿉니다.

Claude Code와 Codex가 같은 `SKILL.md` 형식을 쓰기 때문에 둘 다에서 그대로 동작합니다.

자동 정답 대조를 만드는 개발자는 [그래프 IR의 범위·식별자·미확정 처리](docs/GRAPH_IR.md)를 참고하세요.

## 쓰는 방법

| 어디서 | 방법 |
|---|---|
| **ChatGPT 데스크톱 앱의 로컬 작업 / Codex** | 스킬로 내 PC에서 분석. **서버 불필요**. 설치: [docs/CODEX_SETUP.ko.md](docs/CODEX_SETUP.ko.md) |
| **ChatGPT 웹의 커스텀 MCP 연결** (선택 사항) | MCP 서버 실행 → **Plugins**에 연결. 계정·워크스페이스 권한 및 호스팅 조건: [docs/CHATGPT.ko.md](docs/CHATGPT.ko.md) |
| **Claude 채팅** | Claude 계정 스킬(`ue-repo-reader`) 사용, 또는 같은 MCP 서버를 커스텀 커넥터로 연결 |
| **Claude Code / Codex CLI** (PC) | 이 폴더를 스킬로 설치(아래) |

```
ue-repo-reader/
├─ scripts/            분석 도구 본체 (ue_repo_digest.py, bp/data/map_reader.py)
├─ server/             MCP 서버 (ChatGPT·Claude 채팅용), run_local.bat
├─ chatgpt-plugin/     ChatGPT 플러그인 패키지 (plugin.json, skills/, mcp.json)
├─ deploy/huggingface/ HF Docker Space 설정 (신규 CPU Basic 생성에 PRO 등 구독 필요)
├─ Dockerfile          일반 컨테이너 호스팅용
└─ SKILL.md            Claude Code / Codex 스킬
```

## 설치

| 도구 | 개인 설치 | 프로젝트 설치 |
|---|---|---|
| Codex · ChatGPT 데스크톱 앱의 로컬 스킬 | `~/.agents/skills/ue-repo-reader/` | `<프로젝트>/.agents/skills/ue-repo-reader/` |
| Claude Code | `~/.claude/skills/ue-repo-reader/` | `<프로젝트>/.claude/skills/ue-repo-reader/` |
| GitHub Copilot | `~/.agents/skills/ue-repo-reader/` | `<프로젝트>/.github/skills/ue-repo-reader/` |

저장소 루트의 `SKILL.md`와 `scripts/`가 원본입니다. 다음 명령은 필요한 파일만 표준 폴더에 복사합니다.

```bash
python scripts/install_skill.py --client codex --user
python scripts/install_skill.py --client claude --project "D:/Work/MyGame"
python scripts/install_skill.py --client copilot --project "D:/Work/MyGame"
```

원하는 도구·범위의 명령 하나를 선택하세요. 설치할 프로젝트 폴더는 미리 있어야 하며, 기존 스킬 폴더는 덮어쓰지 않습니다.
복사 설치본은 스냅샷이므로 갱신하려면 기존 폴더를 다른 곳으로 옮긴 후 다시 설치합니다.
자주 업데이트한다면 위 설치 위치에 이 저장소 전체를 `git clone`하고 `git -C "<설치 위치>" pull`로 갱신해도 됩니다.
Windows의 `~`는 `%USERPROFILE%`입니다. Python 선택은 [Windows 설치 가이드](docs/CODEX_SETUP.ko.md)를 참고하세요.

Copilot의 프로젝트 스킬은 `.agents/skills`와 `.claude/skills`에서도 탐색됩니다. Codex와 함께 쓰는 프로젝트는
`--client codex --project "<프로젝트>"`로 한 벌만 설치하면 됩니다. 같은 범위의 여러 위치에 중복 설치하지 마세요.
개인 스킬은 해당 컴퓨터의 로컬 도구용이며, 클라우드 실행 환경의 설치 여부는 별도로 확인합니다.
경로 기준(2026-10-27): [OpenAI Docs](https://learn.chatgpt.com/docs/build-skills),
[Claude Code](https://code.claude.com/docs/en/skills), [GitHub Copilot](https://docs.github.com/en/copilot/concepts/customizations/agent-skills).

로컬 스킬은 `SKILL.md`와 `scripts/`가 같은 폴더에 있어야 합니다. `chatgpt-plugin/skills/`의 스킬은 원격 MCP 전용이며
이 설치 도구로 배포하지 않습니다. MCP 설정이나 사용자 설정 파일은 변경하지 않습니다.
필요한 것은 **Python 3.10+, git, git-lfs**뿐이에요(Git for Windows에는 git-lfs가 포함되어 있습니다).
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

`--workdir`의 기존 클론도 같은 선택 다운로드 규칙을 적용합니다. 재사용 시 필요한 변경 파일만 체크아웃하며
목표 커밋에서 삭제된 추적 파일은 정리합니다. 로컬·스테이징 변경이나 덮어쓸 미추적 파일이 있으면 거부하므로
분석 전용의 깨끗한 일반 클론을 사용하세요(링크된 Git worktree는 지원하지 않음). `--ref`가 없으면 기존 HEAD를 재사용합니다.

에셋별 캐시는 실제 파일 바이트의 Git blob SHA로 바뀐 BP·데이터·맵 본문만 다시 해석합니다. 분류는 작은 헤더만 병렬로 다시 읽어
미지원 아트 에셋 전체를 해시하는 비용을 피합니다. 파서·도구 버전, 콘텐츠 경로,
맵의 외부 액터 목록/내용도 함께 확인하며 실패·부분 결과는 재시도합니다. 사용처·배치·색인은 매번 새로 계산합니다.
기본 위치는 파서 캐시의 `asset-results-v1/`이며 `--asset-cache-dir <폴더>`로 옮기거나 `--no-asset-cache`로 끌 수 있습니다.
출력과 캐시는 서로 겹치면 안 됩니다. JSON/gzip 캐시는 최대 256MB/10,000개로 정리되고 손상되면 다시 해석합니다.

`--out`은 요약본 전용 폴더를 지정하세요. 새 폴더·빈 폴더 또는 기존 ue-repo-reader 요약본만 사용할 수 있습니다.
입력 저장소 자체·그 상위 경로·심볼릭 링크/정션은 거부합니다. 기존 요약본은 `digest.json`의 도구 식별자와
최상위 파일/폴더 구성을 확인한 뒤 교체하며, `blueprints/`, `data/`, `maps/`, `cpp/`, `config/`는 생성 결과 전용입니다.
별도 메모 등 다른 최상위 항목이 있거나 이전 실행이 중단되어 요약본을 식별할 수 없으면 새 출력 폴더를 지정하세요.

## 결과물

```
Project_digest/
├─ INDEX.md          ← 진입점·커버리지·PageRank 읽기 순위 (보통 약 2~4k 토큰)
├─ CATALOG.md        전체 목록·프로젝트 설정·범례·파싱 리포트
├─ blueprints/Game/…/BP_X.md   BP 하나당 파일 하나 (콘텐츠 경로 그대로)
├─ data/Game/…/DT_X.md         데이터 에셋 하나당 파일 하나
├─ maps/Game/…/L_X.md          맵 하나당 파일 하나 (레벨 BP + 배치된 액터)
├─ cpp/CLASSES.md    C++ UCLASS/USTRUCT/UENUM + 블루프린트 노출 함수·프로퍼티
└─ digest.json       위 내용 전체를 기계가 읽는 형태로
```

맵 표는 미리보기라 값당 길이와 표시 개수를 제한합니다. 전체 디코딩 값은
`digest.json`의 `maps_detail[맵 경로].actors`에 액터·루트 컴포넌트의 저장 프로퍼티로 보존합니다.
문자열·중첩 배열·구조체·맵은 생략하지 않으며, 미해석 바이트는 base64로 표시합니다.
각 기록의 `properties_status`가 `partial`이면 읽기·변환이 불완전하므로, 없는 필드의 값은 알 수 없습니다.
다른 컴포넌트의 별도 export나 저장되지 않은 클래스 기본값까지 복원하는 것은 아닙니다.

**INDEX.md**는 먼저 읽을 문서를 링크합니다. 설정된 진입점에 가중치를 주고 정적 참조·고유 이름 언급으로
PageRank를 계산합니다. 런타임 호출이나 게임플레이 중요도를 입증하는 점수는 아닙니다. 이름이 겹치면 추측하지 않습니다.
각 에셋 파일의 머리말에는 순위·해석 상태·들어오는/나가는 문서 링크가 붙습니다.
INDEX는 최대 약 9KB로 제한하며 토큰 수는 언어·토크나이저에 따라 달라집니다(작은 프로젝트는 더 짧음).

**CATALOG.md**에 보존하는 전체 정보:
- 프로젝트 정보: 엔진 버전, 모듈, 플러그인, 기본 맵·게임모드·GameInstance, 입력 설정
- 블루프린트 목록: 종류(일반/위젯/애님), 부모 클래스, 진입점(BeginPlay, 입력, 컴포넌트 이벤트…)
- **C++ ↔ BP 매핑**: 어떤 C++ 클래스를 어떤 BP가 상속하는지, 어떤 C++ 함수를 어떤 BP가 호출하는지
- 데이터 에셋 목록: 요약(행 수, 필드 수, 태스크 수 등)과 **어떤 BP·에셋이 쓰는지(Used by)**
- 파싱 리포트: 부분 디코딩, 실패, LFS 누락 항목

각 문서의 **Parse warnings**에는 속성·그래프 렌더링·레벨 BP·외부 액터의 부분 실패도 표시됩니다.
노드 `N/N`은 핀 디코딩 수치이므로 이 경고도 함께 확인해야 합니다. 레벨 BP를 읽지 못한 경우는 빈 그래프와 구분하고,
실패로 누락된 값은 클래스 기본값이라고 단정하지 않습니다. `digest.json`의 에셋별 `issues`와 `parse_status`에도 같은 상태가 저장됩니다.

데이터 에셋의 명시적 enum 배열은 같은 프로젝트의 실제 enum 값 표와 연결합니다.
예: `E_Crates::NewEnumerator10(6, display="GTIWeaponCrate")`. 저장 이름·숫자를 보존하고 이름의 숫자 값은 enum 정의에서 확인합니다.
이름 배열의 FName 인덱스를 enum 숫자로 오해하지 않습니다. 동명 enum이나 알 수 없는 값은 저장 이름·숫자를 남기고
INDEX/Parse report에 한계를 표시합니다.
enum 이름은 원시 본문 캐시를 읽은 뒤 연결하므로 enum만 변경해도 새 표시 이름이 반영됩니다.

함수 진입점에 저장된 카테고리·툴팁·CallInEditor는 그래프의 `// Function metadata` / `// Function tooltip` 주석에 표시합니다.
한글과 여러 줄 설명을 보존하며, 없는 필드는 추측하지 않습니다. `digest.json`의 BP별 `function_metadata`에는
그래프 경로·진입점 이름과 함께 같은 값을 저장합니다. 읽지 못한 메타데이터는 Parse warnings로 보고합니다.

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
