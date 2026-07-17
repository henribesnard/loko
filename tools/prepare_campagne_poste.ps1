# ============================================================
# P4(ping)/P5/P6 — Préparation campagne LOKO sur le poste de référence
# Mission « préparation de campagne » 2026-07-17 — à lancer depuis la racine du projet :
#   powershell -ExecutionPolicy Bypass -File tools\prepare_campagne_poste.ps1
# Prérequis : Docker Desktop démarré, .env présent (DEEPSEEK_API_KEY, LOKO_SECRET_KEY).
# Aucun secret n'est écrit dans les artefacts.
# ============================================================
$ErrorActionPreference = "Stop"
$TAG = "v1.3.0"
$ART = "eval/preparation-campagne/2026-07-17"
New-Item -ItemType Directory -Force -Path $ART | Out-Null

# --- .env ---
$envmap = @{}
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $envmap[$Matches[1]] = $Matches[2].Trim('"').Trim("'") }
}
if (-not $envmap["DEEPSEEK_API_KEY"]) { throw "DEEPSEEK_API_KEY absente de .env" }

# --- CE-6/CE-8 : ping DeepSeek 5 tokens, temp 0, TTFB ---
Write-Host "`n[CE-8] Ping DeepSeek (5 tokens, temp 0)..."
$body = '{"model":"deepseek-chat","messages":[{"role":"user","content":"ping"}],"max_tokens":5,"temperature":0}'
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$resp = Invoke-WebRequest -Uri "https://api.deepseek.com/chat/completions" -Method POST `
  -Headers @{ "Authorization" = "Bearer $($envmap['DEEPSEEK_API_KEY'])"; "Content-Type" = "application/json" } `
  -Body $body -UseBasicParsing
$sw.Stop()
$ttfb = $sw.ElapsedMilliseconds
$json = $resp.Content | ConvertFrom-Json
@"
CE-8 — Ping provider LLM réel — $(Get-Date -Format o)
provider=deepseek (custom, openai_compat)  model=$($json.model)
http=$($resp.StatusCode)  ttfb_total_ms=$ttfb
completion_tokens=$($json.usage.completion_tokens)  temp=0
"@ | Out-File -Encoding utf8 "$ART/CE-8_ping.txt"
Write-Host "  OK — TTFB ${ttfb} ms → $ART/CE-8_ping.txt"

# --- P5 : build image [server,ml] ---
Write-Host "`n[P5] docker build -t loko:$TAG ..."
docker build -t "loko:$TAG" . ; if ($LASTEXITCODE -ne 0) { throw "docker build FAIL" }
$digest = docker inspect --format='{{index .Id}}' "loko:$TAG"
$sizeBytes = [long](docker inspect --format='{{.Size}}' "loko:$TAG")
$sizeGo = [math]::Round($sizeBytes / 1e9, 3)
Write-Host "  digest=$digest size=$sizeGo Go (gate <= 1.6 Go)"
if ($sizeGo -gt 1.6) { Write-Warning "TAILLE > 1,6 Go — gate A-1 en danger" }

# --- Tag + triple vérification ---
Write-Host "`n[P5] Tag $TAG + triple vérification version..."
git tag $TAG 2>$null
$gitDescribe = git describe --tags
$pyproject = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
$lokoVersion = docker run --rm "loko:$TAG" python -c "import loko; print(loko.__version__)"
$openapi = docker run --rm -e LOKO_MODE=desktop "loko:$TAG" python -c "from loko.main import app; print(app.version)"
@"
06 — Version de campagne — $(Get-Date -Format o)
tag=$TAG          git describe=$gitDescribe
commit=$(git rev-parse HEAD)
digest=$digest
taille_bytes=$sizeBytes (=$sizeGo Go, docker inspect sur digest)
pyproject=$pyproject
loko.__version__ (in-container)=$lokoVersion
openapi app.version (in-container)=$openapi
Triple vérification : tag / loko --version / OpenAPI $( if ("v$pyproject" -eq $TAG -and "v$lokoVersion" -eq $TAG -and "v$openapi" -eq $TAG) { "= COHÉRENTES" } else { "= DIVERGENTES — À CORRIGER" } )
"@ | Out-File -Encoding utf8 "$ART/06_version.txt"
Get-Content "$ART/06_version.txt"

# --- P6 : fiche machine de référence ---
Write-Host "`n[P6] Fiche machine de référence..."
$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1)
$os = Get-CimInstance Win32_OperatingSystem
$ramGo = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$dockerV = docker version --format '{{.Server.Version}} ({{.Server.Os}}/{{.Server.Arch}})'
$wsl = (wsl --status 2>$null | Out-String).Trim()
@"
07 — Machine de référence — $(Get-Date -Format o)
CPU=$($cpu.Name)  coeurs=$($cpu.NumberOfCores) threads=$($cpu.NumberOfLogicalProcessors)
RAM=$ramGo Go
OS=$($os.Caption) $($os.Version)
Docker=$dockerV (Docker Desktop, backend WSL2)
WSL: $wsl
"@ | Out-File -Encoding utf8 "$ART/07_machine_reference.txt"
Get-Content "$ART/07_machine_reference.txt"

Write-Host "`n=== TERMINÉ — artefacts dans $ART : CE-8_ping.txt, 06_version.txt, 07_machine_reference.txt ==="
Write-Host "Puis : git add $ART && git commit -m 'docs(campagne): artefacts P4-ping/P5/P6' (le tag $TAG est posé localement, ne pas pusher sans revue)"
