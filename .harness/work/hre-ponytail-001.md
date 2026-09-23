# HRE-PONYTAIL-001

User authorization 2026-09-11: apply the actually confirmed improvements using Graphify.

Scope: add existing-code reuse and bugfix caller/root-cause checks to the canonical ladder; replace duplicated rung lists with references; validate order and references with negative mutation tests; change the inaccurate ponytail marker in harness_json.py to an ordinary scope comment. Keep safety/risk-based testing and model settings unchanged.

Graphify: existing graph (626 nodes, built_at_commit d668176277a4c8a22414a9e0b2a7fbe1a6f3e852), actual vocabulary laziness/ladder/architecture/contract/review/runner/installer/adoption. CLI timed out at 25 seconds. Bounded NetworkX traversal over the Graphify graph found 13 nodes/11 edges, including laziness-ladder.md, Goal Runner SKILL.md and the original integration work item. Source files verified the current gaps. Evidence: CRM ERP/reports/ponytail-improvements-20260911/graph-impact.json. No inferred graph edge is treated as fact.

Existing solutions: reuse the reference file, architecture check, unittest suite, work-item and delegation templates, and acceptance_gate.py. No new plugin, hooks, dependency, gate registry or model benchmark. Add validation inside tests and invoke it from the existing architecture check.

Safety/impact: workflow-only change plus one Python comment. Existing dirty files are copied byte-for-byte into staging; apply only against matching preimage hashes and verify every unrelated file. Source and installed global role model settings differ; only the ladder-reference sentence may be updated in the installed worker/verifier, preserving their model/effort and other settings, with ownership-manifest readback. Existing skill junction points to this repository.

Acceptance: seven canonical ordered rungs; consumer references; reuse/root-cause evidence fields; mutations for missing/reordered rungs, stale copies/missing pointers and missing evidence must fail; existing pre/post/release gates; manual diff/security/simplify review. Graphify is orientation, not acceptance proof.

Rollback: restore only this task's preimages. No production, commit, push, repository-wide formatter or model changes. Task token/cost savings unknown; no claim of behavioural improvement based only on static tests.


## Завершение 2026-09-11

Внедрены четыре подтверждённых улучшения: переиспользование кода до новой реализации; первопричина/потребители для bugfix; один канон вместо копий с проверками порядка и ссылок; обычный комментарий вместо неточной ponytail-пометки. Семь новых тестов включают отрицательные мутации. 153 unit tests, prechange/postchange/release PASS; acceptance 3/3 свежих PASS. Статические проверки доказывают целостность инструкций, не экономию токенов и не безошибочность будущих действий агента.

При приёмке локализована проблема окружения: Windows PowerShell наследовал PSModulePath от PowerShell 7, поэтому Get-FileHash отсутствовал. Контрольный запуск с удалённым только из дочернего окружения PSModulePath нашёл правильный Microsoft.PowerShell.Utility. Временный обход через hashlib удалён; рабочее хеширование не менялось. Полный архитектурный критерий и итоговые проверки запускаются с системным набором модулей Windows PowerShell; глобальное окружение не менялось. Модели/effort установленных worker/verifier сохранены; обновлены только developer_instructions и соответствующие SHA-256 manifest. Установленный skill уже связан junction с source. Для загрузки обновлённых файлов ролей требуется новая сессия/перезапуск Codex; текущие запущенные агенты не переопределялись.

Graphify: сохранён результат через python -m graphify save-result; reflect обновил LESSONS.md (8 memories, 7 useful, 1 dead end). Основной graph.json не перестраивался; использован как карта и сверен с исходниками. Отчёты/предыдущие версии/дифф: D:/6 Проекты/CRM ERP/reports/ponytail-improvements-20260911/. Посторонние исходные файлы сохранили SHA-256. Commit/push и смена моделей не выполнялись. Токены/стоимость модельных задач: нет данных.
