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
python --version
py -3 --version
```

판단 기준:
- `git`, `git lfs`가 버전을 출력하면 OK.
- 파이썬은 **3.10 이상**이 필요하다. `python`의 Source가 `...\WindowsApps\python.exe`이면 Microsoft Store
  바로가기일 뿐 실제 파이썬이 아니다.
- 3.10 이상을 실행하는 명령(`python` 또는 `py -3`)을 골라 이후 단계의 `<PY>` 자리에 쓴다.

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

## 5. 동작 확인 (1~3분)

실제 저장소 하나를 분석해 본다. 작업 폴더는 `C:\UEReview`를 쓴다(사용자가 다른 곳을 원하면 바꾼다).

```powershell
$work = "C:\UEReview"
New-Item -ItemType Directory -Force $work | Out-Null
<PY> "$skill\scripts\ue_repo_digest.py" https://github.com/immigration2000/ExtractionGame_Fin --workdir "$work\repos\ExtractionGame_Fin" --out "$work\ExtractionGame_Fin_digest"
Select-String -Path "$work\ExtractionGame_Fin_digest\INDEX.md" -Pattern "Coverage:", "decoded cleanly" | ForEach-Object Line
```

성공 기준:
- 명령이 종료 코드 0으로 끝나고 `INDEX.md`가 생긴다.
- `Coverage:` 줄에 `0 failed`, 그리고 `graph nodes decoded N/N`(앞뒤 숫자가 같음)이 보인다.
- 첫 실행 때 파서가 `%USERPROFILE%\.cache\ue-repo-reader`에 자동으로 받아진다(정상).

## 6. 사용자에게 보고 (한국어, 짧게)

- 새로 설치한 것 / 원래 있던 것과 버전 (git, git-lfs, python)
- 스킬 설치 경로
- 5단계의 `Coverage:` 줄
- 앞으로 쓰는 법:
  - 새 Codex 대화에서 `https://github.com/<owner>/<repo> 분석해줘`라고 말한다.
    확실히 부르려면 앞에 `$ue-repo-reader`를 붙인다.
  - 스킬이 안 보이면 앱을 다시 시작하고, 사이드바의 **Skills**에서 `ue-repo-reader`가 있는지 확인한다.
  - 스킬 업데이트: `git -C "$env:USERPROFILE\.agents\skills\ue-repo-reader" pull`
