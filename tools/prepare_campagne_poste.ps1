# ============================================================
# P4(ping)/P5/P6 - Preparation campagne LOKO sur le poste de reference
# Lancer depuis la racine du projet :
#   powershell -ExecutionPolicy Bypass -File tools\prepare_campagne_poste.ps1
# Prerequis : Docker Desktop demarre, .env present (DEEPSEEK_API_KEY).
# Aucun secret ecrit dans les artefacts.
# ============================================================
$ErrorActionPreference = "Stop"
$TAG = "v1.3.0"
$ART = "eval/preparation-campagne/2026-07-17"
New-Item -ItemType Directory -Force -Path $ART | Out-Null

# --- .env ---
$envmap = @{}
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $envmap[$Matches[1]] = $Matches[2].Trim('"') }
}
if (-not $envmap["DEEPSEEK_API_KEY"]) { throw "DEEPSEEK_API_KEY absente de .env" }

# --- CE-6/CE-8 : ping DeepSeek 5 tokens, temp 0, TTFB ---
Write-Host ""
Write-Host "[CE-8] Ping DeepSeek (5 tokens, temp 0)..."
$body = '{"model":"deepseek-chat","messages":[{"role":"user","content":"ping"}],"max_tokens":5,"temperature":0}'
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$resp = Invoke-WebRequest -Uri "https://api.deepseek.com/chat/completions" -Method POST -Headers @{ "Authorization" = "Bearer " + $envmap["DEEPSEEK_API_KEY"]; "Content-Type" = "application/json" } -Body $body -UseBasicParsing
$sw.Stop()
$ttfb = $sw.ElapsedMilliseconds
$json = $resp.Content | ConvertFrom-Json
$lines = @(
  ("CE-8 - Ping provider LLM reel - " + (Get-Date -Format o)),
  ("provider=deepseek (custom, openai_compat)  model=" + $json.model),
  ("http=" + $resp.StatusCode + "  ttfb_total_ms=" + $ttfb),
  ("completion_tokens=" + $json.usage.completion_tokens + "  temp=0")
)
$lines | Out-File -Encoding utf8 "$ART/CE-8_ping.txt"
Write-Host ("  OK - TTFB " + $ttfb + " ms -> " + $ART + "/CE-8_ping.txt")

# --- P5 : build image [server,ml] ---
Write-Host ""
Write-Host "[P5] docker build -t loko:$TAG ..."
docker build -t "loko:$TAG" .
if ($LASTEXITCODE -ne 0) { throw "docker build FAIL" }
$digest = docker inspect --format "{{.Id}}" "loko:$TAG"
$sizeBytes = [long](docker inspect --format "{{.Size}}" "loko:$TAG")
$sizeGo = [math]::Round($sizeBytes / 1e9, 3)
Write-Host ("  digest=" + $digest + " size=" + $sizeGo + " Go (gate 1.6 Go max)")
if ($sizeGo -gt 1.6) { Write-Warning "TAILLE SUPERIEURE A 1,6 Go - gate A-1 en danger" }

# --- Tag + triple verification ---
Write-Host ""
Write-Host "[P5] Tag $TAG + triple verification version..."
git tag $TAG 2>$null
$gitDescribe = git describe --tags
$pyproject = (Select-String -Path pyproject.toml -Pattern 'version = "(.+)"').Matches[0].Groups[1].Value
$lokoVersion = docker run --rm "loko:$TAG" python -c "import loko; print(loko.__version__)"
$openapi = docker run --rm -e LOKO_MODE=desktop "loko:$TAG" python -c "from loko.main import app; print(app.version)"
$coherent = "DIVERGENTES - A CORRIGER"
if (("v" + $pyproject) -eq $TAG -and ("v" + $lokoVersion) -eq $TAG -and ("v" + $openapi) -eq $TAG) { $coherent = "COHERENTES" }
$lines = @(
  ("06 - Version de campagne - " + (Get-Date -Format o)),
  ("tag=" + $TAG + "  git_describe=" + $gitDescribe),
  ("commit=" + (git rev-parse HEAD)),
  ("digest=" + $digest),
  ("taille_bytes=" + $sizeBytes + " (=" + $sizeGo + " Go, docker inspect sur digest)"),
  ("pyproject=" + $pyproject),
  ("loko.__version__ (in-container)=" + $lokoVersion),
  ("openapi app.version (in-container)=" + $openapi),
  ("Triple verification tag / loko --version / OpenAPI : " + $coherent)
)
$lines | Out-File -Encoding utf8 "$ART/06_version.txt"
Get-Content "$ART/06_version.txt"

# --- P6 : fiche machine de reference ---
Write-Host ""
Write-Host "[P6] Fiche machine de reference..."
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$os = Get-CimInstance Win32_OperatingSystem
$ramGo = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$dockerV = docker version --format "{{.Server.Version}} ({{.Server.Os}}/{{.Server.Arch}})"
$wsl = ""
try { $wsl = (wsl --status 2>$null | Out-String).Trim() } catch {}
$lines = @(
  ("07 - Machine de reference - " + (Get-Date -Format o)),
  ("CPU=" + $cpu.Name + "  coeurs=" + $cpu.NumberOfCores + " threads=" + $cpu.NumberOfLogicalProcessors),
  ("RAM=" + $ramGo + " Go"),
  ("OS=" + $os.Caption + " " + $os.Version),
  ("Docker=" + $dockerV + " (Docker Desktop)"),
  ("WSL: " + $wsl)
)
$lines | Out-File -Encoding utf8 "$ART/07_machine_reference.txt"
Get-Content "$ART/07_machine_reference.txt"

Write-Host ""
Write-Host "=== TERMINE - artefacts : CE-8_ping.txt, 06_version.txt, 07_machine_reference.txt ==="
Write-Host "Le tag $TAG est pose localement. Ne pas pusher sans revue."
