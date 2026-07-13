#!/usr/bin/env bash
# Publish a release card SVG to the `release-assets` branch and emit its raw URL.
#
# Usage: publish_card.sh <card-file> <tag>
# Writes `card-url=<raw url>` to $GITHUB_OUTPUT.
set -euo pipefail

CARD_FILE="$1"
TAG="$2"
SAFE_NAME="${TAG//\//-}"
WORKTREE="$(mktemp -d)/release-assets"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

for attempt in 1 2 3 4 5; do
  git fetch origin release-assets 2>/dev/null || true
  rm -rf "$WORKTREE"
  if git rev-parse --verify --quiet refs/remotes/origin/release-assets >/dev/null; then
    git worktree add --force "$WORKTREE" origin/release-assets
    git -C "$WORKTREE" checkout -B release-assets origin/release-assets
  else
    git worktree add --force --detach "$WORKTREE"
    git -C "$WORKTREE" checkout --orphan release-assets
    git -C "$WORKTREE" rm -rfq . 2>/dev/null || true
    printf '# Release assets\n\nGenerated release cards live here.\n' > "$WORKTREE/README.md"
  fi

  mkdir -p "$WORKTREE/cards"
  cp "$CARD_FILE" "$WORKTREE/cards/${SAFE_NAME}.svg"
  git -C "$WORKTREE" add -A
  git -C "$WORKTREE" commit -m "release card: ${TAG}" || true

  if git -C "$WORKTREE" push origin release-assets; then
    git worktree remove --force "$WORKTREE" || true
    echo "card-url=https://raw.githubusercontent.com/${GITHUB_REPOSITORY}/release-assets/cards/${SAFE_NAME}.svg" >> "$GITHUB_OUTPUT"
    exit 0
  fi

  git worktree remove --force "$WORKTREE" || true
  sleep $((attempt * 5))
done

echo "Failed to publish release card after retries" >&2
exit 1
