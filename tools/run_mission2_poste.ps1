# ============================================================
# MISSION 2 - Campagne R0+R1 (volets A+B, gates G-0..G-3) - protocole v2.2
# Lancer depuis la racine du projet :
#   powershell -ExecutionPolicy Bypass -File tools\run_mission2_poste.ps1
# REGLE ABSOLUE : aucun commit, aucune correction pendant la campagne.
# Le runner calcule les verdicts ; l'agent analyse les artefacts ensuite.
# ============================================================
$ErrorActionPreference = "Continue"
$TAG = "v1.3.0"
$BOT = "fa4d8b2d-548f-457b-bf65-acbc61a39cbb"
$CAMP = "eval/recette-integrale/2026-07-17-v1.3.0"

# --- Charger .env dans l'environnement du process (herite par docker/python) ---
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$') {
    [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), "Process")
  }
}
$env:LOKO_MACHINE_ID = "poste-ref-ryzen7-5800HS-win11-docker28.5-wsl2"

# --- Verifications d'entree ---
$describe = git describe --tags --exact-match 2>$null
if ($describe -ne $TAG) { Write-Host "ERREUR: HEAD n'est pas sur $TAG (describe=$describe)"; exit 2 }
$dirty = (git status --porcelain | Measure-Object -Line).Lines
if ($dirty -ne 0) { Write-Host "ERREUR: worktree non propre ($dirty lignes)"; git status --porcelain; exit 2 }

# --- Rebuild image sur le commit tague (cache Docker => rapide) ---
Write-Host "[1/3] docker build -t loko:$TAG (commit $(git rev-parse --short HEAD))..."
docker build -t "loko:$TAG" .
if ($LASTEXITCODE -ne 0) { Write-Host "ERREUR: docker build FAIL"; exit 2 }
$digest = docker inspect --format "{{.Id}}" "loko:$TAG"
Write-Host ("  digest=" + $digest)

# --- Lancement du runner (mode reel, in-container) ---
Write-Host "[2/3] Lancement du runner de campagne..."
python tools/run_campaign.py --bot-dir "data/bots/$BOT" --campaign-dir $CAMP --image "loko:$TAG" --tag $TAG
$rc = $LASTEXITCODE

# --- Cloture ---
Write-Host "[3/3] Exit code runner : $rc  (0=gates PASS, 1=gate FAIL, 2=erreur runner)"
Write-Host ("Rapport : " + $CAMP + "/RAPPORT_CAMPAGNE.md")
Write-Host "NE PAS COMMITTER pendant l'analyse. L'archivage (git add -f) se fera apres verdict et revue."
exit $rc
