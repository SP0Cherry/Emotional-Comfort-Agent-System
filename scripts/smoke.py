"""Exercise a running development API and its independent Worker; no cloud calls."""
import argparse
import time
from secrets import randbelow
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        def call(method, path, body=None):
            response = client.request(method, "/v1" + path, json=body)
            response.raise_for_status()
            return response.json() if response.content else None

        health = call("GET", "/health/live")
        if health["provider_mode"] != "mock":
            raise SystemExit("Smoke requires PROVIDER_MODE=mock to avoid paid cloud requests.")
        phone = "+86199" + f"{randbelow(100_000_000):08d}"
        challenge = call("POST", "/auth/otp/request", {"phone": phone})
        tokens = call("POST", "/auth/otp/verify", {
            "phone": phone, "challenge_id": challenge["challenge_id"], "code": challenge["development_code"],
        })
        client.headers["Authorization"] = "Bearer " + tokens["access_token"]
        persona = call("POST", "/personas", {"display_name": "烟测 AI 陪伴", "style": {"address_user": "您"}})
        chat = call("POST", "/conversations", {"persona_id": persona["id"]})
        run = call("POST", f"/conversations/{chat['id']}/runs", {
            "client_message_id": str(uuid4()), "text": "我喜欢喝龙井茶。",
        })

        def wait_for(fetch, finished, label):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                value = fetch()
                if finished(value):
                    print(f"PASS {label}")
                    return value
                time.sleep(0.3)
            raise RuntimeError(f"Timed out: {label}")

        snapshot = wait_for(lambda: call("GET", f"/runs/{run['run_id']}"),
                            lambda value: value["status"] in {"completed", "failed", "interrupted", "cancelled"},
                            "API to independent Worker")
        assert snapshot["status"] == "completed", snapshot.get("error_code")
        memory_list = wait_for(lambda: call("GET", f"/memories?persona_id={persona['id']}"),
                               lambda value: bool(value["items"]), "candidate extraction")
        memory = memory_list["items"][0]
        call("POST", f"/memories/{memory['id']}/confirm", {"revision": memory["revision"]})
        wait_for(lambda: call("GET", f"/memories?persona_id={persona['id']}&status=active"),
                 lambda value: bool(value["items"]), "confirmed memory embedding")
        exported = call("GET", f"/personas/{persona['id']}/export")
        assert exported
        print("PASS private JSON export")
        reset = call("POST", f"/personas/{persona['id']}/reset-context", {"confirm": True})
        operation = reset.get("operation_id", reset.get("job_id"))
        result = wait_for(lambda: call("GET", f"/operations/{operation}"),
                          lambda value: value.get("status", value.get("state")) in {"completed", "failed"},
                          "context purge")
        assert result.get("status", result.get("state")) == "completed", result.get("error_code")
        history = call("GET", f"/conversations?persona_id={persona['id']}")
        assert not history["items"]
        call("POST", "/auth/logout", {"refresh_token": tokens["refresh_token"]})
        print("PASS clean history and logout")


if __name__ == "__main__":
    main()
