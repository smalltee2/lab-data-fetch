#!/usr/bin/env bash
# One-time setup of the public GitHub repo smalltee2/lab-data-fetch.
# Run on the supervisor's Mac:  bash setup_github.sh
set -euo pipefail
cd "$(dirname "$0")"

# 1. put the workflow where GitHub Actions looks for it
mkdir -p .github/workflows
[ -f nexgddp-thailand.yml ] && mv nexgddp-thailand.yml .github/workflows/

# 2. create the PUBLIC repo (code only: no data, no tokens) and push
if [ ! -d .git ]; then
  git init -q -b main
  git add -A
  git commit -q -m "Add NEX-GDDP-CMIP6 Thailand fetch workflow"
fi
gh repo view smalltee2/lab-data-fetch >/dev/null 2>&1 || \
  gh repo create smalltee2/lab-data-fetch --public --source . --remote origin --push \
     --description "GitHub Actions jobs that download climate data, clip to Thailand, and upload to Hugging Face"

# 3. store the Hugging Face write token as an encrypted Actions secret (paste it when asked)
echo "Paste your Hugging Face WRITE token (hf_...) and press Enter:"
gh secret set HF_TOKEN -R smalltee2/lab-data-fetch

echo
echo "Done. Test with one model first:"
echo "  gh workflow run nexgddp-thailand.yml -R smalltee2/lab-data-fetch -f models=ACCESS-CM2"
echo "Watch it:  gh run watch -R smalltee2/lab-data-fetch"
