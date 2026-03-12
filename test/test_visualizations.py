# test_visualizations.py
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Import the functions to test
from visualizations import (
    create_count, 
    create_count_sets, 
    create_count_unique, 
    create_sum, 
    create_sum_sets,
    _apply_filter
)
from config import PERSON_ID_, ENCOUNTER_ID_, DATE_

@pytest.fixture
def sample_data():
    """lets use the original data but with first 20 patients"""
    sample_data = pd.read_csv('test_data.csv')
    sample_data['Date'] = pd.to_datetime(sample_data['Date'])
    twenty_patients = sample_data['person_id'].unique()[:20].tolist()
    return sample_data[sample_data['person_id'].isin(twenty_patients)]


@pytest.fixture
def sample_data_with_duplicates():
    """Create sample data with duplicate entries"""
    sample_data = pd.read_csv('test_data.csv')
    sample_data['Date'] = pd.to_datetime(sample_data['Date'])
    twenty_patients = sample_data['person_id'].unique()[:20].tolist()
    data = sample_data[sample_data['person_id'].isin(twenty_patients)]
    duplicate_list = data['person_id'].unique()[:4].tolist()
    duplicate_rows = data[data['person_id'].isin(duplicate_list)].copy()
    duplicated_data = pd.concat([data, duplicate_rows], ignore_index=True)
    return duplicated_data


class TestCountFunctions:
    """Test cases for count functions"""
    
    def test_create_count_basic(self, sample_data):
        """Test basic count without filters"""
        result = create_count(
            sample_data, 
            unique_column='person_id'
        )
        # assertion based on pd count including date for cumulative count method
        
        assert result == 10  # 10 unique person_id in sample_data
        
    def test_create_count_with_single_filter(self, sample_data):
        """Test count with single filter"""
        result = create_count(
            sample_data,
            unique_column='person_id',
            filter_col1='Gender',
            filter_value1='Male'
        )
        # assertion based on pd count including date for cumulative count method
        assert result == 5  # 5 unique
        
    def test_create_count_with_multiple_filters(self, sample_data):
        """Test count with multiple filters"""
        result = create_count(
            sample_data,
            unique_column='person_id',
            filter_col1='Gender',
            filter_value1='Female',
            filter_col2='Program',
            filter_value2='OPD Program'
        )
        # assertion based on pd count including date for cumulative count method
        assert result == 5
        
    def test_create_count_with_operator_filter(self, sample_data):
        """Test count with operator filter (> , <)"""
        result = create_count(
            sample_data,
            unique_column='person_id',
            filter_col1='Age',
            filter_value1='>20'
        )
        # assertion based on pd count including date for cumulative count method
        assert result == 4
        
    def test_create_count_with_list_filter(self, sample_data):
        """Test count with list filter"""
        result = create_count(
            sample_data,
            unique_column='person_id',
            filter_col1='Program',
            filter_value1=['OPD Program','NCD PROGRAM']  # Should return all
        )
        # assertion based on pd count including date for cumulative count method
        assert result == 10
        
    def test_create_count_with_date_deduplication(self, sample_data_with_duplicates):
        """Test that count deduplicates by unique_column and Date"""
        result = create_count(
            sample_data_with_duplicates,
            unique_column='person_id'
        )
        assert result == 10  # Should still be 10 unique person_id despite duplicates
        
    def test_create_count_unique_basic(self, sample_data):
        """Test unique person count"""
        result = create_count_unique(
            sample_data,
            unique_column='person_id'
        )
 
        assert result == 10  # 10 unique person_id in sample_data
        
    def test_create_count_unique_with_filter(self, sample_data):
        """Test unique person count with filter"""
        result = create_count_unique(
            sample_data,
            unique_column='person_id',
            filter_col1='Program',
            filter_value1='OPD Program'
        )
        assert result == 10  # All 10 unique person_id are in OPD Program
        
    def test_create_count_unique_with_operator(self, sample_data):
        """Test unique person count with operator"""
        result = create_count_unique(
            sample_data,
            unique_column='person_id',
            filter_col1='Age',
            filter_value1='<35'
        )
        assert result == 8
        
    def test_create_count_sets_basic(self, sample_data):
        """Test count_sets with single condition"""
        result = create_count_sets(
            sample_data,
            unique_column='person_id',
            filter_col1='Gender',
            filter_value1='Male'
        )
        assert result == 5
        
    def test_create_count_sets_multiple_conditions(self, sample_data):
        """Test count_sets with multiple conditions (AND logic)"""
        result = create_count_sets(
            sample_data,
            unique_column='person_id',
            filter_col1='Encounter',
            filter_value1=['DIAGNOSIS','PAST MEDICAL HISTORY'],
            filter_col2='obs_value_coded',
            filter_value2=['Diarrhea',None]
        )

        assert result == 1
        
    def test_create_count_sets_with_operators(self, sample_data):
        """Test count_sets with operator conditions"""
        result = create_count_sets(
            sample_data,
            unique_column='person_id',
            filter_col1='Age',
            filter_value1='>30',
            filter_col2='Program',
            filter_value2='OPD Program'
        )
        # Age>30 AND NCD: persons 3,5 = 2
        assert result == 2
        
    def test_create_count_sets_with_incorrect_list_filters(self, sample_data):
        """Test count_sets with list filters"""
        with pytest.raises(ValueError):
            create_count_sets(
            sample_data,
            unique_column='person_id',
            filter_col1=['Program', 'Gender'],
            filter_value1=['OPD Program', 'Male']
        )
        
    def test_create_count_sets_no_matches(self, sample_data):
        """Test count_sets with no matching records"""
        result = create_count_sets(
            sample_data,
            unique_column='person_id',
            filter_col1='Age',
            filter_value1='>100'
        )
        assert result == 0
        

