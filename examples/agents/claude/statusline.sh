#!/bin/sh
# Copy this folder to ~/.agents-context/agents/claude/: every new project gets the status
# line. Claude Code passes the session as JSON on stdin; show model, folder and project.
input=$(cat)
model=$(printf '%s' "$input" | sed -n 's/.*"display_name" *: *"\([^"]*\)".*/\1/p')
dir=$(printf '%s' "$input" | sed -n 's/.*"current_dir" *: *"\([^"]*\)".*/\1/p')
printf '%s | %s | %s' "${model:-claude}" "${dir##*/}" "${AGENTBOX_PROJECT:-}"
