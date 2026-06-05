#!/bin/bash
# gate-engine.sh
# Meridian Gate DAG Engine
#
# Reads .meridian/gates.yaml and enforces the gate dependency graph
# Called by PreToolUse hooks to block operations when gates haven't cleared
#
# Usage:
#   gate-engine.sh validate              # Validate gates.yaml structure
#   gate-engine.sh check-circular        # Detect circular dependencies
#   gate-engine.sh current               # Get current active gate
#   gate-engine.sh can-proceed <gate-id> # Check if gate can proceed
#   gate-engine.sh mark-passed <gate-id> # Mark gate as passed

set -euo pipefail

# Configuration
GATES_FILE="${MERIDIAN_PROJECT_DIR:-.}/.meridian/gates.yaml"
STATE_FILE="${MERIDIAN_PROJECT_DIR:-.}/.meridian/gate-state.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Error codes
ERR_MISSING_FILE=1
ERR_INVALID_YAML=2
ERR_CIRCULAR_DEP=3
ERR_MISSING_GATE=4
ERR_DEPENDENCY_NOT_MET=5

#######################################
# Print error message and exit
# Arguments:
#   $1 - Error message
#   $2 - Exit code
#######################################
error() {
    echo -e "${RED}ERROR:${NC} $1" >&2
    exit "${2:-1}"
}

#######################################
# Print warning message
# Arguments:
#   $1 - Warning message
#######################################
warn() {
    echo -e "${YELLOW}WARNING:${NC} $1" >&2
}

#######################################
# Print success message
# Arguments:
#   $1 - Success message
#######################################
success() {
    echo -e "${GREEN}✓${NC} $1"
}

#######################################
# Check if gates.yaml exists
#######################################
check_gates_file() {
    if [ ! -f "$GATES_FILE" ]; then
        error "gates.yaml not found at $GATES_FILE" $ERR_MISSING_FILE
    fi
}

#######################################
# Validate gates.yaml structure
# Uses yq if available, basic checks otherwise
#######################################
validate_gates_yaml() {
    check_gates_file

    # Check if yq is available for proper YAML validation
    if command -v yq >/dev/null 2>&1; then
        # Validate YAML syntax
        if ! yq eval '.' "$GATES_FILE" >/dev/null 2>&1; then
            error "Invalid YAML syntax in $GATES_FILE" $ERR_INVALID_YAML
        fi

        # Check required fields
        local version
        version=$(yq eval '.version' "$GATES_FILE" 2>/dev/null || echo "null")
        if [ "$version" = "null" ]; then
            error "Missing 'version' field in gates.yaml" $ERR_INVALID_YAML
        fi

        local gate_count
        gate_count=$(yq eval '.gates | length' "$GATES_FILE" 2>/dev/null || echo "0")
        if [ "$gate_count" -eq 0 ]; then
            error "No gates defined in gates.yaml" $ERR_INVALID_YAML
        fi

        # Validate each gate has required fields
        for i in $(seq 0 $((gate_count - 1))); do
            local gate_id
            gate_id=$(yq eval ".gates[$i].id" "$GATES_FILE" 2>/dev/null || echo "null")
            if [ "$gate_id" = "null" ]; then
                error "Gate at index $i missing 'id' field" $ERR_INVALID_YAML
            fi

            local gate_type
            gate_type=$(yq eval ".gates[$i].type" "$GATES_FILE" 2>/dev/null || echo "null")
            if [ "$gate_type" = "null" ]; then
                error "Gate '$gate_id' missing 'type' field" $ERR_INVALID_YAML
            fi

            if [ "$gate_type" != "human_approval" ] && [ "$gate_type" != "automated" ]; then
                error "Gate '$gate_id' has invalid type '$gate_type' (must be 'human_approval' or 'automated')" $ERR_INVALID_YAML
            fi
        done

        success "gates.yaml structure is valid"
    else
        # Basic validation without yq
        if ! grep -q "^version:" "$GATES_FILE"; then
            error "Missing 'version' field in gates.yaml (install yq for better validation)" $ERR_INVALID_YAML
        fi

        if ! grep -q "^gates:" "$GATES_FILE"; then
            error "Missing 'gates' field in gates.yaml (install yq for better validation)" $ERR_INVALID_YAML
        fi

        warn "yq not found - running basic validation only (install yq for full validation)"
        success "Basic gates.yaml validation passed"
    fi
}

#######################################
# Check for circular dependencies in gate DAG
# Uses depth-first search to detect cycles
#######################################
check_circular_dependencies() {
    check_gates_file

    if ! command -v yq >/dev/null 2>&1; then
        warn "yq not found - cannot check circular dependencies (install yq for this feature)"
        return 0
    fi

    local gate_count
    gate_count=$(yq eval '.gates | length' "$GATES_FILE")

    # Build adjacency list
    declare -A visited
    declare -A rec_stack
    declare -A gate_deps

    # Read all gate IDs and their dependencies
    for i in $(seq 0 $((gate_count - 1))); do
        local gate_id
        gate_id=$(yq eval ".gates[$i].id" "$GATES_FILE")

        local requires
        requires=$(yq eval ".gates[$i].requires[]" "$GATES_FILE" 2>/dev/null || echo "")

        gate_deps["$gate_id"]="$requires"
    done

    # DFS to detect cycles
    for gate_id in "${!gate_deps[@]}"; do
        if [ "${visited[$gate_id]:-}" != "true" ]; then
            if detect_cycle "$gate_id"; then
                error "Circular dependency detected in gate DAG" $ERR_CIRCULAR_DEP
            fi
        fi
    done

    success "No circular dependencies found"
}

