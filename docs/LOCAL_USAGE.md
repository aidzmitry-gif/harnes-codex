# Локальные native Codex метрики

Короткий маршрут для meaningful checkpoint. Это не scanner всех чатов, scheduler, биллинг или разрешение читать чужие проекты. Активные Goal и конфигурация приложения не переключаются.

## Прочитать фактическую дельту

Запускайте `harness_codex.py session-summary <relative-rollout.jsonl> --root <absolute-local-session-root>` с одним явно выбранным журналом. Root должен быть локальным, без reparse/symlink; relative path не может указывать на credentials/.env/auth. Выход — только counters, checkpoint и неизвестные поля; transcript не выводится и не сохраняется.

Читается header до 64 KB и хвост до 4 MB. Первое наблюдаемое значение является baseline: более ранняя история не измерена. Нет двух разных накопительных значений — usage неизвестен, не ноль. Input уже включает cache, output включает reasoning; subsets не прибавляются повторно. Наблюдаемый optional `cache_write_input_tokens` валидируется как subset input, но отдельная цена/экономия по нему не выводится. Не складывайте parent и child counters.

## Записать checkpoint в имеющиеся метрики

Подготовьте маленький event в `.harness/runtime/usage-event.json` с полями существующего `harness_metrics.py`: chainId, subgoalId, pairKey, treatment, mode, model/effort либо null, attempts, failedAttempts либо null, durationMs, reworkCount, accepted, released/used либо null, escapedDefects и checksPassed/checksFailed. RunId будет назначен importer. Input/output оставьте null; собственные cache/checkpoint поля запрещены. Counts, duration и acceptance должны иметь отдельное наблюдаемое основание — importer их не придумывает. Не подставляйте 0 вместо неизвестного обязательного поля; пока данных недостаточно, используйте только read-only summary.

Команда: `harness_codex.py session-record <relative-rollout.jsonl> --source-root <absolute-local-session-root> --root <absolute-project-root> --event .harness/runtime/usage-event.json --metrics .harness/metrics/runs.jsonl`.

Importer записывает schema 3 через существующий append-only ledger; отдельного state нет. Следующий вызов продолжает от последнего endOffset/endUsage, проверяет source ID, UUID и SHA-256 последних 4 KB перед checkpoint. Повтор без новых counters — no-op. Chain rebinding, copied/rotated/truncated source, изменённый anchor, сброс счётчиков, дубликат, overlap, malformed JSON или чужой writer lock запрещают запись. Lock сериализует только cooperating importers, не произвольные старые producers/editor; stale lock не удаляется автоматически. Чтение ledger для импорта ограничено 2 MB; required archive/rebinding — отдельная операция, не автоматическое удаление.

Если между checkpoints более 4 MB, hasMore показывает ограниченное покрытие; повторный импорт может продолжить только при достигнутом новом counter. Если внутри ограниченного окна нет counter, не расширяйте чтение молча и не выдавайте покрытие всей сессии. Ограничение намеренное, расширять после воспроизводимого bounded replay.

Anchor не доказывает неизменность всей многогигабайтной истории: предполагаются доверенные append-only журналы. Правки вне проверяемого anchor не обнаруживаются. Это локальная telemetry, не подписанное финансовое доказательство. Acceptance остаётся caller-declared; source freshness/критерии проверяйте обычным acceptance gate.

## Отчёт и бюджет

`harness_metrics.py task --file .harness/metrics/runs.jsonl --chain <id> --work-item <id>` отдельно показывает tokens, cachedInputTokens, reasoningOutputTokens и coverage. Schemas 1/2 читаются без миграции. В смешанном/неполном покрытии полный итог остаётся null, известная сумма — knownSubtotal. Для одного chain task-summary/budget не суммируют разные native session UUID без доказанной независимости: отчёт отказывает вместо возможного двойного учёта parent/child. Разделяйте ledgers и не объединяйте global summary разных parent/child сессий вручную.

`compare` считает cache/uncached/reasoning только для пар с нужными данными. Один logical attempt/checkpoint записывается один раз; не записывайте тот же расход вторично через старый producer. Время между пользовательскими сообщениями не является временем пользователя; durationMs задаёт наблюдаемая проверка того же checkpoint, не импорт всего истории чата. Existing runBudget opt-in остаётся fail-closed и принимает schema 2/3; активные паспорта не редактируйте автоматически.

## GPT-6.1 Sol

Validator и dispatch принимают явный `gpt-6.1-sol`. Low/medium/high/xhigh/max доступны в официальном API; none/minimal не поддерживаются. Источник: [официальная документация модели](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

Текущий Codex host дополнительно объявляет ultra callable; поэтому этот Codex-профиль включает ultra. Это не утверждение об API: route/capabilities разные. Не переключайте активную модель или effort автоматически. Экономию по сравнению с Sol/Luna/Astra подтверждают только одинаковые реальные задачи с одинаковой приёмкой; детерминированные Python-тесты её не доказывают.
