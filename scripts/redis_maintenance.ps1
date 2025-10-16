#Requires -Version 5.1
<#
.SYNOPSIS
    Redis Maintenance - Cleans old jobs and compacts AOF
    
.DESCRIPTION
    Prevents Redis from accumulating old job data that slows down startup.
    Run this weekly to keep Redis fast.
    
.PARAMETER Force
    Skip confirmation prompts
    
.EXAMPLE
    .\redis_maintenance.ps1
    
.EXAMPLE
    .\redis_maintenance.ps1 -Force
#>

param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Redis Maintenance" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check if Redis is running
$redisRunning = docker ps --filter "name=casestrainer-redis-prod" --format "{{.Names}}" 2>$null
if (-not $redisRunning) {
    Write-Host "[ERROR] Redis container not running" -ForegroundColor Red
    Write-Host "  Start CaseStrainer first with: ./cslaunch" -ForegroundColor Yellow
    exit 1
}

# Get current Redis stats
Write-Host "[INFO] Checking Redis status..." -ForegroundColor Yellow
try {
    $keys = docker exec casestrainer-redis-prod redis-cli -a caseStrainerRedis123 DBSIZE 2>&1 | Select-Object -Last 1
    $memory = docker exec casestrainer-redis-prod redis-cli -a caseStrainerRedis123 INFO memory 2>&1 | Select-String "used_memory_human" | ForEach-Object { $_ -replace ".*:", "" }
    
    Write-Host "`n📊 Current Redis Status:" -ForegroundColor Cyan
    Write-Host "   Keys: $keys" -ForegroundColor Gray
    Write-Host "   Memory: $memory" -ForegroundColor Gray
    
    # Check AOF size
    $aofSize = docker exec casestrainer-redis-prod du -sh /data/appendonlydir 2>&1 | ForEach-Object { ($_ -split '\s+')[0] }
    Write-Host "   AOF Size: $aofSize" -ForegroundColor Gray
} catch {
    Write-Host "  [WARNING] Could not get Redis stats: $_" -ForegroundColor Yellow
}

# Confirm if not forced
if (-not $Force) {
    Write-Host "`n⚠️  This will:" -ForegroundColor Yellow
    Write-Host "   1. Clean RQ jobs older than 7 days" -ForegroundColor Gray
    Write-Host "   2. Compact Redis AOF file" -ForegroundColor Gray
    Write-Host "   3. May take 30-60 seconds" -ForegroundColor Gray
    
    $response = Read-Host "`nContinue? (y/n)"
    if ($response -ne 'y' -and $response -ne 'Y') {
        Write-Host "`n[CANCELLED] Maintenance cancelled" -ForegroundColor Yellow
        exit 0
    }
}

# Step 1: Clean old jobs
Write-Host "`n[STEP 1/2] Cleaning old RQ jobs..." -ForegroundColor Yellow
try {
    $cleanupScript = Join-Path $PSScriptRoot 'clean_redis_old_jobs.py'
    
    if (Test-Path $cleanupScript) {
        docker cp $cleanupScript casestrainer-backend-prod:/app/ 2>$null
        $output = docker exec casestrainer-backend-prod python /app/clean_redis_old_jobs.py 2>&1
        $output | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    } else {
        Write-Host "  ⚠️  Cleanup script not found, skipping..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠️  Cleanup failed: $_" -ForegroundColor Yellow
}

# Step 2: Compact AOF
Write-Host "`n[STEP 2/2] Compacting Redis AOF..." -ForegroundColor Yellow
try {
    $result = docker exec casestrainer-redis-prod redis-cli -a caseStrainerRedis123 BGREWRITEAOF 2>&1 | Select-Object -Last 1
    
    if ($result -like "*Background*") {
        Write-Host "  ✅ AOF rewrite started" -ForegroundColor Green
        Write-Host "  ⏳ Waiting for completion..." -ForegroundColor Gray
        
        # Wait for rewrite to complete (max 60 seconds)
        $waited = 0
        $complete = $false
        
        while ($waited -lt 60 -and -not $complete) {
            Start-Sleep -Seconds 2
            $waited += 2
            
            $status = docker exec casestrainer-redis-prod redis-cli -a caseStrainerRedis123 INFO persistence 2>&1 | Select-String "aof_rewrite_in_progress"
            
            if ($status -like "*:0") {
                $complete = $true
                Write-Host "  ✅ AOF rewrite completed" -ForegroundColor Green
            } else {
                Write-Host "  ⏳ Still compacting... (${waited}s)" -ForegroundColor Gray
            }
        }
        
        if (-not $complete) {
            Write-Host "  ⚠️  Rewrite taking longer than expected (still running in background)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  ⚠️  AOF rewrite may have failed: $result" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠️  AOF compact failed: $_" -ForegroundColor Yellow
}

# Get final stats
Write-Host "`n[INFO] Final Redis status..." -ForegroundColor Yellow
try {
    $finalKeys = docker exec casestrainer-redis-prod redis-cli -a caseStrainerRedis123 DBSIZE 2>&1 | Select-Object -Last 1
    $finalMemory = docker exec casestrainer-redis-prod redis-cli -a caseStrainerRedis123 INFO memory 2>&1 | Select-String "used_memory_human" | ForEach-Object { $_ -replace ".*:", "" }
    $finalAof = docker exec casestrainer-redis-prod du -sh /data/appendonlydir 2>&1 | ForEach-Object { ($_ -split '\s+')[0] }
    
    Write-Host "`n📊 After Maintenance:" -ForegroundColor Cyan
    Write-Host "   Keys: $finalKeys" -ForegroundColor Gray
    Write-Host "   Memory: $finalMemory" -ForegroundColor Gray
    Write-Host "   AOF Size: $finalAof" -ForegroundColor Gray
} catch {
    Write-Host "  [WARNING] Could not get final stats" -ForegroundColor Yellow
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "✅ MAINTENANCE COMPLETE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`nℹ️  Run this maintenance weekly to keep Redis fast" -ForegroundColor Cyan
Write-Host "   Or add to Windows Task Scheduler for automatic maintenance`n" -ForegroundColor Gray
