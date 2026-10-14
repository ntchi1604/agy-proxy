# =============================================================================
# Antigravity IDE & Desktop App Language Server Patcher for Windows (PowerShell)
# Intercepts IDE requests and routes them through agy-proxy via wrapper executable
# Auto-Fallback (Direct Bypass): connects directly to Google if proxy is offline
# Live Auto-Switching: dynamic watchdog auto-detects proxy connect/disconnect
# =============================================================================

[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet("patch", "restore", "unpatch", "status", "restart", "kill")]
    [string]$Command = "status",

    [Alias("e", "EditorPath")]
    [string]$Editor,

    [Alias("f", "File", "FilePath")]
    [string]$Path,

    [int]$Port = 8000,
    [string]$HostName = "127.0.0.1",
    [string]$Url,
    [int]$Timeout = 2,
    [switch]$NoWatchdog,
    [Alias("y")]
    [switch]$Yes
)

$ErrorActionPreference = "Stop"

# Colors & Formatting
function Write-Color([string]$text, [ConsoleColor]$color = [ConsoleColor]::White) {
    Write-Host $text -ForegroundColor $color
}

# Proxy URL Resolution
if ($Url) {
    $ProxyUrl = $Url.TrimEnd("/")
} else {
    $ProxyUrl = "http://${HostName}:${Port}"
}

$DefaultApiUrl = "https://generativelanguage.googleapis.com"
$DefaultCcEndpoint = "https://daily-cloudcode-pa.googleapis.com"

# Candidate Directories & Binary Names on Windows
$KnownBinNames = @(
    "language_server.exe",
    "language_server_windows_x64.exe",
    "language_server_windows_arm.exe",
    "language_server"
)

$KnownSubpaths = @(
    "resources\bin",
    "resources\app\extensions\antigravity\bin",
    "Antigravity IDE\resources\app\extensions\antigravity\bin",
    "bin",
    "."
)

$CandidateDirs = @(
    "$env:LOCALAPPDATA\Programs\Antigravity\resources\bin",
    "$env:LOCALAPPDATA\Programs\Antigravity",
    "$env:LOCALAPPDATA\Antigravity\resources\bin",
    "$env:LOCALAPPDATA\Antigravity",
    "$env:APPDATA\Antigravity\resources\bin",
    "$env:APPDATA\Antigravity",
    "$env:ProgramFiles\Antigravity\resources\bin",
    "$env:ProgramFiles\Antigravity",
    "${env:ProgramFiles(x86)}\Antigravity\resources\bin",
    "${env:ProgramFiles(x86)}\Antigravity",
    "$env:LOCALAPPDATA\Programs\Antigravity IDE\resources\app\extensions\antigravity\bin",
    "$env:LOCALAPPDATA\Programs\Antigravity IDE",
    "$env:LOCALAPPDATA\Antigravity IDE\resources\app\extensions\antigravity\bin",
    "$env:LOCALAPPDATA\Antigravity IDE",
    "$env:ProgramFiles\Antigravity IDE\resources\app\extensions\antigravity\bin",
    "$env:ProgramFiles\Antigravity IDE",
    "${env:ProgramFiles(x86)}\Antigravity IDE\resources\app\extensions\antigravity\bin",
    "${env:ProgramFiles(x86)}\Antigravity IDE",
    "$env:USERPROFILE\Downloads\Antigravity IDE\resources\app\extensions\antigravity\bin",
    "$env:USERPROFILE\Downloads\Antigravity app"
)

$ConfigFile = "$env:USERPROFILE\.config\agy-proxy\config.json"

function Search-DirForBinary([string]$dir) {
    if (-not (Test-Path -Path $dir -PathType Container)) {
        return $null
    }

    # 1. Direct and known subpaths
    foreach ($sub in $KnownSubpaths) {
        $checkDir = Join-Path $dir $sub
        if (Test-Path -Path $checkDir -PathType Container) {
            foreach ($bn in $KnownBinNames) {
                $targetFile = Join-Path $checkDir $bn
                if (Test-Path -Path $targetFile -PathType Leaf) {
                    return $targetFile
                }
                $realFile = Join-Path $checkDir "$bn.real"
                if (Test-Path -Path $realFile -PathType Leaf) {
                    return $targetFile
                }
            }
        }
    }

    # 2. Recursive search
    try {
        $found = Get-ChildItem -Path $dir -Filter "language_server*.exe" -Recurse -File -Depth 5 -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            $baseName = $found.FullName -replace "\.real$", ""
            return $baseName
        }
    } catch {}

    return $null
}

