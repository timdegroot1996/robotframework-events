*** Settings ***
Library             AppiumLibrary
Suite Teardown      Close All Applications


*** Test Cases ***
Settings App
    Open Application    http://127.0.0.1:4723    platformName=Android    appium:automationName=UiAutomator2
    ...    appium:appPackage=com.android.settings    appium:appActivity=com.android.settings.Settings    appium:noReset=true    appium:forceAppLaunch=true
    Wait Until Page Contains    Network    timeout=30s
    Click Element    xpath=//*[contains(@text, 'Network')]
    Wait Until Page Contains    Internet    timeout=15s
    Go Back
    Wait Until Page Contains    Connected devices    timeout=15s
    Click Element    xpath=//*[contains(@text, 'Connected devices')]
    Wait Until Page Contains    Pair new device    timeout=15s
    Go Back
