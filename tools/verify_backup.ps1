param(
    [string]$Destination = "tmp/backup-check-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot
$backupRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $Destination))
if (-not $backupRoot.StartsWith((Join-Path $projectRoot 'tmp') + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'El destino debe estar dentro de tmp del proyecto.'
}
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

$dbUser = (& docker compose exec -T db printenv POSTGRES_USER).Trim()
$dbName = (& docker compose exec -T db printenv POSTGRES_DB).Trim()
if ($LASTEXITCODE -ne 0 -or $dbUser -notmatch '^[A-Za-z_][A-Za-z0-9_]*$' -or
    $dbName -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
    throw 'No se pudieron leer nombres válidos de PostgreSQL desde Docker.'
}
$restoreName = "edh_backup_check_$(Get-Date -Format 'yyyyMMddHHmmss')"
$created = $false
try {
    & docker compose exec -T db pg_dump -U $dbUser -d $dbName -Fc -f /tmp/edh-backup-check.dump
    if ($LASTEXITCODE -ne 0) { throw 'Falló pg_dump.' }
    & docker compose cp db:/tmp/edh-backup-check.dump (Join-Path $backupRoot 'database.dump')
    if ($LASTEXITCODE -ne 0) { throw 'Falló la copia del respaldo PostgreSQL.' }
    $mediaRoot = Join-Path $backupRoot 'media'
    New-Item -ItemType Directory -Force -Path $mediaRoot | Out-Null
    & docker compose cp web:/app/media/. $mediaRoot
    if ($LASTEXITCODE -ne 0) { throw 'Falló la copia del volumen de PDFs.' }

    & docker compose exec -T db createdb -U $dbUser $restoreName
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la base temporal de restauración.' }
    $created = $true
    & docker compose exec -T db pg_restore -U $dbUser -d $restoreName /tmp/edh-backup-check.dump
    if ($LASTEXITCODE -ne 0) { throw 'Falló la restauración PostgreSQL.' }
    $counts = 'SELECT (SELECT count(*) FROM rutas_route), (SELECT count(*) FROM rutas_part), (SELECT count(*) FROM rutas_issueddocument);'
    $original = (& docker compose exec -T db psql -U $dbUser -d $dbName -tAc $counts).Trim()
    $restored = (& docker compose exec -T db psql -U $dbUser -d $restoreName -tAc $counts).Trim()
    if ($original -ne $restored) { throw "Los conteos difieren: origen $original, restaurado $restored" }
    $mediaFiles = @(Get-ChildItem -LiteralPath $mediaRoot -Recurse -File)
    $documents = @(& docker compose exec -T db psql -U $dbUser -d $restoreName -tAc "SELECT pdf || '|' || sha256 FROM rutas_issueddocument;")
    foreach ($document in $documents) {
        if (-not $document.Trim()) { continue }
        $fields = $document.Trim() -split '\|', 2
        $relative = $fields[0].Replace('/', [System.IO.Path]::DirectorySeparatorChar)
        $pdfPath = [System.IO.Path]::GetFullPath((Join-Path $mediaRoot $relative))
        if (-not $pdfPath.StartsWith($mediaRoot + [System.IO.Path]::DirectorySeparatorChar,
                [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Ruta de PDF fuera del respaldo: $relative"
        }
        if (-not (Test-Path -LiteralPath $pdfPath -PathType Leaf)) {
            throw "Falta el PDF restaurado: $relative"
        }
        $digest = (Get-FileHash -LiteralPath $pdfPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($digest -ne $fields[1].ToLowerInvariant()) {
            throw "Hash distinto para el PDF: $relative"
        }
    }
    Write-Output "Restauración temporal verificada: rutas|piezas|documentos = $restored"
    Write-Output "Respaldo en $backupRoot; archivos de medios copiados: $($mediaFiles.Count)"
    if ($mediaFiles.Count -eq 0) {
        Write-Output 'Todavía no hay PDFs emitidos para validar un vínculo documento-archivo real.'
    }
} finally {
    if ($created) {
        & docker compose exec -T db dropdb -U $dbUser $restoreName
        if ($LASTEXITCODE -ne 0) { Write-Warning "Elimina manualmente la base temporal $restoreName." }
    }
}
