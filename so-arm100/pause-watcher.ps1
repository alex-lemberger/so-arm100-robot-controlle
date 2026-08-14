$logA   = "C:\projects\so-arm100-robot-controlle\so-arm100\train-grasp-v1-real10.log"
$marker = "C:\projects\so-arm100-robot-controlle\so-arm100\PAUSE_BEFORE_B"

Write-Host "Watcher started — polling every 30s for A completion..."

while ($true) {
    Start-Sleep -Seconds 30

    $done = Select-String -Path $logA -Pattern "End of training" -Quiet 2>$null
    if ($done) {
        Write-Host "$(Get-Date -Format 'HH:mm:ss') — Run A finished. Killing lerobot-train before B starts..."

        # Find and kill the python process running lerobot-train
        $procs = Get-WmiObject Win32_Process | Where-Object {
            $_.CommandLine -like "*lerobot*train*" -or $_.CommandLine -like "*lerobot-train*"
        }
        foreach ($p in $procs) {
            Write-Host "Killing PID $($p.ProcessId): $($p.CommandLine.Substring(0, [Math]::Min(80, $p.CommandLine.Length)))"
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }

        # Write sentinel so we know the watcher did its job
        Set-Content -Path $marker -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') — paused after A, B and C not started"
        Write-Host "=== PAUSE ACHIEVED — ready for your review before B ==="
        break
    }

    $lastLine = (Get-Content $logA -Tail 1 2>$null)
    Write-Host "$(Get-Date -Format 'HH:mm:ss') — A still running. Last: $lastLine"
}
