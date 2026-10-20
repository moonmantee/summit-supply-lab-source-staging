Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,IsTamperProtected
Get-Item C:/aeacus/phocus.exe -ErrorAction SilentlyContinue | Select-Object Length,LastWriteTimeUtc
