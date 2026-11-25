"""Invite a student to their project: GitHub repo (write) + Hugging Face organization (write).

Run by .github/workflows/invite-student.yml (manual "Run workflow" form). Usernames are
never printed to the log because this repository is public; the job summary shows only
the result of each step.

Secrets: GH_ADMIN_TOKEN (GitHub fine-grained token, Administration: read and write on the
student repositories) and HF_TOKEN (Hugging Face token of an organization admin).
"""
import json
import os
import sys
import tempfile

import requests

OWNER = "smalltee2"
HF_ORG = "smalltee2UPSEEN"
SPACE = "smalltee2/lab-monitor"
REPOS = {
    "msc1 (Heat exposure)": "msc1-heat-exposure-th",
    "msc2 (Compound extreme)": "msc2-compound-extreme-th",
    "msc3 (PM2.5 downscaling)": "msc3-pm25-downscaling-th",
}
results = []


def note(ok, text):
    results.append(("✅" if ok else "⚠️") + " " + text)


def invite_github(repo, user):
    r = requests.put(f"https://api.github.com/repos/{OWNER}/{repo}/collaborators/{user}",
                     headers={"Authorization": f"Bearer {os.environ['GH_ADMIN_TOKEN']}",
                              "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
                     json={"permission": "push"}, timeout=30)
    if r.status_code == 201:
        note(True, f"GitHub: invitation sent for `{repo}` (write). The student must accept it within 7 days.")
    elif r.status_code == 204:
        note(True, f"GitHub: already a collaborator on `{repo}`, nothing to do.")
    elif r.status_code == 404:
        note(False, f"GitHub: user not found, or the token cannot manage `{repo}` (HTTP 404). Check the spelling.")
    else:
        note(False, f"GitHub: HTTP {r.status_code}: {r.text[:200]}")


def invite_hf(user):
    url = f"https://huggingface.co/api/organizations/{HF_ORG}/members/{user}"
    r = requests.post(url, headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"},
                      json={"role": "write"}, timeout=30)
    if r.status_code in (200, 201, 204):
        note(True, f"Hugging Face: added or invited to `{HF_ORG}` with role write.")
    elif r.status_code == 409:
        note(True, f"Hugging Face: already a member of `{HF_ORG}`.")
    else:
        note(False, f"Hugging Face: automatic invite not accepted (HTTP {r.status_code}). Invite by hand at "
                    f"https://huggingface.co/organizations/{HF_ORG}/settings/members (role: write).")


def register(project_key, gh_user, hf_user):
    """Record the student's usernames in students.json in the private monitor Space."""
    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi(token=os.environ["HF_TOKEN"])
    try:
        data = json.loads(open(hf_hub_download(SPACE, "students.json", repo_type="space",
                                               token=os.environ["HF_TOKEN"])).read())
    except Exception:
        data = {}
    entry = data.get(project_key, {})
    if gh_user:
        entry["gh"] = gh_user
    if hf_user:
        entry["hf"] = hf_user
    entry.pop("name", None)  # let the dashboard take the name from the new profile
    data[project_key] = entry
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    try:
        api.upload_file(path_or_fileobj=fh.name, path_in_repo="students.json", repo_id=SPACE,
                        repo_type="space", commit_message=f"Register student for {project_key}")
        note(True, "Dashboard: student registered on the project card (shows after the next snapshot).")
    except Exception as e:
        note(False, f"Dashboard: could not save students.json ({type(e).__name__}).")


def main():
    project = os.environ["PROJECT"]
    gh_user = os.environ.get("GH_USER", "").strip().lstrip("@")
    hf_user = os.environ.get("HF_USER", "").strip().lstrip("@")
    repo = REPOS.get(project)
    if not repo:
        sys.exit(f"Unknown project: {project}")
    if gh_user and os.environ.get("GH_ADMIN_TOKEN"):
        invite_github(repo, gh_user)
    elif gh_user:
        note(False, "GitHub: secret GH_ADMIN_TOKEN is not set, so no GitHub invitation was sent.")
    if hf_user:
        invite_hf(hf_user)
    if not (gh_user or hf_user):
        note(False, "No username given.")
    else:
        register(project.split()[0], gh_user, hf_user)
    results.append(f"\nAlso add the student to the board by hand if needed: https://github.com/users/{OWNER}/projects/1/settings/access")
    summary = f"### Invite for {project}\n\n" + "\n".join(results) + "\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(summary)
    if any(r.startswith("⚠️") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
