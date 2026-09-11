@AGENTS.md

## Только для Claude Code

- Правила проекта — в `AGENTS.md` выше, он общий с Codex и OpenCode. Правки вносить туда,
  а не сюда, иначе другие агенты их не увидят.
- Субагенты ревью: `site-content-auditor` и `site-image-auditor` (`.claude/agents/`) —
  запускать точечно по одной статье через Agent tool. Они только докладывают.
- Скилл `zilma-site-dev` (`.claude/skills/`) — вход в репозиторий.
- Уроки курса на university.zerocoder.ru требуют логина: читать через
  `mcp__claude-in-chrome__*`, не просить у пользователя скриншоты.
- Этот файл держать коротким. Всё, что длиннее абзаца, — в `docs/`.
