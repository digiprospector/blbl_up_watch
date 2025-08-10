# 定义脚本的命令行参数
# 使用 param 块比使用 $args 数组更健壮，并能提供自动的参数验证和帮助
param(
    # 需要传递给 preprocess.py 脚本的名称
    # 此参数是必需的
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Name
)

# 将当前工作目录设置为脚本所在的目录
# $PSScriptRoot 是一个自动变量，包含脚本父目录的完整路径
Set-Location -Path $PSScriptRoot

Write-Host "开始执行主程序..."
# 执行主 Python 脚本。推荐使用调用运算符 (&)
& python.exe blbl_up_watch.py

# 检查上一条命令是否成功执行
if (-not $?) {
    Write-Error "执行 blbl_up_watch.py 失败。"
    # 使用 Python 脚本的退出代码退出
    exit $LASTEXITCODE
}

Write-Host "切换到 data 目录并执行预处理..."
# 路径是相对于当前位置 ($PSScriptRoot) 的
Set-Location -Path ".\data"

# 执行预处理脚本，并传递参数
& python.exe preprocess.py -n $Name
if (-not $?) {
    Write-Error "执行 preprocess.py 失败。"
    exit $LASTEXITCODE
}

Write-Host "脚本执行完毕。"