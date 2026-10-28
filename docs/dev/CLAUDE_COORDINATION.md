# Codex가 관리하는 Claude Code 작업

사용자가 위임·관리를 요청한 경우 적용한다. Codex는 관리자이자 구현자이며 실제 Claude Code CLI와 TASK를 하나씩 나눠 맡는다.
각자의 변경을 서로 검토하고 Codex가 독립 테스트·통합·push를 마친다. 규칙 원본은 [AGENTS.md 8절](../../AGENTS.md)이다.

## 실행 전

1. Codex가 pull 후 TASKS/WORKLOG를 확인하고 겹치지 않는 TASK를 선점한다.
2. Claude 작업은 별도 Git worktree의 `claude/<TASK>-...` 브랜치를 준비한다. main checkout은 편집 작업자로 실행하지 않는다.
3. 사용자가 기존 Claude Code에 로그인한다. `claude auth status`로 확인하며 인증 파일·토큰을 읽거나 복사하지 않는다.
4. UTF-8 지시 파일에 기준 커밋, TASK, 수정 허용 파일, 완료 조건, 읽을 수 있는 테스트 자료를 적는다.
   작업자는 명령 실행·Git·문서 상태 변경을 맡지 않으며 테스트 통과를 주장하지 않는다.

## 실행·상태·재지시

Python 3.10+와 이미 설치된 실제 Claude Code CLI를 사용한다. 아래 경로는 예시이며 현재 기기의 실제 Python/작업 경로로 바꾼다.

```powershell
python tools/claude_delegate.py start Q7 --workdir "D:/worktrees/claude-q7" --prompt-file "D:/jobs/Q7.txt"
# 출력된 job 폴더를 그대로 사용한다. 한 번의 실행은 기본 30분 제한이다.
python tools/claude_delegate.py status "D:/repo/.ue-repo-reader/claude-jobs/Q7-xxxxxxxx"
python tools/claude_delegate.py stop "D:/repo/.ue-repo-reader/claude-jobs/Q7-xxxxxxxx"
python tools/claude_delegate.py continue "D:/repo/.ue-repo-reader/claude-jobs/Q7-xxxxxxxx" --prompt-file "D:/jobs/Q7-rework.txt"
```

`start`/`continue`는 실행이 끝날 때까지 동작한다. Codex의 명령 실행 세션으로 돌리고, 다른 호출에서 상태를 읽으며 독립 작업을 계속한다.
로그는 `.ue-repo-reader/claude-jobs/`에 남고 Git에는 들어가지 않는다. session ID로 같은 Claude 대화를 재개한다.
CLI를 자동 탐색하며 npm Windows shim 옆의 native `claude.exe`도 지원한다. 탐색 실패 시 `--claude`로 실행 파일을 지정한다.

파일 도구(Read/Glob/Grep/Edit/Write)만 열고 `dontAsk`를 사용한다. 셸·MCP·브라우저·추가 에이전트는 도구 목록에 없다.
일반 권한 거절은 `needs_attention`으로 남으며 전체 권한 우회로 재시도하지 않는다.
파일 범위는 작업 지시와 Codex의 diff 검토로 확인한다. 결과·로그는 작업 자료를 포함하므로 공개하지 않는다.

## 교차 검토와 완료

Codex는 Claude 변경을 diff로 검토하고 관련 검사와 전체 `tests/regress.py`를 실행한다. 반대로 Codex 변경도 Claude에 검토시킨다.
읽기 전용 검토는 `--read-only`를 붙인다. 이 모드는 Read/Glob/Grep만 제공하며 primary checkout도 읽을 수 있다.
같은 세션을 읽기 전용으로 재개하면 이후에도 편집 도구를 다시 열지 않는다.

```powershell
python tools/claude_delegate.py start Q4-REVIEW --workdir "D:/repo" --prompt-file "D:/jobs/Q4-review.txt" --read-only
# 수정이 필요하면 검토 근거를 적어 재지시한다.
python tools/claude_delegate.py review "D:/repo/.ue-repo-reader/claude-jobs/Q7-xxxxxxxx" --outcome rework --note "예상 밖 issue 중복 검사가 필요"
# diff·테스트·교차 검토를 통과했을 때만 accepted로 기록한다.
python tools/claude_delegate.py review "D:/repo/.ue-repo-reader/claude-jobs/Q7-xxxxxxxx" --outcome accepted --note "검토와 전체 회귀 통과; 반영 커밋 기록"
```

성공한 작업자 실행도 `awaiting_review`이며 자동으로 TASK를 done으로 만들거나 커밋·병합·push하지 않는다.
Codex가 작업자 변경을 `[claude] TASK: ...`로 커밋하고, TASKS/WORKLOG/필요한 DECISIONS를 갱신한 뒤 main에 통합·push한다.
작업 공간이 더 이상 필요 없으면 Codex 앱의 archive_worktree로 복구 가능한 스냅샷을 남기고 정리한다.

Codex 턴이 끝난 뒤 지속 감시는 실행되지 않는다. 다음 턴에서 job 상태·TASKS·WORKLOG를 읽고 이어간다.
로그인 실패나 세션 손실은 사용자가 인증을 마친 후 새 job으로 배정한다. 남은 변경은 먼저 보존·검토하고 작업을 중복 배정하지 않는다.

CLI 근거: [비대화형 실행과 세션 재개](https://code.claude.com/docs/en/headless),
[CLI 옵션](https://code.claude.com/docs/en/cli-reference). 전역 설정이나 새 SDK 의존성은 필요 없다.
