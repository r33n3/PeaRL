#!/usr/bin/env bash
# Dark Factory Governance Sprint — 2026-03-31
# Launches 4 parallel agents for the dark factory governance layer
# Run from repo root: ./launch-worktrees.sh

SESSION="worktrees"
ROOT="$(pwd)"

# Kill existing session if running
tmux kill-session -t "$SESSION" 2>/dev/null

# Pane 0 (top-left): agent-allowance-profiles — FOUNDATION (P1)
tmux new-session -d -s "$SESSION" -c "$ROOT/.claude/worktrees/agent-allowance-profiles"
tmux send-keys -t "$SESSION" "claude" Enter

# Pane 1 (top-right): task-execution-phase (P2)
tmux split-window -h -t "$SESSION" -c "$ROOT/.claude/worktrees/task-execution-phase"
tmux send-keys -t "$SESSION" "claude" Enter

# Pane 2 (bottom-left): trust-gates (P3 + P5)
tmux select-pane -t "$SESSION:0.0"
tmux split-window -v -t "$SESSION" -c "$ROOT/.claude/worktrees/trust-gates"
tmux send-keys -t "$SESSION" "claude" Enter

# Pane 3 (bottom-right): workload-registry (P4)
tmux select-pane -t "$SESSION:0.1"
tmux split-window -v -t "$SESSION" -c "$ROOT/.claude/worktrees/workload-registry"
tmux send-keys -t "$SESSION" "claude" Enter

# Focus top-left (foundation task)
tmux select-pane -t "$SESSION:0.0"
tmux attach -t "$SESSION"
