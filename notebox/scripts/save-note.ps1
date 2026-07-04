param(
  [Parameter(ValueFromPipeline = $true, Position = 0)]
  [string]$Content,

  [string]$Title,
  [string]$Source = "pc",
  [string[]]$Tags = @()
)

begin {
  $chunks = New-Object System.Collections.Generic.List[string]
}

process {
  if ($null -ne $Content) {
    $chunks.Add($Content)
  }
}

end {
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
}
