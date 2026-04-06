#!/usr/bin/env bash
# Run from repo root: cd /mnt/c/Users/bradj/Development/PeaRL && ./launch-worktrees.sh
# Tmux navigation: Ctrl+B + arrow keys to switch panes | Ctrl+B q to jump by number
# When agents finish: check sprint-progress.md, then merge PRs in order from main session
# Do NOT direct-merge from worktree panes — coordinate from the main session
# Dark Factory Sprint — 2026-04-06
# Launches 2 parallel agents: agent-registry, trust-verdict

SESSION="worktrees"
ROOT="$(pwd)"

# Kill existing session if running
tmux kill-session -t "$SESSION" 2>/dev/null

# Pane 0 (left): agent-registry — M task (AgentRow, /agents CRUD, MCP tool)
tmux new-session -d -s "$SESSION" -c "$ROOT/.claude/worktrees/agent-registry"
tmux send-keys -t "$SESSION" "claude" Enter

# Pane 1 (right): trust-verdict — L task (MASS 2.0 trust review pipeline)
tmux split-window -h -t "$SESSION" -c "$ROOT/.claude/worktrees/trust-verdict"
tmux send-keys -t "$SESSION" "claude" Enter

tmux attach -t "$SESSION"
