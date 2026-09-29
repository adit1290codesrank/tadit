# Render every slide of a deck to PNGs (slide1.png ...) via PowerPoint, for visual QA.
param([string]$Deck, [string]$OutDir)
New-Item -ItemType Directory -Force $OutDir | Out-Null
$pp = New-Object -ComObject PowerPoint.Application
try {
    $p = $pp.Presentations.Open((Resolve-Path $Deck).Path, $true, $false, $false)
    for ($i = 1; $i -le $p.Slides.Count; $i++) {
        $p.Slides.Item($i).Export((Join-Path $OutDir "slide$i.png"), "PNG", 2560, 1440)
    }
    $p.Close()
} finally {
    $pp.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
}
