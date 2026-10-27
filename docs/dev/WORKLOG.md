# WORKLOG

새 항목은 **맨 위**에 추가합니다. 다음 에이전트가 이 항목만 읽고 이어받을 수 있게 씁니다.

```
## YYYY-MM-DD HH:MM KST · <claude|codex> · <TASK-ID들>
- 한 일:
- 검증: (regress 결과, 직접 확인한 것)
- 남은 일·주의:
```

---

## 2026-10-27 11:54 KST · codex · A1
- 한 일: 실행 코드 변경 없이 전체 구조와 실패 처리 분석. `REVIEW-2026-10-27.md`에 근거·재현·우선순위 기록.
  A2(입출력 경로 겹침 삭제), A3(최초 파서 설치 경합), A4(맵/그래프 부분 실패 보고), A5(MCP 무출력 timeout),
  A6(버전 누락/프로젝트 충돌 캐시 키)를 todo로 추가. H7에 regress.py cp949 출력 실패 재현 기록.
- 검증: 앱 번들 Python 3.12.14, 단위 6/6 + UTF-8/준비된 캐시로 regress 3/3 PASS.
  BP 120개·노드 3057/3057, 데이터 97개·맵 9개, 데이터/맵 실패 0.
  모킹 검사에서 입력 루트 삭제 시도·맵 실패를 INDEX가 clean으로 판정·회귀도 통과 확인.
  무출력 자식 0.53s가 0.1s timeout을 넘어 done, 프로젝트 경로 캐시 충돌도 확인. MCP 네트워크 E2E는 미실행.
- 남은 일·주의: 최초 빈 파서 캐시는 워커들의 config/shallow 잠금 충돌로 ves BP 1개 실패; warm 재실행 통과.
  첫 eg/ar checkout 255 원인은 미확정. C: 디스크가 0까지 차서 재현 파일 쓰기 실패; 테스트 클론 약 1.3GB,
  자동 승인 검토가 정리 명령을 차단해 사용자에게 직접 정리 요청. 추가 클론/다운로드 전에 여유 공간 확인.
  다음은 A2/A3 → A4·회귀 강화 권장. 기능 구현은 하지 않음.

## 2026-10-27 16:30 KST · claude · F8
- 한 일: AnimMontage를 데이터 에셋으로 렌더(`DATA_CLASSES`에 추가, `data_reader._render_montage`): 길이·블렌드 인/아웃·자동 블렌드아웃,
  슬롯별 세그먼트(재생 시퀀스, 구간, 재생 속도, 반복), 섹션과 다음 섹션 링크, 노티파이를 시간순으로
  (노티파이 객체 클래스·설정, 이름만 있으면 "event → AnimBP `AnimNotify_X`"로 AnimBP 이벤트와 연결). 중복되는 원시 프로퍼티는 생략.
- 검증: regress 3/3 PASS, F8 검사 추가(AR Primary_Attack_A_Medium_Montage).
- 남은 일·주의: AnimSequence 자체의 노티파이는 아직(시퀀스는 크고 LFS 제한에 걸리기 쉬움). UE 4.25 저장 몽타주(AR 스파이더)는 섹션 이름이
  `0`, `1`로 나오는데 실제 이름인지 FName 해석 문제인지 미확인. 다음 추천 T3(캐시) 또는 D1(커밋 간 BP diff).

## 2026-10-27 16:00 KST · claude · F7
- 한 일: BP 문서에 `## Timelines` — TimelineTemplate(TaggedReader)에서 길이(기본 5s)·autoplay·loop·replicated·LengthMode,
  float/vector/color/event 트랙별 외부 커브 에셋 이름 또는 내부 커브 키(최대 8개, `t→v`). 빈 내부 커브는 "no keys (evaluates to 0)".
