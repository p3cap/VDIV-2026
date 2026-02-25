import requests


class RoverLogger:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def send_setup(self, data: dict):
        return requests.post(f"{self.base_url}/send_setup", json=data)

    def send_live(self, data: dict):
        return requests.post(f"{self.base_url}/send_data", json=data)