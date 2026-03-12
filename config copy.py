import os

USE_LOCALHOST = False
START_DATE = '2026-01-01'
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


# # mahis test
# DB_CONFIG = {
#     'host': '127.0.0.1',
#     'user': 'dhd_db_testadmin',
#     'password': 'mhefM3uUjciBsy47dnRKd',
#     'database': 'opd_test',
#     'port': 3306
# }

# SSH_CONFIG = {
#     'ssh_host': 'ec2-13-247-36-140.af-south-1.compute.amazonaws.com',
#     'ssh_port': 22,
#     'ssh_user': 'ubuntu',
#     # 'ssh_password': 'drinnocent2',  # OR use ssh_pkey if using key
#     'ssh_pkey': 'dhd-dev-aetc-pub-key.pem', # Only indicate file name
#     'remote_bind_address': ('dhd-mahis-mysql-development-db.c7iooimo2e39.af-south-1.rds.amazonaws.com', 3306)
# }

# For local database connection
DB_CONFIG_LOCAL = {
    'host': 'localhost',
    'user': 'user',
    'password': 'password',
    'database': 'local_database',
    'port': 3306
}

# mahis_production
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'db_prod_admin',
    'password': 'ksS2M!EX&s$JxzDLD8T5#B64!',
    'database': 'mahis_development_db',
    'port': 3306
}

SSH_CONFIG = {
    'ssh_host': 'ec2-13-244-149-25.af-south-1.compute.amazonaws.com',
    'ssh_port': 22,
    'ssh_user': 'ubuntu',
    'ssh_pkey': 'dhd-prod-devops-mahis-kp.pem',  # Path to your private key
    'remote_bind_address': ('dhd-production-mysql-db.c7iooimo2e39.af-south-1.rds.amazonaws.com', 3306)
}

# on production remove COLLATE utf8mb3_general_ci
QERY = """
SELECT 
    main.*,
    CASE 
        WHEN visit_days = 1 THEN 'New'
        ELSE 'Revisit'
    END AS new_revisit
FROM (
    SELECT 
        p.person_id,
        e.encounter_id,
        pn2.given_name,
        pn2.family_name,
        gender AS Gender, 
        FLOOR(DATEDIFF(CURRENT_DATE, birthdate) / 365) AS Age, 
        CASE 
            WHEN FLOOR(DATEDIFF(CURRENT_DATE, birthdate) / 365) < 5 THEN 'Under 5'
            ELSE 'Over 5'
        END AS Age_Group,
        DATE(e.encounter_datetime) AS Date, 
        pr.name AS Program, 
        l.name AS Facility,
        l.code AS Facility_CODE, 
        u.username AS User, 
        l.district AS District, 
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
        cnnn.name as Order_Name
    FROM person AS p
    JOIN patient AS pa2 ON p.person_id = pa2.patient_id
    JOIN person_name pn2 ON p.person_id = pn2.person_id
    JOIN person_address AS pa ON p.person_id = pa.person_id
    JOIN encounter AS e ON p.person_id = e.patient_id
    JOIN encounter_type AS et ON e.encounter_type = et.encounter_type_id
    INNER JOIN program AS pr ON e.program_id = pr.program_id
    INNER JOIN users AS u ON e.provider_id = u.user_id
    INNER JOIN facilities AS l ON u.location_id = l.code
    -- Join with precomputed visit days
    JOIN (
        SELECT patient_id, COUNT(DISTINCT DATE(encounter_datetime)) AS visit_days
        FROM encounter
        GROUP BY patient_id
    ) AS v ON v.patient_id = p.person_id
    LEFT JOIN obs o ON o.encounter_id = e.encounter_id
    LEFT JOIN concept_name cn ON o.value_coded = cn.concept_id AND cn.locale = 'en' AND cn.concept_name_type = 'FULLY_SPECIFIED'
    LEFT JOIN concept_name c ON o.concept_id = c.concept_id
    LEFT JOIN concept co ON o.value_text = co.uuid
    LEFT JOIN concept_name cnn ON co.concept_id = cnn.concept_id
    LEFT JOIN drug as d on o.value_drug = d.drug_id
    LEFT JOIN orders as od on o.order_id = od.order_id
    LEFT JOIN concept_name as cnnn on od.concept_id = cnnn.concept_id
    WHERE p.voided = 0
    {date_filter}
) AS main

"""

#  COLLATE utf8mb3_general_ci

actual_keys_in_data = ['person_id', 'encounter_id', 
                                       'Gender', 'Age', 'Age_Group', 
                                       'Date', 'Program', 'Facility', 
                                       'Facility_CODE', 'User', 'District', 
                                       'Encounter', 'Home_district', 'TA', 
                                       'Village', 'visit_days', 'obs_value_coded','concept_name', 'Value',"",
                                       'ValueN', 'DrugName', 'Value_name', 'new_revisit','count','count_set','sum','Order_Name']