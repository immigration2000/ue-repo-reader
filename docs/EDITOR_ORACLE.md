# 독립 에디터 정답 수집과 비교

Q1 도구는 에디터가 읽은 Blueprint와 바이너리 리더의 새 결과를 대조한다. 비교할 패키지의 SHA-256을 수집 전후와
비교 전후에 확인한다. 에디터에 저장하지 않은 변경이 있으면 파일 해시가 같아도 미확정으로 처리한다.
수집기는 `bp_reader`나 `uasset_read`를 사용하지 않는다. 캡처 모듈은 저장·컴파일·프로젝트 수정 API를 호출하지 않는다.

이 도구는 선택적인 개발용 검증 경로다. 레포 요약 생성은 기존처럼 Python과 Git으로 실행한다.
네이티브 정답을 새로 수집할 때만 UE 5.7+ 에디터, Python Script Plugin과 C++ 빌드 도구가 필요하다.

## 격리된 실제 에디터 검사

Windows에서 설치된 엔진 경로와 **새 출력 폴더**를 지정한다.

```powershell
python tests/editor_native_smoke.py --engine "C:/Program Files/Epic Games/UE_5.8" --workdir "D:/checks/oracle-58"
python tests/editor_native_smoke.py --engine "C:/Program Files/Epic Games/UE_5.7" --workdir "D:/checks/oracle-57"
```

검사는 임시 호스트 프로젝트를 만들고 `tools/RepoReaderOracle` 에디터 전용 모듈을 빌드한다. 해당 호스트에서 필요한
플러그인만 켜며 사용자 프로젝트·엔진 전역 설정을 바꾸지 않는다. 고정 UE Shed 에셋을 복사해 에디터로 캡처하고 새 바이너리
읽기와 비교한다. 저장하지 않은 변수도 메모리에 만들어 캡처가 미확정으로 표시되는지 검사하며, `.uasset` 파일은 저장하지 않는다.
빌드·실행 로그와 정답/비교 JSON은 출력 폴더에 남는다. 빌드 결과와 바이너리는 커밋하지 않는다.

## 프로젝트의 정답 수집

독립 검사용 프로젝트 복사본에 `tools/RepoReaderOracle`을 `Plugins/RepoReaderOracle`로 복사하고 에디터 모듈을 빌드한다.
Python Script Plugin을 활성화한 그 에디터에서 다음처럼 수집한다. 프로젝트 파일을 저장하는 작업은 수집기에 포함되지 않는다.

```python
import importlib.util
spec = importlib.util.spec_from_file_location("oracle_export", r"C:/work/ue-repo-reader/tools/export_editor_oracle.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.export_oracle(r"D:/checks/eg.json", ["/Game/DeltaForce/Blueprints/Core/BFL_Util"])
```

원하는 에셋의 정확한 `/Game/...` **패키지 경로**를 목록으로 넘긴다. `.BP_Name`이 붙은 객체 경로, 플러그인/엔진 마운트,
레벨 패키지는 이 수집기의 범위 밖이다. 선택 목록은 전체 프로젝트의 완전한 목록이라는 보증이 아니다.
출력은 `Content/` 밖의 절대 `.json` 경로여야 한다. 환경/인자 오류는 기존 결과를 교체하기 전에 거부하며 정상 수집은 원자적으로 교체한다.
패키지 로드나 개별 필드 수집 실패도 요청된 에셋의 기록과 `issues`를 남긴다. 자동 저장·자동 실패 복구는 수행하지 않는다.

## 새 바이너리 읽기와 비교

```powershell
python tools/compare_editor_oracle.py D:/checks/eg.json --project-root D:/projects/ExtractionGame --out D:/checks/compare-all.json
python tools/compare_editor_oracle.py D:/checks/eg.json --project-root D:/projects/ExtractionGame --profile graph --out D:/checks/compare-graph.json
```

기존 요약본을 실제 결과로 재사용하지 않으며 리더를 새로 실행한다. 다른 PC의 프로젝트 복사본도 같은 패키지 바이트라면 비교할 수 있다.
출력 보고서는 새 파일만 생성한다. 기존 정답/보고서는 덮어쓰지 않는다. 종료 코드 `0`은 **지정한 비교 범위**의 일치,
`1`은 불일치 또는 수집/해석 미확정, `2`는 잘못된 입력/출력 오류다.

- `all`이 기본값이다. 부모 클래스, 변수 선언, 함수 그래프, 함수 메타데이터 일부, 위젯 바인딩과 그래프/핀을 대조한다.
  바이너리에 명시되지 않았거나 리더가 노출하지 않은 값은 추정하지 않고 `unavailable`로 남긴다.
- `graph`는 노드 클래스, 전체 수집 핀의 이름/방향/타입/기본값/표시 플래그와 저장 연결만 대조한다.
  부모·변수/함수 선언·함수 메타데이터·위젯 바인딩은 비교하지 않았다고 보고서에 명시한다.

