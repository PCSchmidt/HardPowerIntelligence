#!/bin/bash
# PreToolUse.sh
# Meridian PreToolUse Hook
#
# Runs BEFORE tool execution to:
# - Enforce gate dependencies (block edits if gates not passed)
# - Validate operations against current project state
# - Log tool usage for telemetry
#
# Exit codes:
#   0 = Allow tool execution
#   1 = Warning (allow but log)
#   2 = Block tool execution

# Load common hook logic
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/hook-wrapper.sh"

HOOK_NAME="PreToolUse"

#######################################
# Main hook logic
#######################################
main() {
    # Parse tool use from stdin (if provided)
    if [ -t 0 ]; then
        # No stdin (running standalone for testing)
        info "Running in test mode (no stdin)"
    else
        parse_tool_use
    fi

    info "Tool: ${TOOL_NAME:-unknown}"

    # Check if we're in a Meridian project
    if ! check_meridian_project; then
        # Not a Meridian project - allow all operations
        info "Not a Meridian project - allowing operation"
        timer_end
        exit 0
    fi

    # Get current gate
    local current_gate
    current_gate=$(get_current_gate)
    info "Current gate: $current_gate"

    # Gate-specific enforcement
    case "$TOOL_NAME" in
        Edit|Write)
            # Check if editing protected files
            if [[ "$FILE_PATH" == *"/.meridian/gate-state.json" ]]; then
                warn "Direct edit of gate-state.json - should use gate-engine.sh"
            fi

            # Check if editing memory files directly
            if [[ "$FILE_PATH" == *"/.meridian/memory/"* ]]; then
                info "Memory file modification detected - will validate in PostToolUse"
            fi
            ;;

        Bash)
            # Destructive-operation detection is handled by block-dangerous.sh
            # (security-rules.yaml), invoked below for all tools.
            :
            ;;
    esac

    # Security blocklist enforcement (Gate 2.1).
    # block-dangerous.sh scans COMMAND / Edit-Write content against
    # .meridian/security-rules.yaml and exits 2 on a deterministic dangerous
    # operation. We capture its code (|| guards `set -e`) and propagate a block.
    local sec_rc=0
    "$SCRIPT_DIR/block-dangerous.sh" || sec_rc=$?
    if [ "$sec_rc" -eq 2 ]; then
        info "Tool execution blocked by security rule"
        timer_end
        exit 2
    fi

    # Log the operation
    info "Tool execution allowed"
    timer_end
    exit 0
}

# Run main
main "$@"
