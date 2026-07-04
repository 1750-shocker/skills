param(
  [Parameter(Position = 0)]
  [string]$Content,
  [string]$ContentFile,
  [string]$Title,
  [string]$Source = "pc",
  [string[]]$Tags = @()
)

[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$chunks = New-Object System.Collections.Generic.List[string]

if ($null -ne $Content) {
  $chunks.Add($Content)
}

foreach ($item in $input) {
  if ($null -ne $item) {
    $chunks.Add([string]$item)
  }
}

$url = $env:NOTEBOX_URL
$token = $env:NOTEBOX_TOKEN

if ([string]::IsNullOrWhiteSpace($url)) {
  $url = [Environment]::GetEnvironmentVariable('NOTEBOX_URL', 'User')
}
if ([string]::IsNullOrWhiteSpace($token)) {
  $token = [Environment]::GetEnvironmentVariable('NOTEBOX_TOKEN', 'User')
}

if ([string]::IsNullOrWhiteSpace($url)) {
  throw "NOTEBOX_URL is not set"
}
if ([string]::IsNullOrWhiteSpace($token)) {
  throw "NOTEBOX_TOKEN is not set"
}

if (-not [string]::IsNullOrWhiteSpace($ContentFile)) {
  if (-not (Test-Path -LiteralPath $ContentFile -PathType Leaf)) {
    throw "ContentFile does not exist: $ContentFile"
  }
  $chunks.Add([System.IO.File]::ReadAllText($ContentFile, [System.Text.Encoding]::UTF8))
}

$bodyContent = ($chunks -join [Environment]::NewLine).Trim()
if ([string]::IsNullOrWhiteSpace($bodyContent)) {
  throw "Content is empty"
}

$body = @{
  content = $bodyContent
  source = $Source
  tags = $Tags
}
if (-not [string]::IsNullOrWhiteSpace($Title)) {
  $body.title = $Title
}

$endpoint = $url.TrimEnd('/') + '/api/messages'
$headers = @{ Authorization = "Bearer $token" }
$json = $body | ConvertTo-Json -Depth 4

try {
  $response = Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers -ContentType 'application/json; charset=utf-8' -Body $json
  if ($null -ne $response.id -and $null -ne $response.created_at) {
    Write-Output ("Saved to Notebox. id: {0}; created_at: {1}" -f $response.id, $response.created_at)
  } else {
    $response
  }
} catch {
  $message = $_.Exception.Message
  throw "Failed to save note: $message"
}
