# Codex 작업 지시서: ue-repo-reader 스킬 설치 (Windows)

> **사람용 사용법:** ChatGPT 데스크톱 앱 → **Codex**에서 아무 폴더나 열고, 이 파일을 첨부(또는 내용을 붙여넣기)한 뒤
> "이 문서대로 셋팅해줘"라고 말하세요.

---

## 목표

이 PC의 Codex(ChatGPT 데스크톱 앱 포함)가 **언리얼 프로젝트 깃 주소만 받아도 블루프린트·맵·데이터 에셋까지 분석**할 수
있도록 `ue-repo-reader` 스킬을 설치하고, 실제 저장소로 동작을 확인한다.

- 스킬 저장소: https://github.com/immigration2000/ue-repo-reader
- 설치 위치: `%USERPROFILE%\.agents\skills\ue-repo-reader` (Codex가 사용자 스킬을 읽는 위치)
- 필요한 것: Git(+Git LFS), Python 3.10 이상

## 규칙

- Windows PowerShell 기준이다. 단계마다 확인 명령을 실행하고, 결과를 보고 다음 단계로 넘어간다.
- **이미 설치된 것은 다시 설치하지 않는다.** 이 작업과 무관한 사용자 설정·파일은 건드리지 않는다.
- winget 설치와 git clone에 **네트워크가 필요**하다. 샌드박스 때문에 막히면 사용자에게 권한을 요청한다.
  winget 설치 중 관리자 권한(UAC) 창이 뜰 수 있으니 사용자에게 승인해 달라고 알린다.
- 실패하면 추측으로 우회하지 말고, 실행한 명령과 에러 메시지를 그대로 보여 주고 멈춘다.

## 1. 현재 상태 확인

```powershell
git --version
git lfs version
Get-Command python, py -ErrorAction SilentlyContinue | Select-Object Name, Source
if (Get-Command python -ErrorAction SilentlyContinue) { python --version }
if (Get-Command py -ErrorAction SilentlyContinue) { py -3 --version }
```

판단 기준:
- `git`, `git lfs`가 버전을 출력하면 OK.
- 파이썬은 **3.10 이상**이 필요하다. `python`의 Source가 `...\WindowsApps\python.exe`이면 Microsoft Store
  바로가기일 뿐 실제 파이썬이 아니다.
- 실제로 쓸 파이썬은 아래 함수가 고른다(`python` → `py -3` → `python3` 순서로 3.10 이상인 첫 번째).
  2단계에서 설치를 했다면 PATH를 다시 읽은 뒤 이 블록을 다시 실행한다.

```powershell
$global:UePy = $null
foreach ($cand in @("python", "py -3", "python3")) {
    $parts = $cand -split " "
    if (-not (Get-Command $parts[0] -ErrorAction SilentlyContinue)) { continue }
    $rest = @($parts | Select-Object -Skip 1)
    $out = & $parts[0] @rest -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
    if ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq "True") { $global:UePy = $parts; break }
}
function Invoke-UePython {
    $rest = @($global:UePy | Select-Object -Skip 1)
    & $global:UePy[0] @rest @args
}
if ($global:UePy) { "python 3.10+: $($global:UePy -join ' ')" } else { "python 3.10+ not found" }
```

- `python 3.10+ not found`가 나오면 2단계에서 파이썬을 설치한다.

## 2. 없는 것만 설치

```powershell
# git이 없을 때만 (Git for Windows에 Git LFS 포함)
winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements

# 3.10 이상 파이썬이 없을 때만
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
```

설치했다면 현재 세션의 PATH를 다시 읽고 1단계 확인을 다시 실행한다.

```powershell
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
```

## 3. Git 설정

```powershell
git lfs install
git config --global core.longpaths true
```

(`core.longpaths`는 언리얼 프로젝트의 긴 파일 경로 때문에 필요하다.)

## 4. 스킬 설치 (이미 있으면 업데이트)

```powershell
$skill = "$env:USERPROFILE\.agents\skills\ue-repo-reader"
if (Test-Path "$skill\.git") { git -C $skill pull --ff-only } else { git clone https://github.com/immigration2000/ue-repo-reader $skill }
Test-Path "$skill\SKILL.md"
Test-Path "$skill\scripts\ue_repo_digest.py"
```

