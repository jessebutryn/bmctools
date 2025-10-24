import requests
import json

class RedfishAPI:
    """
    Redfish API client for interacting with the Redfish service.
    """
    def __init__(self, ip, user, password, verify_ssl=True):
        self.ip = ip
        self.user = user
        self.password = password
        self.base_url = f"https://{ip}"
        self.session = requests.Session()
        self.session.auth = (user, password)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self.verify_ssl = verify_ssl

        if not self.verify_ssl:
            self.disable_ssl_verification()


    def disable_ssl_verification(self):
        self.verify_ssl = False
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)


    def get(self, endpoint, params=None):
        url = self.base_url + endpoint
        response = self.session.get(url, params=params, verify=self.verify_ssl)
        return response


    def post(self, endpoint, data=None):
        url = self.base_url + endpoint
        if data:
            data = json.dumps(data)
        response = self.session.post(url, data=data, verify=self.verify_ssl)
        return response


    def put(self, endpoint, data=None):
        url = self.base_url + endpoint
        if data:
            data = json.dumps(data)
        response = self.session.put(url, data=data, verify=self.verify_ssl)
        return response


    def patch(self, endpoint, data=None):
        url = self.base_url + endpoint
        if data:
            data = json.dumps(data)
        response = self.session.patch(url, data=data, verify=self.verify_ssl)
        return response


    def delete(self, endpoint):
        url = self.base_url + endpoint
        response = self.session.delete(url, verify=self.verify_ssl)
        return response
