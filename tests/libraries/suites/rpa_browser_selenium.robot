*** Settings ***
Library             RPA.Browser.Selenium    run_on_failure=Nothing
Suite Setup         Open Available Browser    ${PAGES}/shop.html    headless=True    browser_selection=Chrome
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
