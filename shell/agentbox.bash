# agentbox bash integration: PATH, completion, git guard.
# Add to ~/.bashrc:   source ~/.agentbox/shell/agentbox.bash
# Folders: override with environment variables, e.g. export AB_PROJECTS=~/code

__ab_pkg=$(builtin cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)
case ":$PATH:" in *":$__ab_pkg/bin:"*) ;; *) PATH=$__ab_pkg/bin:$PATH ;; esac
for __ab_tex in /usr/local/texlive/*/bin/x86_64-linux; do :; done   # newest year (glob sorts)
[[ -d $__ab_tex ]] && case ":$PATH:" in *":$__ab_tex:"*) ;; *) PATH=$PATH:$__ab_tex ;; esac
unset __ab_tex

__ab_projects() { "$__ab_pkg/bin/agentbox" __projects 2>/dev/null; }   # any depth, see lib/projects.py

# --- completion -------------------------------------------------------------
_agentbox() {
  local cur=${COMP_WORDS[COMP_CWORD]} prev=${COMP_WORDS[COMP_CWORD-1]}
  case $prev in
    --runtime) mapfile -t COMPREPLY < <(compgen -W 'runsc crun' -- "$cur"); return ;;
    --ro)      mapfile -t COMPREPLY < <(compgen -d -- "$cur"); return ;;
    --mem|--cpus) return ;;
  esac
  if [[ $cur == -* ]]; then
    mapfile -t COMPREPLY < <(compgen -W '--runtime --mem --cpus --ro --offline --no-update' -- "$cur"); return
  fi
  case $COMP_CWORD in
    1) mapfile -t COMPREPLY < <(compgen -W "$(__ab_projects) list down-all" -- "$cur") ;;
    2) mapfile -t COMPREPLY < <(compgen -W 'claude codex agy copilot shell up down restart status blocked fetch sync' -- "$cur") ;;
    3) [[ $prev == shell ]] && mapfile -t COMPREPLY < <(compgen -W 'dev claude codex agy copilot' -- "$cur") ;;
  esac
}
complete -F _agentbox agentbox
_agentbox_project() { [[ $COMP_CWORD == 1 ]] && mapfile -t COMPREPLY < <(compgen -W "$(__ab_projects)" -- "${COMP_WORDS[1]}"); }
complete -F _agentbox_project agentbox-up agentbox-down agentbox-new-worktree

# --- guard: no host git inside agent copies ---------------------------------
# Your prompt (and any tool you start here) runs `git status` in the current
# folder. In the agent copies an agent may have planted config that makes git run
# commands as YOU. Pointing GIT_DIR nowhere makes every git call there fail harmlessly.
__agentbox_git_guard() {
  local agents=${AB_AGENTS:-$HOME/.agents-projects}
  if [[ $PWD == "$agents" || $PWD == "$agents"/* ]]; then
    if [[ ${GIT_DIR-} != /nonexistent/agentbox-guard ]]; then
      export GIT_DIR=/nonexistent/agentbox-guard
      echo "agentbox: git is disabled in agent copies. Use: agentbox <project> fetch" >&2
    fi
  elif [[ ${GIT_DIR-} == /nonexistent/agentbox-guard ]]; then
    unset GIT_DIR
  fi
}
# Run on every directory change (also inside one-liners) and before each prompt.
cd()    { builtin cd "$@"    && __agentbox_git_guard; }
pushd() { builtin pushd "$@" && __agentbox_git_guard; }
popd()  { builtin popd "$@"  && __agentbox_git_guard; }
if [[ ${PROMPT_COMMAND-} != *__agentbox_git_guard* ]]; then
  PROMPT_COMMAND="__agentbox_git_guard${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
fi
__agentbox_git_guard
