#!/usr/bin/env bash
# One-time: validate GH_PAT, create crimescope repo, enable Pages. Token from env only.
set -euo pipefail
[ -n "${GH_PAT:-}" ] || { echo "GH_PAT missing"; exit 1; }

AUTH=(-H "Authorization: Bearer $GH_PAT" -H "Accept: application/vnd.github+json")

LOGIN=$(curl -s "${AUTH[@]}" https://api.github.com/user | python3 -c "import json,sys;print(json.load(sys.stdin).get('login',''))")
echo "token user: ${LOGIN:-FAILED}"
[ -n "$LOGIN" ] || exit 1

CODE=$(curl -s -o /tmp/gh_repo.json -w "%{http_code}" "${AUTH[@]}" \
  -X POST "https://api.github.com/user/repos" \
  -d '{"name":"crimescope","description":"Street-level police crime + outcome dashboard (Orpington/Bromley)","public":true,"has_issues":false,"has_wiki":false}')
if [ "$CODE" = "201" ]; then echo "repo created"; else
  echo "repo create code=$CODE msg=$(sed -n 's/.*"message":"\([^"]*\)".*/\1/p' /tmp/gh_repo.json | head -1)"
fi

PCODE=$(curl -s -o /tmp/gh_pages.json -w "%{http_code}" "${AUTH[@]}" \
  -X POST "https://api.github.com/repos/$LOGIN/crimescope/pages" \
  -d '{"source":{"branch":"main","root":"/"}}')
echo "pages setup code=$PCODE"
echo "LOGIN=$LOGIN"
