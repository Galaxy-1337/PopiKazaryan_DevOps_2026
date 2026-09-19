#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Single command interface for the "Conference" project on Windows.

.DESCRIPTION
    Single entry point for every project command: setup, run, checks,
    migrations, backups and the container environment. Every mandatory check
    is executed by one command, as required by the course rules
    ("obligatory local verification commands").

    Output messages are ASCII-only on purpose: Windows PowerShell 5.1 reads
    .ps1 files using the system code page, so non-ASCII text would break
    parsing when the file has no BOM.

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
    [string]$BindHost = '127.0.0.1'
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
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PyArgs)
    & (Get-Python) @PyArgs
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}

function Get-Compose {
    docker compose version *> $null
    if ($LASTEXITCODE -eq 0) { return @('docker', 'compose') }
    return @('docker-compose')
}

function Show-Help {
    Write-Host 'Available commands:'
    Write-Host '  setup            Initial setup: venv, dependencies, .env'
    Write-Host '  run              Run the application locally (uvicorn)'
    Write-Host '  test             Automated tests (pytest)'
    Write-Host '  quality          Formatting and static analysis'
    Write-Host '  lint             Static analysis only (ruff check)'
    Write-Host '  format           Apply automatic formatting'
    Write-Host '  migrate          Apply migrations / create database schema'
    Write-Host '  backup           Create a database backup'
    Write-Host '  restore -File F  Restore the database from a backup'
    Write-Host '  verify           Full set of local checks before commit'
    Write-Host '  up               Start containers (app + PostgreSQL)'
    Write-Host '  down             Stop containers'
    Write-Host '  logs             Follow container logs'
    Write-Host '  container-check  Check container health via /health'
    Write-Host '  version          Print application version'
    Write-Host '  clean            Remove caches and virtual environment'
    Write-Host ''
    Write-Host 'Options: -Port <int>   -BindHost <string>   -File <path>'
}

switch ($Command) {
    'help' { Show-Help }

    'setup' {
        Write-Host '[setup] Creating virtual environment' -ForegroundColor Cyan
        python -m venv .venv
        Write-Host '[setup] Installing dependencies' -ForegroundColor Cyan
        Invoke-Py -m pip install --upgrade pip
        Invoke-Py -m pip install -r requirements-dev.txt
        if (-not (Test-Path '.env')) {
            Copy-Item '.env.example' '.env'
            Write-Host '[setup] .env created from .env.example - please review the values' -ForegroundColor Yellow
        }
        Write-Host '[setup] Done. Start the app: .\scripts\dev.ps1 run' -ForegroundColor Green
    }

    'run' {
        $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($busy) {
            Write-Host "[run] Port $Port is already in use." -ForegroundColor Red
            Write-Host "      Another mode is probably running. Stop it first:" -ForegroundColor Yellow
            Write-Host "        containers: docker compose down" -ForegroundColor Yellow
            Write-Host "        local run:  Ctrl+C in its window" -ForegroundColor Yellow
            Write-Host "      Or start on a free port: .\scripts\dev.ps1 run -Port 8010" -ForegroundColor Yellow
            throw "Port $Port is busy"
        }
        Write-Host "[run] http://${BindHost}:$Port" -ForegroundColor Cyan
        Invoke-Py -m uvicorn app.main:app --host $BindHost --port $Port --reload
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
        if (-not $File) {
            throw 'Specify a backup file: .\scripts\dev.ps1 restore -File backups\<file>'
        }
        Invoke-Py -m scripts.restore $File
    }

    'verify' {
        Write-Host '[verify] 1/4 ruff format --check' -ForegroundColor Cyan
        Invoke-Py -m ruff format --check .
        Write-Host '[verify] 2/4 ruff check' -ForegroundColor Cyan
        Invoke-Py -m ruff check .
        Write-Host '[verify] 3/4 pytest' -ForegroundColor Cyan
        Invoke-Py -m pytest -q
        Write-Host '[verify] 4/4 smoke check' -ForegroundColor Cyan
        Invoke-Py -m scripts.smoke
        Write-Host '[verify] All local checks passed' -ForegroundColor Green
    }

    'up' {
        $compose = Get-Compose
        & $compose[0] $compose[1] up --build -d
        if ($LASTEXITCODE -ne 0) { throw 'Failed to start containers' }
        Write-Host "[up] Application: http://${BindHost}:$Port  Swagger: http://${BindHost}:$Port/docs" -ForegroundColor Green
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
        Write-Host '[clean] Caches removed' -ForegroundColor Green
    }
}
