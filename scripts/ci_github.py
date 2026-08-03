#!/usr/bin/env python3
"""CI에서 쓰는 최소한의 GitHub·git 도우미.

왜 별도 파일인가 (2026-08-03):
워크플로 YAML 안에 로직을 적으면 **그 로직을 고칠 때마다 워크플로 파일이 바뀐다.**
그런데 Actions의 기본 토큰은 `.github/workflows/` 아래를 수정할 수 없어서, 그 변경은
자동으로 배포되지 않는다 — 쓰는 사람마다 손으로 복사해야 한다.

그래서 워크플로는 **얇은 껍데기**로 두고 로직을 여기(scripts/)로 내린다. scripts/는
자유롭게 동기화되므로, 앞으로 고치는 것들은 전부 자동으로 퍼진다. 워크플로 파일은
일정·권한이 바뀔 때만 손대면 되고, 그런 일은 드물다.

의존성 없음 — 표준 라이브러리만 쓴다(러너에 pip install이 필요 없다).
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


def repo_slug():
    return os.environ.get("GITHUB_REPOSITORY", "")


def token():
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""


def api(method, path, payload=None):
    """GitHub REST 호출. 실패는 그대로 올린다 — 조용히 넘기면 알림이 사라진다."""
    url = f"{API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "socralearner-ci",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    return json.loads(body) if body else {}


def create_issue(title, body):
    """알림용 Issue. 실패해도 작업 자체를 죽이지는 않는다(알림이 본체가 아니다)."""
    try:
        issue = api("POST", f"/repos/{repo_slug()}/issues",
                    {"title": title, "body": body[:60000]})
        print(f"Issue #{issue.get('number')} 생성")
        return issue
    except urllib.error.HTTPError as e:
        print(f"⚠️  Issue 생성 실패 ({e.code}) — 작업은 계속한다", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  Issue 생성 실패: {e} — 작업은 계속한다", file=sys.stderr)
    return None


def run(*args, check=True, capture=False):
    """git 등 외부 명령. 무엇을 돌렸는지 로그에 남긴다."""
    print("$ " + " ".join(args))
    r = subprocess.run(args, check=check, text=True,
                       capture_output=capture)
    return (r.stdout or "").strip() if capture else ""


def git_identity():
    run("git", "config", "user.name", "socralearner[bot]")
    run("git", "config", "user.email", "noreply@github.com")


def has_changes(*paths):
    out = subprocess.run(["git", "status", "--porcelain", *paths],
                         text=True, capture_output=True).stdout.strip()
    return bool(out)


def commit_and_push(message, paths=("-A",), branch=None, attempts=4):
    """커밋 후 푸시. 같은 시각에 다른 워크플로가 밀었을 수 있어 재시도한다."""
    branch = branch or os.environ.get("GITHUB_REF_NAME", "main")
    git_identity()
    run("git", "add", *paths)
    run("git", "commit", "-m", message)
    for i in range(attempts):
        try:
            run("git", "pull", "--rebase", "origin", branch)
            run("git", "push", "origin", f"HEAD:{branch}")
            return True
        except subprocess.CalledProcessError:
            if i == attempts - 1:
                raise
            import time
            time.sleep(2 ** (i + 1))
    return False