function Resolve-TargetBinary {
    # 1. Explicit path
    if ($Path) {
        $p = [System.IO.Path]::GetFullPath($Path)
        if (Test-Path -Path $p -PathType Leaf) {
            return ($p -replace "\.real$", "")
        } elseif (Test-Path -Path $p -PathType Container) {
            $f = Search-DirForBinary $p
            if ($f) { return $f }
        }
    }

    # 2. Explicit editor directory
    if ($Editor) {
        $ed = [System.IO.Path]::GetFullPath($Editor)
        $f = Search-DirForBinary $ed
        if ($f) { return $f }
    }

    # 3. Environment variables
    foreach ($v in @("ANTIGRAVITY_LS_PATH", "ANTIGRAVITY_EDITOR_PATH", "ANTIGRAVITY_FILE")) {
        $val = [Environment]::GetEnvironmentVariable($v)
        if ($val) {
            if (Test-Path -Path $val -PathType Leaf) {
                return ($val -replace "\.real$", "")
            } elseif (Test-Path -Path $val -PathType Container) {
                $f = Search-DirForBinary $val
                if ($f) { return $f }
            }
        }
    }

    # 4. Config file (~/.config/agy-proxy/config.json)
    if (Test-Path -Path $ConfigFile) {
        try {
            $cfg = Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json
            if ($cfg.language_server_path -and (Test-Path -Path $cfg.language_server_path)) {
                return ($cfg.language_server_path -replace "\.real$", "")
            }
            if ($cfg.editor_path -and (Test-Path -Path $cfg.editor_path -PathType Container)) {
                $f = Search-DirForBinary $cfg.editor_path
                if ($f) { return $f }
            }
        } catch {}
    }

    # 5. Candidate directories
    foreach ($cd in $CandidateDirs) {
        if (Test-Path -Path $cd) {
            $f = Search-DirForBinary $cd
            if ($f) { return $f }
        }
    }

    # 6. Interactive fallback
    if ([Environment]::UserInteractive) {
        Write-Color "`n[?] Could not auto-detect Antigravity language_server path on Windows." Yellow
        $prompt = Read-Host "Enter path to Antigravity directory or language_server.exe"
        if ($prompt) {
            $cleanPrompt = $prompt.Trim('"', "'")
            if (Test-Path -Path $cleanPrompt -PathType Leaf) {
                return ($cleanPrompt -replace "\.real$", "")
            } elseif (Test-Path -Path $cleanPrompt -PathType Container) {
                $f = Search-DirForBinary $cleanPrompt
                if ($f) { return $f }
            }
        }
    }

    return $null
}

function Save-BinaryToConfig([string]$binPath) {
    try {
        $configDir = [System.IO.Path]::GetDirectoryName($ConfigFile)
        if (-not (Test-Path -Path $configDir)) {
            New-Item -ItemType Directory -Path $configDir -Force | Out-Null
        }
        $cfgObj = @{}
        if (Test-Path -Path $ConfigFile) {
            $cfgObj = (Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json)
        }
        $cfgObj | Add-Member -Name "language_server_path" -Value $binPath -MemberType NoteProperty -Force
        $cfgObj | ConvertTo-Json -Depth 5 | Set-Content -Path $ConfigFile -Encoding UTF8
    } catch {}
}

function Test-ProxyAlive {
    try {
        $req = [System.Net.WebRequest]::Create("${ProxyUrl}/health")
        $req.Timeout = 1000
        $req.Method = "GET"
        $resp = $req.GetResponse()
        $resp.Close()
        return $true
    } catch {
        try {
            $req = [System.Net.WebRequest]::Create("${ProxyUrl}/api/info")
            $req.Timeout = 1000
            $req.Method = "GET"
            $resp = $req.GetResponse()
            $resp.Close()
            return $true
        } catch {
            return $false
        }
    }
}

# --- Main Resolution ---
$TargetLs = Resolve-TargetBinary

