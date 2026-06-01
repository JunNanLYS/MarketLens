# NeoData Token 监控脚本 v2
# 检查 ~/.workbuddy/.neodata_token 有效期
# - 如果是 JWT（三段 Base64），检查 exp 声明
# - 如果不是 JWT（tempToken），用 saved_at + 12 小时估算
# 临近过期时弹出 Windows Toast 通知

$TOKEN_FILE = "$env:USERPROFILE\.workbuddy\.neodata_token"
$TOKEN_TTL_HOURS = 12  # tempToken 的回退 TTL
$WARN_BEFORE_DAYS = 7  # JWT 过期前多少天开始提醒

function Show-Toast {
    param([string]$Title, [string]$Message)
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $balloon = New-Object System.Windows.Forms.NotifyIcon
        $balloon.Icon = [System.Drawing.SystemIcons]::Information
        $balloon.BalloonTipTitle = $Title
        $balloon.BalloonTipText = $Message
        $balloon.Visible = $true
        $balloon.ShowBalloonTip(10000)
        Start-Sleep -Seconds 12
        $balloon.Dispose()
    } catch {
        Write-Host "[Toast failed: $_]"
    }
}

function Decode-JwtPayload {
    param([string]$Token)
    try {
        $parts = $Token -split '\.'
        if ($parts.Count -ne 3) { return $null }

        $payload = $parts[1]
        # 补全 Base64 padding
        $pad = 4 - ($payload.Length % 4)
        if ($pad -ne 4) { $payload += '=' * $pad }

        $bytes = [Convert]::FromBase64String($payload.Replace('-', '+').Replace('_', '/'))
        $json = [System.Text.Encoding]::UTF8.GetString($bytes)
        return $json | ConvertFrom-Json
    } catch {
        return $null
    }
}

# 检查 token 文件
if (-not (Test-Path $TOKEN_FILE)) {
    Show-Toast -Title "⚠️ NeoData 凭证缺失" -Message "未找到凭证缓存文件。请打开 WorkBuddy 获取 NeoData 凭证。"
    exit 1
}

try {
    $raw = Get-Content $TOKEN_FILE -Raw -Encoding UTF8 | ConvertFrom-Json
    $token = $raw.token
    $savedAt = [DateTimeOffset]::FromUnixTimeSeconds($raw.saved_at).DateTime
} catch {
    Show-Toast -Title "⚠️ NeoData 凭证异常" -Message "凭证缓存文件格式异常。请打开 WorkBuddy 重新获取凭证。"
    exit 1
}

# 检查是否为 JWT
$jwtPayload = Decode-JwtPayload -Token $token

if ($jwtPayload -and $jwtPayload.exp) {
    # JWT 模式：检查 exp 声明
    $expTime = [DateTimeOffset]::FromUnixTimeSeconds($jwtPayload.exp).DateTime
    $remaining = $expTime - [DateTime]::Now

    if ($remaining.TotalDays -le 0) {
        Show-Toast -Title "🔴 NeoData 凭证已过期 (JWT)" -Message "JWT 已过期。请通过 WorkBuddy 重新获取凭证。"
    } elseif ($remaining.TotalDays -le $WARN_BEFORE_DAYS) {
        Show-Toast -Title "🟡 NeoData 凭证即将过期 (JWT)" -Message "JWT 将在 $($expTime.ToString('yyyy-MM-dd')) 过期（剩余 $([math]::Round($remaining.TotalDays)) 天）。请尽早刷新。"
    }
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] JWT mode: exp=$($expTime.ToString('yyyy-MM-dd')), remaining=$([math]::Round($remaining.TotalDays))d"
} else {
    # tempToken 模式：用 saved_at + 12 小时估算
    $age = [DateTime]::Now - $savedAt
    $remaining = [TimeSpan]::FromHours($TOKEN_TTL_HOURS) - $age

    if ($remaining.TotalHours -le 0) {
        Show-Toast -Title "🔴 NeoData 临时凭证已过期" -Message "tempToken 已过期。请通过 WorkBuddy 重新获取凭证。"
    } elseif ($remaining.TotalHours -le 2) {
        Show-Toast -Title "🟡 NeoData 临时凭证即将过期" -Message "tempToken 有效期还剩约 $([math]::Round($remaining.TotalMinutes)) 分钟。"
    }
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] tempToken mode: age=$([math]::Round($age.TotalHours,1))h, remaining=$([math]::Round($remaining.TotalHours,1))h"
}