- 검증: regress 3/3 PASS, F7 검사 2개(EG BP_NullPointGM TempMatching, AR BP_MusicManager).
- 남은 일·주의: 외부 커브 에셋의 키는 그 커브의 data/ 문서에 있음(링크는 안 걸었음). 다음 추천 F8(몽타주·노티파이), T3(캐시).

## 2026-10-27 15:40 KST · claude · F6
- 한 일: 위젯 BP
  - 위젯 트리에 비기본 속성(Visibility, RenderOpacity, Width/HeightOverride, ColorAndOpacity, Brush 리소스 …, `_WIDGET_KEYS`)과
    슬롯 레이아웃 `[slot Padding=…, HorizontalAlignment=…, Size=…]`(슬롯 export의 저장값 전부, 200자 상한).
  - `## Widget animations`: 애니메이션별 트랙 대상 속성(MovieScene 트랙의 PropertyBinding)과 바인딩된 위젯(AnimationBindings.WidgetName,
    TaggedReader로 읽음). `*_INST` 복사본은 건너뜀.
  - `## Property bindings`: `UWidgetBlueprint.Bindings`(ObjectName.PropertyName ← FunctionName/SourcePath). **테스트 저장소 3개에 바인딩이 하나도
    없어 실데이터 미검증** — 바인딩 쓰는 프로젝트를 만나면 출력 확인할 것.
- 검증: regress 3/3 PASS, F6 검사 추가(WBP_NavBtn).
- 남은 일·주의: 애니메이션 길이·키 값(MovieSceneFrameRange, FloatChannel)은 opaque라 미표시. 다음 추천 T3(blob SHA 캐시), F7(타임라인), F8(몽타주 노티파이).

## 2026-10-27 15:10 KST · claude · F4
- 한 일: 이 프로젝트 BP 클래스의 인스턴스로 저장된 에셋(클래스명 `<BP이름>_C`, 예: PDA_PlayerData로 만든 DA_PlayerData)을
  데이터 에셋으로 분류해 저장값을 렌더. EG에서 DA_PlayerData·DA_Stash·DA_UISetting 3개가 새로 `data/`에 생김.
- 검증: regress 3/3 PASS, F4 검사 추가.
- 남은 일·주의: 바이트 열거형 배열은 숫자로 나옴(`Stashinfo = [7, 0, …]`, 타입 Array<E_Crates>) — 열거형 이름 매핑은 교차 에셋 조회가 필요해 보류.
  PDA_PlayerData 변수 표의 `Map<E_Crates, None>` 값 타입 디코딩이 이상함(별도 확인 필요).

## 2026-10-27 14:50 KST · claude · F3
- 한 일: 함수 헤더에 `[pure, const, static, private, protected, RunOnServer, RunOnOwningClient, Multicast, Reliable]`
  (FunctionEntry `ExtraFlags`). 변수 표 Flags에 Transient·Config·SaveGame·ExposeToCinematics(PropertyFlags),
  `Condition=OwnerOnly` 등(ReplicationCondition), ExposeOnSpawn·Private(메타데이터), 툴팁이 있으면 Tooltip 열.
  메타데이터는 uasset_read가 opaque로 남기므로 `data_reader.TaggedReader`로 BP export를 다시 읽어 얻음(`_variable_metadata`).
- 검증: regress 3/3 PASS + unit, F3 검사 3개 추가. 플래그 분포: pure 9, const 8, pure+static 6, pure+const 6.
- 남은 일·주의: 함수 MetaData(툴팁·카테고리·CallInEditor)는 아직 미표시. 다음 추천 T3(blob SHA 캐시) 또는 F6(위젯 슬롯·바인딩), F4(BP 클래스 DataAsset).

## 2026-10-27 14:10 KST · claude · T2
- 추가: MCP 서버도 자체 git fetch 대신 digest 스크립트의 부분 클론을 씀(`--ref <commit> --workdir`). 로그·digest.json의 URL에서 자격 증명 제거.
  서버 E2E(mcp_client_test) 통과, 서버 작업 폴더 .git 137MB.
