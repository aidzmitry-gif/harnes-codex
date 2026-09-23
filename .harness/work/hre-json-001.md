# HRE-JSON-001: selective large JSON context compression

Authorization: user 2026-09-11 "внедряем для больших Json?" following the approved Headroom pilot.

Outcome: agents can use an explicit local command for large JSON tool-result files; original bytes remain retrievable by SHA-256. No global proxy or automatic changes to model/effort, instructions, production or other projects.

Baseline: Headroom 0.37.0 pilot reduced one real large graph by 67.1%, but default mode hid one ID via CCR. Ordinary small logs/code had no gain. Existing Harness tree is dirty; implementation is staged separately, then applied only to the listed new files and a hash-guarded AGENTS.md addition.

Scope: harness_json.py, tests/test_harness_json.py, scripts/Invoke-HarnessJson.ps1, docs/LARGE_JSON.md, this card, .harness/acceptance/hre-json-001.json, AGENTS.md. Machine-local interpreter pointer/tokenizer cache/originals live under ignored .harness/runtime/. No edits to pre-existing dirty files.

Contract: UTF-8 JSON file <=16 MiB; >=8000 o200k_base tokens; >=15% total output savings including retrieval envelope. Use Headroom strict lossless mode for flat scalar tables only, and accept after independently decoding and checking exact parsed types/values. Otherwise use verified compact JSON if it wins, or original bytes. No row dropping, opaque CCR markers, instruction compression, LLM calls or runtime network. Errors/dependency/storage failures return original bytes for valid readable inputs. Invalid JSON is passed through. Oversize/unreadable inputs return a nonzero error.

Security: local input files supplied by operator; only SHA-256-named originals stored in project .harness/runtime/json-originals. Reject reparse paths in cache. Retrieval verifies digest and never interprets data as commands. New dependency stays in the existing isolated pilot venv via machine-local pointer; no global installation. Original storage has no automatic TTL/deletion. Raw JSON never enters metric logs.

Acceptance: unit tests for size/savings boundaries, exact type/value retention, marker and row-loss rejection, invalid/duplicate-key JSON passthrough, dependency and storage fallback, original retrieval/tamper rejection; real Graphify fixture roundtrip and all IDs; configured Harness pre/post/release gates. Existing acceptance_gate is used for evidence; no second acceptance registry.

Rollback: stop invoking the helper and remove only this new AGENTS paragraph if desired. No production/schema migrations. Runtime tokens/task costs unknown; payload-token savings are not task-cost evidence.

Risk: medium. Review correctness/security first, then simplify. New helper uses stdlib for parsing/storage; Headroom is a bounded optional candidate, never the authority on data integrity.


## Завершение 2026-09-11

Локально внедрено: CLI, PowerShell launcher, правило в AGENTS.md, документация, тесты, runtime pointer к изолированному venv. Prechange/postchange/release PASS; 146 unit tests. Acceptance hre-json-001: 3/3 свежих PASS. Реальный граф: 95655 -> 31621 токенов (-66.94%), все 626 ID inline, оригинал побайтово восстановлен. Машинные результаты и логи: D:/6 Проекты/CRM ERP/reports/headroom-integration-20260911/. Ни один существовавший файл, кроме согласованного дополнения AGENTS.md, не изменён (SHA-256 readback). Рабочая копия остаётся с прежними незавершёнными правками; commit/push и распространение в другие проекты не выполнялись. Runtime LLM tokens/стоимость задач: нет данных.

В ходе проверки launcher обнаружена и исправлена кодировка UTF-8 русского пути к Python; после исправления проверены 600 inline ID и точный binary roundtrip через PowerShell. Review: проверка корректности/безопасности завершена, simplify-pass оставил ограниченный декодер и stdlib fallback без глобального прокси.
