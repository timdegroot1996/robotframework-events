*** Settings ***
Library             QWeb
Suite Setup         OpenBrowser    ${PAGES}/shop.html    chrome    --headless=new, --no-sandbox, --disable-dev-shm-usage
Suite Teardown      CloseAllBrowsers


*** Test Cases ***
Shop Flow
    GoTo    ${PAGES}/shop.html
    ClickElement    //button[@id\="add-backpack"]
    ClickElement    //button[@id\="add-light"]
    VerifyElementText    //span[@id\="cart"]    2
    TypeText    Your name    Robot
    ClickText    Checkout
    VerifyText    Thank you for your order!

Confirm Dialog
    GoTo    ${PAGES}/shop.html
    ClickElement    //button[@id\="ask"]
    CloseAlert    ACCEPT
    VerifyElementText    //span[@id\="answer"]    yes
