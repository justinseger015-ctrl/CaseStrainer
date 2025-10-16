# Minimal CaseStrainer Launcher - Direct & Simple
# Focuses on the most common use cases without complex menus

param(
    [switch]$Quick,      # Quick Start (fastest)
    [switch]$Fast,       # Fast Start (recommended) 
    [switch]$Full,       # Full Rebuild (when needed)
    [switch]$Auto,       # Auto-detect best option
    [switch]$Help
)

function Show-Help {
    Write-Host "Minimal CaseStrainer Launcher" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor White
    Write-Host "  .\cslaunch_minimal.ps1 -Quick    # Quick Start (fastest)" -ForegroundColor Green
    Write-Host "  .\cslaunch_minimal.ps1 -Fast     # Fast Start (recommended)" -ForegroundColor Cyan
    Write-Host "  .\cslaunch_minimal.ps1 -Full     # Full Rebuild (when needed)" -ForegroundColor Yellow
    Write-Host "  .\cslaunch_minimal.ps1 -Auto     # Auto-detect best option" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor White
    Write-Host "  .\cslaunch_minimal.ps1 -Fast     # Most common use case" -ForegroundColor Gray
    Write-Host "  .\cslaunch_minimal.ps1 -Quick    # When everything is already set up" -ForegroundColor Gray
    Write-Host "  .\cslaunch_minimal.ps1 -Full     # After major changes" -ForegroundColor Gray
    Write-Host ""
}

function Start-QuickLaunch {
    """Execute Quick Start - Fastest Launch."""
    Write-Host "🚀 Quick Start - Fastest Launch" -ForegroundColor Green
    Write-Host "Starting with minimal checks..." -ForegroundColor Gray
    
    try {
        # Just start the containers
        docker-compose -f docker-compose.prod.yml up -d
        
        Write-Host "✅ Quick Start completed successfully!" -ForegroundColor Green
        Write-Host "🌐 Application available at: https://localhost:443" -ForegroundColor Cyan
    }
    catch {
        Write-Host "❌ Quick Start failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

function Start-FastLaunch {
    """Execute Fast Start - Recommended."""
    Write-Host "🚀 Fast Start - Recommended" -ForegroundColor Cyan
    Write-Host "Restarting with latest code..." -ForegroundColor Gray
    
    # Clean Python cache
    Write-Host "🧹 Cleaning Python cache..." -ForegroundColor Yellow
    Get-ChildItem -Path . -Recurse -Include *.pyc | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Recurse -Directory -Include __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    
    try {
        # Restart containers
        docker-compose -f docker-compose.prod.yml down
        docker-compose -f docker-compose.prod.yml up -d
        
        Write-Host "✅ Fast Start completed successfully!" -ForegroundColor Green
        Write-Host "🌐 Application available at: https://localhost:443" -ForegroundColor Cyan
    }
    catch {
        Write-Host "❌ Fast Start failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

function Start-FullLaunch {
    """Execute Full Rebuild - Complete Reset."""
    Write-Host "🚀 Full Rebuild - Complete Reset" -ForegroundColor Yellow
    Write-Host "Performing complete rebuild..." -ForegroundColor Gray
    
    try {
        # Full rebuild
        docker-compose -f docker-compose.prod.yml down
        docker system prune -af --volumes
        docker-compose -f docker-compose.prod.yml build --no-cache
        docker-compose -f docker-compose.prod.yml up -d
        
        Write-Host "✅ Full Rebuild completed successfully!" -ForegroundColor Green
        Write-Host "🌐 Application available at: https://localhost:443" -ForegroundColor Cyan
    }
    catch {
        Write-Host "❌ Full Rebuild failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

function Start-AutoLaunch {
    """Auto-detect and execute the best option."""
    Write-Host "🔍 Auto-detecting best launch option..." -ForegroundColor Magenta
    
    # Check if Docker is running
    try {
        $dockerVersion = docker --version 2>$null
        if (-not $dockerVersion) {
            Write-Host "❌ Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
            exit 1
        }
    }
    catch {
        Write-Host "❌ Docker is not accessible. Please start Docker Desktop first." -ForegroundColor Red
        exit 1
    }
    
    # Check if containers are running
    try {
        $containers = docker ps --filter "name=casestrainer" --format "{{.Names}}" 2>$null
        if ($containers) {
            Write-Host "✅ Containers are running - using Quick Start" -ForegroundColor Green
            Start-QuickLaunch
        } else {
            Write-Host "ℹ️  No containers running - using Fast Start" -ForegroundColor Yellow
            Start-FastLaunch
        }
    }
    catch {
        Write-Host "ℹ️  Could not check containers - using Fast Start" -ForegroundColor Yellow
        Start-FastLaunch
    }
}

# Main execution
if ($Help) {
    Show-Help
    exit 0
} elseif ($Quick) {
    Start-QuickLaunch
} elseif ($Fast) {
    Start-FastLaunch
} elseif ($Full) {
    Start-FullLaunch
} elseif ($Auto) {
    Start-AutoLaunch
} else {
    # Default to Fast Start (most common use case)
    Write-Host "No option specified, using Fast Start (recommended)" -ForegroundColor Cyan
    Start-FastLaunch
} 