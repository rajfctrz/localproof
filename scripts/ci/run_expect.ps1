# Run a (windowed) LocalProof.exe with redirected output and assert its exit code.
# Start-Process -Wait is used because PowerShell does not wait for GUI-subsystem exes.
param(
  [Parameter(Mandatory)][string]$Exe,
  [Parameter(Mandatory)][int[]]$Expect,
  [string[]]$AppArgs = @(),
  [string]$MustContain = ""
)
$out = [System.IO.Path]::GetTempFileName()
$err = "$out.err"
$p = Start-Process -FilePath $Exe -ArgumentList $AppArgs -Wait -PassThru -NoNewWindow `
  -RedirectStandardOutput $out -RedirectStandardError $err
$text = (Get-Content $out -Raw) + (Get-Content $err -Raw)
Write-Output $text
Write-Output "exit code: $($p.ExitCode) (expected: $($Expect -join ' or '))"
if ($Expect -notcontains $p.ExitCode) { throw "unexpected exit code $($p.ExitCode)" }
if ($MustContain -and ($text -notmatch [regex]::Escape($MustContain))) { throw "output does not contain '$MustContain'" }
