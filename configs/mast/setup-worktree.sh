#!/usr/bin/env bash
# Bootstrap git worktrees and the runs/output symlink for gem5-NTNU.
#
# Usage:
#   ./setup-worktree.sh link
#       Create or refresh runs/output -> ../../output in the current checkout.
#
#   ./setup-worktree.sh link-all
#       Run link in every registered git worktree.
#
#   ./setup-worktree.sh verify
#       Check that runs/output resolves to the global output directory.
#
#   ./setup-worktree.sh add <branch> [worktree-path]
#       Create a new worktree, check out <branch>, and create the symlink.
#       If worktree-path is omitted, a default name is derived from the branch.
#
#   ./setup-worktree.sh bootstrap
#       Link the main checkout and add standard implementation worktrees
#       that are not already present.
#
# Examples:
#   cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU
#   ./configs/mast/setup-worktree.sh link
#   ./configs/mast/setup-worktree.sh bootstrap
#
#   ./configs/mast/setup-worktree.sh add explicit-data-forwarding
#   ./configs/mast/setup-worktree.sh add n-use/InO

set -euo pipefail

# Relative to runs/ (the directory that contains the symlink).
LINK_TARGET="../../output"
LINK_PATH="runs/output"

# Implementation branches from configs/mast/PROJECT_BRANCHES.md
DEFAULT_BRANCHES=(
    sereno
    explicit-data-forwarding
    hybrid-wl
    n-use/OoO
    n-use/InO
)

default_worktree_path() {
    local branch="$1"
    local parent name slug

    parent="$(git rev-parse --show-toplevel)"
    parent="$(dirname "${parent}")"
    slug="${branch//\//-}"
    name="gem5-NTNU-${slug}"

    if [ "${slug}" = "infra" ]; then
        echo "${parent}/gem5-NTNU"
        return
    fi

    echo "${parent}/${name}"
}

main_root() {
    local git_common

    git_common="$(git rev-parse --git-common-dir)"
    if [ "${git_common}" = ".git" ]; then
        repo_root
        return
    fi

    dirname "${git_common}"
}

repo_root() {
    git rev-parse --show-toplevel
}

global_output_for() {
    local root="$1"
    readlink -f "${root}/../output"
}

ensure_runs_dir() {
    local root="$1"
    mkdir -p "${root}/runs"
}

warn_local_output_dir() {
    local root="$1"
    local stray="${root}/output"

    if [ -d "${stray}" ] && [ ! -L "${stray}" ]; then
        local expected
        expected="$(global_output_for "${root}")"
        if [ "$(readlink -f "${stray}")" != "${expected}" ]; then
            echo "warning: ${stray} exists inside the worktree." >&2
            echo "         a prior ../output symlink may have created it." >&2
            echo "         global output is ${expected}" >&2
        fi
    fi
}

link_output() {
    local root="$1"
    local global_output link

    root="$(readlink -f "${root}")"
    global_output="$(global_output_for "${root}")"
    link="${root}/${LINK_PATH}"

    ensure_runs_dir "${root}"
    warn_local_output_dir "${root}"

    if [ ! -d "${global_output}" ]; then
        echo "error: global output directory not found: ${global_output}" >&2
        echo "       expected a sibling of the worktree: <parent>/output/" >&2
        exit 1
    fi

    if [ -e "${link}" ] && [ ! -L "${link}" ]; then
        echo "error: ${link} exists and is not a symlink" >&2
        exit 1
    fi

    ln -sfn "${LINK_TARGET}" "${link}"

    echo "symlink: ${link} -> $(readlink "${link}")"
    echo "resolved: $(readlink -f "${link}")"
}

verify_output_link() {
    local root expected actual

    root="$(repo_root)"
    expected="$(global_output_for "${root}")"
    actual="$(readlink -f "${root}/${LINK_PATH}" 2>/dev/null || true)"

    if [ -z "${actual}" ]; then
        echo "error: ${root}/${LINK_PATH} does not exist" >&2
        exit 1
    fi

    if [ "${actual}" != "${expected}" ]; then
        echo "error: ${LINK_PATH} resolves to ${actual}" >&2
        echo "       expected ${expected}" >&2
        exit 1
    fi

    echo "ok: ${root}/${LINK_PATH} -> ${actual}"
}

link_all_worktrees() {
    local path

    while IFS= read -r path; do
        [ -n "${path}" ] || continue
        echo "==> ${path}"
        link_output "${path}"
        echo
    done < <(git worktree list --porcelain | awk '/^worktree / { print $2 }')
}

branch_has_worktree() {
    local branch="$1"
    local wt_branch

    while IFS= read -r wt_branch; do
        if [ "${wt_branch}" = "${branch}" ]; then
            return 0
        fi
    done < <(git worktree list --porcelain | awk '/^branch / { sub(/^branch /, ""); print }')

    return 1
}

add_worktree() {
    local branch="$1"
    local path="${2:-$(default_worktree_path "${branch}")}"
    local root parent

    root="$(main_root)"
    path="$(readlink -f -m "${path}")"
    parent="$(dirname "${path}")"

    if [ ! -d "${parent}" ]; then
        echo "error: parent directory does not exist: ${parent}" >&2
        exit 1
    fi

    if [ -e "${path}" ]; then
        echo "error: worktree path already exists: ${path}" >&2
        exit 1
    fi

    if branch_has_worktree "refs/heads/${branch}"; then
        echo "error: branch '${branch}' is already checked out in a worktree" >&2
        git worktree list
        exit 1
    fi

    if ! git -C "${root}" show-ref --verify --quiet "refs/heads/${branch}"; then
        echo "error: local branch not found: ${branch}" >&2
        exit 1
    fi

    echo "adding worktree:"
    echo "  branch: ${branch}"
    echo "  path:   ${path}"

    git -C "${root}" worktree add "${path}" "${branch}"
    link_output "${path}"
}

bootstrap_worktrees() {
    local branch path root

    root="$(main_root)"
    echo "main worktree: ${root}"
    link_output "${root}"
    echo

    for branch in "${DEFAULT_BRANCHES[@]}"; do
        path="$(default_worktree_path "${branch}")"

        if [ -d "${path}" ]; then
            echo "skip: ${path} already exists"
            link_output "${path}"
            echo
            continue
        fi

        if branch_has_worktree "refs/heads/${branch}"; then
            echo "skip: branch ${branch} already has a worktree"
            echo
            continue
        fi

        if ! git -C "${root}" show-ref --verify --quiet "refs/heads/${branch}"; then
            echo "skip: local branch not found: ${branch}"
            echo
            continue
        fi

        add_worktree "${branch}" "${path}"
        echo
    done

    echo "worktrees:"
    git -C "${root}" worktree list
}

usage() {
    sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
}

main() {
    local cmd="${1:-link}"

    case "${cmd}" in
        link)
            link_output "$(repo_root)"
            ;;
        link-all)
            link_all_worktrees
            ;;
        verify)
            verify_output_link
            ;;
        add)
            shift
            if [ $# -lt 1 ]; then
                echo "error: add requires a branch name" >&2
                exit 1
            fi
            add_worktree "$@"
            ;;
        bootstrap)
            bootstrap_worktrees
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            echo "error: unknown command: ${cmd}" >&2
            usage >&2
            exit 1
            ;;
    esac
}

main "$@"
