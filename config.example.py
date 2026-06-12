import os

USE_LOCALHOST = False
START_DATE = '2026-05-01'
LOAD_FRESH_DATA = False # Set to True to always start from START_DATE and fetch fresh data. Not recommended for large datasets.
PREFIX_NAME = '/'  # Set to your desired prefix for https paths, e.g., '/myapp'
BATCH_SIZE = 1000 # Number of records to fetch per batch when loading from database
IS_HARMONIZED_MAHIS = True # Set to True if using the harmonized MAHIS database schema, False for legacy schema
DEMO_UUID = "m3his@dhd"
DEMO_LOCATION = "LL040033"
RELATIVE_DAYS = [ 'Today', 'Yesterday', 'Last 7 Days', 'Last 30 Days', 'This Week', 'Last Week', 'This Month', 'Last Month' ]

# REFERENTIAL COLUMNS - THESE SHOULD MATCH THE QUERY OUTPUT COLUMNS
DATA_PATH_ = "data/default"

# REFERENCE COLUMNS
FIRST_NAME_ = 'given_name'
LAST_NAME_ = 'family_name'
DATE_ = 'Date'
PERSON_ID_ = 'person_id'
ENCOUNTER_ID_ = 'encounter_id'
FACILITY_ = 'Facility'
DISTRICT_ = 'District'
AGE_GROUP_ = 'Age_Group'
AGE_ = 'Age'
GENDER_ = 'Gender'
NEW_REVISIT_ = 'new_revisit'
HOME_DISTRICT_ = 'Home_district'
TA_ = 'TA'
VILLAGE_ = 'Village'
FACILITY_CODE_ = 'Facility_CODE'
OBS_VALUE_CODED_ = 'obs_value_coded'
VALUE_DATETIME_ = 'value_datetime'
CONCEPT_NAME_ = 'concept_name'
VALUE_ = 'Value'
VALUE_NUMERIC_ = 'ValueN'
DRUG_NAME_ = 'DrugName'
VALUE_NAME_ = 'Value_name'
ORDER_NAME_ = 'Order_Name'
PROGRAM_ = 'Program'
ENCOUNTER_ = 'Encounter'

DHIS2_URL = "https://102.211.20.17/dhis"
DHIS2_UNAME='user'
DHIS2_PASSWORD='password'

# For local database connection
DB_CONFIG_LOCAL = {
    'host': 'localhost',
    'user': 'user',
    'password': 'password',
    'database': 'local_database',
    'port': 3306
}

# for production database connection
DB_CONFIG = {
    'host': 'hostname',
    'user': 'user',
    'password': 'password',
    'database': 'database',
    'port': 3306
}

# SSH configuration for production database connection
SSH_CONFIG = {
    'ssh_host': 'aws_host',
    'ssh_port': 22,
    'ssh_user': 'ubuntu',
    'ssh_password': 'password',  # OR use ssh_pkey if using key
    # 'ssh_pkey': 'key.pem',  #private key name stored in ssh directory
    'remote_bind_address': ('path_to_db_endpoint', 3306)
}

actual_keys_in_data = ['person_id', 'visit_id', 'date_started', 'date_stopped', 'identifier', 
                       'patient_identifier_type', 'given_name', 'family_name', 'Gender', 'birthdate', 
                       'AgeDays', 'Age', 'Age_Group', 'person_attribute_name', 'person_attribute_type', 
                       'Home_district', 'TA', 'Village', 'encounter_id', 'Encounter', 'Date', 
                       'location_id', 'creator', 'provider_id', 'Program', 'concept_name', 'obs_datetime', 
                       'obs_group_id', 'accession_number', 'value_group_id', 'value_boolean', 'obs_value_coded', 
                       'value_coded_name_id', 'DrugName', 'value_datetime', 'ValueN', 'Value', 'Order_Type', 'Order_Name', 
                       'Source_Program', 'Reporting_Program', 'Service_Area', 'new_revisit', 'DrugUnits', 'User', 'Facility_CODE', 
                       'Facility', 'District', 'month_key']


