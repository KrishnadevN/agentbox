# agentbox zsh integration: PATH, completion, git guard.
# Add to ~/.zshrc (after compinit):   source ~/.agentbox/shell/agentbox.zsh
# Folders: override with environment variables, e.g. export AB_PROJECTS=~/code

__ab_pkg=${${(%):-%x}:A:h:h}
path=("$__ab_pkg/bin" ${path:#$__ab_pkg/bin})
() { local t=( /usr/local/texlive/*/bin/x86_64-linux(N/On) ); (( $#t )) && path+=("$t[1]") }
typeset -U path

__ab_projects() { "$__ab_pkg/bin/agentbox" __projects 2>/dev/null }   # any depth, see lib/projects.py

# --- completion -------------------------------------------------------------
_agentbox() {
  case $words[CURRENT-1] in
    --runtime) compadd runsc crun; return ;;
    --ro) _files -/; return ;;
    --mem|--cpus) return ;;
  esac
  if [[ $PREFIX == -* ]]; then compadd -- --runtime --mem --cpus --ro --offline --no-update; return; fi
  case $CURRENT in
    2) compadd -- $(__ab_projects) list down-all ;;
    3) compadd -- claude codex agy copilot shell up down restart status blocked fetch sync ;;
    4) [[ $words[3] == shell ]] && compadd -- dev claude codex agy copilot ;;
  esac
}
_agentbox_project() { (( CURRENT == 2 )) && compadd -- $(__ab_projects) }
if (( $+functions[compdef] )); then
  compdef _agentbox agentbox
  compdef _agentbox_project agentbox-up agentbox-down agentbox-new-worktree
fi

# --- guard: no host git inside agent copies ---------------------------------
# See agentbox.bash for the reason. chpwd runs on every directory change.
__agentbox_git_guard() {
  local agents=${AB_AGENTS:-$HOME/.agents-projects}
  if [[ $PWD == $agents || $PWD == $agents/* ]]; then
    if [[ ${GIT_DIR-} != /nonexistent/agentbox-guard ]]; then
      export GIT_DIR=/nonexistent/agentbox-guard
      print -u2 "agentbox: git is disabled in agent copies. Use: agentbox <project> fetch"
    fi
  elif [[ ${GIT_DIR-} == /nonexistent/agentbox-guard ]]; then
    unset GIT_DIR
  fi
}
autoload -Uz add-zsh-hook
add-zsh-hook chpwd __agentbox_git_guard
__agentbox_git_guard
