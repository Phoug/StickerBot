function Show-Tree {
    param (
        [string]$Path = ".",
        # Сюда можно добавлять папки, которые нужно скрыть
        [string[]]$Exclude = @("node_modules", ".github", ".git", "venv", ".venv", "__pycache__"),
        [string]$Indent = ""
    )
    
    $items = Get-ChildItem -Path $Path -Force | Where-Object { $Exclude -notcontains $_.Name }
    $count = $items.Count
    $i = 0
    
    foreach ($item in $items) {
        $i++
        $isLast = ($i -eq $count)
        
        # Классический IF, совместимый со всеми версиями PowerShell
        if ($isLast) { $branch = "+-- " } else { $branch = "|-- " }
        
        Write-Host "$Indent$branch$($item.Name)"
        
        if ($item.PSIsContainer) {
            # Собираем отступ отдельно, чтобы не ломать старый PowerShell
            if ($isLast) { $suffix = "    " } else { $suffix = "|   " }
            $nextIndent = $Indent + $suffix
            
            Show-Tree -Path $item.FullName -Exclude $Exclude -Indent $nextIndent
        }
    }
}

# Запуск для текущей папки
Show-Tree -Path "."