QUERY_OBS_HARMONIZED = """
SELECT
    e.patient_id as person_id,
    v.visit_id,
    v.date_started,
    v.date_stopped,
    pi.identifier,
    pit.name as patient_identifier_type,
    pn.given_name,
    pn.family_name,
    p.gender AS Gender,
    p.birthdate,
    FLOOR(DATEDIFF(e.encounter_datetime, birthdate)) AS AgeDays,
    FLOOR(DATEDIFF(e.encounter_datetime, birthdate) / 365) AS Age,
    CASE
        WHEN FLOOR(DATEDIFF(e.encounter_datetime, birthdate) / 365) < 5 THEN 'Under 5'
        ELSE 'Over 5'
    END AS Age_Group,
    pat.value as cell,
    pa.state_province AS Home_district,
    pa.township_division AS TA,
    pa.city_village AS Village,
    e.encounter_id,
    e.encounter_type AS Encounter,
    e.encounter_datetime AS Date, #date
    e.location_id,
    e.creator,
    e.provider_id,
    e.program_id AS Program,
    o.concept_id AS concept_name,
    o.obs_datetime,
    o.obs_group_id,
    o.accession_number,
    o.value_group_id,
    o.value_boolean,
    o.value_coded AS obs_value_coded,
    o.value_coded_name_id,
    o.value_drug AS DrugName,
    o.value_datetime,
    o.value_numeric as ValueN,
    o.value_text as Value,
    od.order_type_id as Order_Type,
    od.concept_id as Order_Name
FROM encounter e
LEFT JOIN visit v on e.visit_id = v.visit_id AND v.voided = 0
JOIN person p ON e.patient_id = p.person_id AND p.voided = 0
JOIN person_name pn ON e.patient_id = pn.person_id AND pn.voided = 0
LEFT JOIN patient_identifier pi on e.patient_id = pi.patient_id AND pi.identifier_type = 3
LEFT JOIN patient_identifier_type pit on  pi.identifier_type = pit.patient_identifier_type_id AND pit.retired = 0
LEFT JOIN obs o ON e.encounter_id = o.encounter_id
# JOIN patient_program pp ON e.patient_id = pp.patient_id AND pp.voided = 0
LEFT JOIN person_address pa ON pn.person_id = pa.person_id AND pa.voided = 0 AND pa.preferred = 0
LEFT JOIN person_attribute pat ON p.person_id = pat.person_id AND pat.voided = 0
LEFT JOIN orders od ON o.order_id = od.order_id AND od.discontinued = 0
LEFT JOIN person_attribute_type patt ON pat.person_attribute_type_id = patt.person_attribute_type_id 
    AND patt.retired = 0 AND patt.person_attribute_type_id = 12
WHERE e.voided = 0
{date_filter}
"""

# static tables
QUERY_PROGRAMS = """
SELECT program_id, name FROM program WHERE retired = 0
"""
QUERY_CONCEPT_NAMES = """
SELECT concept_id, name FROM concept_name WHERE locale = 'en' AND concept_name_type = 'FULLY_SPECIFIED' AND voided = 0
"""
QUERY_ENCOUNTER_TYPES = """
SELECT encounter_type_id, name FROM encounter_type WHERE retired = 0
"""
QUERY_LOCATIONS = """
SELECT location_id, name, county_district  FROM location WHERE retired = 0
"""
QUERY_FACILITIES = """
SELECT id, code, name, district FROM facilities
"""

QUERY_DRUGS = """
SELECT drug_id, name, units FROM drug WHERE retired = 0
"""

QUERY_ORDER_TYPES = """
SELECT order_type_id, name FROM order_type WHERE retired = 0
"""

QUERY_USERS = """
SELECT
    u.user_id,
    u.username AS User,
    u.person_id,
    u.location_id,
    u.uuid as uuid, 
    ur.role as role,
    l.name as facility_name,
    l.county_district as district
FROM users u 
JOIN user_role ur ON u.user_id = ur.user_id
JOIN location l ON u.location_id = l.location_id
WHERE u.retired = 0
"""

QUERY_USER_PROGRAMS = """
SELECT 
    up.user_id, 
    p.name 
FROM user_programs up
JOIN program p on up.program_id = p.program_id AND p.retired = 0
"""

CUSTOM_MNID_MAP_PROGRAM = {
    "NEONATAL PROGRAM": "NEONATAL PROGRAM",
    "MATERNAL AND CHILD HEALTH": "MATERNAL AND CHILD HEALTH",
    "ANC VISIT": "MATERNAL AND CHILD HEALTH",
    "LABOUR AND DELIVERY": "MATERNAL AND CHILD HEALTH",
    "POSTNATAL CARE": "MATERNAL AND CHILD HEALTH"
}
CUSTOM_MNID_MAP_SERVICE_AREA = {
    "ANC VISIT": "ANC",
    "LABOUR AND DELIVERY": "LABOUR",
    "POSTNATAL CARE": "PNC",
    "NEONATAL PROGRAM": "NEONATAL",
}
CUSTOM_GENDER_MAP = {
    'M': 'Male',
    'F': 'Female',
    'O': 'Other',
    'U': 'Undetermined',
    '{"label"=>"Male", "value"=>"M"}':"Male",
    '{"label"=>"Female", "value"=>"F"}':"Female"
}
