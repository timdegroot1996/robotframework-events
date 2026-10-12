*** Settings ***
Library             RPA.Windows


*** Test Cases ***
Notepad
    Windows Run    notepad
    Control Window    subname:Notepad    timeout=10
    Send Keys    keys=Hello from RPA.Windows
    Send Keys    keys={END}
    Close Current Window