어느 범위든 빈 그래프, 레이아웃, 그래프/노드/변수 GUID, 그래프 핀의 맵 값 타입 const/weak 플래그, FText 지역화 정체성,
함수 키워드/compact title/flags와 위젯 SourcePath 전체는 현재 비교에서 제외한다. 기본값은 저장된 필드이며 유효 CDO/상속값이나
실제 실행·도달성을 검증하지 않는다. 저장 후 엔진의 로드 시 보정과 리더 오류도 차이의 원인이므로 보고서를 확인하고 원인을 구분한다.
관측값 수는 정확도 점수가 아니다.
Control Rig/RigVM 그래프는 현재 비교 어댑터의 범위 밖이며 수집 목록에 있어도 미확정으로 남긴다.
타입의 category/subcategory는 Unreal의 대소문자를 구분하지 않는 FName으로 비교한다. 원본 snapshot의 표기는 보존한다.

## 정답 형식과 식별자

스키마 `1`은 `producer="unreal-editor-native"`, 실제 `engine_version`, `project_file`, `assets`, `issues`를 가진다.
각 에셋은 `asset_path`, 프로젝트 상대 `package_file`, `sha256_before/after`, `snapshot`, `issues`를 가진다.
비교 가능한 snapshot은 `text_values="source"`, `package_dirty=false`여야 한다. FText는 에디터 문화권의 표시 문자열 대신
`FTextInspector::GetSourceString`으로 얻은 원문을 보존하며, 원문을 얻지 못한 필드는 수집 문제로 보고한다.

네이티브 snapshot에는 변수 선언, 함수 그래프 경로, 위젯 바인딩과 그래프/노드/핀의 원본 관측을 보존한다.
객체 경로의 `:` 경계는 리더의 `.` 표기와 대조할 때 한 번 변환한다. 핀 GUID는 에디터의 4개 uint32 표기를 각 워드별
little-endian 저장 바이트로 변환한다. 핀의 소유 노드 경로를 함께 사용하며 같은 GUID가 다른 노드에 있다는 이유로 연결하지 않는다.
배열 순서나 레이아웃은 비교 결과를 바꾸지 않는다. 중복 정체성은 덮어쓰지 않고 오류로 처리하며 중복 연결 관측은 유지한다.

캡처된 정답은 우리 리더 결과로 재생성하면 안 된다. 고정 외부 패키지의 출처·라이선스·해시는
[`tests/asset_fixtures.json`](../tests/asset_fixtures.json)과 [`tests/README.md`](../tests/README.md)를 참고한다.

## 저장 선언 비교 API

변수 타입·선언 기본값과 위젯 바인딩은 표시 문자열 대신 [declaration_ir](DECLARATION_IR.md)를 사용한다.
저장 태그의 부재와 명시적 빈 배열/빈 문자열/0을 구분한다. 선언의 non-map terminal은 저장되지 않아 미확정이며
실효 기본값으로 추정하지 않는다. 이전 캡처의 빈 배열과 비교하더라도 저장 태그가 없으면 검증된 빈 선언으로 세지 않는다.

기본 회귀에는 native 정답 8개(5.7/5.8 핀 정답 2개와 eg 6개)가 있다. Q13의 eg 4개는 Map 값/객체·텍스트·구조체 배열의 선언 7개를 포함하며,
Q14의 BP_Knife는 scalar FText 카테고리 원문을 추가로 검증한다. 개별 정답의 정확한 미확정 경계는 계속 고정한다.
선언 Map 값의 const/weak 플래그도 비교한다. 그래프 핀의 같은 플래그는 기존 제외 범위를 유지한다.
기존 3개 정답의 native 관측은 그대로이며, 저장되지 않은 NewVariables를 빈 배열로 간주하던 경계를 미확정 1개씩으로 정정했다.

## 반복 캡처와 저장/로드 상태 차이

`python tools/compare_native_repeats.py first-a.json fresh-a.json --out new-repeat-report.json`
은 두 native 관측을 기존 all 비교 범위로 대조한다. 정확히 같은 엔진 build/프로젝트·에셋 집합·패키지 해시,
clean 상태를 요구하며 누락/수집 실패가 하나라도 있으면 `incomplete`다. 확인된 차이는 그 상태에서도 남긴다.
`stable`은 지정된 관측 범위의 반복 일치, `changed`는 native 값의 차이이며 리더 오류나 특정 엔진 보정 호출의 증명이 아니다.
종료코드0/1/2는 stable / changed·incomplete / 잘못된 입력·출력이다. 기존 파일은 교체하지 않는다.

Q14는 동일 프로세스 2회씩·서로 다른 프로세스 2개(두 번째는 반대 로드 순서)로 문제 에셋7개를 다시 캡처했다.
프로세스 내부는73318개 관측이 같고, 새 프로세스 사이에는 숨긴 ErrorTolerance17개의 GUID만 달라져34개 차이를 보고했다.
GUID를 이름으로 맞추거나 숨겨 일치로 바꾸지 않는다. const/default2개는 원본 바이트와 안정적인 native 로드 값이 다르다.
카테고리8개와 그래프 밖 노드를 포함하던 실제 리더 오류는 수정했다. 자세한 구분과 한계는 [조사 기록](dev/Q14-LOADED-STATE-2026-10-30.md).

선택적 native smoke에 `--no-pch`를 주면 임시 플러그인의 PCH 사용을 꺼 큰 캐시 생성을 줄인다.
Q14는 실제5.8.4에서 이 방식으로 빌드했다. 프로젝트 복사본의 애니메이션 의존 에셋을 로드할 때는 AnimationData 등
원래 필요한 플러그인도 그 복사본에 활성화해야 한다. 사용자 프로젝트/엔진 전역 설정은 바꾸지 않는다.
