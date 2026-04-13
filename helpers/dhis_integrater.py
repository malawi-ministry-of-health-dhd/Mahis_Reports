import requests as rq
import pandas as pd
import json
from config import DHIS2_UNAME, DHIS2_PASSWORD

def get_dhis_data(url, params=None, auth=(DHIS2_UNAME,DHIS2_PASSWORD)):
    try:
        response = rq.get(url, params=params, auth=auth)
        response.raise_for_status()  # Raise an error for bad responses
        return response.json()['dataValues']
    except Exception:
        return [{"dataElement":"","categoryOptionCombo":"","value":""}]

# example url with parameters for dhis2: https://dhis2.health.gov.mw/api/dataValueSets.json?dataSet=FYfNvfwNw7C&period=202512&orgUnit=glIscvEdIJz 

# data = get_dhis_data('https://dhis2.health.gov.mw/api/dataValueSets.json', params={
#     'dataSet': 'FYfNvfwNw7C',
#     'period': '202512',
#     'orgUnit': 'glIscvEdIJz'
# })