- 한 일:
  - 클론을 부분 클론으로: `--filter=blob:limit=2m --no-checkout --depth 1` → `ls-tree`(크기 조회 없이)와
    `rev-list --missing=print`로 빠진 큰 blob을 알아낸 뒤 필요한 경로만 `checkout --pathspec-from-file`(한 번에 일괄 fetch).
    빠진 blob 중 `.umap`과 이름이 아트 접두사(T_, SM_, SK_, M_, MI_, S_, A_ …)가 아닌 `.uasset`만 가져옴. 나머지는 parse report에 기록.
  - LFS를 `git lfs pull` 대신 LFS batch API로 직접 받음(`lfs_batch_download`, 8병렬, sha256 검증). 이유: git-lfs가 트리 전체를
    훑으면서 부분 클론의 빠진 blob을 하나씩 lazy fetch함(EG에서 53팩, +500MB). 실패·남은 것은 기존 `git lfs pull`로 대체.
    인증은 URL의 자격 증명(서버의 GITHUB_TOKEN)만 사용, `.lfsconfig`가 있으면 git-lfs에 맡김.
- 검증: 새 클론으로 regress 3/3 PASS. EG 36s→17s, .git 603MB→137MB. AR은 LFS가 없고 작은 파일이 대부분이라 46s 그대로(큰 blob 13개만 추가 fetch).
- 남은 일·주의: git 2.43에는 `GIT_NO_LAZY_FETCH`가 없어 직접 다운로드로 우회. 기존 클론 재사용 + `--ref` 경로는 여전히
  `git checkout ref`(빠진 blob lazy fetch) — 필요하면 materialize 재사용으로 바꿀 것. 비공개 저장소의 로컬 실행(자격 증명 도우미)은 git-lfs 경로로 감.

## 2026-10-27 13:10 KST · claude · F1
- 한 일: `config/GameplayTags.md` 신규 + INDEX에 GameplayTags 절.
  - 정의: `Config/DefaultGameplayTags.ini`, `Config/Tags/*.ini`, 플러그인 Config, GameplayTagTableRow DataTable,
    C++ `UE_DEFINE_GAMEPLAY_TAG(_COMMENT|_STATIC|_TYPED)`. 리다이렉트(`GameplayTagRedirects`)도.
  - 사용: 요약본 Markdown의 `TagName=X`(BP·data·map) + C++의 `RequestGameplayTag("X")`와 네이티브 태그 변수 사용.
  - 경고: 쓰였는데 어디에도 정의 안 된 태그, 옛 이름(리다이렉트)으로 저장된 태그. "정의됐는데 미사용" 목록은 보수적 표현.
- 검증: regress 3/3 PASS + unit 6/6, AR에서 22개 정의(네이티브 12)·12개 사용·리다이렉트 2개 확인. EG는 태그가 없어 절 생략.
- 남은 일·주의: 런타임 문자열로 만든 태그는 못 봄(문서에 명시). 맵 인스턴스의 태그 오버라이드가 요약본에 안 나오면 미사용으로 잡힐 수 있음
  (AR의 KeyCard.* — LeverBP 배치 인스턴스 오버라이드 확인 필요, 별도 조사 거리).

## 2026-10-27 12:40 KST · claude · F2
- 한 일:
  - IMC 표의 모디파이어·트리거를 서브오브젝트로 펼쳐 설정값 표시: `InputModifierNegate_4` → `Negate`,
    `Negate(bX=false, bZ=false)`, `Scalar(Scalar=Vector{X=50, Y=50, Z=1})`. 데이터 요약에 `mapped_actions` 추가.
  - INDEX에 "Input check (Enhanced Input)" 절: BP가 처리하는데 어떤 IMC에도 없는 액션(⚠), 매핑됐지만 BP 이벤트가 없는 액션을
    "프로퍼티에 할당됨(C++ 바인딩 추정)"과 "어디서도 참조 안 됨(C++ 확인 필요)"으로 구분.
  - 사용자 프로젝트에서 실제로 `IA_EnterBlackSite ← BP_NullPointPC` 미매핑 검출, `IA_MouseLook`은 IMC_MouseLook에만 있고 미사용.
