"""Local review against a running API/worker; removes only its disposable data.

Run from backend. --provider-failure submits ONE generation to check failure
handling; use only when the configured provider is known to be unavailable.
Without that flag, no provider generation is requested with retrieved evidence.
Keep semantic search disabled for this offline review.
"""

import argparse
import json
import secrets
import statistics
import time
from uuid import uuid4

import httpx
import psycopg2
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-failure", action="store_true")
    args = parser.parse_args()
    config = dotenv_values(".env")
    assert config.get("SUPPORT_EMBEDDINGS_ENABLED", "false").lower() != "true"
    email = f"review-{uuid4()}@example.com"
    password = secrets.token_urlsafe(30)
    checks = []
    wid = None
    client = httpx.Client(base_url="http://127.0.0.1:8000/api/v1", timeout=25)

    def check(name, condition, **details):
        checks.append({"check": name, "passed": bool(condition), **details})
        print(json.dumps(checks[-1]), flush=True)

    def request(method, path, expected=200, **kwargs):
        response = client.request(method, path, **kwargs)
        assert response.status_code == expected, (
            f"{method} {path}: {response.status_code} expected {expected}"
        )
        # Pace subsequent review steps; separately probe immediate signup/login below.
        if method != "GET" and path != "/auth/register":
            time.sleep(0.1)
        return response.json()

    def wait_for(path, item_id, states):
        started = time.monotonic()
        while time.monotonic() - started < 90:
            item = next(x for x in request("GET", path) if x["id"] == item_id)
            if item["state"] in states:
                return item, round(time.monotonic() - started, 2)
            time.sleep(0.5)
        raise AssertionError("Worker did not finish within 90 seconds")

    try:
        timings = []
        for _ in range(10):
            start = time.perf_counter()
            request("GET", "/health/ready")
            timings.append((time.perf_counter() - start) * 1000)
        check(
            "readiness",
            True,
            median_ms=round(statistics.median(timings), 1),
            max_ms=round(max(timings), 1),
        )
        request("GET", "/workspaces", expected=401)
        check("unauthenticated workspace denied", True)
        request(
            "POST",
            "/auth/register",
            expected=201,
            json={"email": email, "password": password, "full_name": "Disposable Review"},
        )
        login = client.post("/auth/login", data={"username": email, "password": password})
        check(
            "immediate login after successful signup",
            login.status_code == 200,
            status=login.status_code,
        )
        if login.status_code == 401:
            time.sleep(0.2)
            login = client.post("/auth/login", data={"username": email, "password": password})
            check("login after commit delay", login.status_code == 200, status=login.status_code)
        assert login.status_code == 200
        token = login.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        workspace = request("POST", "/workspaces", expected=201, json={"name": "Disposable review"})
        wid = workspace["id"]
        base = f"/workspaces/{wid}"
        request("POST", base + "/support/cases", expected=422, json={"question": ""})
        check("empty case rejected", True)
        for name, content, expected in [
            ("bad.exe", b"abc", 422),
            ("empty.txt", b"", 422),
            ("bad.pdf", b"not pdf", 422),
            ("binary.txt", b"\x00abc", 422),
            ("encoding.txt", b"\xff\xfe", 422),
            ("large.txt", b"x" * (10 * 1024 * 1024 + 1), 413),
        ]:
            request("POST", base + "/knowledge", expected=expected, files={"file": (name, content)})
            check(f"reject {name}", True, status=expected)
        malformed = request(
            "POST",
            base + "/knowledge",
            expected=202,
            files={"file": ("broken.pdf", b"%PDF-1.7\nbroken")},
        )
        failed, duration = wait_for(base + "/knowledge", malformed["id"], {"failed", "ready"})
        check(
            "malformed PDF worker failure",
            failed["state"] == "failed",
            seconds=duration,
            error=failed["error"],
        )
        request("POST", base + f"/knowledge/{malformed['id']}/retry", expected=202)
        failed, _ = wait_for(base + "/knowledge", malformed["id"], {"failed", "ready"})
        check("failed document retry terminates safely", failed["state"] == "failed")
        case = request(
            "POST",
            base + "/support/cases",
            expected=201,
            json={"question": "What are your spaceship warranty terms?"},
        )
        generation = base + f"/support/cases/{case['id']}/generations"
        key = {"request_key": str(uuid4())}
        job = request("POST", generation, expected=202, json=key)
        repeated = request("POST", generation, expected=202, json=key)
        check("generation request deduplicated", job["id"] == repeated["id"])
        done, duration = wait_for(base + "/jobs", job["id"], {"completed", "failed"})
        drafts = request("GET", base + f"/support/cases/{case['id']}")["drafts"]
        check(
            "no evidence safe fallback without AI call",
            done["state"] == "completed"
            and len(drafts) == 1
            and drafts[0]["outcome"] == "insufficient_evidence",
            seconds=duration,
        )
        draft = drafts[0]
        dp = base + f"/support/drafts/{draft['id']}"
        request("POST", dp + "/copied", expected=422, json={"version": 1})
        request("POST", dp + "/approve", json={"version": 1})
        request("POST", dp + "/copied", json={"version": 1})
        request("POST", dp + "/feedback", json={"feedback": "Requires a human response"})
        edit = request(
            "PATCH",
            dp,
            json={"version": 1, "reply": "A support employee will review your request."},
        )
        request("PATCH", dp, expected=409, json={"version": 1, "reply": "Stale edit"})
        check(
            "review copy feedback edit and conflict",
            edit["version"] == 2 and edit["approved_by"] is None,
        )
        content = b"Refund requests are accepted within fourteen days of purchase. Contact support with your order number."
        doc = request(
            "POST", base + "/knowledge", expected=202, files={"file": ("refunds.txt", content)}
        )
        ready, duration = wait_for(base + "/knowledge", doc["id"], {"ready", "failed"})
        check("TXT ingestion", ready["state"] == "ready", seconds=duration)
        evidence = request("GET", base + "/knowledge/search", params={"q": "refund policy"})
        source = evidence["sources"][0]
        check("literal retrieval", source["document_id"] == doc["id"], mode=evidence["mode"])
        semantic = request(
            "GET", base + "/knowledge/search", params={"q": "Can I get my money back?"}
        )
        check(
            "paraphrased refund question retrieves evidence",
            any(s["document_id"] == doc["id"] for s in semantic["sources"]),
            source_count=len(semantic["sources"]),
        )
        if args.provider_failure:
            case = request(
                "POST",
                base + "/support/cases",
                expected=201,
                json={"question": "What is your refund policy?"},
            )
            job = request(
                "POST",
                base + f"/support/cases/{case['id']}/generations",
                expected=202,
                json={"request_key": str(uuid4())},
            )
            done, duration = wait_for(base + "/jobs", job["id"], {"completed", "failed"})
            drafts = request("GET", base + f"/support/cases/{case['id']}")["drafts"]
            check(
                "provider outage produces failed job and no draft",
                done["state"] == "failed" and not drafts,
                seconds=duration,
                error=done["error"],
            )
        duplicate = request(
            "POST", base + "/knowledge", expected=202, files={"file": ("refunds.txt", content)}
        )
        wait_for(base + "/knowledge", duplicate["id"], {"ready", "failed"})
        check("duplicate upload deduplicated", duplicate["id"] == doc["id"])
        request("DELETE", base + f"/knowledge/{duplicate['id']}")
        replacement = request(
            "POST",
            base + "/knowledge",
            expected=202,
            params={"replaces": doc["id"]},
            files={
                "file": (
                    "refunds-v2.md",
                    b"Refund requests are accepted within thirty days of purchase.",
                )
            },
        )
        ready, _ = wait_for(base + "/knowledge", replacement["id"], {"ready", "failed"})
        old = next(d for d in request("GET", base + "/knowledge") if d["id"] == doc["id"])
        request("GET", base + f"/knowledge/chunks/{source['id']}", expected=410)
        evidence = request("GET", base + "/knowledge/search", params={"q": "refund"})
        check(
            "replacement archives old evidence",
            ready["state"] == "ready"
            and old["state"] == "archived"
            and all(s["document_id"] != doc["id"] for s in evidence["sources"]),
        )
        request("DELETE", base + f"/knowledge/{replacement['id']}")
        check(
            "deleted document excluded from search",
            not request("GET", base + "/knowledge/search", params={"q": "refund"})["sources"],
        )
        request("DELETE", base, expected=422, json={"name": "wrong name"})
        request("DELETE", base, json={"name": "Disposable review"})
        request("GET", base + "/knowledge", expected=404)
        check("workspace deletion confirmation and access", True)
    finally:
        client.close()
        with (
            psycopg2.connect(
                host=config["POSTGRES_HOST"],
                port=config["POSTGRES_PORT"],
                user=config["POSTGRES_USER"],
                password=config["POSTGRES_PASSWORD"],
                dbname=config["POSTGRES_DB"],
            ) as conn,
            conn.cursor() as cursor,
        ):
            if wid:
                cursor.execute(
                    "DELETE FROM support_workspaces WHERE id=%s AND id IN (SELECT workspace_id FROM support_memberships WHERE user_id IN (SELECT id FROM users WHERE email=%s))",
                    (wid, email),
                )
            cursor.execute("DELETE FROM users WHERE email=%s", (email,))
        print(
            json.dumps(
                {
                    "cleanup": "completed",
                    "checks": len(checks),
                    "passed": sum(c["passed"] for c in checks),
                    "findings": [c["check"] for c in checks if not c["passed"]],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
