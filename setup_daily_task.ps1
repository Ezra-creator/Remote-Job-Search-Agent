# setup_daily_task.ps1 - Registers a daily Windows Scheduled Task for RJS Pipeline
# Runs every morning at 08:00 AM to fetch and score new job postings

$TaskName = "RemoteJobSearchAgent_Daily"
$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = (Get-Command python).Source
$ScriptPath = Join-Path $ProjectPath "run_pipeline.py"

$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$ScriptPath`"" -WorkingDirectory $ProjectPath
$Trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily sourcing and scoring for Remote Job Search Agent"
    Write-Host "Successfully registered Windows Task '$TaskName' to run daily at 8:00 AM." -ForegroundColor Green
} catch {
    Write-Host "Error creating scheduled task: $_" -ForegroundColor Red
}
