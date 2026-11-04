#!/bin/sh
# Read-only discovery on an existing physical iOS terminal; no network/setup.
# Usage: sh probe_ios.sh [environment|status]
# Output: UTF-8 TSV. Exit 0 = probe completed (inspect result.status),
# 2 = invalid invocation, 4 = unsupported/unverified platform.
set -u

probe_mode=${1:-environment}
if [ "$#" -gt 1 ]; then
    printf '%s\n' 'Usage: sh probe_ios.sh [environment|status]' >&2
    exit 2
fi
case "$probe_mode" in
    environment|status) ;;
    *) printf '%s\n' 'Usage: sh probe_ios.sh [environment|status]' >&2; exit 2 ;;
esac

LC_ALL=C
export LC_ALL
# Preserve custom/relocated bootstraps already provided by the session.
PATH=${PATH:-/usr/bin:/bin}:/var/jb/usr/bin:/var/jb/usr/sbin:/var/jb/bin:/var/jb/sbin:/usr/bin:/bin:/usr/sbin:/sbin
export PATH
probe_partial=0

field() {
    printf '%s\t' "$1"
    printf '%s' "$2" | tr '\t\r\n' '   '
    printf '\n'
}

available() {
    command -v "$1" >/dev/null 2>&1
}

scalar() {
    probe_key=$1
    shift
    if probe_value=$("$@" 2>/dev/null) && [ -n "$probe_value" ]; then
        field "$probe_key" "$probe_value"
    else
        field "$probe_key" unknown
        probe_partial=1
    fi
}

section() {
    probe_section=$1
    shift
    if ! available "$1"; then
        field "$probe_section.status" unavailable
        probe_partial=1
        return
    fi
    if probe_output=$("$@" 2>&1); then
        field "$probe_section.status" verified
        field "$probe_section.exit_code" 0
    else
        probe_rc=$?
        field "$probe_section.status" error
        field "$probe_section.exit_code" "$probe_rc"
        probe_partial=1
    fi
    # These small status commands have bounded practical output. Preserve
    # failures, limit presentation, and explicitly mark output truncation.
    printf '%s\n' "$probe_output" | awk -v key="$probe_section" '
        NR <= 80 { gsub(/\t/, " "); print key ".line\t" $0 }
        NR == 81 { print key ".truncated\ttrue" }
    '
    probe_line_count=$(printf '%s\n' "$probe_output" | awk 'END { print NR }')
    if [ "$probe_line_count" -gt 80 ]; then probe_partial=1; fi
}

field schema ios-jailbreak-probe-v1
scalar observed_at date -u '+%Y-%m-%dT%H:%M:%SZ'
probe_kernel=$(uname -s 2>/dev/null) || probe_kernel=unknown
field platform.kernel "$probe_kernel"
if [ "$probe_kernel" != Darwin ]; then
    field result.status unavailable
    field result.reason 'Current shell is not a verified iOS device shell.'
    exit 4
fi
probe_hardware=$(sysctl -n hw.machine 2>/dev/null) || probe_hardware=unknown
field device.hardware "$probe_hardware"
case "$probe_hardware" in
    iPhone[0-9]*,*|iPad[0-9]*,*|iPod[0-9]*,*) ;;
    *)
        field result.status unavailable
        field result.reason 'Darwin host is not a verified physical iPhone/iPad/iPod.'
        exit 4
        ;;
esac

scalar platform.release uname -r
scalar user.uid id -u
scalar user.name id -un
field user.home "${HOME:-unknown}"
field user.login_shell "${SHELL:-unknown}"
field execution.interpreter 'sh (login shell may differ)'

probe_version=
probe_version_source=unknown
if available plutil; then
    if probe_version=$(plutil -extract ProductVersion raw -o - /System/Library/CoreServices/SystemVersion.plist 2>/dev/null); then
        probe_version_source=SystemVersion.plist
    else
        probe_version=
    fi
fi
if [ -z "$probe_version" ] && available sw_vers; then
    if probe_version=$(sw_vers -productVersion 2>/dev/null); then
        probe_version_source=sw_vers
    else
        probe_version=
    fi
fi
if [ -z "$probe_version" ]; then
    probe_version=unknown
    probe_partial=1
fi
field ios.version "$probe_version"
field ios.version_source "$probe_version_source"

probe_scheme=unknown
if [ -e /var/jb ] || [ -L /var/jb ]; then
    field bootstrap.var_jb_entry present
    if probe_real_prefix=$(cd /var/jb 2>/dev/null && pwd -P); then
        field bootstrap.var_jb_realpath "$probe_real_prefix"
        probe_scheme=rootless_candidate
    else
        field bootstrap.var_jb_realpath unknown
        probe_partial=1
    fi
else
    field bootstrap.var_jb_entry absent
fi
if available dpkg; then
    probe_dpkg_path=$(command -v dpkg)
    field bootstrap.dpkg_path "$probe_dpkg_path"
    case "$probe_dpkg_path" in
        /usr/bin/dpkg|/bin/dpkg)
            if [ "$probe_scheme" = unknown ]; then probe_scheme=rootful_candidate; fi
            ;;
        */usr/bin/dpkg)
            field bootstrap.tool_prefix_candidate "${probe_dpkg_path%/usr/bin/dpkg}"
            if [ "$probe_scheme" = unknown ]; then probe_scheme=custom_prefix_candidate; fi
            ;;
    esac
    scalar packages.architecture dpkg --print-architecture
fi
field bootstrap.scheme_evidence "$probe_scheme"
field bootstrap.note 'Candidates require corroboration; UID 0 does not imply rootful.'

for probe_tool in sh ps launchctl find stat du df plutil dpkg-query log ioreg vm_stat ssh scp rg jq python3; do
    if probe_tool_path=$(command -v "$probe_tool" 2>/dev/null); then
        field "tool.$probe_tool" "$probe_tool_path"
    else
        field "tool.$probe_tool" unavailable
    fi
done
field live_activities.source not_probed

if [ "$probe_mode" = status ]; then
    section uptime uptime
    section disk df -k / /var/mobile
    section memory vm_stat
    if available ioreg; then
        if probe_battery=$(ioreg -r -c AppleSmartBattery 2>/dev/null); then
            probe_battery_fields=$(printf '%s\n' "$probe_battery" | awk '
                /^[[:space:]|]*"(CurrentCapacity|MaxCapacity|AppleRawCurrentCapacity|AppleRawMaxCapacity|IsCharging|ExternalConnected|Temperature|BatteryInstalled)"[[:space:]]*=/ {
                    sub(/^[[:space:]|]*/, "")
                    gsub(/\t/, " ")
                    print "battery.raw\t" $0
                }
            ')
            if [ -n "$probe_battery_fields" ]; then
                field battery.status verified
                printf '%s\n' "$probe_battery_fields"
                field battery.units 'raw; interpret only with verified field semantics'
            else
                field battery.status unavailable
                probe_partial=1
            fi
        else
            probe_rc=$?
            field battery.status error
            field battery.exit_code "$probe_rc"
            probe_partial=1
        fi
    else
        field battery.status unavailable
        probe_partial=1
    fi
fi

if [ "$probe_partial" -eq 1 ]; then
    field result.status partial
else
    field result.status verified
fi
