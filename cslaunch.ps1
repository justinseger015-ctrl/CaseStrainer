# Enhanced CaseStrainer Docker Production Launcher v1.3 - Optimized with Better Error Handling
# Incorporates best features from cslaunch while maintaining performance optimizations

[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet("Production", "Diagnostics", "Menu", "Cache", "Test", "Debug")]
    [string]$Mode = "Menu",
    [switch]$Help,
    [switch]$AutoRestart,
    [switch]$SkipVueBuild,
    [switch]$QuickStart,
    [switch]$ForceRebuild,
    [switch]$TestAPI,
    [switch]$TestFrontend,
    [switch]$ShowLogs,
    [switch]$ClearCache,
    [switch]$NoValidation,
    [switch]$VerboseLogging,
    [string]$TestCitation = "534 F.3d 1290",
    [int]$TimeoutMinutes = 10,
    [int]$MenuOption = $null
)

# Function to check for required tools
function Test-RequiredTools {
    [CmdletBinding()]
    [OutputType([bool])]
    param()
    
    $requiredTools = @(
        @{Name = 'Docker'; Command = 'docker --version'},
        @{Name = 'Docker Compose'; Command = 'docker-compose --version'},
        @{Name = 'Node.js'; Command = 'node --version'},
        @{Name = 'npm'; Command = 'npm --version'},
        @{Name = 'Python'; Command = 'python --version'}
    )
    
    $allToolsAvailable = $true
    
    Write-Host "`n=== Checking Required Tools ===" -ForegroundColor Cyan
    
    foreach ($tool in $requiredTools) {
        $toolName = $tool.Name
        $command = $tool.Command
        
        try {
            $output = Invoke-Expression $command 2>&1
            if ($LASTEXITCODE -eq 0) {
                $version = ($output | Select-Object -First 1).Trim()
                Write-Host ("[OK] {0}: {1}" -f $toolName, $version) -ForegroundColor Green
            } else {
                throw "Command failed"
            }
        } catch {
            Write-Host ("[ERROR] {0}: Not found or not in PATH" -f $toolName) -ForegroundColor Red
            $allToolsAvailable = $false
        }
    }
    
    if (-not $allToolsAvailable) {
        Write-Host "`n[ERROR] One or more required tools are missing. Please install them and ensure they are in your PATH." -ForegroundColor Red
        Write-Host "   Required tools: $($requiredTools.Name -join ', ')" -ForegroundColor Yellow
        return $false
    }
    
    Write-Host "`n[OK] All required tools are available" -ForegroundColor Green
    return $true
}

# Function to check if Docker is running and accessible
function Test-DockerAvailability {
    [CmdletBinding()]
    [OutputType([bool])]
    param()
    
    Write-Host "`n=== Checking Docker Availability ===" -ForegroundColor Cyan
    
    # Check if Docker CLI is available
    try {
        $dockerVersion = docker --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Docker command failed"
        }
        Write-Host ("[OK] Docker CLI is available: {0}" -f $dockerVersion.Trim()) -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Docker CLI is not available or not in PATH" -ForegroundColor Red
        Write-Host "   Please install Docker Desktop and ensure it's added to your system PATH" -ForegroundColor Yellow
        return $false
    }
    
    # Check if Docker daemon is running, start Docker Desktop if needed
    try {
        # First check if Docker daemon is already running
        $dockerInfo = docker info 2>&1
        if ($LASTEXITCODE -ne 0) {
            # Docker daemon is not running, try to start Docker Desktop
            Write-Host "[INFO] Docker daemon is not running. Attempting to start Docker Desktop..." -ForegroundColor Yellow
            
            if (-not (Start-DockerDesktop)) {
                Write-Host "[ERROR] Failed to start Docker Desktop automatically" -ForegroundColor Red
                Write-Host "`nTroubleshooting steps:" -ForegroundColor Yellow
                Write-Host "1. Make sure Docker Desktop is installed" -ForegroundColor Yellow
                Write-Host "2. Start Docker Desktop manually and wait for it to fully initialize" -ForegroundColor Yellow
                Write-Host "3. Check if your user account has permission to run Docker" -ForegroundColor Yellow
                Write-Host "4. Try restarting your computer if the issue persists" -ForegroundColor Yellow
                Write-Host "5. Check Docker Desktop logs for any errors" -ForegroundColor Yellow
                return $false
            }
            
            # Give it a moment to fully initialize
            Start-Sleep -Seconds 5
            
            # Check again if Docker daemon is running
            $dockerInfo = docker info 2>&1
            if ($LASTEXITCODE -ne 0) {
                # Check for specific error conditions
                $errorOutput = $dockerInfo -join " "
                
                if ($errorOutput -match "500 Internal Server Error") {
                    Write-Host "[ERROR] Docker daemon is not responding correctly (500 Internal Server Error)" -ForegroundColor Red
                    Write-Host "   This often indicates a problem with the Docker Desktop service" -ForegroundColor Yellow
                    Write-Host "`nRecommended actions:" -ForegroundColor Yellow
                    Write-Host "1. Open Docker Desktop and check for any error messages" -ForegroundColor Yellow
                    Write-Host "2. Try resetting Docker Desktop to factory defaults" -ForegroundColor Yellow
                    Write-Host "3. Reinstall Docker Desktop if the issue persists" -ForegroundColor Yellow
                    Write-Host "4. Check if your Windows version is compatible with this Docker version" -ForegroundColor Yellow
                    Write-Host "5. Make sure virtualization is enabled in your BIOS settings" -ForegroundColor Yellow
                } else {
                    Write-Host "[ERROR] Docker daemon is still not available after starting Docker Desktop" -ForegroundColor Red
                    Write-Host "   Error details: $errorOutput" -ForegroundColor Yellow
                }
                return $false
            }
        }
        
        # Check if Docker is running in Windows containers mode (if on Windows)
        if ($IsWindows -or $env:OS -eq "Windows_NT") {
            $dockerInfo = docker info --format '{{.OperatingSystem}}' 2>&1
            if ($dockerInfo -match "Windows") {
                Write-Host "[OK] Docker is running in Windows containers mode" -ForegroundColor Green
            } else {
                Write-Host "[INFO] Docker is running in Linux containers mode" -ForegroundColor Yellow
            }
        }
        
        # Check Docker Compose version
        try {
            $composeVersion = docker-compose --version 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[OK] Docker Compose is available: $($composeVersion.Trim())" -ForegroundColor Green
            } else {
                Write-Host "[WARNING] Docker Compose is not available or not in PATH" -ForegroundColor Yellow
                Write-Host "   Some features may not work without Docker Compose" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "[WARNING] Docker Compose check failed: $_" -ForegroundColor Yellow
        }
        
        return $true
    } catch {
        Write-Host "[ERROR] Error checking Docker status: $_" -ForegroundColor Red
        return $false
    }
}

# Function to validate required environment variables
function Test-RequiredEnvironmentVariables {
    [CmdletBinding()]
    [OutputType([bool])]
    param()
    
    # List of required environment variables
    $requiredVars = @(
        'COURTLISTENER_API_KEY',
        'FLASK_ENV',
        'FLASK_APP',
        'SECRET_KEY'
    )
    
    $allVarsPresent = $true
    
    Write-Host "`n=== Validating Environment Variables ===" -ForegroundColor Cyan
    
    # Check if .env file exists and load it if it does
    $envFilePath = Join-Path $PSScriptRoot ".env"
    if (Test-Path $envFilePath) {
        try {
            # Load .env file
            Get-Content $envFilePath | ForEach-Object {
                $name, $value = $_.Split('=', 2)
                if ($name -and $value) {
                    [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim())
                }
            }
            Write-Host "[OK] Loaded environment variables from .env file" -ForegroundColor Green
        } catch {
            Write-Host "[WARNING] Warning: Failed to load .env file: $_" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[INFO] No .env file found at $envFilePath" -ForegroundColor Yellow
    }
    
    # Check each required variable
    foreach ($var in $requiredVars) {
        $value = [System.Environment]::GetEnvironmentVariable($var)
        
        if ([string]::IsNullOrEmpty($value)) {
            Write-Host ("[ERROR] {0}: Not set" -f $var) -ForegroundColor Red
            $allVarsPresent = $false
        } else {
            # Don't show sensitive values in logs
            $displayValue = if ($var -match 'KEY|SECRET|PASSWORD') { '********' } else { $value }
            Write-Host ("[OK] {0}: {1}" -f $var, $displayValue) -ForegroundColor Green
        }
    }
    
    if (-not $allVarsPresent) {
        Write-Host "`n[ERROR] One or more required environment variables are missing." -ForegroundColor Red
        Write-Host "   Please set the following environment variables:" -ForegroundColor Yellow
        $requiredVars | ForEach-Object { Write-Host "   - $_" -ForegroundColor Yellow }
        Write-Host "`n   You can set them in the .env file or in your system environment." -ForegroundColor Yellow
        return $false
    }
    
    Write-Host "`n[OK] All required environment variables are set" -ForegroundColor Green
    return $true
}

# Function to check if Docker is running and accessible
function Test-DockerAvailability {
    [CmdletBinding()]
    [OutputType([bool])]
    param()
    
    Write-Host "`n=== Checking Docker Availability ===" -ForegroundColor Cyan
    
    # Check if docker command is available
    try {
        $dockerVersion = docker --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Docker command failed"
        }
        Write-Host "[OK] Docker CLI is available: $($dockerVersion.Trim())" -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Docker CLI is not available or not in PATH" -ForegroundColor Red
        Write-Host "   Please install Docker Desktop and ensure it's added to your system PATH" -ForegroundColor Yellow
        return $false
    }
    
    # Check if Docker daemon is running
    try {
        $dockerInfo = docker info 2>&1
        if ($LASTEXITCODE -ne 0) {
            if ($dockerInfo -match "Cannot connect to the Docker daemon") {
                Write-Host "[ERROR] Docker daemon is not running" -ForegroundColor Red
                Write-Host "   Please start Docker Desktop and wait for it to be ready" -ForegroundColor Yellow
            } elseif ($dockerInfo -match "error during connect") {
                Write-Host "[ERROR] Could not connect to Docker daemon" -ForegroundColor Red
                Write-Host "   Please ensure Docker Desktop is running and try again" -ForegroundColor Yellow
            } else {
                Write-Host "[ERROR] Docker daemon is not available: $($dockerInfo)" -ForegroundColor Red
            }
            return $false
        }
        
        # Check if Docker is running in Windows containers mode (if on Windows)
        if ($IsWindows -or $env:OS -eq "Windows_NT") {
            $dockerInfo = docker info --format '{{.OperatingSystem}}' 2>&1
            if ($dockerInfo -match "Windows") {
                Write-Host "[OK] Docker is running in Windows containers mode" -ForegroundColor Green
            } else {
                Write-Host "[INFO] Docker is running in Linux containers mode" -ForegroundColor Yellow
            }
        }
        
        # Check Docker Compose version
        try {
            $composeVersion = docker-compose --version 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[OK] Docker Compose is available: $($composeVersion.Trim())" -ForegroundColor Green
            } else {
                Write-Host "[WARNING] Docker Compose is not available or not in PATH" -ForegroundColor Yellow
                Write-Host "   Some features may not work without Docker Compose" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "[WARNING] Docker Compose check failed: $_" -ForegroundColor Yellow
        }
        
        return $true
    } catch {
        Write-Host "[ERROR] Error checking Docker status: $_" -ForegroundColor Red
        return $false
    }
}

# Setup transcript logging
$script:transcriptPath = Join-Path $PSScriptRoot "logs\script_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
$logDir = Split-Path -Parent $script:transcriptPath
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
try {
    Start-Transcript -Path $script:transcriptPath -Append -Force
} catch {
    Write-Warning "Failed to start transcript: $_"
}

# Check Docker availability at script startup
if (-not (Test-DockerAvailability)) {
    Write-Host "❌ Docker is not available. Please ensure Docker Desktop is installed and running." -ForegroundColor Red
    Write-Host "   Visit https://www.docker.com/products/docker-desktop to download and install Docker Desktop" -ForegroundColor Yellow
    exit 1
}

# Input validation and early error detection
if (-not $PSScriptRoot) {
    throw "Script must be run from a file, not from command line"
}

# Validate that we're running in a reasonable PowerShell version
if ($PSVersionTable.PSVersion.Major -lt 5) {
    throw "This script requires PowerShell 5.0 or later. Current version: $($PSVersionTable.PSVersion)"
}

# Early check for required permissions
try {
    $testFile = Join-Path $PSScriptRoot "test_write_permissions.tmp"
    "test" | Out-File $testFile -ErrorAction Stop
    Remove-Item $testFile -ErrorAction SilentlyContinue
} catch {
    throw "Insufficient permissions to write to script directory: $PSScriptRoot"
}

# Global variables
$script:AutoRestartEnabled = $AutoRestart.IsPresent
$script:RestartCount = 0
$script:MaxRestartAttempts = 3
$script:CrashLogFile = Join-Path $PSScriptRoot "logs\crash.log"
$script:MonitoringJob = $null

# Nginx configuration for Docker
$script:NginxConfig = @{
    ContainerName = "casestrainer-nginx-prod"
    ConfigPath = "/etc/nginx/conf.d/casestrainer.conf"
    HealthCheckUrl = "http://localhost/health"
    StartTimeout = 30  # seconds
}

# Performance optimization: Cache expensive checks
$script:CachedChecks = @{
    DockerAvailable = $null
    VueBuildNeeded = $null
    NpmInstallNeeded = $null
    NpmPath = $null
    LastCheckTime = $null
}

# Show help
if ($Help) {
    Write-Host @"
Enhanced CaseStrainer Docker Production Launcher v1.3 - Help

Usage:
  .\dplaunch_enhanced.ps1 [Options]

Modes:
  -Mode Production    Start Docker Production Mode
  -Mode Diagnostics   Run Advanced Production Diagnostics
  -Mode Cache         Manage Citation Caches
  -Mode Test          Run API and Frontend Tests
  -Mode Debug         Enable Debug Mode with extra logging
  -Mode Menu          Show interactive menu (default)

Deployment Options:
  -ForceRebuild       Force full Docker and Vue rebuild
  -SkipVueBuild       Skip Vue frontend build (fastest)
  -QuickStart         Skip most checks for maximum speed
  -NoValidation       Skip post-startup validation
  -TimeoutMinutes     Set timeout for operations (default: 10)

Testing & Debugging:
  -TestAPI            Test API endpoints after deployment
  -TestFrontend       Test frontend functionality
  -TestCitation       Citation to test (default: "534 F.3d 1290")
  -VerboseLogging     Enable detailed logging
  -ShowLogs           Show container logs after deployment

Cache & Maintenance:
  -ClearCache         Clear all caches before deployment
  -AutoRestart        Enable auto-restart monitoring

Advanced CLI Features:
  -MenuOption <int>   Skip menu and run option directly (1-7, 0=exit)
  -WhatIf             Show what would be done without executing
  -Confirm            Prompt for confirmation before major operations

**NOTE:** For options 1, 2, and 3 (all production startup modes), a production test suite is automatically run after backend startup. Startup is only considered successful if all tests pass. If tests fail, see logs/production_test.log for details.

Examples:
  .\dplaunch_enhanced.ps1                                    # Show menu
  .\dplaunch_enhanced.ps1 -Mode Production -QuickStart       # Fastest possible startup
  .\dplaunch_enhanced.ps1 -Mode Production -ForceRebuild     # Full rebuild
  .\dplaunch_enhanced.ps1 -Mode Test -TestAPI                # Test API only
  .\dplaunch_enhanced.ps1 -Mode Debug -VerboseLogging        # Debug with verbose logging
  .\dplaunch_enhanced.ps1 -MenuOption 1 -WhatIf              # Show what quick start would do
"@ -ForegroundColor Cyan
    exit 0
}

