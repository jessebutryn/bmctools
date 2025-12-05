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
            'Accept': 'application/json',
            'OData-Version': '4.0'
        })
        self.verify_ssl = verify_ssl

        if not self.verify_ssl:
            self.disable_ssl_verification()
        
        # Try to establish a Redfish session
        self._establish_session()


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


    def patch(self, endpoint, data=None, headers=None):
        url = self.base_url + endpoint
        if data:
            data = json.dumps(data)
        response = self.session.patch(url, data=data, headers=headers, verify=self.verify_ssl)
        return response


    def delete(self, endpoint):
        url = self.base_url + endpoint
        response = self.session.delete(url, verify=self.verify_ssl)
        return response


    def _establish_session(self):
        """Attempt to create a Redfish session if supported."""
        try:
            # Try session-based authentication
            session_url = f"{self.base_url}/redfish/v1/SessionService/Sessions"
            payload = {
                "UserName": self.user,
                "Password": self.password
            }
            response = self.session.post(
                session_url,
                json=payload,
                verify=self.verify_ssl,
                timeout=10
            )
            
            if response.status_code == 201:
                # Session created successfully
                auth_token = response.headers.get('X-Auth-Token')
                if auth_token:
                    self.session.headers.update({'X-Auth-Token': auth_token})
                    # Remove basic auth since we have a token
                    self.session.auth = None
        except Exception:
            # If session creation fails, fall back to basic auth
            pass
