
class SMCFish:
    """
    Supermicro Redfish implementation.
    """
    def __init__(self, fishapi: str):
        self.api = fishapi

    
    def get_boot_order(self) -> list:
        response = self.api.get('/redfish/v1/Systems/1')
        if response.status_code == 200:
            data = response.json()
            boot_order = data.get('Boot', {}).get('BootOrder', [])
            if not boot_order:
                raise ValueError("BootOrder not found in response")
            return boot_order
        else:
            raise ValueError(f'Failed to retrieve boot order, status code: {response.status_code}')
        
    
    def get_boot_options(self) -> list:
        response = self.api.get('/redfish/v1/Systems/1/BootOptions')
        if response.status_code == 200:
            data = response.json()
            members = data.get('Members', [])
            boot_options = []
            for member in members:
                option_response = self.api.get(member['@odata.id'])
                if option_response.status_code == 200:
                    option_data = option_response.json()
                    boot_options.append(option_data)
            return boot_options
        else:
            raise ValueError(f'Failed to retrieve boot options, status code: {response.status_code}')