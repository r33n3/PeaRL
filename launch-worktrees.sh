#!/usr/bin/env bash
SESSION="worktrees"
tmux new-session -d -s "$SESSION" -c "$(pwd)/.claude/worktrees/enterprise-gaps"
tmux send-keys -t "$SESSION" "claude" Enter
tmux split-window -h -t "$SESSION" -c "$(pwd)/.claude/worktrees/security-audit"
tmux send-keys -t "$SESSION" "claude" Enter
tmux select-pane -t "$SESSION:0.0"
tmux split-window -v -t "$SESSION" -c "$(pwd)/.claude/worktrees/frontend-ux"
tmux send-keys -t "$SESSION" "claude" Enter
tmux select-pane -t "$SESSION:0.1"
tmux split-window -v -t "$SESSION" -c "$(pwd)/.claude/worktrees/full-audit"
tmux send-keys -t "$SESSION" "claude" Enter
tmux select-pane -t "$SESSION:0.0"
tmux attach -t "$SESSION"
