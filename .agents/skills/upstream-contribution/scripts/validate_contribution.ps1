param(
    [string]$BaseRef = "upstream/main",
    [string]$TargetRef = "HEAD",
    [string[]]$AllowPath = @(),
    [switch]$IncludeIndex,
    [switch]$AllowReleaseMetadata
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Error $Message
    $script:Failed = $true
}

function Matches-AllowPath([string]$Path) {
    foreach ($pattern in $AllowPath) {
        if ($Path -like $pattern) {
            return $true
        }
    }
    return $false
}

$script:Failed = $false

git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Run this script inside the contribution worktree."
}

$branch = (git branch --show-current).Trim()
if (-not $branch) {
    Fail "Contribution worktree is on detached HEAD. Create or attach a named branch."
}

git rev-parse --verify $BaseRef *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "Base ref does not exist: $BaseRef"
}

git rev-parse --verify $TargetRef *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "Target ref does not exist: $TargetRef"
}

if (-not $script:Failed) {
    git merge-base --is-ancestor $BaseRef $TargetRef
    if ($LASTEXITCODE -ne 0) {
        Fail "$TargetRef is not based on $BaseRef. Fetch and inspect branch topology."
    }
}

if ($IncludeIndex) {
    $changed = @(git diff --cached --name-only $BaseRef | Where-Object { $_ })
} else {
    $changed = @(git diff --name-only "$BaseRef...$TargetRef" | Where-Object { $_ })
}
$forbidden = @(
    ".agents/*",
    ".opencode/*",
    ".claude/*",
    "issues/*",
    "logs/*",
    "config.yaml"
)

if (-not $AllowReleaseMetadata) {
    $forbidden += @(
        "CHANGELOG.md",
        "assets/config/version.txt"
    )
}

foreach ($path in $changed) {
    if (Matches-AllowPath $path) {
        continue
    }
    foreach ($pattern in $forbidden) {
        if ($path -like $pattern) {
            Fail "Forbidden or downstream-local path in contribution: $path (matched $pattern)"
            break
        }
    }
}

if ($IncludeIndex) {
    $addedLines = git diff --cached --unified=0 $BaseRef -- $changed |
        Where-Object { $_ -match '^\+(?!\+\+\+)' }
} else {
    $addedLines = git diff --unified=0 "$BaseRef...$TargetRef" -- $changed |
        Where-Object { $_ -match '^\+(?!\+\+\+)' }
}
$suspicious = @(
    'debug_',
    'canary',
    '\.opencode[\\/]',
    '\.agents[\\/]',
    'issues[\\/]',
    'logs[\\/]'
)

foreach ($pattern in $suspicious) {
    $hits = @($addedLines | Select-String -Pattern $pattern -CaseSensitive:$false)
    if ($hits.Count -gt 0) {
        Write-Warning "Review added lines matching downstream-risk pattern '$pattern':"
        $hits | ForEach-Object { Write-Warning $_.Line }
    }
}

if ($changed.Count -eq 0) {
    if ($IncludeIndex) {
        Write-Warning "No staged changes found against $BaseRef."
    } else {
        Write-Warning "No committed changes found in $BaseRef...$TargetRef."
    }
}

if ($script:Failed) {
    exit 1
}

$mode = if ($IncludeIndex) { "index" } else { "committed" }
Write-Output "Contribution scope check passed: branch=$branch base=$BaseRef target=$TargetRef mode=$mode files=$($changed.Count)"
