*** Settings ***
Library             PuppeteerLibrary
Suite Setup         Open Browser    ${PAGES}/shop.html    browser=pwchrome    options=${{ {"headless": True} }}
Suite Teardown      Close All Browser


*** Test Cases ***
Shop Flow
    Go To    ${PAGES}/shop.html
    Click Element    id:add-backpack
    Click Element    id:add-light
    Element Text Should Be    id:cart    2
    Input Text    id:name    Robot
    Click Element    id:checkout
    Wait Until Page Contains    Thank you for your order!

Confirm Dialog
    Go To    ${PAGES}/shop.html
    Run Async Keywords    Handle Alert    ACCEPT    AND    Click Element    id:ask
    Element Text Should Be    id:answer    yes
