*** Settings ***
Library             RPA.Browser.Playwright    run_on_failure=None
Suite Setup         New Browser    chromium    headless=True
Suite Teardown      Close Browser    ALL


*** Test Cases ***
Shop Flow
    New Page    ${PAGES}/shop.html
    Click    id=add-backpack
    Click    id=add-light
    Get Text    id=cart    ==    2
    Fill Text    id=name    Robot
    Click    id=checkout
    Get Text    id=title    ==    Thank you for your order!

Confirm Dialog
    New Page    ${PAGES}/shop.html
    ${promise}    Promise To    Wait For Alert    action=accept    text=Sure?
    Click    id=ask
    Wait For    ${promise}
    Get Text    id=answer    ==    yes
