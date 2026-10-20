#Requires -RunAsAdministrator
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$name='forum-build-validation-'+[guid]::NewGuid().ToString('N')+'.php'
$path=Join-Path C:\inetpub\wwwroot $name
$php='<?php header("Content-Type: application/json"); echo json_encode(array("loaded_ini"=>php_ini_loaded_file(),"expose_php"=>ini_get("expose_php"),"display_errors"=>ini_get("display_errors"),"log_errors"=>ini_get("log_errors"),"allow_url_include"=>ini_get("allow_url_include"),"session.cookie_httponly"=>ini_get("session.cookie_httponly"))); ?>'
try {
 [IO.File]::WriteAllText($path,$php,[Text.Encoding]::ASCII)
 $r=Invoke-WebRequest ('http://127.0.0.1/'+$name) -UseBasicParsing -TimeoutSec 20
 $effective=$r.Content | ConvertFrom-Json
 if($effective.loaded_ini -ne 'C:\PHP\php.ini'){throw 'IIS loads an unexpected PHP configuration'}
 if($effective.expose_php -ne '1' -or $effective.display_errors -ne '1' -or $effective.log_errors -ne '' -or $effective.allow_url_include -ne '1' -or $effective.'session.cookie_httponly' -ne ''){throw 'IIS PHP challenge settings differ from CLI probe'}
 $effective | ConvertTo-Json | Set-Content C:\ProgramData\SummitLab\ForumCompetition-20261004\php-web-effective.json -Encoding UTF8
 $effective | ConvertTo-Json
} finally {if(Test-Path $path){Remove-Item -LiteralPath $path}}