#######################################
# Detect cycle using DFS (helper function)
# Arguments:
#   $1 - Gate ID to check
#######################################
detect_cycle() {
    local gate_id="$1"

    visited["$gate_id"]="true"
    rec_stack["$gate_id"]="true"

    # Check all dependencies
    local deps="${gate_deps[$gate_id]:-}"
    for dep in $deps; do
        if [ "${visited[$dep]:-}" != "true" ]; then
            if detect_cycle "$dep"; then
                return 0  # Cycle found
            fi
        elif [ "${rec_stack[$dep]:-}" = "true" ]; then
            echo "Cycle: $gate_id → $dep" >&2
            return 0  # Cycle found
        fi
    done

    rec_stack["$gate_id"]="false"
    return 1  # No cycle
}

#######################################
# Get current active gate
# Returns the gate ID that should be worked on next
#######################################
get_current_gate() {
    check_gates_file

    # Initialize state file if it doesn't exist
    if [ ! -f "$STATE_FILE" ]; then
        echo '{"passed_gates": []}' > "$STATE_FILE"
    fi

    if ! command -v yq >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
        warn "yq or jq not found - cannot determine current gate"
        echo "unknown"
        return 0
    fi

    # Read passed gates from state
    local passed_gates
    passed_gates=$(jq -r '.passed_gates[]' "$STATE_FILE" 2>/dev/null || echo "")

    # Find first gate whose dependencies are all met but hasn't passed yet
    local gate_count
    gate_count=$(yq eval '.gates | length' "$GATES_FILE")

    for i in $(seq 0 $((gate_count - 1))); do
        local gate_id
        gate_id=$(yq eval ".gates[$i].id" "$GATES_FILE")

        # Check if already passed
        if echo "$passed_gates" | grep -qx "$gate_id"; then
            continue
        fi

        # Check if all dependencies are met
        local requires
        requires=$(yq eval ".gates[$i].requires[]" "$GATES_FILE" 2>/dev/null || echo "")

        local deps_met=true
        for dep in $requires; do
            if ! echo "$passed_gates" | grep -qx "$dep"; then
                deps_met=false
                break
            fi
        done

        if [ "$deps_met" = true ]; then
            echo "$gate_id"
            return 0
        fi
    done

    echo "all_complete"
}

#######################################
# Check if a specific gate can proceed
# Arguments:
#   $1 - Gate ID to check
#######################################
can_proceed_gate() {
    local gate_id="$1"
    check_gates_file

    if ! command -v yq >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
        warn "yq or jq not found - cannot check gate status"
        return 0  # Permissive when tools unavailable
    fi

    # Check if gate exists
    local gate_exists
    gate_exists=$(yq eval ".gates[] | select(.id == \"$gate_id\") | .id" "$GATES_FILE" 2>/dev/null || echo "")

    if [ -z "$gate_exists" ]; then
        error "Gate '$gate_id' not found in gates.yaml" $ERR_MISSING_GATE
    fi

    # Check if dependencies are met
    local passed_gates
    passed_gates=$(jq -r '.passed_gates[]' "$STATE_FILE" 2>/dev/null || echo "")

    local requires
    requires=$(yq eval ".gates[] | select(.id == \"$gate_id\") | .requires[]" "$GATES_FILE" 2>/dev/null || echo "")

    for dep in $requires; do
        if ! echo "$passed_gates" | grep -qx "$dep"; then
            echo "Gate '$gate_id' blocked: dependency '$dep' not met" >&2
            return $ERR_DEPENDENCY_NOT_MET
        fi
    done

    success "Gate '$gate_id' can proceed"
    return 0
}

#######################################
# Mark a gate as passed
# Arguments:
#   $1 - Gate ID to mark as passed
#######################################
mark_gate_passed() {
    local gate_id="$1"

    # Initialize state file if needed
    if [ ! -f "$STATE_FILE" ]; then
        echo '{"passed_gates": []}' > "$STATE_FILE"
    fi

    if ! command -v jq >/dev/null 2>&1; then
        warn "jq not found - cannot update gate state"
        return 0
    fi

    # Add gate to passed list if not already there
    local new_state
    new_state=$(jq ".passed_gates |= (. + [\"$gate_id\"] | unique)" "$STATE_FILE")
    echo "$new_state" > "$STATE_FILE"

    success "Gate '$gate_id' marked as passed"
}

