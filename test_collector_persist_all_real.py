import datetime
import os
from dotenv import load_dotenv

from collector import Collector, CollectorData
from rest_client import RestClient

load_dotenv()

def test_persist_all_to_real_api():
    # Real API endpoint config
    api_url = os.getenv("API_URL", "https://homegadget.co.th/api/homeminer/bitcoin/miner/monitor/event?_format=json")
    api_url = os.getenv("API_URL", "https://homegadget.co.th/api/homeminer/bitcoin/miner/monitor/event?_format=json")
    api_key = os.getenv("API_KEY", "c2l0dGljaG9rZWtyb25nYm9vbjpqITddUS1RZDlNfkNIRng=")
    api_path = os.getenv("API_PATH", "")  # keep empty if included in full URL

    # Create real RestClient (NO mocking)
    rest = RestClient(
        base_url=api_url,
        api_key=api_key,
        timeout=5,
    )

    # Collector with real REST client, no DB
    collector = Collector(db=None, rest_client=rest, rest_path=api_path)

    # Mock collector data
    mock_data = [
        CollectorData(
            collected_at=datetime.datetime.utcnow(),
            ip=f"192.168.1.{i}",
            model=f"PyMockMiner-{i}",
            hashrate_avg=12000.5,
            temperature=65.5,
            worker_name=f"test.worker{i}",
            pool="stratum+tcp://mock.pool:3333",
            owner_name="integration-tester",
            is_online=True
        )
        for i in range(2)  # Create 2 fake miners
    ]

    # Perform the actual API call
    collector._persist_all(mock_data)

    print("✅ test_persist_all_to_real_api: success")
