#!/usr/bin/env bash
# Auth Sprint — launch auth-backend-core + auth-frontend in parallel
# auth-oauth-identity launches AFTER auth-backend-core is merged to main
# Run from repo root: ./launch-worktrees.sh

SESSION="worktrees"
ROOT="$(pwd)"

# Kill existing session if running
tmux kill-session -t "$SESSION" 2>/dev/null

tmux new-session -d -s "$SESSION" -c "$ROOT/.claude/worktrees/auth-backend-core"
tmux send-keys -t "$SESSION" "claude" Enter

tmux split-window -h -t "$SESSION" -c "$ROOT/.claude/worktrees/auth-frontend"
tmux send-keys -t "$SESSION" "claude" Enter

tmux select-pane -t "$SESSION:0.0"
tmux attach -t "$SESSION"
