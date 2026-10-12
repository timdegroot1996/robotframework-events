*** Settings ***
Library    FakeBrowser.py
Library    FakeBrowser.FakeAngular
Resource    screenshots.resource


*** Test Cases ***
Steps With A Page
    Open Page
    Click    button
    Get Title
    Element Should Be Visible    button
    Click    missing

Keywords That Do Not Run
    Open Page
    IF    False
        Click    never
    END
    Click    button

Own Keyword And Borrowed Page
    Open Page
    Log In
    Wait For Angular
    Click Angular Button

Dialog Stays Open
    Open Page
    Open Dialog
    Click    button
    Handle Alert

Slow Screenshots Turn The Library Off
    Open Page
    Make Screenshots    slow
    Click    one
    Click    two
    Click    three
    Click    four

Broken API Turns The Library Off
    Open Page
    Make Screenshots    broken
    Click    one
    Click    two
