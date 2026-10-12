*** Settings ***
Library             AppiumLibrary
Suite Teardown      Close All Applications


*** Test Cases ***
Chrome On Android
    Open Application    http://127.0.0.1:4723    platformName=Android    appium:automationName=UiAutomator2
    ...    browserName=Chrome    appium:chromedriverAutodownload=${True}
    ...    goog:chromeOptions=${{ {"args": ["--disable-fre", "--no-first-run", "--no-default-browser-check"]} }}
    Go To Url    http://10.0.2.2:8765/shop.html
    Wait Until Page Contains Element    css=#add-backpack    timeout=30s
    Click Element    css=#add-backpack
    Click Element    css=#add-light
    Element Text Should Be    css=#cart    2
    Click Element    css=#checkout
    Wait Until Page Contains    Thank you for your order!    timeout=15s
