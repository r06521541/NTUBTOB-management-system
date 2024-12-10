import requests

web_portal_url = 'https://web-portal-7uz453jt3a-de.a.run.app/'
clear_cache_api = web_portal_url + '/clear-cache'

def clear_cache_of_attendance_page():
    return requests.get(clear_cache_api + '/attendance')