#######################################
# Extract a gate's pre-hooks (hooks.pre) from gates.yaml.
# Arguments: $1 - gate id
# Emits: one hook script name per line (yq when available, awk fallback).
#######################################
get_pre_hooks() {
    local gate_id="$1"

    if command -v yq >/dev/null 2>&1; then
        yq eval ".gates[] | select(.id == \"$gate_id\") | .hooks.pre[]" "$GATES_FILE" 2>/dev/null \
            | grep -v '^null$' || true
        return 0
    fi

    # Fallback: line-based awk parser for the regular 2-space-indent format.
    awk -v target="$gate_id" '
        /^[[:space:]]*-[[:space:]]+id:/ {
            id=$0; sub(/^[^:]*:[[:space:]]*/, "", id);
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", id);
            cur=(id==target); inpre=0; next
        }
        cur && /^[[:space:]]+pre:[[:space:]]*$/ { inpre=1; next }
        cur && inpre && /^[[:space:]]+-[[:space:]]+/ {
            h=$0; sub(/^[[:space:]]+-[[:space:]]+/, "", h);
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", h); print h; next
        }
        cur && inpre && /^[[:space:]]+[A-Za-z_]+:/ { inpre=0 }
    ' "$GATES_FILE"
}

#######################################
# Resolve a hook name to an executable path (.claude/hooks then scripts).
# Arguments: $1 - hook script name
# Echoes resolved path, or nothing if not found.
#######################################
resolve_hook() {
    local name="$1"
    local base="${MERIDIAN_PROJECT_DIR:-.}"
    if [ -f "$base/.claude/hooks/$name" ]; then
        echo "$base/.claude/hooks/$name"
    elif [ -f "$base/scripts/$name" ]; then
        echo "$base/scripts/$name"
    fi
}

#######################################
# Verify a gate: run its hooks.pre in order; block (exit 2) if any fails.
# This is the mechanical gate-enforcement entrypoint (Gate 2.2). It does NOT
# mark the gate passed - run mark-passed after a clean verify.
# Arguments: $1 - gate id
#######################################
verify_gate() {
    local gate_id="$1"
    check_gates_file

    local log_event="${MERIDIAN_PROJECT_DIR:-.}/scripts/log-event.sh"
    local hooks
    hooks=$(get_pre_hooks "$gate_id")

    if [ -z "$hooks" ]; then
        success "Gate '$gate_id' has no pre-hooks to verify"
        return 0
    fi

    local hook path rc=0
    while IFS= read -r hook; do
        [ -n "$hook" ] || continue
        path=$(resolve_hook "$hook")
        if [ -z "$path" ]; then
            warn "Pre-hook '$hook' not found (skipping) - install it under .claude/hooks/ or scripts/"
            continue
        fi
        echo -e "${YELLOW}→${NC} running pre-hook: $hook" >&2
        rc=0
        bash "$path" >&2 || rc=$?
        if [ "$rc" -eq 2 ]; then
            [ -f "$log_event" ] && bash "$log_event" gate_blocked gate="$gate_id" \
                reason="pre-hook $hook failed" >/dev/null 2>&1 || true
            error "Gate '$gate_id' verification FAILED: pre-hook '$hook' blocked (exit 2)" 2
        elif [ "$rc" -ne 0 ]; then
            warn "Pre-hook '$hook' exited $rc (non-blocking)"
        fi
    done <<< "$hooks"

    success "Gate '$gate_id' verified - all pre-hooks passed"
    return 0
}

#######################################
# Main command dispatcher
#######################################
main() {
    local command="${1:-}"

    case "$command" in
        validate)
            validate_gates_yaml
            ;;
        check-circular)
            check_circular_dependencies
            ;;
        current)
            get_current_gate
            ;;
        can-proceed)
            if [ $# -lt 2 ]; then
                error "Usage: gate-engine.sh can-proceed <gate-id>"
            fi
            can_proceed_gate "$2"
            ;;
        mark-passed)
            if [ $# -lt 2 ]; then
                error "Usage: gate-engine.sh mark-passed <gate-id>"
            fi
            mark_gate_passed "$2"
            ;;
        verify)
            if [ $# -lt 2 ]; then
                error "Usage: gate-engine.sh verify <gate-id>"
            fi
            verify_gate "$2"
            ;;
        *)
            echo "Meridian Gate Engine"
            echo ""
            echo "Usage:"
            echo "  gate-engine.sh validate              Validate gates.yaml structure"
            echo "  gate-engine.sh check-circular        Detect circular dependencies"
            echo "  gate-engine.sh current               Get current active gate"
            echo "  gate-engine.sh can-proceed <gate-id> Check if gate can proceed"
            echo "  gate-engine.sh verify <gate-id>      Run gate pre-hooks (block on failure)"
            echo "  gate-engine.sh mark-passed <gate-id> Mark gate as passed"
            echo ""
            echo "Dependencies (optional but recommended):"
            echo "  - yq: YAML parsing and validation"
            echo "  - jq: JSON state management"
            exit 1
            ;;
    esac
}

main "$@"
