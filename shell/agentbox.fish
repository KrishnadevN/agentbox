# agentbox fish integration. agentbox-prep.sh links this file to
# ~/.config/fish/conf.d/agentbox.fish
# Folders: override with universal variables, e.g. set -Ux AB_PROJECTS ~/code

set -l __ab_pkg (path dirname (path dirname (path resolve (status filename))))
fish_add_path -g $__ab_pkg/bin
set -q AB_PROJECTS; or set -g __ab_projects $HOME/Projects
set -q AB_PROJECTS; and set -g __ab_projects $AB_PROJECTS
set -q AB_AGENTS; or set -g __ab_agents $HOME/.agents-projects
set -q AB_AGENTS; and set -g __ab_agents $AB_AGENTS

# TeX Live from TUG (newest year), if installed. Pure host convenience.
set -l __ab_tex /usr/local/texlive/*/bin/x86_64-linux    # `set` tolerates no match
set -q __ab_tex[1]; and fish_add_path -g (path sort $__ab_tex)[-1]

function __agentbox_projects
    set -l d $__ab_projects/*/
    set -q d[1]; and path basename $d
end

# --- completion -------------------------------------------------------------
complete -c agentbox -f
complete -c agentbox -n 'test (count (commandline -opc)) -eq 1' -a '(__agentbox_projects) list down-all'
complete -c agentbox -n 'test (count (commandline -opc)) -eq 2' \
    -a 'claude codex agy copilot shell up down restart status blocked fetch sync'
complete -c agentbox -n 'test (count (commandline -opc)) -eq 3; and __fish_seen_subcommand_from shell' \
    -a 'dev claude codex agy copilot'
complete -c agentbox -l runtime -x -a 'runsc crun'
complete -c agentbox -l mem -x -d 'RAM cap, e.g. 32G'
complete -c agentbox -l cpus -x -d 'CPU threads'
complete -c agentbox -l ro -r -F -d 'extra read-only folder'
complete -c agentbox -l offline -d 'no network'
complete -c agentbox -l no-update -d 'skip agent CLI update'
for c in agentbox-up agentbox-down agentbox-new-worktree
    complete -c $c -f -n 'test (count (commandline -opc)) -eq 1' -a '(__agentbox_projects)'
end

# --- guard: no host git inside agent copies ---------------------------------
# Your prompt (and any tool you start here) runs `git status` in the current
# folder. In the agent copies (~/.agents-projects) an agent may have planted config that makes git
# run commands as YOU. Pointing GIT_DIR nowhere makes every git call there fail
# harmlessly ("not a git repository") - the prompt simply shows no git info.
function __agentbox_git_guard --on-variable PWD
    if string match -q -- "$__ab_agents*" $PWD
        if test "$GIT_DIR" != /nonexistent/agentbox-guard
            set -gx GIT_DIR /nonexistent/agentbox-guard
            echo "agentbox: git is disabled in agent copies. Use: agentbox <project> fetch" >&2
        end
    else if test "$GIT_DIR" = /nonexistent/agentbox-guard
        set -e GIT_DIR
    end
end
__agentbox_git_guard
