# Deploy Vue Build Files to Static Directories
# This script copies the built Vue files to the correct static directories for serving

Write-Host "Building Vue application..." -ForegroundColor Green
Set-Location casestrainer-vue-new
npm run build
Set-Location ..

Write-Host "Copying built files to static directories..." -ForegroundColor Green

# Create directories if they don't exist
New-Item -ItemType Directory -Force -Path "static/vue" | Out-Null
New-Item -ItemType Directory -Force -Path "static/assets" | Out-Null

# Copy main HTML file
Copy-Item "casestrainer-vue-new/dist/index.html" "static/vue/index.html" -Force

# Copy all assets (CSS, JS, and other files) from dist/assets to static/assets
$sourceDir = "casestrainer-vue-new/dist/assets"
$destDir = "static/assets"

# Ensure the destination directory exists
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

# Get all files from the source directory
$files = Get-ChildItem -Path $sourceDir -File -Recurse

foreach ($file in $files) {
    $relativePath = $file.FullName.Substring($sourceDir.Length).TrimStart('\')
    $destPath = Join-Path -Path $destDir -ChildPath $relativePath
    
    # Ensure the destination directory exists
    $destFile = New-Item -ItemType File -Path $destPath -Force
    
    # Copy the file
    Copy-Item -Path $file.FullName -Destination $destFile.FullName -Force
}

Write-Host "Deployment completed successfully!" -ForegroundColor Green
Write-Host "Files are now available at:" -ForegroundColor Yellow
Write-Host "  - /casestrainer/vue/index.html" -ForegroundColor Cyan
Write-Host "  - /casestrainer/assets/" -ForegroundColor Cyan