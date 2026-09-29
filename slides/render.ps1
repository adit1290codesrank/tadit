# Render one slide of a deck to PNG (and optionally the whole deck to PDF) via PowerPoint.
param([string]$Deck, [int]$Slide = 5, [string]$Png, [string]$Pdf = "")
$pp = New-Object -ComObject PowerPoint.Application
try {
    $p = $pp.Presentations.Open((Resolve-Path $Deck).Path, $true, $false, $false)
    $p.Slides.Item($Slide).Export($Png, "PNG", 2560, 1440)
    if ($Pdf) { $p.SaveAs($Pdf, 32) }
    $p.Close()
} finally {
    $pp.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
}
