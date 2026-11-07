# Codex Cloud 분석 준비 상태

2026-11-07 · Linux Cloud · ue-repo-reader 1.18.0

## 현재 실행 가능한 기능

- Python 3.10+와 Git/Git LFS만으로 UE 5.7/5.8 저장 패키지의 Blueprint, map, data asset digest 생성
- graph/declaration IR, saved graph membership, 새 semantic references 생성
- 단위·고정 프로젝트·독립 캡처 재생 회귀
- 선택 MCP HTTP 서버와 검색/cache smoke
- C++ 헤더의 제한된 리플렉션 표면 색인

Unreal Engine 설치, 프로젝트 컴파일, 에디터 실행, Clang AST 분석은 현재 Cloud 검증 범위에 없다.

## 설치

```bash
cd /workspace/ue-repo-reader
export UE_REPO_READER_CACHE=/workspace/shared/ue-repo-reader-cache
mkdir -p "$UE_REPO_READER_CACHE"
python -c "import sys; sys.path.insert(0, 'scripts'); import bp_reader; bp_reader.ensure_uasset_read()"
python -m pip install --target tests/.cache/server-deps --upgrade -r server/requirements.txt
```

기본 홈의 `.cache`가 읽기 전용인 관리형 환경이 있으므로 cache 변수를 명시한다. 고정 parser commit과 TLS 검증을
유지하며 원본 에셋·Oracle JSON을 수정하지 않는다.

## 재사용 가능한 분석·검증 절차

```bash
cd /workspace/ue-repo-reader
export UE_REPO_READER_CACHE=/workspace/shared/ue-repo-reader-cache

# 빠른 로컬 검사
python tests/unit_tests.py

# 전체 회귀: 외부 에셋, Native Oracle replay, eg/ar/ves/bt
python tests/regress.py

# 선택 MCP 실제 HTTP 검사
python tests/server_smoke.py --deps tests/.cache/server-deps
```

실제 프로젝트 분석은 다음 형태다.

```bash
python scripts/ue_repo_digest.py /path/to/clean/project-clone --out /path/to/new_digest
```

입력은 깨끗한 전용 clone을 사용한다. 분석기가 local/staged 변경을 감지하면 중단하며 reset으로 덮어쓰지 않는다.
이번 검증에서는 이전 회귀가 LFS pointer를 materialize한 캐시 clone을 보존 이름으로 옮기고 새 고정 clone을 사용했다.

## 엔진 없이 검증된 범위

- package hash와 고정 source commit
- node/pin identity, type/default/flags, saved link의 기존 Native Oracle replay
- saved declaration subset과 graph membership 증거 재생
- 잘못된 owner, 중복 이름/식별자, 누락/invalid reference, partial propagation 합성 반례
- digest 수량·필수 문자열·known issue exact multiset

이 범위는 저장된 정적 관측과 기존 독립 캡처의 재생이다. 새 semantic references는 실제 패키지에서 생성했지만
새 에디터 캡처와 직접 비교하지 않았으므로 부분 검증이다.

## Windows Unreal Editor가 필요한 검증

다음은 UE 5.7과 특히 5.8 Windows 호스트에서 수행해야 한다.

1. `tools/RepoReaderOracle`에 FMemberReference와 macro graph identity의 native capture를 추가한다.
2. 기존 정답 JSON을 덮어쓰지 않고 새 출력 폴더에 캡처한다.
3. package SHA-256 전후, dirty=false, 엔진 버전과 source commit을 확인한다.
4. `tools/compare_editor_oracle.py`의 새 profile로 binary saved identity와 native loaded identity를 비교한다.
5. saved/load 불일치는 reader 오류로 단정하지 말고 엔진 load fixup 여부를 별도로 기록한다.

기존 절차:

```powershell
python tests/editor_native_smoke.py --engine "C:/Program Files/Epic Games/UE_5.8" --workdir "D:/checks/oracle-58"
python tests/editor_native_smoke.py --engine "C:/Program Files/Epic Games/UE_5.7" --workdir "D:/checks/oracle-57"
```

## 준비 상태 판정

| 기능 | 상태 |
|---|---|
| Cloud digest 생성 | 준비됨 |
| 기존 단위/외부 에셋/4개 프로젝트/Native Oracle replay | 검증 완료 |
| MCP HTTP 6도구와 캐시·재시작 | 검증 완료 |
| 새 saved semantic reference 보존 | 부분 검증 |
| 새 native member-reference 비교 | 미실행, Windows Editor 필요 |
| 정밀 C++ AST/call graph | 미구현 |
| Grid-based-Inventory-System 적용 | 이번 범위 밖, 수정하지 않음 |
