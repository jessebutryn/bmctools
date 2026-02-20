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


    def post_file(self, endpoint, file_path, additional_data=None, file_field_name='file'):
        """Upload a file via multipart form data.

        Args:
            endpoint: The API endpoint
            file_path: Path to the file to upload
            additional_data: Optional dict of additional form fields
            file_field_name: Name of the file field in multipart form (default: 'file')

        Returns:
            Response object
        """
        url = self.base_url + endpoint

        # Temporarily remove Content-Type header for multipart upload
        original_content_type = self.session.headers.pop('Content-Type', None)

        try:
            with open(file_path, 'rb') as f:
                files = {file_field_name: f}
                data = additional_data or {}
                response = self.session.post(
                    url,
                    files=files,
                    data=data,
                    verify=self.verify_ssl
                )
        finally:
            # Restore Content-Type header
            if original_content_type:
                self.session.headers['Content-Type'] = original_content_type

        return response


    def post_multipart(self, endpoint, file_path, update_params, oem_params=None):
        """Upload firmware using Redfish multipart HTTP push format.

        All parts are sent as proper multipart file parts with correct content types.

        Args:
            endpoint: The API endpoint
            file_path: Path to the firmware file
            update_params: Dict of update parameters (sent as application/json)
            oem_params: Optional dict of OEM parameters (sent as application/json)

        Returns:
            Response object
        """
        import os
        url = self.base_url + endpoint
        filename = os.path.basename(file_path)

        # Temporarily remove Content-Type header for multipart upload
        original_content_type = self.session.headers.pop('Content-Type', None)

        try:
            with open(file_path, 'rb') as f:
                # Build multipart parts with proper content types
                files = [
                    ('UpdateParameters', ('UpdateParameters.json', json.dumps(update_params), 'application/json')),
                    ('UpdateFile', (filename, f, 'application/octet-stream')),
                ]
                if oem_params is not None:
                    files.insert(1, ('OemParameters', ('OemParameters.json', json.dumps(oem_params), 'application/json')))

                response = self.session.post(
                    url,
                    files=files,
                    verify=self.verify_ssl
                )
        finally:
            if original_content_type:
                self.session.headers['Content-Type'] = original_content_type

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
                    # Keep basic auth as fallback for endpoints that don't accept tokens
                    # Some BMCs (like Asus) require basic auth for file uploads
                    # self.session.auth = None  # Commented out to keep basic auth
        except Exception:
            # If session creation fails, fall back to basic auth
            pass