class TestSumFunctions:
    """Test cases for sum functions"""
    
    def test_create_sum_basic(self, sample_data):
        """Test basic sum without filters"""
        result = create_sum(
            sample_data,
            num_field='ValueN'
        )
        assert result == 448  # Sum of all ValueN in sample_data
        
    def test_create_sum_with_filter(self, sample_data):
        """Test sum with single filter"""
        result = create_sum(
            sample_data,
            num_field='ValueN',
            filter_col1='Gender',
            filter_value1='Male'
        )
        assert result == 200 # Sum of ValueN for Male records in sample_data
        
    def test_create_sum_with_operator(self, sample_data):
        """Test sum with operator filter"""
        result = create_sum(
            sample_data,
            num_field='ValueN',
            filter_col1='Age',
            filter_value1='>30'
        )
        assert result == 224 # Sum of ValueN for records with Age >30 in sample_data
        
    # def test_create_sum_with_multiple_filters(self, sample_data):
    #     """Test sum with multiple filters"""
    #     result = create_sum(
    #         sample_data,
    #         num_field='ValueN',
    #         filter_col1='Gender',
    #         filter_value1='Female',
    #         filter_col2='Program',
    #         filter_value2='NCD PROGRAM'
    #     )
    #     assert result == 0
        
    # def test_create_sum_sets_basic(self, sample_data):
    #     """Test sum_sets with paired conditions"""
    #     # Test sum for persons who have both SBP and DBP readings
    #     result = create_sum_sets(
    #         sample_data,
    #         filter_col1='concept_name',
    #         filter_value1=['SBP', 'SBP'],
    #         filter_col2='concept_name',
    #         filter_value2=['DBP', 'DBP'],
    #         num_field='ValueN',
    #         unique_column='person_id'
    #     )
    #     # Person 2 has SBP(130) and DBP(120)
    #     # Person 3 has SBP(140) and DBP(135)
    #     # Sum: 130+120+140+135 = 525
    #     assert result == 525
        
    # def test_create_sum_sets_with_extra_filters(self, sample_data):
    #     """Test sum_sets with extra filters"""
    #     result = create_sum_sets(
    #         sample_data,
    #         filter_col1='concept_name',
    #         filter_value1=['SBP', 'SBP'],
    #         filter_col2='concept_name',
    #         filter_value2=['DBP', 'DBP'],
    #         num_field='ValueN',
    #         unique_column='person_id',
    #         filter_col3='Gender',
    #         filter_value3='M'
    #     )
    #     # Male persons with both SBP and DBP: person3 only
    #     # Sum: 140+135 = 275
    #     assert result == 275
        
    # def test_create_sum_sets_no_matches(self, sample_data):
    #     """Test sum_sets with no matching records"""
    #     result = create_sum_sets(
    #         sample_data,
    #         filter_col1='concept_name',
    #         filter_value1=['SBP', 'SBP'],
    #         filter_col2='concept_name',
    #         filter_value2=['DBP', 'DBP'],
    #         num_field='ValueN',
    #         unique_column='person_id',
    #         filter_col3='Age',
    #         filter_value3='>50'
    #     )
    #     assert result == 0
        
    # def test_create_sum_sets_invalid_inputs(self, sample_data):
    #     """Test sum_sets with invalid inputs should raise ValueError"""
    #     with pytest.raises(ValueError):
    #         create_sum_sets(
    #             sample_data,
    #             filter_col1='concept_name',
    #             filter_value1=['SBP'],  # Different lengths
    #             filter_col2='concept_name',
    #             filter_value2=['DBP', 'DBP'],
    #             num_field='ValueN',
    #             unique_column='person_id'
    #         )