if (-not $TargetLs) {
    Write-Color "[-] Error: Could not locate Antigravity language_server binary on Windows." Red
    Write-Color "Please specify path with -Editor 'C:\Path\To\Antigravity' or -Path 'C:\Path\To\language_server.exe'" Gray
    Write-Color "Or configure permanently with: agy-proxy config set ls-path <PATH>" Gray
    exit 1
}

$BinDir = [System.IO.Path]::GetDirectoryName($TargetLs)
$BinName = [System.IO.Path]::GetFileName($TargetLs)
$RealLs = Join-Path $BinDir "$BinName.real"
$WrapperMarker = Join-Path $BinDir "$BinName.is_proxy_wrapper"

Save-BinaryToConfig $TargetLs

# --- Status Command ---
if ($Command -eq "status") {
    Write-Color "`n============================================================" Cyan
    Write-Color "  Antigravity Language Server Windows Status" Cyan
    Write-Color "============================================================" Cyan
    Write-Host "Target Binary:     $TargetLs"
    Write-Host "Backup (.real):    $(if (Test-Path $RealLs) { '[Present]' } else { '[None]' })"

    $isPatched = (Test-Path $RealLs) -or (Test-Path $WrapperMarker)
    if ($isPatched) {
        Write-Color "Patch Status:      [PATCHED -> Proxy Active]" Green
    } else {
        Write-Color "Patch Status:      [UNPATCHED -> Original Binary]" Yellow
    }

    $proxyAlive = Test-ProxyAlive
    if ($proxyAlive) {
        Write-Color "agy-proxy Server:  [ONLINE at $ProxyUrl]" Green
    } else {
        Write-Color "agy-proxy Server:  [OFFLINE / NOT RUNNING at $ProxyUrl]" Red
    }

    $procs = Get-Process -Name "*language_server*" -ErrorAction SilentlyContinue
    if ($procs) {
        Write-Color "Running Instances: $($procs.Count) process(es) (PIDs: $(($procs | ForEach-Object { $_.Id }) -join ', '))" Cyan
    } else {
        Write-Host "Running Instances: None"
    }
    Write-Color "============================================================`n" Cyan
    exit 0
}

# --- Kill / Restart Command ---
if ($Command -in @("kill", "restart")) {
    $procs = Get-Process -Name "*language_server*" -ErrorAction SilentlyContinue
    if ($procs) {
        Write-Color "Stopping active language_server processes..." Yellow
        $procs | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        Write-Color "[+] Stopped running processes." Green
    } else {
        Write-Color "[i] No running language_server processes found." Gray
    }
    if ($Command -eq "kill") { exit 0 }
    Write-Color "[i] Waiting for Antigravity to respawn process..." Gray
    exit 0
}

# --- Restore / Unpatch Command ---
if ($Command -in @("restore", "unpatch")) {
    if (-not (Test-Path $RealLs)) {
        Write-Color "[i] Original binary backup not found at: $RealLs. It appears already restored or unpatched." Yellow
        if (Test-Path $WrapperMarker) { Remove-Item -Force $WrapperMarker }
        exit 0
    }

    Write-Color "Restoring original language_server binary..." Cyan
    Get-Process -Name "*language_server*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500

    Move-Item -Path $RealLs -Destination $TargetLs -Force
    if (Test-Path $WrapperMarker) { Remove-Item -Force $WrapperMarker }

    Write-Color "[+] Successfully restored original language_server binary!" Green
    Write-Color "    Restored file: $TargetLs`n" Gray
    exit 0
}

