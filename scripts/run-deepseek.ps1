param([switch]$Compare, [string]$PythonExe = 'python')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$taskPreviousKey = $env:DEEPSEEK_API_KEY
$taskSecret = Read-Host 'DeepSeek API key (hidden input; not saved to disk)' -AsSecureString
$taskPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecret)
try {
    $env:DEEPSEEK_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer)
    if ($Compare) {
        & $PythonExe -m loanlab.compare --live --max-model-calls 24
    } else {
        & $PythonExe -m loanlab.server --port 8769
    }
} finally {
    if ($null -ne $taskPreviousKey) { $env:DEEPSEEK_API_KEY = $taskPreviousKey }
    else { Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue }
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer)
    $taskSecret.Dispose()
}
