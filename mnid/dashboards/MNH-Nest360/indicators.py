"""
Nest360 indicator definitions mapped to actual MAHIS concept_name / derived flags.

Status:
  tracked           - calculated from MAHIS data
  awaiting_baseline - data not yet in this extract (device data, timing, blood culture, etc.)
"""


def get_nest360_indicators():
    _NB = {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn'}
    return [

        # Vital signs
        {
            'id': 'nest360_pulse_oximeter_used_at_admission',
            'label': 'Pulse oximeter used at admission',
            'category': 'Nest360', 'subcategory': 'Vital signs', 'target': 100, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'Service_Area', 'value1': 'Newborn',
                                  'variable2': 'mnid_newborn_pulse_oximeter_admission', 'value2': 'Yes'},
            'denominator_filters': _NB,
        },
        {
            'id': 'nest360_temperature_taken_at_admission',
            'label': 'Temperature taken at admission',
            'category': 'Nest360', 'subcategory': 'Vital signs', 'target': 100, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name',
                                  'value1': 'Thermal status on admission'},
            'denominator_filters': _NB,
        },
        {
            'id': 'nest360_weight_taken_at_birth',
            'label': 'Weight taken at birth',
            'category': 'Nest360', 'subcategory': 'Vital signs', 'target': 100, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Birth weight'},
            'denominator_filters': _NB,
        },
        {
            'id': 'nest360_glucose_monitored_at_admission',
            'label': 'Glucose monitored at admission',
            'category': 'Nest360', 'subcategory': 'Vital signs', 'target': 75,
            'status': 'awaiting_baseline',
            'numerator_filters': _NB, 'denominator_filters': _NB,
        },

        # CPAP
        {
            'id': 'nest360_cpap_for_eligible_babies',
            'label': 'CPAP for eligible babies',
            'category': 'Nest360', 'subcategory': 'CPAP', 'target': 100, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'CPAP support'},
            'denominator_filters': _NB,
        },
        {
            'id': 'nest360_cpap_for_babies_1000_1499g',
            'label': 'CPAP for babies 1000-1499g (prophylactic)',
            'category': 'Nest360', 'subcategory': 'CPAP', 'target': 100, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_cpap_1000_1499', 'value1': 'Yes'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_birth_weight_band', 'value1': '1000-1499g'},
        },
        {
            'id': 'nest360_cpap_1500_1999g_with_symptoms',
            'label': 'CPAP 1500-1999g (with symptoms)',
            'category': 'Nest360', 'subcategory': 'CPAP', 'target': 100, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_cpap_1500_1999', 'value1': 'Yes'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_birth_weight_band', 'value1': '1500-1999g'},
        },
        {
            'id': 'nest360_cpap_timing_birth',
            'label': 'Time: Birth to CPAP initiation (1000-1999g)',
            'category': 'Nest360', 'subcategory': 'CPAP', 'target': 100,
            'status': 'awaiting_baseline',
            'numerator_filters': _NB, 'denominator_filters': _NB,
        },

        # KMC
        {
            'id': 'nest360_kmc_1000_1999g',
            'label': 'KMC 1000-1999g',
            'category': 'Nest360', 'subcategory': 'KMC', 'target': 75, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_kmc', 'value1': 'Yes',
                                  'variable2': 'mnid_birth_weight_band', 'value2': '1000-1499g'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_lbw_kmc_eligible', 'value1': 'Yes'},
        },
        {
            'id': 'nest360_kmc_2000_2499g',
            'label': 'KMC 2000-2499g',
            'category': 'Nest360', 'subcategory': 'KMC', 'target': 75, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_kmc', 'value1': 'Yes',
                                  'variable2': 'mnid_birth_weight_band', 'value2': '2000-2499g'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_birth_weight_band', 'value1': '2000-2499g'},
        },
        {
            'id': 'nest360_kmc_timing',
            'label': 'Time: Birth to KMC initiation (1000-2500g)',
            'category': 'Nest360', 'subcategory': 'KMC', 'target': 100,
            'status': 'awaiting_baseline',
            'numerator_filters': _NB, 'denominator_filters': _NB,
        },

        # Hypothermia / warm chain
        {
            'id': 'nest360_not_hypothermic_at_admission',
            'label': 'Not hypothermic at admission',
            'category': 'Nest360', 'subcategory': 'Hypothermia', 'target': 100, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name',
                                  'value1': 'Thermal status on admission',
                                  'variable2': 'obs_value_coded', 'value2': 'Not hypothermic'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'concept_name',
                                    'value1': 'Thermal status on admission'},
        },
        {
            'id': 'nest360_thermal_care_recorded',
            'label': 'Thermal care recorded',
            'category': 'Nest360', 'subcategory': 'Hypothermia', 'target': 100, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'thermal care'},
            'denominator_filters': _NB,
        },

        # Jaundice
        {
            'id': 'nest360_phototherapy_for_jaundice',
            'label': 'Phototherapy for clinical jaundice',
            'category': 'Nest360', 'subcategory': 'Jaundice', 'target': 90, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice_phototherapy', 'value1': 'Yes'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice', 'value1': 'Yes'},
        },
        {
            'id': 'nest360_bilirubin_measurement',
            'label': 'Bilirubin measured in babies with jaundice',
            'category': 'Nest360', 'subcategory': 'Jaundice', 'target': 80, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice_bilirubin_measured', 'value1': 'Yes'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_jaundice', 'value1': 'Yes'},
        },
        {
            'id': 'nest360_exchange_transfusion',
            'label': 'Exchange Transfusion',
            'category': 'Nest360', 'subcategory': 'Jaundice', 'target': 100,
            'status': 'awaiting_baseline',
            'numerator_filters': _NB, 'denominator_filters': _NB,
        },

        # Infection
        {
            'id': 'nest360_neonatal_sepsis_rate',
            'label': 'Neonatal sepsis among admissions',
            'category': 'Nest360', 'subcategory': 'Infection', 'target': 10,
            'status': 'tracked', 'target_mode': 'min',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_sepsis', 'value1': 'Yes'},
            'denominator_filters': _NB,
        },
        {
            'id': 'nest360_antibiotics_for_sepsis',
            'label': 'Antibiotics for clinical sepsis',
            'category': 'Nest360', 'subcategory': 'Infection', 'target': 100, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_sepsis_antibiotics', 'value1': 'Yes'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_sepsis', 'value1': 'Yes'},
        },
        {
            'id': 'nest360_blood_culture',
            'label': 'Blood culture done for babies on antibiotics',
            'category': 'Nest360', 'subcategory': 'Infection', 'target': 100,
            'status': 'awaiting_baseline',
            'numerator_filters': _NB, 'denominator_filters': _NB,
        },

        # Resuscitation
        {
            'id': 'nest360_birth_asphyxia_rate',
            'label': 'Birth asphyxia among admissions',
            'category': 'Nest360', 'subcategory': 'Resuscitation', 'target': 10,
            'status': 'tracked', 'target_mode': 'min',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_birth_asphyxia', 'value1': 'Yes'},
            'denominator_filters': _NB,
        },
        {
            'id': 'nest360_resuscitation_given',
            'label': 'Eligible babies receiving bag-mask ventilation',
            'category': 'Nest360', 'subcategory': 'Resuscitation', 'target': 80, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_asphyxia_resuscitated', 'value1': 'Yes'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_birth_asphyxia', 'value1': 'Yes'},
        },

        # Birth weight
        {
            'id': 'nest360_birth_weight_recorded',
            'label': 'Birth weight recorded',
            'category': 'Nest360', 'subcategory': 'Birth weight', 'target': 80, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Birth weight'},
            'denominator_filters': _NB,
        },
        {
            'id': 'nest360_low_birthweight_rate',
            'label': 'Low birthweight rate (<2500g)',
            'category': 'Nest360', 'subcategory': 'Birth weight', 'target': 12,
            'status': 'tracked', 'target_mode': 'min',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'mnid_newborn_low_birthweight', 'value1': 'Yes'},
            'denominator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Birth weight'},
        },

        # Data Quality (proxy)
        {
            'id': 'nest360_data_completeness',
            'label': 'Data completeness (birth weight proxy)',
            'category': 'Nest360', 'subcategory': 'Data Quality', 'target': 95, 'status': 'tracked',
            'numerator_filters': {'unique': 'person_id', 'variable1': 'concept_name', 'value1': 'Birth weight'},
            'denominator_filters': _NB,
        },

        # Devices & Supplies / HR / Infrastructure - awaiting data
        {
            'id': 'nest360_devices_supplies',
            'label': 'Device / supply availability',
            'category': 'Nest360', 'subcategory': 'Devices & Supplies', 'target': 100,
            'status': 'awaiting_baseline',
            'numerator_filters': _NB, 'denominator_filters': _NB,
        },
        {
            'id': 'nest360_human_resources',
            'label': 'Nurse ratios and training',
            'category': 'Nest360', 'subcategory': 'Human Resources', 'target': 100,
            'status': 'awaiting_baseline',
            'numerator_filters': _NB, 'denominator_filters': _NB,
        },
    ]