class TestEdgeCases:
    """Test edge cases for all functions"""
    
    def test_empty_dataframe(self):
        """Test functions with empty dataframe"""
        empty_df = pd.DataFrame(columns=['person_id', 'encounter_id', 'ValueN'])
        
        assert create_count(empty_df, unique_column='person_id') == 0
        assert create_count_unique(empty_df, unique_column='person_id') == 0
        assert create_sum(empty_df, num_field='ValueN') == 0
        
    def test_no_filters(self, sample_data):
        """Test that functions work with no filters specified"""
        assert create_count(sample_data) == 10  # Uses default ENCOUNTER_ID_
        assert create_count_unique(sample_data) == 10 # 10 unique person_id
        
    def test_none_values(self):
        """Test handling of None values"""
        data = {
            'person_id': [1, 2, 3, 4],
            'encounter_id': [101, 102, 103, 104],
            'ValueN': [10, None, 30, None]
        }
        df = pd.DataFrame(data)
        
        # Sum should ignore None/NaN values
        result = create_sum(df, num_field='ValueN')
        assert result == 40  # 10 + 30
        
    def test_all_filters_none(self, sample_data):
        """Test when all filters are None"""
        result = create_count(
            sample_data,
            filter_col1=None,
            filter_value1=None,
            filter_col2=None,
            filter_value2=None
        )
        assert result == 10

class TestApplyFilter:
    """Test the _apply_filter helper function directly"""
    
    def test_apply_filter_equality(self, sample_data):
        """Test equality filter"""
        result = _apply_filter(sample_data, 'Gender', 'Male')
        assert len(result) == 13  # 13 M records
        
    def test_apply_filter_not_equal(self, sample_data):
        """Test not equal filter with person exclusion"""
        result = _apply_filter(sample_data, 'Gender', '!=Male')
        # Should return all records where Gender is not Male
        assert len(result) == 10  # 10 records
        
    def test_apply_filter_greater_than(self, sample_data):
        """Test greater than filter"""
        result = _apply_filter(sample_data, 'Age', '>35')
        assert len(result) == 7
        
    def test_apply_filter_less_than(self, sample_data):
        """Test less than filter"""
        result = _apply_filter(sample_data, 'Age', '<30')
        assert len(result) == 16 
        
    def test_apply_filter_list(self, sample_data):
        """Test list filter"""
        result = _apply_filter(sample_data, 'Encounter', ['DIAGNOSIS', 'VITALS'])
        assert len(result) == 11  # all records
        
    def test_apply_filter_multi_column(self, sample_data):
        """Test multi-column filter"""
        result = _apply_filter(
            sample_data, 
            ['Gender', 'Program'], 
            ['Male', 'OPD Program']
        )
        # Gender=M AND Program=NCD: persons 1,3,5
        assert len(result) == 13  # person1(3), person3(2), person5(1)
        
    # def test_apply_filter_invalid_column(self, sample_data):
    #     """Test filter with invalid column returns original data"""
    #     result = _apply_filter(sample_data, 'InvalidColumn', 'Male')
    #     assert len(result) == 10  # No filtering applied

if __name__ == '__main__':
    pytest.main([__file__, '-v'])