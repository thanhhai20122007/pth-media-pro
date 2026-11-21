Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)

' 1. Chạy tiến trình pythonw ngầm ẩn 100% không hiện cửa sổ đen CMD
WshShell.Run "pythonw.exe """ & strDir & "\main.py"" --mode headless", 0, False

' 2. Chờ 1.5 giây để Web Server khởi động
WScript.Sleep 1500

' 3. Tự động mở trình duyệt trên máy tính
WshShell.Run "http://127.0.0.1:5000", 1, False
