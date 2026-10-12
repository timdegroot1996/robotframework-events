*** Settings ***
Library             FlaUILibrary    screenshot_on_failure=False
Library             Process
Suite Teardown      Terminate All Processes    kill=True


*** Test Cases ***
Notepad
    ${pid}    Launch Application    notepad.exe
    Sleep    1s
    Set Text To Textbox    //Window[contains(@Name,'Notepad')]//Document | //Window[contains(@Name,'Notepad')]//Edit    Hello from FlaUI
    Click    //Window[contains(@Name,'Notepad')]//MenuItem[@Name='Edit']
    Press Key    s'ESCAPE'
    Close Application    ${pid}