# --- Patch Command ---
if ($Command -eq "patch") {
    if (Test-Path $RealLs) {
        Write-Color "[i] Already patched! Original binary is safely backed up at: $RealLs" Yellow
        Write-Color "    To re-apply, run with 'restore' first, or restart the server." Gray
        exit 0
    }

    Write-Color "`n[+] Preparing to patch language_server for Windows..." Cyan
    Write-Color "    Target:    $TargetLs" Gray
    Write-Color "    Backup:    $RealLs" Gray
    Write-Color "    Proxy URL: $ProxyUrl" Gray

    # Backup original binary
    Get-Process -Name "*language_server*" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500

    Move-Item -Path $TargetLs -Destination $RealLs -Force
    Write-Color "    Original binary safely moved to: $RealLs" Green

    # C# Wrapper source code for native high-performance execution on Windows
    $CSharpSource = @"
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Threading;

public class Program {
    public static int Main(string[] rawArgs) {
        string scriptDir = AppDomain.CurrentDomain.BaseDirectory;
        string realBinName = "$BinName.real";
        string realLs = Path.Combine(scriptDir, realBinName);

        if (!File.Exists(realLs)) {
            Console.Error.WriteLine("[wrapper] ERROR: Real binary not found at: " + realLs);
            return 1;
        }

        string proxyUrl = Environment.GetEnvironmentVariable("AGY_PROXY_URL") ?? "$ProxyUrl";
        string defaultApiUrl = "$DefaultApiUrl";
        string defaultCcEndpoint = "$DefaultCcEndpoint";

        bool proxyOnline = false;
        try {
            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(proxyUrl + "/health");
            req.Timeout = 1000;
            req.Method = "GET";
            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse()) {
                proxyOnline = ((int)resp.StatusCode >= 200 && (int)resp.StatusCode < 300);
            }
        } catch {
            proxyOnline = false;
        }

        string effectiveApi = proxyOnline ? proxyUrl : defaultApiUrl;
        string effectiveCc = proxyOnline ? proxyUrl : defaultCcEndpoint;

        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = realLs;
        psi.UseShellExecute = false;

        bool hasApi = false;
        bool hasCc = false;

        foreach (string arg in rawArgs) {
            if (arg.StartsWith("--api_server_url=")) {
                psi.ArgumentList.Add("--api_server_url=" + effectiveApi);
                hasApi = true;
            } else if (arg == "--api_server_url") {
                psi.ArgumentList.Add(arg);
                psi.ArgumentList.Add(effectiveApi);
                hasApi = true;
            } else if (arg.StartsWith("--cloud_code_endpoint=")) {
                psi.ArgumentList.Add("--cloud_code_endpoint=" + effectiveCc);
                hasCc = true;
            } else if (arg == "--cloud_code_endpoint") {
                psi.ArgumentList.Add(arg);
                psi.ArgumentList.Add(effectiveCc);
                hasCc = true;
            } else {
                psi.ArgumentList.Add(arg);
            }
        }

        if (!hasApi) {
            psi.ArgumentList.Add("--api_server_url=" + effectiveApi);
        }
        if (!hasCc) {
            psi.ArgumentList.Add("--cloud_code_endpoint=" + effectiveCc);
        }

        try {
            using (Process proc = Process.Start(psi)) {
                if (proc == null) return 1;

                // Watchdog thread
                Thread watchdog = new Thread(() => {
                    bool initialProxy = proxyOnline;
                    int consecutive = 0;
                    Thread.Sleep(4000);
                    while (!proc.HasExited) {
                        bool currentOnline = false;
                        try {
                            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(proxyUrl + "/health");
                            req.Timeout = 1000;
                            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse()) {
                                currentOnline = ((int)resp.StatusCode >= 200 && (int)resp.StatusCode < 300);
                            }
                        } catch {
                            currentOnline = false;
                        }

                        if (currentOnline != initialProxy) {
                            consecutive++;
                            if (consecutive >= 2) {
                                try { proc.Kill(); } catch {}
                                return;
                            }
                        } else {
                            consecutive = 0;
                        }
                        Thread.Sleep(2000);
                    }
                });
                watchdog.IsBackground = true;
                watchdog.Start();

                proc.WaitForExit();
                return proc.ExitCode;
            }
        } catch (Exception ex) {
            Console.Error.WriteLine("[wrapper] Failed to spawn real binary: " + ex.Message);
            return 1;
        }
    }
}
"@

    try {
        Write-Color "    Compiling native Windows wrapper..." Gray
        Add-Type -TypeDefinition $CSharpSource -OutputAssembly $TargetLs -OutputType WindowsCommandLineApplication
        Set-Content -Path $WrapperMarker -Value "agy-proxy-wrapper" -Force
        Write-Color "`n[+] Successfully patched language_server!" Green
        Write-Color "    Wrapper installed: $TargetLs" Cyan
        Write-Color "    Traffic will automatically route through agy-proxy at $ProxyUrl" Green
        Write-Color "    Auto-fallback to Google backend is active if proxy is offline.`n" Gray
    } catch {
        Write-Color "[-] Compilation failed: $_" Red
        Write-Color "    Restoring backup..." Yellow
        Move-Item -Path $RealLs -Destination $TargetLs -Force
        exit 1
    }
}
