import requests

# logger with basic try catch 
class RoverLogger:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def send_setup(self, data: dict):
        try:
            response = requests.post(f"{self.base_url}/send_setup", json=data, timeout=3)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Error sending setup data: {e}")
            return None

    def send_live(self, data: dict):
        try:
            response = requests.post(f"{self.base_url}/send_data", json=data, timeout=3)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Error sending live data: {e}")
            return None
    
    # habibbbi fasz
