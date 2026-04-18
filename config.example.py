import os

USE_LOCALHOST = True
START_DATE = '2025-12-01'
LOAD_FRESH_DATA = False # Set to True to always start from START_DATE and fetch fresh data. Not recommended for large datasets.
PREFIX_NAME = '/'  # Set to your desired prefix for https paths, e.g., '/myapp'


RELATIVE_DAYS = [ 'Today', 'Yesterday', 'Last 7 Days', 'Last 30 Days', 'This Week', 'Last Week', 'This Month', 'Last Month' ]

# REFERENTIAL COLUMNS - THESE SHOULD MATCH THE QUERY OUTPUT COLUMNS
DATA_FILE_NAME_ = "latest_data_opd.parquet"

FIRST_NAME_ = 'given_name'
LAST_NAME_ = 'family_name'
DATE_ = 'Date'
PERSON_ID_ = 'person_id'
ENCOUNTER_ID_ = 'encounter_id'
FACILITY_ = 'Facility'
AGE_GROUP_ = 'Age_Group'
AGE_ = 'Age'
GENDER_ = 'Gender'
NEW_REVISIT_ = 'new_revisit'
HOME_DISTRICT_ = 'Home_district'
TA_ = 'TA'
VILLAGE_ = 'Village'
FACILITY_CODE_ = 'Facility_CODE'
OBS_VALUE_CODED_ = 'obs_value_coded'
CONCEPT_NAME_ = 'concept_name'
VALUE_ = 'Value'
VALUE_NUMERIC_ = 'ValueN'
DRUG_NAME_ = 'DrugName'
VALUE_NAME_ = 'Value_name'
ORDER_NAME_ = 'Order_Name'
PROGRAM_ = 'Program'
ENCOUNTER_ = 'Encounter'

# HANDLE GLOBAL IMPORT OF DATA FROM PARQUET FILE AND MANAGE AS CACHE FILES
PARQUET_FILE_PATH = os.path.join(os.getcwd(), 'data', 'latest_data_opd.parquet')
CACHE_FILE_PATH = os.path.join(os.getcwd(), 'data', 'cache_opd.parquet')
TIMESTAMP_FILE_PATH = os.path.join(os.getcwd(), 'data', 'TimeStamp.csv')

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

# on production remove COLLATE utf8mb3_general_ci
QERY = """
SELECT 
        p.person_id,
        e.encounter_id,
        pn2.given_name,
        pn2.family_name,
        gender AS Gender, 
        FLOOR(DATEDIFF(e.encounter_datetime, birthdate) / 365) AS Age, 
        CASE 
            WHEN FLOOR(DATEDIFF(e.encounter_datetime, birthdate) / 365) < 5 THEN 'Under 5'
            ELSE 'Over 5'
        END AS Age_Group,
        DATE(e.encounter_datetime) AS Date, 
        pr.name AS Program, 
        l.name AS Facility,
        l.location_id AS Facility_CODE, 
        u.username AS User, 
        l.city_village AS District, 
        et.name AS Encounter,
        pa.state_province AS Home_district,
        pa.township_division AS TA,
        pa.city_village AS Village,
        v.visit_days,
        cn.name AS obs_value_coded,
        c.name AS concept_name,
        o.value_text as Value,
        o.value_numeric as ValueN,
        d.name as DrugName,
        cnn.name as Value_name,
        d.name as Order_Name
    FROM person AS p
    JOIN patient AS pa2 ON p.person_id = pa2.patient_id
    JOIN person_name pn2 ON p.person_id = pn2.person_id
    JOIN person_address AS pa ON p.person_id = pa.person_id
    JOIN encounter AS e ON p.person_id = e.patient_id
    JOIN encounter_type AS et ON e.encounter_type = et.encounter_type_id
    INNER JOIN program AS pr ON e.program_id = pr.program_id
    INNER JOIN users AS u ON e.creator = u.user_id
    INNER JOIN location AS l ON u.location_id = l.location_id
    -- Join with precomputed visit days
    JOIN (
        SELECT patient_id, COUNT(DISTINCT DATE(encounter_datetime)) AS visit_days
        FROM encounter
        GROUP BY patient_id
    ) AS v ON v.patient_id = p.person_id
    LEFT JOIN obs o ON o.encounter_id = e.encounter_id AND o.voided = 0
    LEFT JOIN concept_name cn ON o.value_coded = cn.concept_id
        AND cn.locale = 'en'
        AND cn.concept_name_type = 'FULLY_SPECIFIED'
        AND cn.voided = 0
    LEFT JOIN concept_name c ON o.concept_id = c.concept_id
        AND c.locale = 'en'
        AND c.concept_name_type = 'FULLY_SPECIFIED'
        AND c.voided = 0
    LEFT JOIN concept co ON o.value_text = co.uuid
    LEFT JOIN concept_name cnn ON co.concept_id = cnn.concept_id
        AND cnn.locale = 'en'
        AND cnn.concept_name_type = 'FULLY_SPECIFIED'
        AND cnn.voided = 0
    LEFT JOIN drug as d on o.value_drug = d.drug_id
    WHERE p.voided = 0
    {date_filter}
) AS main

"""

actual_keys_in_data = ['person_id', 'encounter_id', 
                                       'Gender', 'Age', 'Age_Group', 
                                       'Date', 'Program', 'Facility', 
                                       'Facility_CODE', 'User', 'District', 
                                       'Encounter', 'Home_district', 'TA', 
                                       'Village', 'visit_days', 'obs_value_coded','concept_name', 'Value',"",
                                       'ValueN', 'DrugName', 'Value_name', 'new_revisit','count','count_set','sum','Order_Name']

CONCEPTS = """
SELECT 
    q.concept_id AS question_concept_id,
    qn.name AS question_name,
    a.concept_id AS answer_concept_id,
    an.name AS obs_value_coded,
    ca.sort_weight AS display_order
    
FROM concept q  -- q = question concept
INNER JOIN concept_answer ca ON ca.concept_id = q.concept_id
INNER JOIN concept a ON a.concept_id = ca.answer_concept  -- a = answer concept
INNER JOIN concept_name qn ON qn.concept_id = q.concept_id 
    AND qn.locale = 'en' 
    AND qn.concept_name_type = 'FULLY_SPECIFIED'
    AND qn.voided = 0
INNER JOIN concept_name an ON an.concept_id = a.concept_id 
    AND an.locale = 'en' 
    AND an.concept_name_type = 'FULLY_SPECIFIED'
    AND an.voided = 0
WHERE q.datatype_id = (
    SELECT concept_datatype_id 
    FROM concept_datatype 
    WHERE name = 'Coded'  -- Only Coded type questions have dropdown answers
)
AND q.retired = 0
AND a.retired = 0
ORDER BY q.concept_id, ca.sort_weight
"""
