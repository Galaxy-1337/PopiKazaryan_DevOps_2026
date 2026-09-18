# =====================================================================
#  Включение WSL 2 и компонентов виртуализации для Docker Desktop.
#
#  ЗАПУСКАТЬ ОТ ИМЕНИ АДМИНИСТРАТОРА:
#     правый клик по PowerShell -> «Запуск от имени администратора»,
#     затем выполнить:
#         Set-Location "C:\Users\Иван\Desktop\ПЕРВЫЙ проект\DevOps"
#         .\scripts\enable-wsl2.ps1
#
#  После успешного выполнения ОБЯЗАТЕЛЬНА ПЕРЕЗАГРУЗКА Windows.
# =====================================================================
[CmdletBinding()]
param(
    [switch]$NoPause
)

$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'enable-wsl2.log'

function Write-Log {
    param([string]$Message, [string]$Color = 'Gray')
    $stamp = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$stamp] $Message" -ForegroundColor $Color
    Add-Content -Path $log -Value "[$stamp] $Message" -Encoding UTF8
}

Set-Content -Path $log -Value 'Включение WSL 2 для Docker Desktop' -Encoding UTF8

# --- Проверка прав администратора -------------------------------------
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Log "Пользователь: $($identity.Name)" 'Cyan'
Write-Log "Права администратора: $isAdmin" 'Cyan'

if (-not $isAdmin) {
    Write-Log 'ОШИБКА: скрипт должен быть запущен от имени администратора.' 'Red'
    Write-Log 'Закройте окно, откройте PowerShell через «Запуск от имени администратора» и повторите.' 'Yellow'
    if (-not $NoPause) { Read-Host 'Нажмите Enter для выхода' }
    exit 1
}

# --- Шаг 1. Компоненты Windows ----------------------------------------
$features = @(
    @{ Name = 'Microsoft-Windows-Subsystem-Linux'; Title = 'Windows Subsystem for Linux' },
    @{ Name = 'VirtualMachinePlatform';            Title = 'Платформа виртуальных машин' }
)

foreach ($feature in $features) {
    $state = (Get-WindowsOptionalFeature -Online -FeatureName $feature.Name -ErrorAction SilentlyContinue).State
    Write-Log "$($feature.Title) сейчас: $state"

    if ($state -ne 'Enabled') {
        Write-Log "Включаю: $($feature.Title)..." 'Yellow'
        $result = Enable-WindowsOptionalFeature -Online -FeatureName $feature.Name -All -NoRestart -ErrorAction SilentlyContinue
        Write-Log "  запрос перезагрузки: $($result.RestartNeeded)"
    }
    else {
        Write-Log "  уже включено, пропускаю" 'Green'
    }
}

# --- Шаг 2. Установка пакета WSL из Microsoft Store -------------------
Write-Log 'Обновляю пакет WSL (wsl --update)...'
$update = (& wsl.exe --update 2>&1 | Out-String).Trim()
if ($update) { Write-Log "  $update" }

# --- Шаг 3. Итоговое состояние ----------------------------------------
Write-Log '--- Итоговое состояние компонентов ---' 'Cyan'
$allFeatures = @(
    @{ Name = 'Microsoft-Windows-Subsystem-Linux'; Title = 'Windows Subsystem for Linux' },
    @{ Name = 'VirtualMachinePlatform';            Title = 'Платформа виртуальных машин' },
    @{ Name = 'Microsoft-Hyper-V-All';             Title = 'Hyper-V' }
)
foreach ($feature in $allFeatures) {
    $state = (Get-WindowsOptionalFeature -Online -FeatureName $feature.Name -ErrorAction SilentlyContinue).State
    Write-Log "  $($feature.Title): $state"
}

# --- Шаг 4. Что делать дальше -----------------------------------------
Write-Log ''
Write-Log 'ГОТОВО. Дальнейшие действия:' 'Green'
Write-Log '  1. Перезагрузите компьютер (обязательно).' 'Green'
Write-Log '  2. После перезагрузки запустите Docker Desktop.' 'Green'
Write-Log '  3. Если движок снова не запустится: Docker Desktop ->' 'Yellow'
Write-Log '     Settings -> General -> снять галочку «Use libkrun» (Docker VMM),' 'Yellow'
Write-Log '     выбрать движок WSL 2 -> Apply & restart.' 'Yellow'
Write-Log ''
Write-Log "Журнал сохранён: $log"

if (-not $NoPause) {
    Read-Host 'Нажмите Enter для выхода'
}
