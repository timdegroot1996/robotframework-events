*** Variables ***
${N}    1000

*** Test Cases ***
Loop
    FOR    ${i}    IN RANGE    ${N}
        No Operation
    END
