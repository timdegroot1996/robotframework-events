*** Settings ***
Library             WhiteLibrary


*** Test Cases ***
Notepad
    Launch Application    notepad.exe
    Attach Window    Untitled - Notepad
    Input Text To Textbox    id:15    Hello from White
    Press Special Key    END
    Close Application
