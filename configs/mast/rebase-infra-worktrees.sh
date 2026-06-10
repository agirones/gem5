#!/usr/bin/env bash
# Rebase implementation branches onto updated infra in every worktree.
#
# Run from the main checkout (gem5-NTNU on infra) after committing infra changes:
#
#   cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU
#   git commit -m "cpu-o3: ..."
#   ./configs/mast/rebase-infra-worktrees.sh
#
# Rebase order matches configs/mast/PROJECT_BRANCHES.md §9:
#   sereno, explicit-data-forwarding, n-use/OoO  → infra
#   n-use/InO                                      → n-use/OoO
#   hybrid-wl                                      → sereno
#   baseline                                       → fast-forward to sereno
#
# Options:
#   --onto <ref>   Rebase onto this ref (default: infra)
#   --fetch        Run git fetch origin before rebasing
#   --dry-run      Print planned steps without rebasing
#   -h, --help     Show this help

set -euo pipefail

ONTO="infra"
FETCH=0
DRY_RUN=0

usage() {
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

main_root() {
    local git_common

    git_common="$(git rev-parse --git-common-dir)"
    if [ "${git_common}" = ".git" ]; then
        git rev-parse --show-toplevel
        return
    fi

    dirname "${git_common}"
}

default_worktree_path() {
    local branch="$1"
    local parent slug

    parent="$(dirname "$(main_root)")"
    slug="${branch//\//-}"
    echo "${parent}/gem5-NTNU-${slug}"
}

rebase_in_worktree() {
    local branch="$1"
    local onto="$2"
    local path

    path="$(default_worktree_path "${branch}")"

    if [ ! -d "${path}" ]; then
        echo "skip: ${branch} (worktree not found: ${path})"
        return 0
    fi

    local checked_out
    checked_out="$(git -C "${path}" branch --show-current)"
    if [ "${checked_out}" != "${branch}" ]; then
        echo "error: ${path} is on '${checked_out}', expected '${branch}'" >&2
        exit 1
    fi

    echo "==> ${branch}"
    echo "    worktree: ${path}"
    echo "    rebase:   git rebase ${onto}"

    if [ "${DRY_RUN}" -eq 1 ]; then
        return 0
    fi

    if ! git -C "${path}" rebase "${onto}"; then
        echo >&2
        echo "error: rebase failed for ${branch} in ${path}" >&2
        echo "       resolve conflicts, then run:" >&2
        echo "         cd ${path} && git rebase --continue" >&2
        echo "       or abort and fix infra first:" >&2
        echo "         cd ${path} && git rebase --abort" >&2
        exit 1
    fi
}

sync_baseline_worktree() {
    local baseline_path

    baseline_path="$(default_worktree_path baseline)"

    if [ ! -d "${baseline_path}" ]; then
        echo "skip: baseline (worktree not found: ${baseline_path})"
        return 0
    fi

    echo "==> baseline"
    echo "    worktree: ${baseline_path}"
    echo "    sync:     git reset --hard sereno"

    if [ "${DRY_RUN}" -eq 1 ]; then
        return 0
    fi

    git -C "${baseline_path}" reset --hard sereno
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --onto)
                shift
                ONTO="${1:?--onto requires a ref}"
                ;;
            --fetch)
                FETCH=1
                ;;
            --dry-run)
                DRY_RUN=1
                ;;
            -h|--help|help)
                usage
                exit 0
                ;;
            *)
                echo "error: unknown option: $1" >&2
                usage >&2
                exit 1
                ;;
        esac
        shift
    done
}

main() {
    local root current

    parse_args "$@"

    root="$(main_root)"
    current="$(git -C "${root}" branch --show-current)"

    if [ "${current}" != "infra" ]; then
        echo "error: main worktree (${root}) is on '${current}', expected 'infra'" >&2
        echo "       commit infra changes there, then rerun this script." >&2
        exit 1
    fi

    if [ -n "$(git -C "${root}" status --porcelain)" ]; then
        echo "error: main worktree has uncommitted changes; commit or stash first." >&2
        exit 1
    fi

    echo "main worktree: ${root} [infra @ $(git -C "${root}" rev-parse --short HEAD)]"
    echo "rebase onto:   ${ONTO}"
    echo

    if [ "${FETCH}" -eq 1 ]; then
        echo "fetching origin..."
        git -C "${root}" fetch origin
        echo
    fi

    if ! git -C "${root}" show-ref --verify --quiet "refs/heads/${ONTO}"; then
        echo "error: branch or ref not found: ${ONTO}" >&2
        exit 1
    fi

    # Dependency order from PROJECT_BRANCHES.md §9.
    rebase_in_worktree sereno "${ONTO}"
    rebase_in_worktree explicit-data-forwarding "${ONTO}"
    rebase_in_worktree n-use/OoO "${ONTO}"
    rebase_in_worktree n-use/InO n-use/OoO
    rebase_in_worktree hybrid-wl sereno
    sync_baseline_worktree

    echo
    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "dry run complete (no branches were rebased)."
    else
        echo "done. worktrees:"
        git -C "${root}" worktree list
    fi
}

main "$@"
