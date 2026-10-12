*** Settings ***
Library             SeleniumLibrary    run_on_failure=Nothing
Suite Setup         Open Browser    ${PAGES}/shop.html    chrome    options=add_argument("--headless=new");add_argument("--no-sandbox");add_argument("--disable-dev-shm-usage")
Suite Teardown      Close All Browsers


*** Test Cases ***
Shop Flow
    Go To    ${PAGES}/shop.html
    Click Button    id:add-backpack
    Click Button    id:add-light
    Element Text Should Be    id:cart    2
    Input Text    id:name    Robot
    Click Link    id:checkout
    Element Text Should Be    id:title    Thank you for your order!

Confirm Dialog
    Go To    ${PAGES}/shop.html
    Click Button    id:ask
    Handle Alert    ACCEPT
    Element Text Should Be    id:answer    yes