- 검증: regress 3/3 PASS + unit 6/6, F2 검사 3개 추가.
- 남은 일·주의: InputAction 에셋 자체의 트리거·모디파이어(IA 단위 설정)는 아직 표시 안 함. 다음 추천 F1(GameplayTags), T2(부분 클론).

## 2026-10-27 12:10 KST · claude · H2 H3 H5 T1
- 한 일 (VERSION 1.5.0 — B7·B8·H5·T1로 출력 표기가 바뀐 것을 묶어 올림):
  - H2 맵 핀 세 번째 bool(`bTerminalIsUObjectWrapper`)을 `FReleaseObjectVersion >= 31`일 때만 읽음.
  - H3 핀 필드 조합을 커스텀 버전으로 먼저 결정(단정밀도 플래그 `FUE5ReleaseStreamObjectVersion >= 36`,
    UObject 래퍼 `FReleaseObjectVersion >= 31`, SourceIndex는 게이트 불명이라 둘 다 시도). 기존 탐색은 대체 경로로 유지.
    요약 정보 읽기는 `_custom_versions()`(경로별 캐시)로 통합.
  - H5 `FileVersionUE5 > 1018` 또는 알려진 커스텀 버전(FNMB 268, Release 44, UE5RS 68)보다 새 패키지면 BP·data·map 헤더와
    parse report에 경고. 값은 `bp_reader._KNOWN_*` — **새 엔진 버전을 검증하면 여기를 올릴 것**.
  - T1 `digest.json` 압축(공백 제거, AR 124KB→97KB) + "읽지 말 것" 안내(INDEX 범례, SKILL.md). 60k자 넘는 Markdown은
    `X.md` + `X.part2.md…`로 자동 분할(코드 펜스 닫고 다시 염, 끝에 이어보기 링크). 서버는 원래 .md만 나열.
  - 단위 테스트 추가: newer_format_note, combo_order, split_md.
- 검증: regress 3/3 PASS + unit 6/6. H2·H3·H5 전후 출력 동일(경고 오탐 0). 분할은 낮은 한도(10k)로 실제 요약본에 돌려 확인.
- 남은 일·주의: 다음 추천 T2(부분 클론, 콜드 실행의 85~90%가 클론) → T3(blob SHA 캐시). 기능은 F1(GameplayTags)·F2(입력 교차 검사)가 싸고 효과 큼.
  H6·H7(Windows 실기)은 사람 PC가 필요할 수 있음.

## 2026-10-27 11:30 KST · claude · B7 B8 H1
- 한 일:
  - B7 구조체 값 읽기 쉽게: `Name_N_<GUID>` 멤버명 → `Name`(BP·data·map 전부), 구조체 안 object 프로퍼티를 에셋 이름으로
    (`ObjRef` = int 하위 클래스, uasset_read의 object/class 핸들러를 감쌈, `Ctx` 생성 시 `_CUR_CTX` 설정),
    핀 기본값 `0.000000,0.000000,80.000000` → `Vector{X=0, Y=0, Z=80}`, `(TagName="A")` → `GameplayTag{TagName=A}`.
  - B8 길고(60자 초과) 두 곳 이상에서 쓰는 순수 식을 그래프 끝 `// where` 블록에 `$N`으로 한 번만 출력(순수 노드는 매번
    재평가되므로 let이 아니라 where로 표기). 여러 출력 핀을 가진 순수 호출도 대상. 범례·SKILL.md 반영.
  - H1 FText DevNotes를 FString으로 읽음, 게이트를 커스텀 버전(FNMB ≥ 260, 에디터 전용 필터 아님)으로 교체(D-005).
  - `tests/unit_tests.py` 추가(regress가 먼저 실행): DevNotes 합성 바이트, 멤버명, 핀 구조체 표기.
