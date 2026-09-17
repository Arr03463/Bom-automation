import os
import requests
from dotenv import load_dotenv

load_dotenv()


class NexarClient:
    def __init__(self):
        self.client_id = os.getenv("NEXAR_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("NEXAR_CLIENT_SECRET", "").strip()
        self.token_url = os.getenv("NEXAR_TOKEN_URL", "https://identity.nexar.com/connect/token").strip()
        self.graphql_url = os.getenv("NEXAR_GRAPHQL_URL", "https://api.nexar.com/graphql").strip()
        self.access_token = None

    def validate_config(self):
        missing = []
        if not self.client_id:
            missing.append("NEXAR_CLIENT_ID")
        if not self.client_secret:
            missing.append("NEXAR_CLIENT_SECRET")
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

    def get_access_token(self):
        self.validate_config()

        response = requests.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        token = data.get("access_token")
        if not token:
            raise ValueError("No access token returned from Nexar.")

        self.access_token = token
        return token

    def run_query(self, query, variables=None):
        if not self.access_token:
            self.get_access_token()

        response = requests.post(
            self.graphql_url,
            json={
                "query": query,
                "variables": variables or {},
            },
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        if "errors" in data:
            raise ValueError(f"Nexar GraphQL error: {data['errors']}")

        return data

    def search_part_by_mpn(self, mpn):
        query = """
        query SearchPart($q: String!) {
          supSearchMpn(q: $q) {
            hits
            results {
              part {
                mpn
                manufacturer {
                  name
                }
                sellers {
                  company {
                    name
                  }
                  offers {
                    inventoryLevel
                    prices {
                      quantity
                      price
                      currency
                    }
                  }
                }
              }
            }
          }
        }
        """
        return self.run_query(query, {"q": mpn})