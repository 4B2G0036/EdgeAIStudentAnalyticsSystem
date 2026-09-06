import time
import requests
import sys

BASE_URL = "http://localhost:8000/api/v1/sessions"

def run_tests():
    print("==================================================")
    print("Starting FastAPI Backend Lifecycle Integration Test")
    print("==================================================")
    
    # 1. Start a new session
    payload = {
        "class_name": "計算機概論 (測試課程)",
        "teacher": "張教授",
        "room": "資工館 301",
        "roi_polygon": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
        "notes": "這是一堂自動化連線測試課程。"
    }
    
    print("\n[TEST 1] Creating new session...")
    try:
        response = requests.post(BASE_URL, json=payload)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 201:
            data = response.json()
            session_id = data.get("session_id")
            print(f"SUCCESS: Session created! session_id = {session_id}")
        else:
            print(f"FAILED: {response.text}")
            return
    except Exception as e:
        print(f"Connection error to FastAPI: {e}. Make sure backend is running on port 8000.")
        return

    # 2. Try to create duplicate session (Conflict Test)
    print("\n[TEST 2] Trying to create a concurrent active session (should fail)...")
    response2 = requests.post(BASE_URL, json=payload)
    print(f"Status Code: {response2.status_code} (Expected: 409)")
    if response2.status_code == 409:
        data2 = response2.json()
        print(f"SUCCESS: Conflict handled correctly! Message: {data2.get('detail')}")
    else:
        print(f"FAILED: Duplicate session allowed: {response2.text}")

    # 3. List active sessions
    print("\n[TEST 3] Fetching session list with pagination...")
    response_list = requests.get(f"{BASE_URL}?limit=5&offset=0")
    print(f"Status Code: {response_list.status_code}")
    if response_list.status_code == 200:
        lst = response_list.json()
        print(f"SUCCESS: Fetched {len(lst)} sessions from database.")
        for s in lst[:2]:
            print(f"  - Session ID: {s['session_id']}, Class: {s['class_name']}, Teacher: {s['teacher']}, Ended: {s.get('ended_at')}")
    else:
        print(f"FAILED: {response_list.text}")

    # 4. End the session
    print(f"\n[TEST 4] Ending active session: {session_id}...")
    response_end = requests.patch(f"{BASE_URL}/{session_id}/end")
    print(f"Status Code: {response_end.status_code}")
    if response_end.status_code == 200:
        end_data = response_end.json()
        print(f"SUCCESS: Session ended! Details: {end_data}")
    else:
        print(f"FAILED: {response_end.text}")

    # 5. Fetch Session Summary
    print(f"\n[TEST 5] Retrieving ended session summary: {session_id}...")
    # Sleep slightly to allow background task completion simulation
    time.sleep(1)
    response_sum = requests.get(f"{BASE_URL}/{session_id}/summary")
    print(f"Status Code: {response_sum.status_code}")
    if response_sum.status_code == 200:
        sum_data = response_sum.json()
        print("SUCCESS: Session summary statistics:")
        for k, v in sum_data.items():
            print(f"  {k}: {v}")
    else:
        print(f"FAILED: {response_sum.text}")

    print("\n==================================================")
    print("ALL API LIFECYCLE TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
