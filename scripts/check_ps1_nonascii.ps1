# ASCII-only by design: audit ps1 files for non-ASCII characters inside CODE
# strings (comments are inert for parsing, but we report them separately).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check_ps1_nonascii.ps1 <file.ps1> ...
param([Parameter(Mandatory = $true)][string[]]$Files)
$bad = 0
foreach ($f in $Files) {
    $errs = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        (Resolve-Path $f), [ref]$null, [ref]$errs)
    if ($errs.Count -gt 0) {
        Write-Output "PARSE-FAIL $f : $($errs[0].Message)"
        $bad++
        continue
    }
    $found = @()
    # all string constants (incl. literal segments of expandable strings)
    $strings = $ast.FindAll({
        param($n) $n -is [System.Management.Automation.Language.StringConstantExpressionAst]
    }, $true)
    foreach ($s in $strings) {
        if ($s.Value -match '[^\x00-\x7F]') {
            $found += ("  line {0}: {1}" -f $s.Extent.StartLineNumber,
                $s.Value.Substring(0, [Math]::Min(60, $s.Value.Length)))
        }
    }
    # command names must be ASCII (defensive)
    $cmds = $ast.FindAll({
        param($n) $n -is [System.Management.Automation.Language.CommandAst]
    }, $true)
    foreach ($c in $cmds) {
        $name = $c.GetCommandName()
        if ($name -and $name -match '[^\x00-\x7F]') {
            $found += "  line $($c.Extent.StartLineNumber): CMD $name"
        }
    }
    if ($found.Count -eq 0) {
        Write-Output "CLEAN $f"
    } else {
        Write-Output "NONASCII-IN-CODE $f"
        $found | ForEach-Object { Write-Output $_ }
        $bad++
    }
}
if ($bad -eq 0) { Write-Output "summary: all clean" }
else { Write-Output "summary: $bad file(s) need fix" }
exit $bad
