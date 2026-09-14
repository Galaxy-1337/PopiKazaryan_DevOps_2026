#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Единый командный интерфейс проекта «Конференция» для Windows.

.DESCRIPTION
    Полный аналог Makefile для среды без GNU make. Любая проверка выполняется
    одной командой, что требуется общими требованиями к лабораторным работам.

.EXAMPLE
    .\scripts\dev.ps1 setup
    .\scripts\dev.ps1 verify
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'run', 'test', 'quality', 'lint', 'format',
        'migrate', 'backup', 'restore', 'verify', 'up', 'down', 'logs',
        'container-check', 'version', 'clean')]
    [string]$Command = 'help',

    [string]$File,
    [int]$Port = 8000,
    [string]$Host_ = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'

function Get-Python {
    if (Test-Path $VenvPython) { return $VenvPython }
    return 'python'
}

function Invoke-Py {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & (Get-Python) @Args
    if ($LASTEXITCODE -ne 0) { throw "Команда завершилась с кодом $LASTEXITCODE" }
}

function Get-Compose {
    docker compose version *> $null
    if ($LASTEXITCODE -eq 0) { return @('docker', 'compose') }
    return @('docker-compose')
}

function Show-Help {
    Write-Host @'
Доступные команды:
  setup            Первоначальная настройка: venv, зависимости, .env
  run              Локальный запуск приложения (uvicorn)
  test             Автоматические тесты (pytest)
  quality          Форматирование и статический анализ
  lint             Статический анализ (ruff check)
  format           Автоматическое форматирование кода
  migrate          Применение миграций / создание схемы БД
  backup           Резервная копия базы данных
  restore -File X  Восстановление базы из резервной копии
  verify           Полный набор локальных проверок перед коммитом
  up               Запуск контейнерного окружения (app + PostgreSQL)
  down             Остановка контейнерного окружения
  logs             Логи контейнеров
  container-check  Проверка работоспособности контейнера через /health
  version          Показать версию приложения
  clean            Удалить кэши и виртуальное окружение
'@
}

switch ($Command) {
    'help' { Show-Help }

    'setup' {
        Write-Host '==> Создание виртуального окружения' -ForegroundColor Cyan
        python -m venv .venv
        Write-Host '==> Установка зависимостей' -ForegroundColor Cyan
        Invoke-Py -m pip install --upgrade pip
        Invoke-Py -m pip install -r requirements-dev.txt
        if (-not (Test-Path '.env')) {
            Copy-Item '.env.example' '.env'
            Write-Host '==> Создан .env из .env.example (проверьте значения)' -ForegroundColor Yellow
        }
        Write-Host '==> Готово. Запуск: .\scripts\dev.ps1 run' -ForegroundColor Green
    }

    'run' {
        Invoke-Py -m uvicorn app.main:app --host $Host_ --port $Port --reload
    }

    'test' { Invoke-Py -m pytest -q }
    'lint' { Invoke-Py -m ruff check . }
    'quality' {
        Invoke-Py -m ruff format --check .
        Invoke-Py -m ruff check .
    }
    'format' {
        Invoke-Py -m ruff format .
        Invoke-Py -m ruff check --fix .
    }
    'migrate' { Invoke-Py -m scripts.migrate }
    'backup' { Invoke-Py -m scripts.backup }
    'restore' {
        if (-not $File) { throw 'Укажите файл: .\scripts\dev.ps1 restore -File backups\<файл>' }
        Invoke-Py -m scripts.restore $File
    }

    'verify' {
        Invoke-Py -m ruff format --check .
        Invoke-Py -m ruff check .
        Invoke-Py -m pytest -q
        Invoke-Py -m scripts.smoke
        Write-Host '==> Все локальные проверки пройдены' -ForegroundColor Green
    }

    'up' {
        $compose = Get-Compose
        & $compose[0] $compose[1] up --build -d
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось запустить контейнеры' }
        Write-Host "==> Приложение: http://${Host_}:$Port  Swagger: http://${Host_}:$Port/docs" -ForegroundColor Green
    }

    'down' {
        $compose = Get-Compose
        & $compose[0] $compose[1] down
    }

    'logs' {
        $compose = Get-Compose
        & $compose[0] $compose[1] logs -f --tail=100
    }

    'container-check' { Invoke-Py -m scripts.container_check }
    'version' { Invoke-Py -c "from app import __version__; print(__version__)" }

    'clean' {
        foreach ($path in @('.venv', '.pytest_cache', '.ruff_cache', '.mypy_cache', 'htmlcov', '.coverage')) {
            if (Test-Path $path) { Remove-Item -Recurse -Force $path }
        }
        Get-ChildItem -Recurse -Directory -Filter '__pycache__' |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
        Write-Host '==> Кэши удалены' -ForegroundColor Green
    }
}
