# 멀티 에이전트 오케스트레이션 운영 규약

cmux 워크스페이스 하나에서 여러 CLI 에이전트를 동시에 굴리기 위한 규약이다.
지휘자(오케스트레이터)는 Claude Code 세션 하나이며, 나머지 터미널은 워커다.

## 역할

| 역할 | 터미널 제목 | 에이전트 |
| --- | --- | --- |
| 오케스트레이터 | `◐ 오케스트레이션 세팅` | Claude Code (Opus 5) |
| 워커 `codex` | `Team3_EcommerceSystemAI` | OpenAI Codex CLI |
| 워커 `agy` | `agy` | Antigravity CLI (Gemini) |

워커는 `scripts/orchestration/workers.tsv` 에 등록한다. 서피스 UUID 는 앱을 다시 띄우면
바뀌고, 터미널 **제목은 CLI 가 자기 실행 명령으로 갈아치우기 때문에**(예: agy 를 재기동하면
제목이 `agy --dangerously-skip-permissions` 로 바뀐다) 식별자로 쓸 수 없다. 그래서 pane 수명
동안 고정되는 **tty 로 해석**한다. 워커를 추가/변경하려면 `cmux tree --all` 에서 tty 를 확인해
`alias<TAB>tty<TAB>종류<TAB>idle_정규식` 한 줄을 넣는다.

## 지휘 도구

```
scripts/orchestration/orc list                 # 워커와 idle/busy 상태
scripts/orchestration/orc send <alias> "…"     # 한 줄 지시
scripts/orchestration/orc task <alias> "제목"  # stdin 브리프를 파일로 넘김 (긴 작업)
scripts/orchestration/orc wait <alias> [sec]   # 입력 대기 상태로 돌아올 때까지 폴링
scripts/orchestration/orc read <alias> [lines] # 워커 화면 회수
scripts/orchestration/orc board                # 작업 보드
```

## 배분 규칙

1. **긴 지시는 `orc send` 로 보내지 않는다.** TUI 프롬프트는 개행에서 바로 제출되므로
   두 줄 이상이면 `orc task` 로 브리프 파일(`.orchestration/tasks/<시각>-<alias>.md`)을
   만들고, 워커에게는 "그 파일을 읽고 수행하라"는 한 줄만 보낸다.
2. **파일 충돌을 방지한다.** 같은 파일을 두 워커에 동시에 배정하지 않는다. 브리프에
   담당 경로를 명시하고, 겹치면 순차로 돌린다.
3. **워커는 자기 브리프 파일 하단에 `## 결과` 로 보고**한다. 지휘자는 `orc wait` 후
   브리프 파일과 `git diff` 로 검증한다. 화면(`orc read`)은 보조 확인용이다.
4. **커밋은 지휘자만 한다.** 워커에게는 커밋·푸시·서버 실행을 시키지 않는다.
5. `.orchestration/` 은 런타임 상태이므로 git 에 올리지 않는다(.gitignore 처리됨).

## 인계

메인 관리자의 사용량이 소진되어 다른 세션에 "일 이어받아"라고 넘길 때는,
`.orchestration/board.md` 와 진행 중인 브리프 파일이 인계 자료다. 인계받는 세션은
**원래 작업의 목적과 금지 사항을 그대로 승계**하며, 작업 성격(점검 → 수정 등)을
임의로 바꾸지 않는다.
