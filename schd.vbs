' --- �������� ---
' ����Ƿ������ṩ��һ�������в���
If WScript.Arguments.Count < 1 Then
    WScript.Echo "����: ȱ�ٱ���Ĳ��� 'Parts'��"
    WScript.Echo "�÷�: cscript.exe schd.vbs <Parts>"
    WScript.Quit(1) ' �Դ������ 1 �˳�
End If

' ��ȡ��һ������
Dim partsArg
partsArg = WScript.Arguments(0)

' --- �������� ---
' ���� WScript.Shell �� FileSystemObject ��������ִ�г���ʹ���·��
Dim WshShell, fso, scriptPath, scriptDir
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' ��ȡ�ű����ڵ�Ŀ¼����������Ϊ��ǰ����Ŀ¼
' WScript.ScriptFullName �ṩ�˽ű�������·��
scriptPath = WScript.ScriptFullName
scriptDir = fso.GetParentFolderName(scriptPath)
WshShell.CurrentDirectory = scriptDir

' ִ���� Python �ű�
' WshShell.Run ��������ִ���ⲿ����
' �ڶ������� 0 ��ʾ���ش��ڣ����������� True ��ʾ�ȴ�����ִ�����
Dim exitCode
exitCode = WshShell.Run("python.exe blbl_up_watch.py", 0, True)

' �����һ��������˳����� (0 ͨ����ʾ�ɹ�)
If exitCode <> 0 Then
    WScript.Echo "����: ִ�� blbl_up_watch.py ʧ�ܡ��˳�����: " & exitCode
    WScript.Quit(exitCode) ' ʹ�� Python �ű����˳������˳�
End If

' ����ǰĿ¼����Ϊ data ��Ŀ¼
WshShell.CurrentDirectory = fso.BuildPath(scriptDir, "data")

' ִ��Ԥ����ű��������ݲ��� (Ϊ�˰�ȫ������ܰ����ո�Ĳ��������Ǹ�������������)
Dim command
command = "python.exe preprocess.py -n " & partsArg
exitCode = WshShell.Run(command, 0, True)

' �ٴμ���˳�����
If exitCode <> 0 Then
    WScript.Echo "����: ִ�� preprocess.py ʧ�ܡ��˳�����: " & exitCode
    WScript.Quit(exitCode)
End If

WScript.Echo "�ű�ִ����ϡ�"

' --- ���� ---
Set fso = Nothing
Set WshShell = Nothing
WScript.Quit(0) ' �Գɹ����� 0 �˳