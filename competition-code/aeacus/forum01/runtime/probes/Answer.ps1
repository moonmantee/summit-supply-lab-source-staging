function Get-AnswerValue([string]$Text) {
 $sections=[regex]::Matches($Text,'(?im)^Answer:[ \t]*\r?$')
 if($sections.Count -ne 1){return $null}
 return $Text.Substring($sections[0].Index+$sections[0].Length).Trim().ToLowerInvariant()
}
function Get-TextHash([string]$Value) {
 $sha=[Security.Cryptography.SHA256]::Create()
 try {return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-','').ToLowerInvariant()}
 finally {$sha.Dispose()}
}