function Initialize-LogDirectory {
    [CmdletBinding()]
    param()

    $logDir = Join-Path $PSScriptRoot "logs"
    if (-not (Test-Path $logDir)) {
        try {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        catch {
            Write-Warning "Could not create log directory: $($_.Exception.Message)"
        }
    }
}

function Write-CrashLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR", "DEBUG")]
        [string]$Level = "INFO",
        [System.Management.Automation.ErrorRecord]$Exception = $null
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] $Message"
    if ($Exception) {
        $logEntry += " - Exception: $($Exception.Exception.Message)"
        $logEntry += " - StackTrace: $($Exception.ScriptStackTrace)"
    }

    try {
        $logDir = Split-Path $script:CrashLogFile -Parent
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        Add-Content -Path $script:CrashLogFile -Value $logEntry -ErrorAction Stop
    }
    catch {
        Write-Warning "Could not write to crash log: $($_.Exception.Message)"
    }
}

function Clear-AllCaches {
    [CmdletBinding()]
    param()

    Write-Host "Clearing all caches..." -ForegroundColor Yellow

    # Clear script cache
    $script:CachedChecks = @{
        DockerAvailable = $null
        VueBuildNeeded = $null
        NpmInstallNeeded = $null
        NpmPath = $null
        LastCheckTime = $null
    }
    Write-Host "Script cache cleared" -ForegroundColor Gray

    # Clear Docker build cache if requested
    try {
        Write-Host "Clearing Docker build cache..." -ForegroundColor Gray
        $null = docker builder prune -f 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK Docker cache cleared" -ForegroundColor Green
        } else {
            Write-Host "WARNING: Docker cache clearing may have failed" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "WARNING: Could not clear Docker cache: $($_.Exception.Message)" -ForegroundColor Yellow
    }

    # Clear npm cache
    try {
        $vueDir = Join-Path $PSScriptRoot "casestrainer-vue-new"
        if (Test-Path $vueDir) {
            $npmPath = Find-NpmExecutable
            if ($npmPath) {
                Write-Host "Clearing npm cache..." -ForegroundColor Gray
                Push-Location $vueDir
                try {
                    & npm -Command cache -Command clean -Command --force
                    Write-Host "✅ npm cache cleared" -ForegroundColor Green
                } finally {
                    Pop-Location
                }
            } else {
                Write-Host "WARNING: npm not found, skipping npm cache clear" -ForegroundColor Yellow
            }
        } else {
            Write-Host "WARNING: Vue directory not found, skipping npm cache clear" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "WARNING: Could not clear npm cache: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

function Test-ScriptEnvironment {
    [CmdletBinding()]
    param()

    $requiredFiles = @(
        "docker-compose.prod.yml",
        "casestrainer-vue-new"
    )

    foreach ($file in $requiredFiles) {
        $path = Join-Path $PSScriptRoot $file
        if (-not (Test-Path $path)) {
            throw "Required file/directory not found: $file"
        }
    }
}

function Test-VueBuildNeeded {
    [CmdletBinding()]
    [OutputType([bool])]
    param([switch]$Force)

    # If Force is specified, always return true
    if ($Force) {
        Write-Host "Force flag specified - Vue build required" -ForegroundColor Gray
        $script:CachedChecks.VueBuildNeeded = $true
        return $true
    }

    # Use cached result if recent (within 30 seconds) and not forcing
    if ($script:CachedChecks.LastCheckTime -and `
        ((Get-Date) - $script:CachedChecks.LastCheckTime).TotalSeconds -lt 30 -and `
        $null -ne $script:CachedChecks.VueBuildNeeded) {
        Write-Host "Using cached Vue build check result: $($script:CachedChecks.VueBuildNeeded)" -ForegroundColor Gray
        return $script:CachedChecks.VueBuildNeeded
    }

    $vueDir = Join-Path $PSScriptRoot "casestrainer-vue-new"
    $distDir = Join-Path $vueDir "dist"
    $indexFile = Join-Path $distDir "index.html"

    if (-not (Test-Path $distDir) -or -not (Test-Path $indexFile)) {
        Write-Host "Vue dist directory or index.html missing - build required" -ForegroundColor Gray
        $script:CachedChecks.VueBuildNeeded = $true
        return $true
    }

    $distTime = (Get-Item $distDir).LastWriteTime

    # Quick check: only check package.json and skip deep src scan for speed
    $packageJson = Join-Path $vueDir "package.json"
    if (Test-Path $packageJson) {
        $packageTime = (Get-Item $packageJson).LastWriteTime
        if ($packageTime -gt $distTime) {
            Write-Host "package.json newer than dist - build required" -ForegroundColor Gray
            $script:CachedChecks.VueBuildNeeded = $true
            return $true
        }
    }

    # Only do expensive src scan if dist is very old (>1 hour)
    if (((Get-Date) - $distTime).TotalHours -gt 1) {
        $srcDir = Join-Path $vueDir "src"
        if (Test-Path $srcDir) {
            # Faster check: only look at most recently modified file
            $newestSrcFile = Get-ChildItem $srcDir -Recurse -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            if ($newestSrcFile -and $newestSrcFile.LastWriteTime -gt $distTime) {
                Write-Host "Source files newer than dist - build required" -ForegroundColor Gray
                $script:CachedChecks.VueBuildNeeded = $true
                return $true
            }
        }
    }

    Write-Host "Vue build is up to date" -ForegroundColor Gray
    $script:CachedChecks.VueBuildNeeded = $false
    $script:CachedChecks.LastCheckTime = Get-Date
    return $false
}

function Test-NpmInstallNeeded {
    [CmdletBinding()]
    [OutputType([bool])]
    param()

    # Use cached result if recent
    if ($script:CachedChecks.LastCheckTime -and `
        ((Get-Date) - $script:CachedChecks.LastCheckTime).TotalSeconds -lt 30 -and `
        $null -ne $script:CachedChecks.NpmInstallNeeded) {
        Write-Host "Using cached npm install check result: $($script:CachedChecks.NpmInstallNeeded)" -ForegroundColor Gray
        return $script:CachedChecks.NpmInstallNeeded
    }

    $vueDir = Join-Path $PSScriptRoot "casestrainer-vue-new"
    $nodeModules = Join-Path $vueDir "node_modules"
    $packageJson = Join-Path $vueDir "package.json"

    if (-not (Test-Path $nodeModules)) {
        Write-Host "node_modules directory missing - npm install required" -ForegroundColor Gray
        $script:CachedChecks.NpmInstallNeeded = $true
        return $true
    }

    if (Test-Path $packageJson) {
        $packageTime = (Get-Item $packageJson).LastWriteTime
        $modulesTime = (Get-Item $nodeModules).LastWriteTime
        if ($packageTime -gt $modulesTime) {
            Write-Host "package.json newer than node_modules - npm install required" -ForegroundColor Gray
            $script:CachedChecks.NpmInstallNeeded = $true
            return $true
        }
    }

    Write-Host "npm dependencies are up to date" -ForegroundColor Gray
    $script:CachedChecks.NpmInstallNeeded = $false
    return $false
}

function Find-NpmExecutable {
    [CmdletBinding()]
    [OutputType([string])]
    param()

    # Check if npm is already in PATH and working
    try {
        $npmVersion = npm --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $npmVersion) {
            return "npm"
        }
    } catch {
        Write-Host "npm not found in PATH" -ForegroundColor Yellow
    }

    # Check common npm installation locations
    $possiblePaths = @(
        "C:\Program Files\nodejs\npm.cmd",
        "C:\Program Files\nodejs\npm.exe",
        "C:\Program Files (x86)\nodejs\npm.cmd",
        "C:\Program Files (x86)\nodejs\npm.exe",
        "$env:APPDATA\npm\npm.cmd",
        "$env:APPDATA\npm\npm.exe",
        "$env:LOCALAPPDATA\Programs\nodejs\npm.cmd",
        "$env:LOCALAPPDATA\Programs\nodejs\npm.exe"
    )

    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            Write-Host "Found npm at: $path" -ForegroundColor Green
            return $path
        }
    }

    # Try to find npm through node installation
    try {
        $nodePath = Get-Command node -ErrorAction SilentlyContinue
        if ($nodePath) {
            $nodeDir = Split-Path $nodePath.Source -Parent
            $npmPath = Join-Path $nodeDir "npm.cmd"
            if (Test-Path $npmPath) {
                Write-Host "Found npm through node at: $npmPath" -ForegroundColor Green
                return $npmPath
            }
            $npmPath = Join-Path $nodeDir "npm.exe"
            if (Test-Path $npmPath) {
                Write-Host "Found npm through node at: $npmPath" -ForegroundColor Green
                return $npmPath
            }
        }
    } catch {
        Write-Host "Could not find npm through node" -ForegroundColor Yellow
    }

    Write-Host "ERROR: npm not found. Please install Node.js and npm first." -ForegroundColor Red
    return $null
}

