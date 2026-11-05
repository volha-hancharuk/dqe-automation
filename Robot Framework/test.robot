*** Settings ***
Documentation       Compares the table in the "BI" HTML report with the Parquet dataset
...                 facility_type_avg_time_spent_per_visit_date.
...                 Run with: robot --outputdir ./results test.robot

Library             OperatingSystem
Library             SeleniumLibrary
Library             helper.py

Test Teardown       Close All Browsers


*** Variables ***
${REPORT_FILE}          ${CURDIR}/report.html
${PARQUET_FOLDER}       ${CURDIR}/parquet_data/facility_type_avg_time_spent_per_visit_date
# Rows with visit_date >= FILTER_DATE are compared. Set to ${EMPTY} to read the whole dataset.
${FILTER_DATE}          2026-09-26

${BROWSER}              chrome
${HEADLESS}             ${TRUE}
${TABLE_LOCATOR}        css:div.js-plotly-plot g.table
${TIMEOUT}              15s

&{COLUMN_MAPPING}       Facility Type=facility_type
...                     Visit Date=visit_date
...                     Average Time Spent=avg_time_spent


*** Test Cases ***
HTML Report Table Should Match Parquet Dataset
    [Documentation]    Passes when the report table and the filtered Parquet data are identical,
    ...    fails and lists every mismatched row otherwise.
    [Tags]    data-quality    report
    Open Report In Chrome    ${REPORT_FILE}
    ${table}=    Locate Report Table
    ${html_df}=    Read HTML Table To DataFrame    ${table}    ${COLUMN_MAPPING}
    ${parquet_df}=    Read Parquet Dataset    ${PARQUET_FOLDER}    ${FILTER_DATE}
    ${differences}=    Compare DataFrames    ${html_df}    ${parquet_df}
    Should Be Empty    ${differences}
    ...    msg=HTML table does not match Parquet dataset (filter date: ${FILTER_DATE}):\n${differences}


*** Keywords ***
Open Report In Chrome
    [Arguments]    ${report_file}
    File Should Exist    ${report_file}
    ${url}=    Evaluate    pathlib.Path(r'''${report_file}''').resolve().as_uri()    modules=pathlib
    ${options}=    Evaluate    selenium.webdriver.ChromeOptions()    modules=selenium.webdriver
    IF    ${HEADLESS}
        Call Method    ${options}    add_argument    --headless\=new
    END
    Call Method    ${options}    add_argument    --no-sandbox
    Call Method    ${options}    add_argument    --disable-dev-shm-usage
    Call Method    ${options}    add_argument    --window-size\=1920,1080
    Open Browser    ${url}    ${BROWSER}    options=${options}

Locate Report Table
    Wait Until Page Contains Element    ${TABLE_LOCATOR}    timeout=${TIMEOUT}
    ${table}=    Get WebElement    ${TABLE_LOCATOR}
    RETURN    ${table}