- 두 `Test-Path`가 모두 `True`여야 한다.
- `$skill` 폴더가 이미 있는데 git 저장소가 아니면 **지우지 말고** 사용자에게 어떻게 할지 물어본다.

이 가이드는 개인용 Git 클론 설치를 사용한다. 프로젝트에만 설치하거나 Claude Code/Copilot용 폴더가 필요하면
[README의 설치 표와 install_skill.py](../README.md#설치)를 따른다. 복사 설치본도 `SKILL.md`와 `scripts/`가 같은
폴더에 있으며 5단계에서 `$skill`을 그 폴더로 지정해 실행할 수 있다. 복사 설치본에는 `.git`이 없어 `git pull`은 적용하지 않는다.

## 5. 동작 확인 (1~3분)

실제 저장소 하나를 분석해 본다. 작업 폴더는 `C:\UEReview`를 쓴다(사용자가 다른 곳을 원하면 바꾼다).

```powershell
$work = "C:\UEReview"
New-Item -ItemType Directory -Force $work | Out-Null
$env:PYTHONIOENCODING = "utf-8:replace"   # 한국어 Windows(cp949) 콘솔에서도 로그가 깨지지 않게
Invoke-UePython "$skill\scripts\ue_repo_digest.py" https://github.com/immigration2000/ExtractionGame_Fin --workdir "$work\repos\ExtractionGame_Fin" --out "$work\ExtractionGame_Fin_digest"
"exit code: $LASTEXITCODE"
Select-String -LiteralPath "$work\ExtractionGame_Fin_digest\INDEX.md" -Pattern "Coverage:", "decoded cleanly" | ForEach-Object Line
```

성공 기준:
- `exit code: 0`이 나오고 `INDEX.md`가 생긴다. **성공 여부는 종료 코드로만 판단한다.** 진행 로그(`[fetch]`, `[bp]` …)는
  stderr로 나오므로 Windows PowerShell 5.1에서는 빨간 `NativeCommandError`처럼 보일 수 있는데, 오류가 아니다.
  (`$ErrorActionPreference = "Stop"`이 설정된 세션이면 이 로그 때문에 중단되므로 그 블록에서는 `"Continue"`로 둔다.)
- `Coverage:` 줄에 `0 failed`, 그리고 `graph nodes decoded N/N`(앞뒤 숫자가 같음)이 보인다.
- INDEX의 Parse report와 문서별 Parse warnings도 확인한다. 노드 N/N이어도 속성·그래프 렌더링·레벨 BP·외부 액터는
  부분 실패할 수 있으며, 모두 읽혔을 때만 `everything decoded cleanly`가 표시된다.
- 첫 실행 때 파서가 `%USERPROFILE%\.cache\ue-repo-reader`에 자동으로 받아진다(정상).
- `--out`은 요약본 전용 폴더다. 입력 저장소 자체/상위 경로나 심볼릭 링크/정션은 쓸 수 없으며,
  일반 파일이 있는 폴더나 중단된 실행 결과를 요약본으로 식별할 수 없으면 새 출력 폴더를 지정한다.
  정상 완료된 요약본은 같은 명령으로 다시 생성할 수 있다.

## 6. 사용자에게 보고 (한국어, 짧게)

지원 경계: 프로젝트의 `.uproject`가 숫자 5.7/5.8을 선언하면 기본 분석한다. 5.7 미만·빌드 GUID/누락·미검증 신버전은
거부하며 기존 CLI 출력은 보존한다. 사용자가 범위 밖 탐색을 요청하면 `--best-effort`를 명시하고 INDEX의 **Project support**를
함께 보고한다. 에셋 저장 버전이 오래됐다는 이유로 5.7+ 프로젝트를 거부하거나, 최신 에셋 하나로 프로젝트 버전을 추정하지 않는다.

- 새로 설치한 것 / 원래 있던 것과 버전 (git, git-lfs, python)
- 스킬 설치 경로
- 5단계의 `Coverage:` 줄
- 앞으로 쓰는 법:
  - 새 Codex 대화에서 `https://github.com/<owner>/<repo> 분석해줘`라고 말한다.
    확실히 부르려면 앞에 `$ue-repo-reader`를 붙인다.
  - 스킬이 안 보이면 앱을 다시 시작하고, 사이드바의 **Skills**에서 `ue-repo-reader`가 있는지 확인한다.
  - 스킬 업데이트: `git -C "$env:USERPROFILE\.agents\skills\ue-repo-reader" pull`
