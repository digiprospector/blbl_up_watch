' --- 参数处理 ---
' 检查是否至少提供了一个命令行参数
If WScript.Arguments.Count < 1 Then
    WScript.Echo "错误: 缺少必需的参数 'Parts'。"
    WScript.Echo "用法: cscript.exe schd.vbs <Parts>"
    WScript.Quit(1) ' 以错误代码 1 退出
End If

' 获取第一个参数
Dim partsArg
partsArg = WScript.Arguments(0)

' --- 环境设置 ---
' 创建 WScript.Shell 和 FileSystemObject 对象，用于执行程序和处理路径
Dim WshShell, fso, scriptPath, scriptDir
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' 获取脚本所在的目录并将其设置为当前工作目录
' WScript.ScriptFullName 提供了脚本的完整路径
scriptPath = WScript.ScriptFullName
scriptDir = fso.GetParentFolderName(scriptPath)
WshShell.CurrentDirectory = scriptDir

' 执行主 Python 脚本
' WshShell.Run 方法用于执行外部程序
' 第二个参数 0 表示隐藏窗口，第三个参数 True 表示等待程序执行完成
Dim exitCode
exitCode = WshShell.Run("python.exe blbl_up_watch.py", 0, True)

' 检查上一条命令的退出代码 (0 通常表示成功)
If exitCode <> 0 Then
    WScript.Echo "错误: 执行 blbl_up_watch.py 失败。退出代码: " & exitCode
    WScript.Quit(exitCode) ' 使用 Python 脚本的退出代码退出
End If

' 将当前目录更改为 data 子目录
WshShell.CurrentDirectory = fso.BuildPath(scriptDir, "data")

' 执行预处理脚本，并传递参数 (为了安全处理可能包含空格的参数，我们给参数加上引号)
Dim command
command = "python.exe preprocess.py -n " & partsArg
exitCode = WshShell.Run(command, 0, True)

' 再次检查退出代码
If exitCode <> 0 Then
    WScript.Echo "错误: 执行 preprocess.py 失败。退出代码: " & exitCode
    WScript.Quit(exitCode)
End If

WScript.Echo "脚本执行完毕。"

' --- 清理 ---
Set fso = Nothing
Set WshShell = Nothing
WScript.Quit(0) ' 以成功代码 0 退出