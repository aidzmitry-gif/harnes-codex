# Контекст проекта «Харнес разработка»

<!-- context-handoff:start -->
## Current handoff

- Updated: 2026-09-05, Europe/Istanbul; сверять с git и текущими receipts.
- Objective: HRE-006 — доставить проверенный Harness в зарегистрированные доступные проекты, сохранив локальные правила и данные.
- Approval: после HRE-005 пользователь попросил распространение на все проекты/ПК и подтвердил «все сделай обновление смотри Графифай». Контракт и границы: .harness/work/hre-006-distribution.md. Новые обычные задачи, worktrees и расширение доступа не разрешены.
- Verified state: 20 local проектов получили 18 core-файлов release 2026.09.05-hre006.1; independent initial wave audit 19/19 PASS, дополнительная установка в Graphify прошла после pull --ff-only и сверки 18 хешей/validator smoke. Во всех profileConfigured=false, projectAcceptance=not-run: наличие core не равно внедрению в процессы.
- Inventory: 31 root = 20 current, 9 deferred, 1 SEO conflict, 1 source. Graphify использован как карта, реальные roots сверены по Codex/файлам; его графы/генераторы/реестры/заметки не менялись. Другие ПК не подключены и не обновлены.
- Invariants: AGENTS.md baseline SHA-256 b0184c9d679de0622e8f42f9673132007c3bb4e3bf18af85a44845e9e4d116bf сохранён. Никаких изменений чужих AGENTS/CLAUDE/config/work/context/runtime, production, ACL, моделей/cap или active automations. 155 protected path hash/absence comparisons: 0 changes.
- Changed surfaces: HRE-005 skill/radar/planner + HRE-006 offline distribution CLI, Windows wrapper, fixed release manifest, exact18 LF attributes, tests и документы. Global skills текущего ПК уже junction на source; глобальный installer/config не запускался.
- Verification: 19 targeted distribution tests PASS, full strict release PASS; актуальная техническая приёмка .harness/acceptance/hre-006.json. HRE-005 acceptance — исторический checkpoint до HRE-006, не текущая свежесть. Точная приватная матрица и protected snapshots в ignored .harness/runtime/hre006-*.json.
- Publication: source branch codex/hre-004-update-watcher; version tag harness-v2026.09.05-hre006.1. Фактическую публикацию/commit проверять по git ls-remote и финальной записи work item, не выводить её из наличия manifest.
- Risks: raw-byte install не является project acceptance; нет автоскачивания/scheduler. Dirty/active/custom-flow проекты и конфликтные файлы не перезаписывать. Radar остаётся single-writer; live scheduler adoption не выполнялся. Экономия токенов/времени на реальных задачах не измерена.
- Next minimal slice: подключить следующий ПК или выбрать один deferred/conflict проект, прочитать его контракт и проверить минимальную интеграцию. Не повторять массовую установку без свежих plan/idle/permissions.
- Startup reads: AGENTS.md; .harness/work/hre-006-distribution.md; docs/DISTRIBUTION.md; .harness/acceptance/hre-006.json; точный модуль следующего среза.
- Successor: не создавался; исходная задача не архивировалась.
<!-- context-handoff:end -->
