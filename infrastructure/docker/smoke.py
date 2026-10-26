"""A round trip through the running lab, run INSIDE the built image by ci.yml and publish-images.yml:

    docker exec -i <container> python - < infrastructure/docker/smoke.py

It proves what the unit tests (which read the repository's folders, not the image's) cannot: that the image holds the
pane and the four sample files where the lab looks for them, and that an upload goes through from start to finish in
the hardened, read-only container: sample, upload, read, report file, owner isolation, delete. The exit status is 0 only
if all of it holds. It prints names and statuses, never content. The container must run with CC_ALLOW_NO_TURNSTILE=1,
because a CI container holds no verification secret.
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
SAMPLES = (
    "sample-resource-graph.json",
    "decision-starter.json",
    "decision-zone-redundancy.json",
    "decision-wave-one.json",
)


def call(method, path, body=None, token=None):
    headers = {"x-owner-token": token} if token else {}
    data = None
    if body is not None:
        data, headers["content-type"] = json.dumps(body).encode(), "application/json"
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def check(label, ok):
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        sys.exit(1)


status, body = call("GET", "/api/health")
health = json.loads(body)
check("health answers with the upload capabilities", status == 200 and "upload-evidence" in health["capabilities"])
check("the pane is served", call("GET", "/")[0] == 200 and call("GET", "/app.js")[0] == 200)
for name in SAMPLES:
    check(f"sample {name} is served", call("GET", f"/api/samples/{name}")[0] == 200)
check("a file that is not a sample is not served", call("GET", "/api/samples/README.md")[0] == 404)

evidence, decision = (json.loads(call("GET", f"/api/samples/{name}")[1]) for name in SAMPLES[:1] + SAMPLES[2:3])
status, body = call(
    "POST", "/api/uploads", {"evidence": [{"kind": "arg-export", "content": evidence}], "decision": decision}
)
created = json.loads(body)
check("an upload is created (201)", status == 201)
check(
    "the engine's answer for the sample is the App's",
    created["summary"]["contradicted"] == 2 and created["summary"]["supported"] == 3,
)
upload, token = created["uploadId"], created["ownerToken"]
check("the owner reads it", call("GET", f"/api/uploads/{upload}", token=token)[0] == 200)
check("anyone else gets 404", call("GET", f"/api/uploads/{upload}", token="not-the-token")[0] == 404)
status, body = call("GET", f"/api/uploads/{upload}/files/NOT-AN-AUDIT.md", token=token)
check("the not-an-audit note is in the bundle", status == 200 and body.startswith(b"# Not an audit"))
check("the owner deletes it", call("DELETE", f"/api/uploads/{upload}", token=token)[0] == 200)
check("it is gone", call("GET", f"/api/uploads/{upload}", token=token)[0] == 404)
print("upload round trip ok")