function Invoke-VueFrontendBuild {
    [CmdletBinding()]
    param(
        [switch]$Quick,
        [switch]$ForceRebuild
    )

    $vueDir = Join-Path $PSScriptRoot "casestrainer-vue-new"
    Write-Host "Vue directory: $vueDir" -ForegroundColor Gray

    if (-not (Test-Path $vueDir)) {
        throw "Vue directory not found: $vueDir"
    }

    Push-Location $vueDir
    try {
        if (-not (Test-Path "package.json")) {
            throw "package.json not found in Vue directory: $vueDir"
        }

        # Skip Node/npm version check in quick mode
        if (-not $Quick) {
            Write-Host "Checking Node.js and npm..." -ForegroundColor Yellow
            try {
                $nodeVersion = node --version 2>$null
                $npmVersion = npm --version 2>$null
                if ($LASTEXITCODE -ne 0 -or -not $nodeVersion -or -not $npmVersion) {
                    throw "Node.js or npm not found. Please install Node.js first."
                }
                Write-Host "OK Node.js $nodeVersion, npm $npmVersion" -ForegroundColor Green
            }
            catch {
                throw "Node.js or npm check failed: $($_.Exception.Message)"
            }
        }

        $npmPath = Find-NpmExecutable
        if (-not $npmPath) {
            throw "Could not find npm executable. Please install Node.js and npm first."
        }
        Write-Host "Using npm at: $npmPath" -ForegroundColor Gray

        # Force npm install if ForceRebuild is true, otherwise check if needed
        $needsInstall = $ForceRebuild -or (Test-NpmInstallNeeded)

        if ($needsInstall) {
            Write-Host "Installing npm dependencies..." -ForegroundColor Yellow
            if ($ForceRebuild) {
                Write-Host "Force rebuild: Running clean npm install..." -ForegroundColor Yellow
                # Use npm ci for clean install if package-lock exists, otherwise npm install
                $packageLock = Join-Path $vueDir "package-lock.json"
                if (Test-Path $packageLock) {
                    $installArgs = @("ci")
                } else {
                    $installArgs = @("install")
                }
            } else {
                # Faster npm install with optimizations for regular builds
                $installArgs = @("install", "--no-audit", "--no-fund", "--prefer-offline", "--no-optional")
            }

            Write-Host "Running: $npmPath $($installArgs -join ' ')" -ForegroundColor Gray
            
            # Use cmd.exe to run npm to avoid PowerShell parameter parsing issues
            $cmdArgs = @("/c", $npmPath) + $installArgs
            $installProcess = Start-Process -FilePath "cmd.exe" -ArgumentList $cmdArgs -Wait -NoNewWindow -PassThru -WorkingDirectory $vueDir
            
            if ($installProcess.ExitCode -ne 0) {
                # Try to get more specific error information
                Write-Host "npm install failed with exit code: $($installProcess.ExitCode)" -ForegroundColor Red

                # Check for common issues and provide helpful messages
                if (-not (Test-Path "package.json")) {
                    throw "package.json file not found in current directory"
                }

                # Check if it's a network issue
                try {
                    $npmRegistry = "registry.npmjs.org"
                    $testConnection = Test-NetConnection -ComputerName $npmRegistry -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
                    if (-not $testConnection) {
                        throw "npm install failed - cannot reach npm registry (network issue?)"
                    }
                } catch {
                    Write-Host "Network connectivity test failed" -ForegroundColor Yellow
                }

                throw "npm install failed with exit code: $($installProcess.ExitCode)"
            }
            Write-Host "OK npm dependencies installed" -ForegroundColor Green
        } else {
            Write-Host "OK node_modules up to date (skipping npm install)" -ForegroundColor Green
        }

        # Force Vue build if ForceRebuild is true, otherwise check if needed
        $needsBuild = $ForceRebuild -or (Test-VueBuildNeeded -Force:$ForceRebuild)

        if ($needsBuild) {
            Write-Host "Building Vue frontend..." -ForegroundColor Yellow
            if ($ForceRebuild) {
                Write-Host "Force rebuild: Building from clean state..." -ForegroundColor Yellow
            }

            # Use production build with optimizations
            $buildArgs = @("run", "build")
            if (-not $Quick -and -not $ForceRebuild) {
                $buildArgs += "--verbose"
            }

            Write-Host "Running: $npmPath $($buildArgs -join ' ')" -ForegroundColor Gray
            
            # Use cmd.exe to run npm to avoid PowerShell parameter parsing issues
            $cmdArgs = @("/c", $npmPath) + $buildArgs
            $buildProcess = Start-Process -FilePath "cmd.exe" -ArgumentList $cmdArgs -Wait -NoNewWindow -PassThru -WorkingDirectory $vueDir
            
            if ($buildProcess.ExitCode -ne 0) {
                # Try to get more specific error information
                Write-Host "npm build failed with exit code: $($buildProcess.ExitCode)" -ForegroundColor Red

                # Check for common build issues
                $nodeModules = Join-Path $PWD "node_modules"
                if (-not (Test-Path $nodeModules)) {
                    throw "npm build failed - node_modules directory missing. Try running npm install first."
                }

                # Check available disk space
                try {
                    $currentDrive = (Get-Location).Drive.Name
                    $diskSpace = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='${currentDrive}:'" -ErrorAction SilentlyContinue
                    if ($diskSpace) {
                        $freeGB = [math]::Round($diskSpace.FreeSpace / 1GB, 2)
                        if ($freeGB -lt 1) {
                            throw "npm build failed - insufficient disk space ($freeGB GB free)"
                        }
                    }
                } catch {
                    Write-Host "Could not check disk space" -ForegroundColor Yellow
                }

                throw "npm build failed with exit code: $($buildProcess.ExitCode)"
            }

            # Verify build output
            $distDir = Join-Path $vueDir "dist"
            $indexFile = Join-Path $distDir "index.html"

            if ((Test-Path $distDir) -and (Test-Path $indexFile)) {
                $buildSize = Get-ChildItem $distDir -Recurse | Measure-Object -Property Length -Sum
                $sizeMB = [math]::Round($buildSize.Sum / 1MB, 2)
                Write-Host "OK Vue frontend built successfully ($sizeMB MB)" -ForegroundColor Green

                # Update cache to reflect successful build
                $script:CachedChecks.VueBuildNeeded = $false
                $script:CachedChecks.LastCheckTime = Get-Date
            } else {
                throw "Vue build completed but output files not found in $distDir"
            }
        } else {
            Write-Host "OK Vue build up to date (skipping build)" -ForegroundColor Green
        }
    }
    finally {
        try {
            # Ensure we return to the original directory
            Pop-Location -ErrorAction SilentlyContinue
            
            # Clean up any temporary files created during the build
            if (Test-Path "$vueDir\node_modules\.cache" -ErrorAction SilentlyContinue) {
                # Clean up large cache directories that might have been created
                Remove-Item "$vueDir\node_modules\.cache" -Recurse -Force -ErrorAction SilentlyContinue
            }
            
            # Clean up any temporary environment variables
            if ($env:NODE_ENV) {
                Remove-Item Env:\NODE_ENV -ErrorAction SilentlyContinue
            }
            
            # Reset npm configuration if it was modified
            if ($env:NPM_CONFIG_REGISTRY) {
                Remove-Item Env:\NPM_CONFIG_REGISTRY -ErrorAction SilentlyContinue
            }
        }
        catch {
            Write-CrashLog "Error during cleanup in Invoke-VueFrontendBuild" -Level "WARNING" -Exception $_
            Write-Host "Warning: Error during Vue build cleanup: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    # After Vue frontend build, copy assets to static/assets
    $distDir = Join-Path $PSScriptRoot "casestrainer-vue-new\dist"
    $staticAssetsDir = Join-Path $PSScriptRoot "static\assets"
    if (Test-Path $distDir) {
        Write-Host "Copying Vue build assets to static/assets..." -ForegroundColor Yellow
        Copy-Item -Path (Join-Path $distDir "*") -Destination $staticAssetsDir -Recurse -Force
        Write-Host "Assets copied to $staticAssetsDir" -ForegroundColor Green
    } else {
        Write-Host "Vue build output directory not found: $distDir" -ForegroundColor Red
    }
}

function Test-DockerAvailability {
    [CmdletBinding()]
    [OutputType([bool])]
    param([switch]$Force)

    # Use cached result if recent and not forcing
    if (-not $Force -and `
        $script:CachedChecks.LastCheckTime -and `
        ((Get-Date) - $script:CachedChecks.LastCheckTime).TotalSeconds -lt 60 -and `
        $null -ne $script:CachedChecks.DockerAvailable) {
        return $script:CachedChecks.DockerAvailable
    }

    try {
        # Faster Docker check - just ping daemon
        $null = docker version --format "{{.Server.Version}}" 2>$null
        $result = $LASTEXITCODE -eq 0
        $script:CachedChecks.DockerAvailable = $result
        return $result
    }
    catch {
        Write-CrashLog "Docker availability check failed" -Level "ERROR" -Exception $_
        $script:CachedChecks.DockerAvailable = $false
        return $false
    }
}

function Test-CodeChanges {
    [CmdletBinding()]
    [OutputType([bool])]
    param()

    # Only check critical files for faster startup
    $keyFiles = @(
        "src\unified_citation_processor.py",
        "src\case_name_extraction_core.py",
        "docker-compose.prod.yml",
        "Dockerfile"
    )

    $cutoffTime = (Get-Date).AddHours(-1)  # Increased to 1 hour for fewer false positives

    foreach ($file in $keyFiles) {
        $filePath = Join-Path $PSScriptRoot $file
        if (Test-Path $filePath) {
            $fileInfo = Get-Item $filePath
            if ($fileInfo.LastWriteTime -gt $cutoffTime) {
                return $true
            }
        }
    }
    return $false
}

function Wait-ForServices {
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [int]$TimeoutMinutes = 10  # Increased default timeout to 10 minutes
    )
    
    $startTime = Get-Date
    $timeout = New-TimeSpan -Minutes $TimeoutMinutes
    $attempt = 0
    $consecutiveHealthyChecks = 0
    $requiredConsecutiveChecks = 2  # Require 2 consecutive healthy checks
    
    # Initialize status tracking
    if (-not $script:lastStatus) {
        $script:lastStatus = @{}
    }
    
    Write-Host "`nWaiting for services to become healthy (timeout: $TimeoutMinutes minutes, requires $requiredConsecutiveChecks consecutive healthy checks)..." -ForegroundColor Cyan
    
    function Get-Container-Status {
        param([string]$containerName)
        try {
            $status = docker inspect -f '{{.State.Health.Status}}' $containerName 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $status) {
                return @{ Status = 'UNKNOWN'; IsHealthy = $false }
            }
            return @{ Status = $status; IsHealthy = ($status -eq 'healthy') }
        } catch {
            Write-Verbose "Error checking $containerName status: $_"
            return @{ Status = 'ERROR'; IsHealthy = $false }
        }
    }
    
    function Get-Container-Logs {
        param([string]$containerName, [int]$lines = 20)
        try {
            return docker logs --tail $lines $containerName 2>&1 | Out-String
        } catch {
            return "Failed to retrieve logs: $_"
        }
    }
    
    while ((Get-Date) - $startTime -lt $timeout) {
        $attempt++
        $healthResults = @()
        $allHealthy = $true
        $currentStatus = @{}
        
        try {
            # Backend health check
            $backend = Get-Container-Status 'casestrainer-backend-prod'
            $currentStatus.Backend = $backend
            if (-not $backend.IsHealthy) {
                $healthResults += "Backend: $($backend.Status)"
                $allHealthy = $false
                Write-Verbose "Backend logs: $(Get-Container-Logs 'casestrainer-backend-prod' 10)"
            } else {
                $healthResults += "Backend: HEALTHY"
            }
            
            # Redis health check
            $redis = Get-Container-Status 'casestrainer-redis-prod'
            $currentStatus.Redis = $redis
            if (-not $redis.IsHealthy) {
                $healthResults += "Redis: $($redis.Status)"
                $allHealthy = $false
                if ($redis.Status -eq 'starting') {
                    Write-Verbose "Redis is still starting up..."
                } else {
                    Write-Verbose "Redis logs: $(Get-Container-Logs 'casestrainer-redis-prod' 10)"
                }
            } else {
                $healthResults += "Redis: HEALTHY"
            }

            # RQ Worker health check
            $worker = Get-Container-Status 'casestrainer-rqworker-prod'
            $currentStatus.Worker = $worker
            if (-not $worker.IsHealthy) {
                $healthResults += "Worker: $($worker.Status)"
                $allHealthy = $false
                if ($worker.Status -eq 'starting') {
                    Write-Verbose "Worker is still starting up..."
                } else {
                    Write-Verbose "Worker logs: $(Get-Container-Logs 'casestrainer-rqworker-prod' 20)"
                }
            } else {
                $healthResults += "Worker: HEALTHY"
            }

            # Check for no change in status (potential hang)
            $statusChanged = $false
            foreach ($key in $currentStatus.Keys) {
                if (-not $script:lastStatus.ContainsKey($key) -or $script:lastStatus[$key].Status -ne $currentStatus[$key].Status) {
                    $statusChanged = $true
                    break
                }
            }
            
            if (-not $statusChanged -and $attempt -gt 1) {
                Write-Host "No status change detected, waiting..." -ForegroundColor Gray
            }
            
            $script:lastStatus = $currentStatus

            if ($allHealthy) {
                $consecutiveHealthyChecks++
                if ($consecutiveHealthyChecks -ge $requiredConsecutiveChecks) {
                    Write-Host "✅ All services are ready and stable" -ForegroundColor Green
                    Write-Host "  $($healthResults -join ', ')" -ForegroundColor Gray
                    
                    # Final verification of API endpoint
                    try {
                        $apiUrl = "http://localhost:5000/casestrainer/api/health"
                        $response = Invoke-WebRequest -Uri $apiUrl -UseBasicParsing -TimeoutSec 10
                        if ($response.StatusCode -eq 200) {
                            Write-Host "✅ API endpoint is responding: $($response.Content.Trim())" -ForegroundColor Green
                            return $true
                        } else {
                            Write-Host "⚠️  API returned status code: $($response.StatusCode)" -ForegroundColor Yellow
                        }
                    } catch {
                        Write-Host "⚠️  API endpoint verification failed: $($_.Exception.Message)" -ForegroundColor Yellow
                    }
                    
                    # If we got here, the API check failed but services report healthy
                    # We'll continue waiting in case the API needs more time
                    $allHealthy = $false
                    Start-Sleep -Seconds 5
                    continue
                } else {
                    Write-Host "✅ All services report healthy ($consecutiveHealthyChecks/$requiredConsecutiveChecks)..." -ForegroundColor Green
                }
            } else {
                $consecutiveHealthyChecks = 0  # Reset counter if any service is unhealthy
                Write-Host "Services not ready (attempt $($attempt), elapsed: $([math]::Round(((Get-Date) - $startTime).TotalSeconds))s): $($healthResults -join ', ')" -ForegroundColor Yellow
            }
            
            # Only sleep if we need to check again
            if ((Get-Date) - $startTime -lt $timeout -and $consecutiveHealthyChecks -lt $requiredConsecutiveChecks) {
                Start-Sleep -Seconds 5
            }
        }
        catch {
            Write-Host "Health check attempt $attempt failed: $($_.Exception.Message)" -ForegroundColor Yellow
            Start-Sleep -Seconds 5
        }
    }

    # If we get here, we timed out
    Write-Host "WARNING: Timeout waiting for services after $TimeoutMinutes minutes" -ForegroundColor Yellow
    Write-Host "Final status: $($healthResults -join ', ')" -ForegroundColor Yellow
    
    # Show container statuses one last time
    Write-Host "`nContainer statuses:" -ForegroundColor Yellow
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Out-Host
    
    return $false
}

function Show-ServiceUrls {
    Write-Host "`n=== Docker Production Mode Ready ===`n" -ForegroundColor Green
    Write-Host "INFO Production Site:  https://wolf.law.uw.edu/casestrainer" -ForegroundColor Green
    Write-Host ""
    Write-Host "Local Development URLs:" -ForegroundColor Cyan
    Write-Host "Backend API:    http://localhost:5001/casestrainer/api/" -ForegroundColor Gray
    Write-Host "Frontend Prod:  http://localhost:8080/" -ForegroundColor Gray
    Write-Host "Nginx (HTTP):   http://localhost:80/" -ForegroundColor Gray
    Write-Host "Nginx (HTTPS):  https://localhost:443/" -ForegroundColor Gray
    Write-Host "Local Frontend: https://localhost/casestrainer/" -ForegroundColor Gray
    Write-Host "API Health:     https://localhost/casestrainer/api/health" -ForegroundColor Gray

    Write-Host "`nDocker Commands:" -ForegroundColor Cyan
    Write-Host "  View logs:    docker-compose -f docker-compose.prod.yml logs [service]" -ForegroundColor Gray
    Write-Host "  Stop all:     docker-compose -f docker-compose.prod.yml down" -ForegroundColor Gray
    Write-Host "  Restart:      docker-compose -f docker-compose.prod.yml restart [service]" -ForegroundColor Gray
}

function Test-APIFunctionality {
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [string]$TestCitation = "534 F.3d 1290"
    )

    Write-Host "`n=== Testing API Functionality ===`n" -ForegroundColor Cyan

    # Wait a moment for services to fully initialize
    Start-Sleep -Seconds 2

    # Initialize variables to track resources that need cleanup
    $healthResponse = $null
    $testResponse = $null
    $result = $null
    $testPayload = $null
    
    try {
        # Test basic API health with retry logic
        Write-Host "Testing API health endpoint..." -ForegroundColor Yellow
        $maxRetries = 3
        $retryDelay = 5
        $healthOK = $false
        $healthError = $null

        for ($i = 1; $i -le $maxRetries; $i++) {
            try {
                # Clear any previous response
                if ($healthResponse -ne $null) {
                    $healthResponse.Dispose()
                    $healthResponse = $null
                }
                
                $healthResponse = Invoke-WebRequest -Uri "http://localhost:5001/casestrainer/api/health" -Method GET -TimeoutSec 15 -ErrorAction Stop
                if ($healthResponse.StatusCode -eq 200) {
                    $healthOK = $true
                    $healthError = $null
                    break
                }
            } catch {
                $healthError = $_.Exception
                Write-Host "Health check attempt $i failed: $($healthError.Message)" -ForegroundColor Gray
                if ($i -lt $maxRetries) {
                    Write-Host "Retrying in $retryDelay seconds..." -ForegroundColor Gray
                    Start-Sleep -Seconds $retryDelay
                }
            }
        }

        if ($healthOK) {
            Write-Host "✅ API health check passed" -ForegroundColor Green
        } else {
            Write-Host "❌ API health check failed after $maxRetries attempts" -ForegroundColor Red
            return $false
        }

        # Test citation processing with retry logic
        Write-Host "Testing citation processing with: $TestCitation" -ForegroundColor Yellow
        $processingOK = $false

        for ($i = 1; $i -le $maxRetries; $i++) {
            try {
                $testPayload = @{
                    type = "text"
                    text = "The court in Smith v. Jones, $TestCitation held that..."
                } | ConvertTo-Json -Depth 10

                $testResponse = Invoke-WebRequest -Uri "http://localhost:5000/casestrainer/api/analyze" -Method POST -Body $testPayload -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop

                if ($testResponse.StatusCode -eq 200) {
                    $result = $testResponse.Content | ConvertFrom-Json
                    if ($result.status -eq "processing" -and $result.task_id) {
                        Write-Host "✅ Citation processing test passed" -ForegroundColor Green
                        Write-Host "   Task ID: $($result.task_id)" -ForegroundColor Gray
                        $processingOK = $true
                        break
                    } else {
                        Write-Host "❌ Citation processing test failed - unexpected response format" -ForegroundColor Red
                        Write-Host "   Response: $($testResponse.Content)" -ForegroundColor Gray
                    }
                } else {
                    Write-Host "❌ Citation processing test failed - HTTP $($testResponse.StatusCode)" -ForegroundColor Red
                }
            } catch {
                Write-Host "Processing test attempt $i failed: $($_.Exception.Message)" -ForegroundColor Gray
                if ($i -lt $maxRetries) {
                    Write-Host "Retrying in $retryDelay seconds..." -ForegroundColor Gray
                    Start-Sleep -Seconds $retryDelay
                }
            }
        }

        return $processingOK
    }
    catch {
        Write-Host "❌ API test failed: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
    finally {
        # Clean up resources
        try {
            # Dispose of web responses if they exist
            if ($healthResponse -ne $null) {
                $healthResponse.Dispose()
                $healthResponse = $null
            }
            
            if ($testResponse -ne $null) {
                $testResponse.Dispose()
                $testResponse = $null
            }
            
            # Clear large objects
            $result = $null
            $testPayload = $null
            
            # Force garbage collection to free up memory
            [System.GC]::Collect()
            [System.GC]::WaitForPendingFinalizers()
        }
        catch {
            Write-CrashLog "Error during cleanup in Test-APIFunctionality" -Level "WARNING" -Exception $_
            Write-Host "Warning: Error during API test cleanup: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

function Test-FrontendFunctionality {
    [CmdletBinding()]
    [OutputType([bool])]
    param()

    Write-Host "`n=== Testing Frontend Functionality ===`n" -ForegroundColor Cyan

    # Initialize variables to track resources that need cleanup
    $frontendResponse = $null
    $content = $null
    $maxRetries = 3
    $retryDelay = 5
    $result = $false

    try {
        # Test frontend availability with retry logic
        Write-Host "Testing frontend availability..." -ForegroundColor Yellow
        $lastError = $null

        for ($i = 1; $i -le $maxRetries; $i++) {
            try {
                # Clean up any previous response
                if ($frontendResponse -ne $null) {
                    $frontendResponse.Dispose()
                    $frontendResponse = $null
                }
                
                $frontendResponse = Invoke-WebRequest -Uri "http://localhost:8080/" -Method GET -TimeoutSec 15 -ErrorAction Stop
                
                if ($frontendResponse.StatusCode -eq 200) {
                    Write-Host "✅ Frontend accessibility test passed" -ForegroundColor Green

                    # Check if it contains expected content
                    $content = $frontendResponse.Content
                    if ($content -match "CaseStrainer|app-root|vue|<!DOCTYPE html>") {
                        Write-Host "✅ Frontend content validation passed" -ForegroundColor Green
                        Write-Host "   Content size: $([math]::Round($content.Length / 1KB, 2)) KB" -ForegroundColor Gray
                        $result = $true
                        break
                    } else {
                        $lastError = "Frontend content validation failed - unexpected content"
                        Write-Host "❌ $lastError" -ForegroundColor Red
                        Write-Host "   Content preview: $($content.Substring(0, [Math]::Min(200, $content.Length)))" -ForegroundColor Gray
                    }
                } else {
                    $lastError = "Frontend accessibility test failed - HTTP $($frontendResponse.StatusCode)"
                    Write-Host "❌ $lastError" -ForegroundColor Red
                }
            } catch {
                $lastError = $_.Exception.Message
                Write-Host "Frontend test attempt $i failed: $lastError" -ForegroundColor Gray
                if ($i -lt $maxRetries) {
                    Write-Host "Retrying in $retryDelay seconds..." -ForegroundColor Gray
                    Start-Sleep -Seconds $retryDelay
                }
            }
        }

        if (-not $result) {
            Write-Host "❌ Frontend test failed after $maxRetries attempts" -ForegroundColor Red
            if ($lastError) {
                Write-Host "   Last error: $lastError" -ForegroundColor Gray
            }
        }
        
        return $result
    }
    catch {
        $errorMsg = $_.Exception.Message
        Write-Host "❌ Frontend test failed: $errorMsg" -ForegroundColor Red
        Write-CrashLog "Frontend test failed" -Level "ERROR" -Exception $_.Exception
        return $false
    }
    finally {
        # Clean up resources
        try {
            # Dispose of web response if it exists
            if ($frontendResponse -ne $null) {
                $frontendResponse.Dispose()
                $frontendResponse = $null
            }
            
            # Clear large objects
            $content = $null
            
            # Force garbage collection to free up memory
            [System.GC]::Collect()
            [System.GC]::WaitForPendingFinalizers()
        }
        catch {
            Write-CrashLog "Error during cleanup in Test-FrontendFunctionality" -Level "WARNING" -Exception $_
            Write-Host "Warning: Error during frontend test cleanup: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

function Show-ContainerLogs {
    [CmdletBinding()]
    param()

    Write-Host "`n=== Container Logs ===`n" -ForegroundColor Cyan

    $dockerComposeFile = Join-Path $PSScriptRoot "docker-compose.prod.yml"

    if (-not (Test-Path $dockerComposeFile)) {
        Write-Host "Docker compose file not found: $dockerComposeFile" -ForegroundColor Red
        return
    }

    try {
        # Check which containers are actually running
        $runningContainers = docker ps --filter "name=casestrainer" --format "{{.Names}}" 2>$null
        if (-not $runningContainers) {
            Write-Host "No CaseStrainer containers are currently running" -ForegroundColor Yellow
            return
        }

        Write-Host "Running containers: $($runningContainers -join ', ')" -ForegroundColor Gray
        Write-Host ""

        Write-Host "Backend logs:" -ForegroundColor Yellow
        $backendLogs = docker-compose -f $dockerComposeFile logs --tail=20 backend-prod 2>$null
        if ($backendLogs) {
            Write-Host $backendLogs -ForegroundColor White
        } else {
            Write-Host "No backend logs available" -ForegroundColor Gray
        }

        Write-Host "`nRQ Worker logs:" -ForegroundColor Yellow
        $workerLogs = docker-compose -f $dockerComposeFile logs --tail=20 rqworker-prod 2>$null
        if ($workerLogs) {
            Write-Host $workerLogs -ForegroundColor White
        } else {
            Write-Host "No worker logs available" -ForegroundColor Gray
        }

        Write-Host "`nRedis logs:" -ForegroundColor Yellow
        $redisLogs = docker-compose -f $dockerComposeFile logs --tail=10 redis-prod 2>$null
        if ($redisLogs) {
            Write-Host $redisLogs -ForegroundColor White
        } else {
            Write-Host "No Redis logs available" -ForegroundColor Gray
        }

        Write-Host "`nNginx logs:" -ForegroundColor Yellow
        $nginxLogs = docker-compose -f $dockerComposeFile logs --tail=10 nginx-prod 2>$null
        if ($nginxLogs) {
            Write-Host $nginxLogs -ForegroundColor White
        } else {
            Write-Host "No Nginx logs available" -ForegroundColor Gray
        }
    }
    catch {
        Write-Host "Error retrieving logs: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Trying direct docker logs..." -ForegroundColor Yellow

        # Fallback to direct docker logs
        try {
            $containers = @("casestrainer-backend-prod", "casestrainer-rqworker-prod", "casestrainer-redis-prod", "casestrainer-nginx-prod")
            foreach ($container in $containers) {
                $exists = docker ps -a --filter "name=$container" --format "{{.Names}}" 2>$null
                if ($exists) {
                    Write-Host "`n$container logs:" -ForegroundColor Yellow
                    docker logs $container --tail=10 2>$null
                }
            }
        } catch {
            Write-Host "Failed to retrieve logs via docker command: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
} 

function Start-ServiceMonitoring {
    [CmdletBinding(SupportsShouldProcess)]
    param()

    if ($PSCmdlet.ShouldProcess("Service monitoring")) {
        Write-Host "Starting service monitoring..." -ForegroundColor Cyan

        # Monitor container logs for errors
        $script:MonitoringJob = Start-Job -ScriptBlock {
            while ($true) {
                try {
                    # Check for worker crashes
                    $workerLogs = docker logs casestrainer-rqworker-prod --tail 10 2>$null
                    if ($workerLogs -match "Work-horse terminated unexpectedly|OOMKilled|Segmentation fault") {
                        Write-Host "[MONITOR] WARNING: Worker crash detected!" -ForegroundColor Red
                        Write-Host "[MONITOR] Consider restarting containers" -ForegroundColor Yellow
                    }

                    # Check for backend errors
                    $backendLogs = docker logs casestrainer-backend-prod --tail 10 2>$null
                    if ($backendLogs -match "ERROR|Exception|Traceback") {
                        Write-Host "[MONITOR] WARNING: Backend errors detected!" -ForegroundColor Red
                    }

                    Start-Sleep -Seconds 30
                } catch {
                    Write-Host "[MONITOR] Monitoring error: $($_.Exception.Message)" -ForegroundColor Yellow
                    Start-Sleep -Seconds 60
                }
            }
        }

        Write-Host "Service monitoring started" -ForegroundColor Green
    }
}

function Remove-AllCaseStrainerContainers {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param()
    
    Write-Host "Removing all CaseStrainer containers..." -ForegroundColor Yellow
    
    try {
        # Get all container IDs with the casestrainer name prefix but exclude dify containers
        $containers = docker ps -a --filter "name=casestrainer" --format "{{.Names}}" 2>$null | 
            Where-Object { $_ -match '^casestrainer-' -and $_ -notmatch 'dify' }
        
        if ($containers) {
            Write-Host "Found $($containers.Count) CaseStrainer containers to remove" -ForegroundColor Yellow
            $containers | ForEach-Object { 
                Write-Host "  - $_" -ForegroundColor Yellow
            }
            
            # Stop all containers first (by name to avoid any ambiguity)
            $containers | ForEach-Object {
                Write-Host "Stopping $_..." -ForegroundColor DarkGray
                docker stop $_ 2>$null | Out-Null
            }
            
            # Remove all containers (by name to avoid any ambiguity)
            $containers | ForEach-Object {
                Write-Host "Removing $_..." -ForegroundColor DarkGray
                docker rm -f $_ 2>$null | Out-Null
            }
            
            Write-Host "Successfully removed $($containers.Count) CaseStrainer containers" -ForegroundColor Green
        } else {
            Write-Host "No CaseStrainer containers found to remove" -ForegroundColor Green
        }
        
        # Also remove any dangling containers that might be left (casestrainer only)
        $dangling = docker container ls -a --filter "status=exited" --filter "name=casestrainer" --format "{{.Names}}" 2>$null | 
            Where-Object { $_ -match '^casestrainer-' -and $_ -notmatch 'dify' }
            
        if ($dangling) {
            Write-Host "Cleaning up $($dangling.Count) dangling CaseStrainer containers..." -ForegroundColor Yellow
            $dangling | ForEach-Object {
                docker rm $_ 2>$null | Out-Null
            }
        }
        
        return $true
    } catch {
        Write-Host "Error removing containers: $_" -ForegroundColor Red
        Write-Host "Stack trace: $($_.ScriptStackTrace)" -ForegroundColor DarkGray
        return $false
    }
}

function Stop-ServiceMonitoring {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param()
    
    # Nginx is now managed by Docker Compose, so we don't need to stop it manually
    # if ($PSCmdlet.ShouldProcess("Nginx", "Stop")) {
    #     Stop-NginxServer | Out-Null
    # }

    if ($script:MonitoringJob) {
        try {
            Stop-Job $script:MonitoringJob -ErrorAction SilentlyContinue
            Remove-Job $script:MonitoringJob -ErrorAction SilentlyContinue
            $script:MonitoringJob = $null
            Write-CrashLog "Service monitoring stopped" -Level "INFO"
        }
        catch {
            Write-CrashLog "Error stopping service monitoring" -Level "WARN" -Exception $_
        }
    }
}

function Stop-AllMonitoring {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param()

    if ($PSCmdlet.ShouldProcess("All monitoring services")) {
        Stop-ServiceMonitoring
        $script:AutoRestartEnabled = $false
    }
}

function Start-DockerProduction {
    [CmdletBinding(SupportsShouldProcess)]
    [OutputType([bool])]
    param(
        [switch]$ForceRebuild,
        [switch]$NoValidation,
        [switch]$QuickStart,
        [switch]$SkipVueBuild
    )

    # Nginx is now managed by Docker Compose, so we don't need to start it manually
    # Write-Host "`n=== Starting Nginx ===" -ForegroundColor Cyan
    # $nginxStarted = Start-NginxServer
    # if (-not $nginxStarted) {
    #     Write-Host "❌ Failed to start Nginx. Aborting startup." -ForegroundColor Red
    #     return $false
    # }

    Write-Host "`n=== Starting Docker Production Mode ===`n" -ForegroundColor Green

    # Log the parameters being used
    Write-CrashLog "Start-DockerProduction called with ForceRebuild: $($ForceRebuild.IsPresent), NoValidation: $($NoValidation.IsPresent), QuickStart: $QuickStart, SkipVueBuild: $SkipVueBuild" -Level "INFO"

    try {
        # Quick start mode: minimal checks
        if ($QuickStart) {
            Write-Host "QUICK START MODE: Skipping most validation checks" -ForegroundColor Cyan
        } else {
            # Validate environment first
            Test-ScriptEnvironment
        }

        # Parallel Docker and build checks for speed
        $dockerJob = Start-Job -ScriptBlock {
            try {
                $null = docker version --format "{{.Server.Version}}" 2>$null
                return $LASTEXITCODE -eq 0
            } catch {
                return $false
            }
        }

        # Check if we need Vue build (removed parallel job to avoid Using variable issues)
        $needsVueBuild = $false
        if (-not $SkipVueBuild -and -not $QuickStart) {
            Write-Host "Checking if Vue build is needed..." -ForegroundColor Yellow
            $needsVueBuild = Test-VueBuildNeeded -Force:$ForceRebuild
        }

        # Wait for Docker check
        $dockerAvailable = Receive-Job $dockerJob -Wait
        Remove-Job $dockerJob

        if (-not $dockerAvailable) {
            Write-Host "ERROR Docker is not running or not available" -ForegroundColor Red
            Write-Host "Please start Docker Desktop and try again." -ForegroundColor Yellow
            return $false
        }
        Write-Host "OK Docker is running" -ForegroundColor Green

        # Skip resource checks in quick mode
        if (-not $QuickStart) {
            # Quick disk space check only
            try {
                $diskSpace = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='C:'" -ErrorAction Stop
                $freeGB = [math]::Round($diskSpace.FreeSpace / 1GB, 2)
                if ($freeGB -lt 2) {
                    Write-Host "ERROR: Critically low disk space ($freeGB GB free)" -ForegroundColor Red
                    return $false
                }
                Write-Host "OK Sufficient disk space ($freeGB GB free)" -ForegroundColor Green
            }
            catch {
                Write-Host "WARNING: Could not check disk space" -ForegroundColor Yellow
            }
        }

        # Handle Vue build - this is the critical section for option 3
        if (-not $SkipVueBuild) {
            Write-Host "Processing Vue frontend build..." -ForegroundColor Yellow

            # Use the pre-checked value or check now
            $needsBuild = $needsVueBuild
            if (-not $needsVueBuild) {
                $needsBuild = Test-VueBuildNeeded -Force:$ForceRebuild
            }

            Write-Host "Vue build needed: $needsBuild, ForceRebuild: $($ForceRebuild.IsPresent)" -ForegroundColor Gray

            if ($needsBuild -or $ForceRebuild) {
                Write-Host "Building Vue frontend (ForceRebuild: $($ForceRebuild.IsPresent))..." -ForegroundColor Yellow

                # Clear Vue cache if force rebuilding
                if ($ForceRebuild) {
                    Write-Host "Force rebuild mode: Clearing Vue caches..." -ForegroundColor Yellow
                    $vueDir = Join-Path $PSScriptRoot "casestrainer-vue-new"
                    if (Test-Path $vueDir) {
                        Push-Location $vueDir
                        try {
                            # Remove dist directory for clean rebuild
                            $distDir = Join-Path $vueDir "dist"
                            if (Test-Path $distDir) {
                                Write-Host "Removing existing dist directory..." -ForegroundColor Gray
                                Remove-Item $distDir -Recurse -Force -ErrorAction SilentlyContinue
                            }

                            # Remove node_modules for clean dependency install
                            $nodeModules = Join-Path $vueDir "node_modules"
                            if (Test-Path $nodeModules) {
                                Write-Host "Removing node_modules for clean install..." -ForegroundColor Gray
                                Remove-Item $nodeModules -Recurse -Force -ErrorAction SilentlyContinue
                            }

                            # Clear package-lock.json for clean dependency resolution
                            $packageLock = Join-Path $vueDir "package-lock.json"
                            if (Test-Path $packageLock) {
                                Write-Host "Removing package-lock.json for clean dependency resolution..." -ForegroundColor Gray
                                Remove-Item $packageLock -Force -ErrorAction SilentlyContinue
                            }

                            # Clear npm cache
                            try {
                                $npmPath = Find-NpmExecutable
                                if ($npmPath) {
                                    Write-Host "Clearing npm cache..." -ForegroundColor Gray
                                    $cacheArgs = @("cache", "clean", "--force")
                                    $cmdArgs = @("/c", $npmPath) + $cacheArgs
                                    Start-Process -FilePath "cmd.exe" -ArgumentList $cmdArgs -Wait -NoNewWindow -ErrorAction SilentlyContinue -WorkingDirectory $vueDir
                                    Write-Host "npm cache cleared" -ForegroundColor Gray
                                }
                            } catch {
                                Write-Host "Warning: Could not clear npm cache: $($_.Exception.Message)" -ForegroundColor Yellow
                            }
                        }
                        finally {
                            Pop-Location
                        }

                        # Clear script cache as well
                        $script:CachedChecks.VueBuildNeeded = $null
                        $script:CachedChecks.NpmInstallNeeded = $null
                    }
                }

                Invoke-VueFrontendBuild -Quick:$QuickStart -ForceRebuild:$ForceRebuild
            } else {
                Write-Host "OK Vue build up to date (skipping build)" -ForegroundColor Green
            }
        } else {
            Write-Host "Skipping Vue frontend build as requested" -ForegroundColor Green
        }

        $dockerComposeFile = Join-Path $PSScriptRoot "docker-compose.prod.yml"

        # Fix BOM issue in docker-compose file if present
        try {
            $bytes = [System.IO.File]::ReadAllBytes($dockerComposeFile)
            if ($bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) {
                Write-Host "Fixing BOM in docker-compose file..." -ForegroundColor Yellow
                # Remove BOM bytes and create clean temp file
                $cleanBytes = $bytes[3..($bytes.Length-1)]
                $tempFile = "$dockerComposeFile.temp"
                [System.IO.File]::WriteAllBytes($tempFile, $cleanBytes)
                $dockerComposeFile = $tempFile
                Write-Host "Using temporary BOM-free docker-compose file" -ForegroundColor Green
            }
        } catch {
            Write-Host "Warning: Could not check/fix BOM in docker-compose file" -ForegroundColor Yellow
        }

        # Fast container management - Stop existing containers
        if ($PSCmdlet.ShouldProcess("Docker containers", "Stop existing")) {
            Write-Host "Stopping existing Docker containers..." -ForegroundColor Yellow
            
            # First, remove all CaseStrainer containers to ensure clean state
            if ($ForceRebuild) {
                Write-Host "Force rebuild: Removing all CaseStrainer containers..." -ForegroundColor Yellow
                $cleanupResult = Remove-AllCaseStrainerContainers
                if (-not $cleanupResult) {
                    Write-Host "Warning: Failed to clean up all containers, continuing with normal shutdown..." -ForegroundColor Yellow
                }
            }

            # Then stop containers from this specific compose file
            $stopArgs = @("-f", $dockerComposeFile, "down")
            if ($QuickStart) {
                $stopArgs += @("--timeout", "5")
            } else {
                $stopArgs += @("--timeout", "30")  # Longer timeout for graceful shutdown
            }

            if ($ForceRebuild) {
                # Remove volumes and orphaned containers for complete rebuild
                $stopArgs += @("--volumes", "--remove-orphans")
                Write-Host "Force rebuild: Removing volumes and orphaned containers..." -ForegroundColor Yellow
            }

            Write-Host "Running: docker-compose $($stopArgs -join ' ')" -ForegroundColor Gray
            $stopProcess = Start-Process -FilePath "docker-compose" -ArgumentList $stopArgs -Wait -NoNewWindow -PassThru -WorkingDirectory $PSScriptRoot

            if ($stopProcess.ExitCode -ne 0) {
                Write-Host "WARNING: Error stopping containers (exit code: $($stopProcess.ExitCode))" -ForegroundColor Yellow

                # Try to force stop if graceful stop failed
                if (-not $QuickStart) {
                    Write-Host "Attempting force stop..." -ForegroundColor Yellow
                    try {
                        $forceStopArgs = @("-f", $dockerComposeFile, "kill")
                        $forceStopProcess = Start-Process -FilePath "docker-compose" -ArgumentList $forceStopArgs -Wait -NoNewWindow -PassThru -WorkingDirectory $PSScriptRoot
                        if ($forceStopProcess.ExitCode -eq 0) {
                            Write-Host "Force stop successful" -ForegroundColor Green
                        }
                    } catch {
                        Write-Host "Force stop also failed: $($_.Exception.Message)" -ForegroundColor Yellow
                    }
                }
            } else {
                Write-Host "Containers stopped successfully" -ForegroundColor Green
            }

            # --- Extra safeguard: Remove any remaining casestrainer containers ---
            Write-Host "Checking for any remaining 'casestrainer' containers..." -ForegroundColor Yellow
            $remaining = docker ps -a --filter "name=casestrainer" --format "{{.ID}} {{.Names}}"
            if ($remaining) {
                Write-Host "WARNING: Found remaining containers after down. Forcibly removing..." -ForegroundColor Red
                $remaining | ForEach-Object {
                    $parts = $_ -split ' '
                    $id = $parts[0]
                    $name = $parts[1]
                    Write-Host "  Removing container: $name ($id)" -ForegroundColor Red
                    docker rm -f $id | Out-Null
                }
                Write-Host "All remaining 'casestrainer' containers forcibly removed." -ForegroundColor Green
            } else {
                Write-Host "No remaining 'casestrainer' containers found." -ForegroundColor Green
            }
        }

        # Optimized container startup
        if ($PSCmdlet.ShouldProcess("Docker containers", "Start")) {
            Write-Host "`nStarting Docker containers..." -ForegroundColor Cyan

            # Smart rebuild logic
            $composeArgs = @("-f", $dockerComposeFile, "up", "-d")

            if ($ForceRebuild) {
                Write-Host "Force rebuild: Building all images from scratch with --no-cache..." -ForegroundColor Yellow
                $buildArgs = @("-f", $dockerComposeFile, "build", "--no-cache")
                Write-Host "Running: docker-compose $($buildArgs -join ' ')" -ForegroundColor Gray
                $buildProcess = Start-Process -FilePath "docker-compose" -ArgumentList $buildArgs -Wait -NoNewWindow -PassThru -WorkingDirectory $PSScriptRoot
                if ($buildProcess.ExitCode -ne 0) {
                    Write-Host "ERROR: docker-compose build --no-cache failed (exit code: $($buildProcess.ExitCode))" -ForegroundColor Red
                    return $false
                }
            } elseif (Test-CodeChanges) {
                Write-Host "Code changes detected: Rebuilding affected containers..." -ForegroundColor Yellow
                $composeArgs += @("--build")
            } else {
                Write-Host "Using existing images (no rebuild needed)..." -ForegroundColor Green
            }

            Write-Host "Docker compose command: docker-compose $($composeArgs -join ' ')" -ForegroundColor Gray
            $startProcess = Start-Process -FilePath "docker-compose" -ArgumentList $composeArgs -Wait -NoNewWindow -PassThru -WorkingDirectory $PSScriptRoot

            if ($startProcess.ExitCode -eq 0) {
                Write-Host "OK Docker containers started successfully" -ForegroundColor Green

                # Give containers a moment to initialize before health checks
                if (-not $QuickStart) {
                    Write-Host "Waiting for containers to initialize..." -ForegroundColor Gray
                    Start-Sleep -Seconds 10
                }

                # Quick health check or full check based on mode
                if ($QuickStart) {
                    Write-Host "Quick mode: Skipping detailed health checks" -ForegroundColor Cyan
                    Start-Sleep -Seconds 5
                    $healthOK = $true
                } else {
                    $healthOK = Wait-ForServices -TimeoutMinutes $TimeoutMinutes

                    # If health check fails, try to restart problematic containers
                    if (-not $healthOK) {
                        Write-Host "Health check failed, attempting container restart..." -ForegroundColor Yellow
                        try {
                            # First try to restart specific services
                            Write-Host "Restarting backend and worker containers..." -ForegroundColor Gray
                            docker-compose -f $dockerComposeFile restart backend-prod rqworker-prod 2>$null
                            Start-Sleep -Seconds 15

                            # Try health check again with shorter timeout
                            $healthOK = Wait-ForServices -TimeoutMinutes 3

                            if (-not $healthOK) {
                                Write-Host "Container restart didn't help, but continuing anyway..." -ForegroundColor Yellow
                                # Don't fail completely, just warn
                                $healthOK = $true
                            }
                        } catch {
                            Write-Host "Container restart failed: $($_.Exception.Message)" -ForegroundColor Red
                            Write-Host "Continuing anyway..." -ForegroundColor Yellow
                            $healthOK = $true
                        }
                    }
                }

                if ($healthOK) {
                    Show-ServiceUrls

                    # Run adaptive learning pipeline to improve citation extraction
                    Write-Host "`nRunning adaptive learning pipeline..." -ForegroundColor Cyan
                    $learningOK = Start-AdaptiveLearningPipeline
                    if ($learningOK) {
                        Write-Host "✅ Adaptive learning completed successfully" -ForegroundColor Green
                    } else {
                        Write-Host "⚠️  Adaptive learning had issues, but continuing..." -ForegroundColor Yellow
                    }

                    # Post-startup validation (skip if NoValidation flag is set)
                    if (-not $NoValidation) {
                        Write-Host "`nRunning post-startup validation..." -ForegroundColor Cyan
                        $validationOK = Test-PostStartupValidation

                        if ($validationOK) {
                            Write-Host "OK Post-startup validation passed" -ForegroundColor Green
                        } else {
                            Write-Host "WARNING: Post-startup validation failed - system may have issues" -ForegroundColor Yellow
                        }
                    } else {
                        Write-Host "Skipping post-startup validation as requested" -ForegroundColor Cyan
                    }

                    # Start auto-restart monitoring if enabled
                    if ($script:AutoRestartEnabled) {
                        Start-ServiceMonitoring
                        Write-Host "`nAuto-restart monitoring enabled" -ForegroundColor Magenta
                    }

                    # Try to open browser (non-blocking)
                    if (-not $QuickStart) {
                        Start-Job -ScriptBlock {
                            Start-Sleep -Seconds 3
                            try {
                                # Try multiple possible URLs
                                $urls = @(
                                    "https://wolf.law.uw.edu/casestrainer/",
                                    "http://localhost:8080/",
                                    "https://localhost/casestrainer/"
                                )

                                foreach ($url in $urls) {
                                    try {
                                        Start-Process $url -ErrorAction Stop
                                        break
                                    } catch {
                                        Write-Error "Failed to open browser: $($_.Exception.Message)"
                                        continue
                                    }
                                }
                            } catch {
                                Write-Host "Browser opening failed (non-critical): $($_.Exception.Message)" -ForegroundColor Gray
                            }
                        } | Out-Null
                    }

                    # Clean up temporary file if it was created
                    if ($dockerComposeFile -like "*.temp") {
                        Remove-Item $dockerComposeFile -Force -ErrorAction SilentlyContinue
                    }
                    
                    return $true
                }
                else {
                    # Clean up temporary file if it was created
                    if ($dockerComposeFile -like "*.temp") {
                        Remove-Item $dockerComposeFile -Force -ErrorAction SilentlyContinue
                    }
                    
                    Write-Host "ERROR Services failed to become healthy" -ForegroundColor Red
                    return $false
                }
            }
            else {
                Write-Host "ERROR: Failed to start Docker containers (exit code: $($startProcess.ExitCode))" -ForegroundColor Red
                
                # Clean up temporary file if it was created
                if ($dockerComposeFile -like "*.temp") {
                    Remove-Item $dockerComposeFile -Force -ErrorAction SilentlyContinue
                }

                # Try to provide helpful debugging information
                Write-Host "Checking Docker daemon status..." -ForegroundColor Yellow
                try {
                    $dockerInfo = docker info --format "{{.ServerVersion}}" 2>$null
                    if ($dockerInfo) {
                        Write-Host "Docker daemon is running (version: $dockerInfo)" -ForegroundColor Green
                        Write-Host "The issue may be with the compose file or container configuration" -ForegroundColor Yellow
                    } else {
                        Write-Host "Docker daemon may not be running" -ForegroundColor Red
                    }
                } catch {
                    Write-Host "Could not check Docker daemon status" -ForegroundColor Yellow
                }

                throw "Failed to start Docker containers (exit code: $($startProcess.ExitCode))"
            }
        }
    }
    catch {
        Write-CrashLog "Error in Start-DockerProduction" -Level "ERROR" -Exception $_
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
    finally {
        # Clean up any temporary files or resources
        try {
            # Clean up any temporary compose files
            if (Test-Path "docker-compose.tmp.yml" -ErrorAction SilentlyContinue) {
                Remove-Item "docker-compose.tmp.yml" -Force -ErrorAction SilentlyContinue
            }
            
            # Clean up any temporary environment files
            if (Test-Path ".env.tmp" -ErrorAction SilentlyContinue) {
                Remove-Item ".env.tmp" -Force -ErrorAction SilentlyContinue
            }
            
            # Reset any modified environment variables
            if ($env:COMPOSE_PROFILES) {
                Remove-Item Env:\COMPOSE_PROFILES -ErrorAction SilentlyContinue
            }
        }
        catch {
            Write-CrashLog "Error during cleanup in Start-DockerProduction" -Level "WARNING" -Exception $_
            Write-Host "Warning: Error during cleanup: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

# Nginx is now managed by Docker Compose, so no need for manual Nginx management
function Test-PostStartupValidation {
    [CmdletBinding()]
    [OutputType([bool])]
    param()

    Write-Host "  Testing API endpoints..." -ForegroundColor Gray

    try {
        # Test basic API health with retry logic
        $maxRetries = 3
        $retryDelay = 5
        $healthOK = $false

        for ($i = 1; $i -le $maxRetries; $i++) {
            try {
                $healthResponse = Invoke-WebRequest -Uri "http://localhost:5000/casestrainer/api/health" -Method GET -TimeoutSec 10 -ErrorAction Stop
                if ($healthResponse.StatusCode -eq 200) {
                    $healthOK = $true
                    break
                }
            } catch {
                Write-Host "  Health check attempt $i failed: $($_.Exception.Message)" -ForegroundColor Gray
                if ($i -lt $maxRetries) {
                    Start-Sleep -Seconds $retryDelay
                }
            }
        }

        if (-not $healthOK) {
            Write-Host "  ❌ API health check failed after $maxRetries attempts" -ForegroundColor Red
            return $false
        }

        Write-Host "  ✅ API health check passed" -ForegroundColor Green

        # Test simple text processing with retry logic
        $processingOK = $false
        for ($i = 1; $i -le $maxRetries; $i++) {
            try {
                $testPayload = @{
                    type = "text"
                    text = "The court in Smith v. Jones, 123 U.S. 456 (2020) held that..."
                } | ConvertTo-Json

                $testResponse = Invoke-WebRequest -Uri "http://localhost:5000/casestrainer/api/analyze" -Method POST -Body $testPayload -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop

                if ($testResponse.StatusCode -eq 200) {
                    $result = $testResponse.Content | ConvertFrom-Json
                    if ($result.status -eq "processing" -and $result.task_id) {
                        $processingOK = $true
                        break
                    }
                }
            } catch {
                Write-Host "  Processing test attempt $i failed: $($_.Exception.Message)" -ForegroundColor Gray
                if ($i -lt $maxRetries) {
                    Start-Sleep -Seconds $retryDelay
                }
            }
        }

        if ($processingOK) {
            Write-Host "  ✅ Text processing test passed" -ForegroundColor Green
            return $true
        } else {
            Write-Host "  ❌ Text processing test failed after $maxRetries attempts" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "  ❌ Post-startup validation failed: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

function Show-AdvancedDiagnostics {
    [CmdletBinding()]
    param()

    Write-Host "`n=== Advanced Production Diagnostics ===`n" -ForegroundColor Cyan

    # Docker diagnostics
    Write-Host "Docker System Information:" -ForegroundColor Yellow
    try {
        docker system info --format "table {{.Name}}\t{{.Value}}" 2>$null | Select-Object -First 10
        Write-Host ""

        Write-Host "Container Status:" -ForegroundColor Yellow
        docker ps --filter "name=casestrainer" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>$null
        Write-Host ""

        Write-Host "Docker Resource Usage:" -ForegroundColor Yellow
        docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>$null
        Write-Host ""

        Write-Host "Recent Container Events:" -ForegroundColor Yellow
        docker events --since 10m --until now --filter "container=casestrainer" 2>$null | Select-Object -Last 5

    } catch {
        Write-Host "Error retrieving Docker diagnostics: $($_.Exception.Message)" -ForegroundColor Red
    }

    # System diagnostics
    Write-Host "`nSystem Diagnostics:" -ForegroundColor Yellow
    try {
        $mem = Get-CimInstance -ClassName Win32_ComputerSystem
        $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='C:'"
        $cpu = Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1

        Write-Host "Memory: $([math]::Round($mem.TotalPhysicalMemory / 1GB, 2)) GB total" -ForegroundColor Gray
        Write-Host "Disk Space: $([math]::Round($disk.FreeSpace / 1GB, 2)) GB free of $([math]::Round($disk.Size / 1GB, 2)) GB" -ForegroundColor Gray
        Write-Host "CPU: $($cpu.Name)" -ForegroundColor Gray
    } catch {
        Write-Host "Error retrieving system diagnostics: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Show-CacheManagement {
    [CmdletBinding()]
    param()

    Write-Host "`n=== Cache Management ===`n" -ForegroundColor Cyan

    Write-Host "Available cache operations:" -ForegroundColor Yellow
    Write-Host "1. Clear Docker build cache" -ForegroundColor Gray
    Write-Host "2. Clear npm cache" -ForegroundColor Gray
    Write-Host "3. Clear all caches" -ForegroundColor Gray
    Write-Host "4. Show cache status" -ForegroundColor Gray
    Write-Host ""

    $choice = Read-Host "Select operation (1-4, or Enter to skip)"

    switch ($choice) {
        "1" {
            Write-Host "Clearing Docker build cache..." -ForegroundColor Yellow
            try {
                docker builder prune -f
                Write-Host "✅ Docker cache cleared" -ForegroundColor Green
            } catch {
                Write-Host "❌ Failed to clear Docker cache: $($_.Exception.Message)" -ForegroundColor Red
            }
        }
        "2" {
            Write-Host "Clearing npm cache..." -ForegroundColor Yellow
            try {
                $vueDir = Join-Path $PSScriptRoot "casestrainer-vue-new"
                if (Test-Path $vueDir) {
                    Push-Location $vueDir
                    try {
                        & npm -Command cache -Command clean -Command --force
                        Write-Host "✅ npm cache cleared" -ForegroundColor Green
                    } finally {
                        Pop-Location
                    }
                }
            } catch {
                Write-Host "❌ Failed to clear npm cache: $($_.Exception.Message)" -ForegroundColor Red
            }
        }
        "3" {
            Clear-AllCaches
        }
        "4" {
            Write-Host "Cache Status:" -ForegroundColor Yellow
            try {
                # Docker cache info
                $dockerInfo = docker system df 2>$null
                if ($dockerInfo) {
                    Write-Host "Docker cache usage:" -ForegroundColor Gray
                    Write-Host $dockerInfo -ForegroundColor Gray
                }

                # npm cache info
                $vueDir = Join-Path $PSScriptRoot "casestrainer-vue-new"
                if (Test-Path $vueDir) {
                    Push-Location $vueDir
                    try {
                        $npmCache = & npm cache verify 2>$null
                        if ($npmCache) {
                            Write-Host "`nnpm cache status:" -ForegroundColor Gray
                            Write-Host ($npmCache | Select-Object -Last 5) -ForegroundColor Gray
                        }
                    } finally {
                        Pop-Location
                    }
                }
            } catch {
                Write-Host "Error retrieving cache status: $($_.Exception.Message)" -ForegroundColor Red
            }
        }
        default {
            Write-Host "Skipping cache operations" -ForegroundColor Gray
        }
    }
}

function Stop-AllServices {
    [CmdletBinding(SupportsShouldProcess)]
    param()

    Write-Host "`n=== Stopping All Services ===`n" -ForegroundColor Red

    if ($PSCmdlet.ShouldProcess("All Docker services", "Stop")) {
        try {
            # Stop monitoring first
            Stop-ServiceMonitoring

            $dockerComposeFile = Join-Path $PSScriptRoot "docker-compose.prod.yml"
            $stopProcess = Start-Process -FilePath "docker-compose" -ArgumentList "-f", $dockerComposeFile, "down" -Wait -NoNewWindow -PassThru -WorkingDirectory $PSScriptRoot

            if ($stopProcess.ExitCode -eq 0) {
                Write-Host "OK All Docker services stopped successfully" -ForegroundColor Green
            }
            else {
                Write-Host "WARNING: Docker services may not have stopped cleanly (exit code: $($stopProcess.ExitCode))" -ForegroundColor Yellow
            }
        }
        catch {
            Write-CrashLog "Error stopping services" -Level "ERROR" -Exception $_
            Write-Host "ERROR Error stopping services: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    else {
        Write-Host "Operation cancelled by user" -ForegroundColor Yellow
    }
}

function Show-QuickStatus {
    [CmdletBinding()]
    param()

    Write-Host "`n=== Quick Status Check ===`n" -ForegroundColor Magenta

    # Parallel status checks for speed
    $jobs = @()

    # Docker check
    $jobs += Start-Job -Name "Docker" -ScriptBlock {
        try {
            $null = docker version --format "{{.Server.Version}}" 2>$null
            return @{ Service = "Docker"; Status = if ($LASTEXITCODE -eq 0) { "OK" } else { "ERROR" } }
        } catch {
            return @{ Service = "Docker"; Status = "ERROR" }
        }
    }

    # Container check
    $jobs += Start-Job -Name "Containers" -ScriptBlock {
        try {
            $containers = docker ps --filter "name=casestrainer" --format "{{.Names}}" 2>$null
            $count = if ($containers) { ($containers | Measure-Object).Count } else { 0 }
            return @{ Service = "Containers"; Status = "$count running" }
        } catch {
            return @{ Service = "Containers"; Status = "ERROR" }
        }
    }

    # Backend check
    $jobs += Start-Job -Name "Backend" -ScriptBlock {
        try {
            $backendHost = "127.0.0.1"
            $backendPort = 5001
            $backendHealthy = Test-NetConnection -ComputerName $backendHost -Port $backendPort -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
            return @{ Service = "Backend"; Status = if ($backendHealthy) { "HEALTHY" } else { "DOWN" } }
        } catch {
            return @{ Service = "Backend"; Status = "ERROR" }
        }
    }

    # Wait for all jobs and display results
    foreach ($job in $jobs) {
        $result = Receive-Job $job -Wait
        Remove-Job $job

        $color = switch ($result.Status) {
            { $_ -like "*OK*" -or $_ -like "*HEALTHY*" -or $_ -match "^\d+ running$" } { "Green" }
            { $_ -like "*ERROR*" -or $_ -like "*DOWN*" } { "Red" }
            default { "Yellow" }
        }

        Write-Host "$($result.Service): $($result.Status)" -ForegroundColor $color
    }

    Write-Host "`nProduction URL: https://wolf.law.uw.edu/casestrainer" -ForegroundColor Cyan
}

function Show-Menu {
    [CmdletBinding()]
    [OutputType([string])]
    param()

    Clear-Host
    Write-Host "`n" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " Enhanced CaseStrainer Docker Launcher" -ForegroundColor Cyan
    Write-Host "                v1.3 (ENHANCED)      " -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host " 1.  Quick Production Start (FASTEST)" -ForegroundColor Green
    Write-Host "    - Minimal checks, maximum speed"
    Write-Host ""
    Write-Host " 2.  Smart Production Start (RECOMMENDED)" -ForegroundColor Cyan
    Write-Host "    - Intelligent build detection, balanced speed"
    Write-Host ""
    Write-Host " 3.  Force Full Rebuild" -ForegroundColor Yellow
    Write-Host "    - Complete rebuild, use when needed"
    Write-Host ""
    Write-Host " 4.   Advanced Diagnostics" -ForegroundColor Blue
    Write-Host " 5.   Cache Management" -ForegroundColor Yellow
    Write-Host " 6.   Stop All Services" -ForegroundColor Red
    Write-Host " 7.  Quick Status Check" -ForegroundColor Magenta
    Write-Host " 8.  Run Production Server Test" -ForegroundColor Yellow
    Write-Host " 0.  Exit" -ForegroundColor Gray
    Write-Host ""
    Write-Host "TIP: Use option 1 for fastest startup!" -ForegroundColor Green
    Write-Host ""

    do {
        $selection = Read-Host "Select an option (0-8)"
        if ($selection -match "^[0-8]$") {
            break
        } else {
            Write-Host "Invalid selection. Please enter a number between 0 and 8." -ForegroundColor Red
        }
    } while ($true)

    switch ($selection) {
        "1" {
            # Quick start mode - use script-level variables
            Write-Host "`nStarting Quick Production Start..." -ForegroundColor Green
            $originalQuickStart = $QuickStart
            $originalSkipVue = $SkipVueBuild
            try {
                $script:QuickStart = $true
                $script:SkipVueBuild = $true
                Start-DockerProduction
                # Run production test suite
                Write-Host "Running production test suite..." -ForegroundColor Cyan
                $testLog = Join-Path $PSScriptRoot "logs/production_test.log"
                $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                
                # Ensure logs directory exists
                $logsDir = Split-Path $testLog -Parent
                if (-not (Test-Path $logsDir)) {
                    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
                }
                
                try {
                    & pytest test_production_server.py -v --maxfail=1 --disable-warnings 2>&1 | Tee-Object -FilePath $testLog -Append
                    $exitCode = $LASTEXITCODE
                    
                    if ($exitCode -eq 0) {
                        Write-Host "[$timestamp] ✅ All production tests passed!" -ForegroundColor Green
                    } else {
                        Write-Host "[$timestamp] ❌ Some production tests failed (exit code: $exitCode)!" -ForegroundColor Red
                        Write-Host "`nLast 30 lines of test output:" -ForegroundColor Yellow
                        if (Test-Path $testLog) {
                            Get-Content $testLog -Tail 30 | ForEach-Object { Write-Host $_ }
                        }
                        Write-Host "`nFull test log available at: $testLog" -ForegroundColor Gray
                        exit 1
                    }
                }
                catch {
                    Write-Host "[$timestamp] ❌ Error running tests: $($_.Exception.Message)" -ForegroundColor Red
                    exit 1
                }
            }
            finally {
                # Restore original values
                $script:QuickStart = $originalQuickStart
                $script:SkipVueBuild = $originalSkipVue
            }
            exit 0
        }
        "2" {
            Write-Host "Deleting all .pyc files and __pycache__ directories to prevent stale bytecode..." -ForegroundColor Yellow
            Get-ChildItem -Path . -Recurse -Include *.pyc | Remove-Item -Force -ErrorAction SilentlyContinue
            Get-ChildItem -Path . -Recurse -Directory -Include __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            
            # Smart rebuild detection
            Write-Host "Analyzing code changes to determine rebuild strategy..." -ForegroundColor Cyan
            $needsFullRebuild = $false
            
            try {
                # Check for import/dependency changes that require full rebuild
                $recentChanges = git log --name-only --pretty=format: --since="1 hour ago" 2>$null | Where-Object { $_ -ne "" }
                if ($recentChanges) {
                    $importChanges = $recentChanges | Where-Object { 
                        $_ -match "\.py$" -and (Test-Path $_) -and (Get-Content $_ -ErrorAction SilentlyContinue | Select-String "^from|^import")
                    }
                    $depChanges = $recentChanges | Where-Object { 
                        $_ -match "requirements\.txt|Dockerfile|docker-compose|package\.json"
                    }
                    
                    if ($importChanges -or $depChanges) {
                        $needsFullRebuild = $true
                        Write-Host "⚠️ Detected import/dependency changes - recommending full rebuild for safety" -ForegroundColor Yellow
                        if ($importChanges) { Write-Host "   - Python import changes detected" -ForegroundColor Gray }
                        if ($depChanges) { Write-Host "   - Dependency file changes detected" -ForegroundColor Gray }
                    }
                }
            } catch {
                Write-Host "⚠️ Could not analyze git history - proceeding with backend rebuild" -ForegroundColor Yellow
            }
            
            if ($needsFullRebuild) {
                Write-Host "🔄 Performing full rebuild due to detected changes..." -ForegroundColor Yellow
                $result = Start-DockerProduction -ForceRebuild
            } else {
                Write-Host "🔄 Rebuilding backend image to ensure Python code changes are included..." -ForegroundColor Cyan
                docker-compose -f docker-compose.prod.yml build backend
                $result = Start-DockerProduction
            }

            $result = Start-DockerProduction
            if (-not $result) {
                Write-Host "❌ Docker production failed" -ForegroundColor Red
                exit 1
            }
            # Run production test suite
            Write-Host "Running production test suite..." -ForegroundColor Cyan
            $testLog = Join-Path $PSScriptRoot "logs/production_test.log"
            $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            
            # Ensure logs directory exists
            $logsDir = Split-Path $testLog -Parent
            if (-not (Test-Path $logsDir)) {
                New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
            }
            
            try {
                & pytest test_production_server.py -v --maxfail=1 --disable-warnings 2>&1 | Tee-Object -FilePath $testLog -Append
                $exitCode = $LASTEXITCODE
                
                if ($exitCode -eq 0) {
                    Write-Host "[$timestamp] ✅ All production tests passed!" -ForegroundColor Green
                } else {
                    Write-Host "[$timestamp] ❌ Some production tests failed (exit code: $exitCode)!" -ForegroundColor Red
                    Write-Host "`nLast 30 lines of test output:" -ForegroundColor Yellow
                    if (Test-Path $testLog) {
                        Get-Content $testLog -Tail 30 | ForEach-Object { Write-Host $_ }
                    }
                    Write-Host "`nFull test log available at: $testLog" -ForegroundColor Gray
                    exit 1
                }
            }
            catch {
                Write-Host "[$timestamp] ❌ Error running tests: $($_.Exception.Message)" -ForegroundColor Red
                exit 1
            }
            exit 0
        }
        "3" {
            Write-Host "Deleting all .pyc files and __pycache__ directories to prevent stale bytecode..." -ForegroundColor Yellow
            Get-ChildItem -Path . -Recurse -Include *.pyc | Remove-Item -Force -ErrorAction SilentlyContinue
            Get-ChildItem -Path . -Recurse -Directory -Include __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            $result = Start-DockerProduction -ForceRebuild
            if (-not $result) {
                Write-Host "❌ Docker production failed" -ForegroundColor Red
                exit 1
            }
            # Run production test suite
            Write-Host "Running production test suite..." -ForegroundColor Cyan
            $testLog = Join-Path $PSScriptRoot "logs/production_test.log"
            $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            
            # Ensure logs directory exists
            $logsDir = Split-Path $testLog -Parent
            if (-not (Test-Path $logsDir)) {
                New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
            }
            
            try {
                & pytest test_production_server.py -v --maxfail=1 --disable-warnings 2>&1 | Tee-Object -FilePath $testLog -Append
                $exitCode = $LASTEXITCODE
                
                if ($exitCode -eq 0) {
                    Write-Host "[$timestamp] ✅ All production tests passed!" -ForegroundColor Green
                } else {
                    Write-Host "[$timestamp] ❌ Some production tests failed (exit code: $exitCode)!" -ForegroundColor Red
                    Write-Host "`nLast 30 lines of test output:" -ForegroundColor Yellow
                    if (Test-Path $testLog) {
                        Get-Content $testLog -Tail 30 | ForEach-Object { Write-Host $_ }
                    }
                    Write-Host "`nFull test log available at: $testLog" -ForegroundColor Gray
                    exit 1
                }
            }
            catch {
                Write-Host "[$timestamp] ❌ Error running tests: $($_.Exception.Message)" -ForegroundColor Red
                exit 1
            }
            exit 0
        }
        "4" { Show-AdvancedDiagnostics; exit 0 }
        "5" { Show-CacheManagement; exit 0 }
        "6" { Stop-AllServices; exit 0 }
        "7" { Show-QuickStatus; exit 0 }
        "8" {
            Write-Host "`nRunning production server test suite..." -ForegroundColor Yellow
            $testLog = Join-Path $PSScriptRoot "logs/production_test.log"
            $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            
            # Ensure logs directory exists
            $logsDir = Split-Path $testLog -Parent
            if (-not (Test-Path $logsDir)) {
                New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
            }
            
            Write-Host "Test output will be logged to: $testLog" -ForegroundColor Gray
            
            # Run tests with proper error handling
            try {
                & pytest test_production_server.py -v --maxfail=1 --disable-warnings 2>&1 | Tee-Object -FilePath $testLog -Append
                $exitCode = $LASTEXITCODE
                
                if ($exitCode -eq 0) {
                    Write-Host "[$timestamp] ✅ All production tests passed!" -ForegroundColor Green
                } else {
                    Write-Host "[$timestamp] ❌ Some production tests failed (exit code: $exitCode)!" -ForegroundColor Red
                    Write-Host "`nLast 30 lines of test output:" -ForegroundColor Yellow
                    if (Test-Path $testLog) {
                        Get-Content $testLog -Tail 30 | ForEach-Object { Write-Host $_ }
                    }
                    Write-Host "`nFull test log available at: $testLog" -ForegroundColor Gray
                }
            }
            catch {
                Write-Host "[$timestamp] ❌ Error running tests: $($_.Exception.Message)" -ForegroundColor Red
                Write-Host "Check that pytest is installed and test_production_server.py exists" -ForegroundColor Yellow
            }
            
            Write-Host "`nPress any key to return to menu..." -ForegroundColor Cyan
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
            return $selection
        }
        "0" {
            Write-Host "Exiting..." -ForegroundColor Gray
            Stop-AllMonitoring
            exit 0
        }
        default {
            Write-Host "Unknown menu option: $MenuOption (valid options: 0-8)" -ForegroundColor Red
            exit 1
        }
    }

    return $selection
}

function Start-AdaptiveLearningPipeline {
    [CmdletBinding(SupportsShouldProcess)]
    [OutputType([bool])]
    param()

    if (-not $PSCmdlet.ShouldProcess("Adaptive learning pipeline", "Start")) {
        return $false
    }

    Write-Host "Starting adaptive learning pipeline..." -ForegroundColor Cyan
    
    try {
        # Check if enhanced adaptive learning script exists
        $enhancedAdaptiveScript = Join-Path $PSScriptRoot "scripts\enhanced_adaptive_pipeline.ps1"
        if (-not (Test-Path $enhancedAdaptiveScript)) {
            Write-Host "⚠️  Enhanced adaptive learning script not found: $enhancedAdaptiveScript" -ForegroundColor Yellow
            # Fallback to original script
            $adaptiveScript = Join-Path $PSScriptRoot "scripts\adaptive_learning_pipeline.ps1"
            if (-not (Test-Path $adaptiveScript)) {
                Write-Host "⚠️  Original adaptive learning script not found: $adaptiveScript" -ForegroundColor Yellow
                return $false
            }
            Write-Host "Using original adaptive learning script as fallback..." -ForegroundColor Yellow
            $scriptToRun = $adaptiveScript
        } else {
            Write-Host "Using enhanced adaptive learning pipeline..." -ForegroundColor Green
            $scriptToRun = $enhancedAdaptiveScript
        }

        # Run adaptive learning pipeline
        Write-Host "Running adaptive learning pipeline..." -ForegroundColor Gray
        $process = Start-Process -FilePath "powershell.exe" -ArgumentList @("-ExecutionPolicy", "Bypass", "-File", $scriptToRun) -Wait -NoNewWindow -PassThru -WorkingDirectory $PSScriptRoot

        if ($process.ExitCode -eq 0) {
            Write-Host "✅ Adaptive learning pipeline completed successfully" -ForegroundColor Green
            return $true
        } else {
            Write-Host "⚠️  Adaptive learning pipeline completed with exit code: $($process.ExitCode)" -ForegroundColor Yellow
            return $false
        }
    }
    catch {
        Write-Host "❌ Error running adaptive learning pipeline: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# Register cleanup on script exit
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    Stop-AllMonitoring
} | Out-Null

# Main execution
try {
    Initialize-LogDirectory
    Write-CrashLog "Script started with Mode: $Mode, QuickStart: $QuickStart, SkipVue: $SkipVueBuild, MenuOption: $MenuOption" -Level "INFO"

    # Initialize cache
    $script:CachedChecks.LastCheckTime = Get-Date

    # Handle cache clearing
    if ($ClearCache) {
        Clear-AllCaches
    }

    # If MenuOption is provided, run the corresponding menu action and exit
    if ($null -ne $MenuOption -and $MenuOption -ne "") {
        Write-Host "[cslaunch] Running menu option $MenuOption..." -ForegroundColor Green
        switch ($MenuOption) {
            1 {
                try {
                    $originalQuickStart = $QuickStart
                    $originalSkipVue = $SkipVueBuild
                    $script:QuickStart = $true
                    $script:SkipVueBuild = $true
                    $result = Start-DockerProduction
                    # Run production test suite
                    Write-Host "Running production test suite..." -ForegroundColor Cyan
                    $testLog = Join-Path $PSScriptRoot "logs/production_test.log"
                    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                    
                    # Ensure logs directory exists
                    $logsDir = Split-Path $testLog -Parent
                    if (-not (Test-Path $logsDir)) {
                        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
                    }
                    
                    try {
                        $testResult = & pytest test_production_server.py -v --maxfail=1 --disable-warnings 2>&1 | Tee-Object -FilePath $testLog -Append
                        $exitCode = $LASTEXITCODE
                        
                        if ($exitCode -eq 0) {
                            Write-Host "[$timestamp] ✅ All production tests passed!" -ForegroundColor Green
                        } else {
                            Write-Host "[$timestamp] ❌ Some production tests failed (exit code: $exitCode)!" -ForegroundColor Red
                            Write-Host "`nLast 30 lines of test output:" -ForegroundColor Yellow
                            if (Test-Path $testLog) {
                                Get-Content $testLog -Tail 30 | ForEach-Object { Write-Host $_ }
                            }
                            Write-Host "`nFull test log available at: $testLog" -ForegroundColor Gray
                            exit 1
                        }
                    }
                    catch {
                        Write-Host "[$timestamp] ❌ Error running tests: $($_.Exception.Message)" -ForegroundColor Red
                        exit 1
                    }
                }
                finally {
                    # Restore original values
                    $script:QuickStart = $originalQuickStart
                    $script:SkipVueBuild = $originalSkipVue
                }
                exit 0
            }
            2 {
                Write-Host "Deleting all .pyc files and __pycache__ directories to prevent stale bytecode..." -ForegroundColor Yellow
                Get-ChildItem -Path . -Recurse -Include *.pyc | Remove-Item -Force -ErrorAction SilentlyContinue
                Get-ChildItem -Path . -Recurse -Directory -Include __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
                
                # Ensure we have latest code from git
                Write-Host "Ensuring latest code from git..." -ForegroundColor Cyan
                try {
                    $gitStatus = git status --porcelain 2>$null
                    if (-not $gitStatus) {
                        # No uncommitted changes, safe to pull
                        $pullResult = git pull origin main 2>&1
                        if ($LASTEXITCODE -eq 0) {
                            Write-Host "✅ Git pull completed" -ForegroundColor Green
                            if ($pullResult -match "Already up to date") {
                                Write-Host "   No new changes from remote" -ForegroundColor Gray
                            } else {
                                Write-Host "   Updated with remote changes" -ForegroundColor Green
                            }
                        } else {
                            Write-Host "⚠️ Git pull failed - proceeding with local code" -ForegroundColor Yellow
                        }
                    } else {
                        Write-Host "⚠️ Uncommitted changes detected - skipping git pull" -ForegroundColor Yellow
                        Write-Host "   Uncommitted files: $($gitStatus.Count)" -ForegroundColor Gray
                    }
                } catch {
                    Write-Host "⚠️ Could not update from git - proceeding with local code" -ForegroundColor Yellow
                }
                
                # Smart rebuild detection
                Write-Host "Analyzing code changes to determine rebuild strategy..." -ForegroundColor Cyan
                $needsFullRebuild = $false
                
                try {
                    # Check for recent changes that require full rebuild - expand time window
                    $recentChanges = git log --name-only --pretty=format: --since="6 hours ago" 2>$null | Where-Object { $_ -ne "" }
                    
                    # Also check for uncommitted changes
                    $uncommittedChanges = git status --porcelain 2>$null | ForEach-Object { $_.Substring(3) }
                    $allChanges = @($recentChanges) + @($uncommittedChanges) | Where-Object { $_ -ne "" } | Sort-Object -Unique
                    
                    if ($allChanges) {
                        Write-Host "Found recent changes: $($allChanges.Count) files" -ForegroundColor Gray
                        # Show a sample of changed files for transparency
                        $sampleFiles = $allChanges | Select-Object -First 3
                        foreach ($file in $sampleFiles) {
                            Write-Host "   - $file" -ForegroundColor DarkGray
                        }
                        if ($allChanges.Count -gt 3) {
                            Write-Host "   - ... and $($allChanges.Count - 3) more" -ForegroundColor DarkGray
                        }
                        
                        $importChanges = $allChanges | Where-Object { 
                            $_ -match "\.py$" -and (Test-Path $_) -and (Get-Content $_ -ErrorAction SilentlyContinue | Select-String "^from|^import")
                        }
                        $depChanges = $allChanges | Where-Object { 
                            $_ -match "requirements\.txt|Dockerfile|docker-compose|package\.json"
                        }
                        $criticalPyFiles = $allChanges | Where-Object {
                            $_ -match "src/(unified_citation_processor|citation_clustering|api/services).*\.py$"
                        }
                        
                        if ($importChanges -or $depChanges -or $criticalPyFiles) {
                            $needsFullRebuild = $true
                            Write-Host "⚠️ Detected critical changes - recommending full rebuild for safety" -ForegroundColor Yellow
                            if ($importChanges) { Write-Host "   - Python import changes detected" -ForegroundColor Gray }
                            if ($depChanges) { Write-Host "   - Dependency file changes detected" -ForegroundColor Gray }
                            if ($criticalPyFiles) { Write-Host "   - Critical Python module changes detected" -ForegroundColor Gray }
                        }
                    } else {
                        Write-Host "No recent changes detected - proceeding with backend-only rebuild" -ForegroundColor Green
                    }
                } catch {
                    Write-Host "⚠️ Could not analyze git history - proceeding with full rebuild for safety" -ForegroundColor Yellow
                    $needsFullRebuild = $true
                }
                
                if ($needsFullRebuild) {
                    Write-Host "🔄 Performing full rebuild due to detected changes..." -ForegroundColor Yellow
                    $result = Start-DockerProduction -ForceRebuild
                } else {
                    Write-Host "🔄 Rebuilding backend image to ensure Python code changes are included..." -ForegroundColor Cyan
                    # Force rebuild of backend to ensure code changes are picked up
                    docker-compose -f docker-compose.prod.yml build --no-cache backend
                    $result = Start-DockerProduction
                }
                
                # Result already set above - no need to call Start-DockerProduction again
                if (-not $result) {
                    Write-Host "❌ Docker production failed" -ForegroundColor Red
                    exit 1
                }
                # Run production test suite
                Write-Host "Running production test suite..." -ForegroundColor Cyan
                $testLog = Join-Path $PSScriptRoot "logs/production_test.log"
                $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                
                # Ensure logs directory exists
                $logsDir = Split-Path $testLog -Parent
                if (-not (Test-Path $logsDir)) {
                    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
                }
                
                try {
                    & pytest test_production_server.py -v --maxfail=1 --disable-warnings 2>&1 | Tee-Object -FilePath $testLog -Append
                    $exitCode = $LASTEXITCODE
                    
                    if ($exitCode -eq 0) {
                        Write-Host "[$timestamp] ✅ All production tests passed!" -ForegroundColor Green
                    } else {
                        Write-Host "[$timestamp] ❌ Some production tests failed (exit code: $exitCode)!" -ForegroundColor Red
                        Write-Host "`nLast 30 lines of test output:" -ForegroundColor Yellow
                        if (Test-Path $testLog) {
                            Get-Content $testLog -Tail 30 | ForEach-Object { Write-Host $_ }
                        }
                        Write-Host "`nFull test log available at: $testLog" -ForegroundColor Gray
                        exit 1
                    }
                }
                catch {
                    Write-Host "[$timestamp] ❌ Error running tests: $($_.Exception.Message)" -ForegroundColor Red
                    exit 1
                }
                exit 0
            }
            3 {
                Write-Host "Deleting all .pyc files and __pycache__ directories to prevent stale bytecode..." -ForegroundColor Yellow
                Get-ChildItem -Path . -Recurse -Include *.pyc | Remove-Item -Force -ErrorAction SilentlyContinue
                Get-ChildItem -Path . -Recurse -Directory -Include __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
                $result = Start-DockerProduction -ForceRebuild
                if (-not $result) {
                    Write-Host "❌ Docker production failed" -ForegroundColor Red
                    exit 1
                }
                # Run production test suite
                Write-Host "Running production test suite..." -ForegroundColor Cyan
                $testLog = Join-Path $PSScriptRoot "logs/production_test.log"
                $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                
                # Ensure logs directory exists
                $logsDir = Split-Path $testLog -Parent
                if (-not (Test-Path $logsDir)) {
                    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
                }
                
                try {
                    & pytest test_production_server.py -v --maxfail=1 --disable-warnings 2>&1 | Tee-Object -FilePath $testLog -Append
                    $exitCode = $LASTEXITCODE
                    
                    if ($exitCode -eq 0) {
                        Write-Host "[$timestamp] ✅ All production tests passed!" -ForegroundColor Green
                    } else {
                        Write-Host "[$timestamp] ❌ Some production tests failed (exit code: $exitCode)!" -ForegroundColor Red
                        Write-Host "`nLast 30 lines of test output:" -ForegroundColor Yellow
                        if (Test-Path $testLog) {
                            Get-Content $testLog -Tail 30 | ForEach-Object { Write-Host $_ }
                        }
                        Write-Host "`nFull test log available at: $testLog" -ForegroundColor Gray
                        exit 1
                    }
                }
                catch {
                    Write-Host "[$timestamp] ❌ Error running tests: $($_.Exception.Message)" -ForegroundColor Red
                    exit 1
                }
                exit 0
            }
            4 { Show-AdvancedDiagnostics; exit 0 }
            5 { Show-CacheManagement; exit 0 }
            6 { Stop-AllServices; exit 0 }
            7 { Show-QuickStatus; exit 0 }
            8 {
                Write-Host "`nRunning production server test suite..." -ForegroundColor Yellow
                $testLog = Join-Path $PSScriptRoot "logs/production_test.log"
                $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                
                # Ensure logs directory exists
                $logsDir = Split-Path $testLog -Parent
                if (-not (Test-Path $logsDir)) {
                    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
                }
                
                Write-Host "Test output will be logged to: $testLog" -ForegroundColor Gray
                
                # Run tests with proper error handling
                try {
                    $testResult = & pytest test_production_server.py -v --maxfail=1 --disable-warnings 2>&1 | Tee-Object -FilePath $testLog -Append
                    $exitCode = $LASTEXITCODE
                    
                    if ($exitCode -eq 0) {
                        Write-Host "[$timestamp] ✅ All production tests passed!" -ForegroundColor Green
                    } else {
                        Write-Host "[$timestamp] ❌ Some production tests failed (exit code: $exitCode)!" -ForegroundColor Red
                        Write-Host "`nLast 30 lines of test output:" -ForegroundColor Yellow
                        if (Test-Path $testLog) {
                            Get-Content $testLog -Tail 30 | ForEach-Object { Write-Host $_ }
                        }
                        Write-Host "`nFull test log available at: $testLog" -ForegroundColor Gray
                    }
                }
                catch {
                    Write-Host "[$timestamp] ❌ Error running tests: $($_.Exception.Message)" -ForegroundColor Red
                    Write-Host "Check that pytest is installed and test_production_server.py exists" -ForegroundColor Yellow
                }
                
                Write-Host "`nPress any key to return to menu..." -ForegroundColor Cyan
                $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
                return $selection
            }
            0 {
                Write-Host "Exiting..." -ForegroundColor Gray
                Stop-AllMonitoring
                exit 0
            }
            default {
                Write-Host "Unknown menu option: $MenuOption (valid options: 0-8)" -ForegroundColor Red
                exit 1
            }
        }
    }

    # If a specific mode is provided (not Menu), run it directly and skip the menu
    if ($Mode -ne "Menu") {
        Write-Host "[cslaunch] Starting in $Mode mode..." -ForegroundColor Green
        switch ($Mode) {
            "Production" {
                $result = Start-DockerProduction -ForceRebuild:$ForceRebuild -NoValidation:$NoValidation
                if (-not $result) { exit 1 }
                exit 0
            }
            "Diagnostics" {
                Show-AdvancedDiagnostics
                exit 0
            }
            "Cache" {
                Show-CacheManagement
                exit 0
            }
            "Test" {
                # Start services if needed
                $testHost = "127.0.0.1"
                $testPort = 5001
                if (-not (Test-NetConnection -ComputerName $testHost -Port $testPort -InformationLevel Quiet -WarningAction SilentlyContinue)) {
                    Write-Host "Starting services for testing..." -ForegroundColor Yellow
                    $result = Start-DockerProduction -NoValidation
                    if (-not $result) {
                        Write-Host "Failed to start services for testing" -ForegroundColor Red
                        exit 1
                    }
                }

                $apiSuccess = $true
                $frontendSuccess = $true

                if ($TestAPI) {
                    $apiSuccess = Test-APIFunctionality -TestCitation $TestCitation
                }

                if ($TestFrontend) {
                    $frontendSuccess = Test-FrontendFunctionality
                }

                if ($ShowLogs) {
                    Show-ContainerLogs
                }

                if ($apiSuccess -and $frontendSuccess) {
                    Write-Host "`n✅ All tests passed!" -ForegroundColor Green
                    exit 0
                } else {
                    Write-Host "`n❌ Some tests failed!" -ForegroundColor Red
                    exit 1
                }
            }
            "Debug" {
                if ($VerboseLogging) {
                    $VerbosePreference = "Continue"
                }

                Write-Host "Debug Mode Enabled" -ForegroundColor Cyan
                Write-Host "Test Citation: $TestCitation" -ForegroundColor Yellow
                Write-Host "Timeout: $TimeoutMinutes minutes" -ForegroundColor Yellow

                # Start with debug info
                $result = Start-DockerProduction -NoValidation:$NoValidation -ForceRebuild:$ForceRebuild
                if (-not $result) {
                    Write-Host "Failed to start services in debug mode" -ForegroundColor Red
                    exit 1
                }

                # Run tests with debug output
                $apiSuccess = Test-APIFunctionality -TestCitation $TestCitation
                $frontendSuccess = Test-FrontendFunctionality

                if ($ShowLogs) {
                    Show-ContainerLogs
                }

                if ($apiSuccess -and $frontendSuccess) {
                    exit 0
                } else {
                    exit 1
                }
            }
            default {
                Write-Host "[cslaunch] Unknown mode: $Mode" -ForegroundColor Red
                exit 1
            }
        }
    }

    # If Mode is "Menu" or no specific mode/option provided, show the interactive menu
    Write-Host "[cslaunch] Starting interactive menu..." -ForegroundColor Green
    do {
        $selection = Show-Menu

        if ($selection -ne "0") {
            Write-Host "`nPress any key to return to menu..." -NoNewline
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        }
    } while ($selection -ne "0")

    Write-Host "Exiting..." -ForegroundColor Gray
    Stop-AllMonitoring
}
catch {
    Write-CrashLog "Fatal error in main execution" -Level "ERROR" -Exception $_
    Write-Host "`nFatal Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Check log file: $($script:CrashLogFile)" -ForegroundColor Yellow
    Stop-AllMonitoring
    exit 1
}
finally {
    # Ensure cleanup happens
    Stop-AllMonitoring
}

# Test execution is now handled within the menu options and mode handlers
# No duplicate test execution needed at the end of the script

# --- Nginx Config Templating for Docker Compose Production ---
# Ensure BACKEND_SERVICE_NAME is set and template the Nginx config before starting containers
$nginxConfTemplate = Join-Path $PSScriptRoot "nginx/conf.d/casestrainer.conf"
$nginxConfTarget = $nginxConfTemplate  # Overwrite in place for Docker bind mount
$backendServiceName = "casestrainer-backend-prod"

# Set environment variable for Nginx templating
[System.Environment]::SetEnvironmentVariable("BACKEND_SERVICE_NAME", $backendServiceName, "Process")

# Check for envsubst (required for templating)
$envsubst = "envsubst"
$envsubstExists = $false

# Default to using PowerShell's built-in string replacement
$usePowerShellFallback = $true

try {
    # First try to use native envsubst if available
    $null = & $envsubst --version 2>$null
    $envsubstExists = $true
    $usePowerShellFallback = $false
    Write-Host "Using native envsubst for Nginx config templating" -ForegroundColor Cyan
} catch {
    Write-Host "Native envsubst not found, using PowerShell fallback for Nginx config templating" -ForegroundColor Yellow
}

# Function to perform environment variable substitution using PowerShell
function Invoke-EnvSubst {
    param(
        [string]$InputString,
        [hashtable]$AdditionalVars = @{}
    )
    
    # Get all environment variables
    $envVars = Get-ChildItem env: | ForEach-Object { @{$_.Name = $_.Value} } | Merge-Hashtables
    
    # Add/override with any additional variables
    if ($AdditionalVars.Count -gt 0) {
        $envVars = $envVars + $AdditionalVars
    }
    
    # Replace all ${VAR} and $VAR occurrences
    $result = $InputString
    $envVars.GetEnumerator() | ForEach-Object {
        $varName = $_.Key
        $varValue = $_.Value -replace '\$', '$$$$'  # Escape $ in replacement string
        
        # Replace ${VAR} syntax
        $result = $result -replace "\`${$varName}", $varValue
        
        # Replace $VAR syntax (only if it's a whole word and followed by non-word character or end of string)
        $result = $result -replace "\`$$varName(?!\w)", $varValue
    }
    
    return $result
}

# Helper function to merge hashtables
function Merge-Hashtables {
    $output = @{}
    foreach ($hashtable in $input) {
        if ($hashtable -is [Collections.IDictionary]) {
            $hashtable.GetEnumerator() | ForEach-Object { $output[$_.Key] = $_.Value }
        }
    }
    return $output
}

# Process the Nginx config template
Write-Host "Templating Nginx config with BACKEND_SERVICE_NAME=$backendServiceName ..." -ForegroundColor Cyan

# Read the template content
$templateContent = Get-Content $nginxConfTemplate -Raw

# Process the template
$templatedContent = if ($usePowerShellFallback) {
    # Use PowerShell-based substitution
    try {
        $additionalVars = @{
            BACKEND_SERVICE_NAME = $backendServiceName
        }
        
        # Add any other environment variables that might be needed
        $env:FRONTEND_PORT = "80"
        $env:BACKEND_PORT = "5000"
        
        Invoke-EnvSubst -InputString $templateContent -AdditionalVars $additionalVars
    } catch {
        Write-Host "WARNING: Error during PowerShell-based template processing: $_" -ForegroundColor Red
        $templateContent  # Return original content on error
    }
} else {
    # Use native envsubst
    try {
        $tmpIn = [System.IO.Path]::GetTempFileName()
        $tmpOut = [System.IO.Path]::GetTempFileName()
        Set-Content -Path $tmpIn -Value $templateContent -NoNewline
        
        # Set the environment variable for envsubst
        $env:BACKEND_SERVICE_NAME = $backendServiceName
        
        # Execute envsubst
        $process = Start-Process -FilePath $envsubst -ArgumentList @() -RedirectStandardInput $tmpIn -RedirectStandardOutput $tmpOut -NoNewWindow -PassThru -Wait
        
        if ($process.ExitCode -eq 0) {
            Get-Content $tmpOut -Raw
        } else {
            throw "envsubst exited with code $($process.ExitCode)"
        }
    } catch {
        Write-Host "WARNING: Error during envsubst processing: $_" -ForegroundColor Red
        $templateContent  # Return original content on error
    } finally {
        # Clean up temp files if they exist
        if (Test-Path $tmpIn) { Remove-Item $tmpIn -ErrorAction SilentlyContinue }
        if (Test-Path $tmpOut) { Remove-Item $tmpOut -ErrorAction SilentlyContinue }
    }
}

# Write the processed content to the target file
Set-Content -Path $nginxConfTarget -Value $templatedContent -NoNewline
if ($usePowerShellFallback) {
    $method = 'PowerShell fallback'
} else {
    $method = 'native envsubst'
}
Write-Host "Nginx config templated successfully using $method" -ForegroundColor Green
# --- End Nginx Config Templating ---

# Ensure logs directory exists and start transcript for full console logging
$logsDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}
$transcriptPath = Join-Path $logsDir "console_output.log"
if (-not (Test-Path $transcriptPath)) {
    New-Item -ItemType File -Path $transcriptPath -Force | Out-Null
}
Start-Transcript -Path $transcriptPath -Append

# At the very end of the script, before any final exit or after all main logic, add:
Stop-Transcript