# Карта перенесённых функций

| Функция | Источник | Итоговый модуль | Проверка |
| --- | --- | --- | --- |
| Форматы, ключ, очередь, строгий API | OKO и FORTE | app/api.py, config.py, worker.py | test_service, test_integration_api, smoke_test |
| Кадры, V13, confidence, review, склейка | OKO pipeline | app/oko/pipeline | реальные positive/negative video tests |
| Каталог 21 правила и источники | OKO catalog | app/oko/rules/catalog.py | API catalog и browser help |
| Модель команды | FORTE model adapter | app/model.py, app/oko/pipeline/detectors/team.py | контракт model adapter; веса отдельно |
| Постоянные видео и отдельные запуски | Творческий пакет | app/db.py, web/archive.js | test_archive_db, API и browser |
| Поиск, фильтры, review, повторное открытие | Творческий пакет | db.py, api.py, archive.js | API filters, browser reload без POST |
| Дедупликация запроса и поздние ответы | Творческий пакет | db.py, web/app.js | concurrent tests, browser A clear B |
| Очистка, плеер, 1×/2×, fullscreen | FORTE и пакет | web/player.js, app.js | browser |
| Чат, evidence dialog, нормы | FORTE и OKO | web/chat.js, report.js | browser и настоящие JPEG |
| Таймлайн и полный JSON | OKO | web/report.js | browser timeline/copy |
| Три мира, порталы, темы, motion | FORTE и пакет | web/worlds.js, styles.css | browser 1366/1920/390, reduced motion |
| Звук, duck, mute | FORTE и пакет | web/audio.js, config.js | browser и source assertions |
| Выход End и титры | Творческий пакет | web/credits.js, content/credits.json | browser pause/skip и точные имена |
| Windows и Docker запуск | FORTE | start.ps1, app/__main__.py, compose.yaml | локальный сервер; Docker отдельно |