- 검증: regress 3/3 PASS + unit 3/3. H1 전후 출력 바이트 동일(노트가 전부 비어 있음). B7·B8 검사를 이전 출력에 돌리면 실패 확인.
- 남은 일·주의: P0 끝. 다음 추천: H2·H3(맵 핀 bool·단정밀도 플로트를 버전 게이트로), H5(5.9 대비 경고), T1(digest.json 분리).
  `$N` 별칭 기준은 `_ALIAS_MIN_LEN = 60` (bp_reader.py).

## 2026-10-27 10:40 KST · claude · B1 B2 B3 B4 B5 B6
- 한 일 (출력 포맷 v1.4.0):
  - B1 함수 결과: `return true/false` 등 값 출력(5.8은 결과 핀 default==auto_default라 기존 필터가 숨김), 헤더에 `-> Out: T`.
  - B2 애님 전환: `bAutomaticRuleBasedOnSequencePlayerInState` → `when auto (…)`, 상수 False 규칙 → `when never (…)`,
    비기본 전환 설정 `[blend Xs, priority N, on start/end/interrupt notify X]`. `state_machine()`이 이제 4-튜플(…, props).
  - B3 goto: exec 진입 수를 reroute knot 너머 실제 대상으로 셈 + 라벨 없는 goto가 남으면 강제 라벨로 한 번 재렌더.
  - B4 연결 안 된 object/class/interface 입력을 `Pin=∅`로 표시(advanced/hidden 핀 제외).
  - B5 `--ref`: 40자 SHA는 그 커밋만 fetch, 짧은 SHA는 blobless 클론으로 해석, 못 찾으면 명확한 error로 종료.
    기존 클론 재사용 시에도 `--ref`로 체크아웃(이전에는 무시됐음).
  - B6 Used by 자기 이름(같은 이름의 다른 에셋) 제외, 깨진 클래스명(`/Script/…_1476395008`) 버림,
    이름 추정 분류를 실제 클래스에 합침(`NiagaraSystem 23`), `other (by name)` → `unknown class`.
  - 범례(INDEX.md), SKILL.md, chatgpt-plugin SKILL.md에 새 표기 반영. VERSION 1.4.0.
- 검증: regress 3/3 PASS, 버그별 검사 7개 추가(fixtures.json). 같은 검사를 수정 전 출력에 돌리면 eg 11·ar 3건 실패 → 검사가 실제로 잡음.
  수정 전후 diff에서 의도하지 않은 변화 없음(라벨 번호 이동만). 짧은 SHA/없는 SHA/전체 SHA 클론 경로 직접 실행 확인.
- 남은 일·주의: P0 중 B7(구조체 기본값 원시 출력)·B8(순수 노드 반복 인라인)은 todo. 다음 추천은 H1(FText DevNotes FString).
  `Pin=∅`는 선택 입력(OwningPlayer 등)에도 붙는다 — 사실이지만 많아지면 F-계열에서 "선택 입력" 구분 검토.

## 2026-10-27 09:30 KST · claude · (규칙 도입)
- 한 일: AGENTS.md(공용 규칙 원본), CLAUDE.md, `.githooks/commit-msg`(태그 검사), docs/dev/TASKS·WORKLOG·DECISIONS,
  회귀 테스트 `tests/regress.py` + `tests/fixtures.json`(고정 커밋 3개) 추가. TASKS는 2026-10-26 조사 로드맵을 옮긴 것.
- 검증: 현재 코드로 regress 3/3 PASS (eg 49 BP·1779 노드, ar 69·1271, ves 2·7).
- 남은 일·주의: 새 기기에서는 `git config core.hooksPath .githooks` 한 번. 이어서 claude가 P0 버그(B1~B6) 수정 진행.
