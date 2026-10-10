*** Settings ***
Suite Setup       Log    suite setup
Suite Teardown    Log    suite teardown

*** Test Cases ***
Passing With Structures
    [Setup]    Log    test setup
    My Keyword    hello
    FOR    ${i}    IN RANGE    3
        IF    ${i} == 1
            Log    one
        ELSE
            Log    not one    WARN
        END
    END
    TRY
        Fail    expected
    EXCEPT    expected
        Log    caught
    END
    VAR    ${x}    1
    Log    ${x}
    Run Keyword And Ignore Error    Fail    ignored
    [Teardown]    Log    test teardown

Failing Test
    My Keyword    a
    Should Be Equal    1    2
    Log    never runs

Skipped Test
    Skip    not today

*** Keywords ***
My Keyword
    [Arguments]    ${arg}
    Log    ${arg}
    Nested Keyword

Nested Keyword
    No Operation
