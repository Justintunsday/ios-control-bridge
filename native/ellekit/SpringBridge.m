#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdbool.h>
#include "../common/RuntimeABI.h"
#include "SocketServer.h"

/*
 * ElleKit SpringBoard bridge for settings that require SpringBoard context.
 *
 * The constructor uses only C/Objective-C runtime C APIs and starts a detached
 * thread. The thread waits for SpringBoard to finish starting, then polls a
 * small line-based command file and dispatches each fixed command to the main
 * queue, where SpringBoard UI-state APIs are expected to run.
 *
 * Only the fixed actions below are accepted; there is no generic selector
 * execution.
 */


typedef long long (*LongGetter)(id, SEL);
typedef BOOL (*BoolGetter)(id, SEL);
typedef void (*VoidCall)(id, SEL);
typedef BOOL (*BoolSetter)(id, SEL, long long, id);

static id string_with_utf8(const char *value) {
    Class cls = objc_getClass("NSString");
    return ((id (*)(id, SEL, const char *))objc_msgSend)(
        (id)cls, sel_registerName("stringWithUTF8String:"), value);
}

static id shared_instance_named(const char *class_name, const char *selector_name) {
    Class cls = objc_getClass(class_name);
    if (!cls) {
        return nil;
    }
    SEL selector = sel_registerName(selector_name);
    if (!ICBABI((id)cls, selector_name, "@16@0:8")) {
        return nil;
    }
    return ((id (*)(id, SEL))objc_msgSend)((id)cls, selector);
}

static bool execute_low_power_get(char *detail, size_t detail_size, int *value) {
    id manager = shared_instance_named("_PMLowPowerMode", "sharedInstance");
    if (!ICBABI(manager, "getPowerMode", "q16@0:8")) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    long long mode = ((LongGetter)objc_msgSend)(manager, sel_registerName("getPowerMode"));
    *value = mode != 0 ? 1 : 0;
    snprintf(detail, detail_size, "power_mode=%lld", mode);
    return true;
}

static bool execute_low_power_set(Command *command, char *detail, size_t detail_size, int *readback) {
    id manager = shared_instance_named("_PMLowPowerMode", "sharedInstance");
    if (!ICBABI(manager, "setPowerMode:fromSource:", "B32@0:8q16@24")
        || !ICBABI(manager, "getPowerMode", "q16@0:8")) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    if (icb_now_ms() >= command->deadline_ms || !icb_connected(command->socket_fd)) {
        snprintf(detail, detail_size, "request_expired_or_disconnected"); return false;
    }
    id source = string_with_utf8("ios-control-bridge");
    ((BoolSetter)objc_msgSend)(manager, sel_registerName("setPowerMode:fromSource:"),
                               (long long)(command->value ? 1 : 0), source);
    long long mode = ((LongGetter)objc_msgSend)(manager, sel_registerName("getPowerMode"));
    *readback = mode != 0 ? 1 : 0;
    snprintf(detail, detail_size, "power_mode=%lld", mode);
    return true;
}

static bool execute_orientation_get(char *detail, size_t detail_size, int *value) {
    id manager = shared_instance_named("SBOrientationLockManager", "sharedInstance");
    if (!ICBABI(manager, "isUserLocked", "B16@0:8")) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    BOOL locked = ((BoolGetter)objc_msgSend)(manager, sel_registerName("isUserLocked"));
    *value = locked ? 1 : 0;
    snprintf(detail, detail_size, "isUserLocked=%d", locked ? 1 : 0);
    return true;
}

static bool execute_orientation_set(Command *command, char *detail, size_t detail_size, int *readback) {
    id manager = shared_instance_named("SBOrientationLockManager", "sharedInstance");
    if (!ICBABI(manager, command->value ? "lock" : "unlock", "v16@0:8")
        || !ICBABI(manager, "isUserLocked", "B16@0:8")) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    if (icb_now_ms() >= command->deadline_ms || !icb_connected(command->socket_fd)) {
        snprintf(detail, detail_size, "request_expired_or_disconnected"); return false;
    }
    if (command->value) {
        ((VoidCall)objc_msgSend)(manager, sel_registerName("lock"));
    } else {
        ((VoidCall)objc_msgSend)(manager, sel_registerName("unlock"));
    }
    BOOL locked = ((BoolGetter)objc_msgSend)(manager, sel_registerName("isUserLocked"));
    *readback = locked ? 1 : 0;
    snprintf(detail, detail_size, "isUserLocked=%d", locked ? 1 : 0);
    return true;
}

static bool execute_wifi_get(char *detail, size_t detail_size, int *value) {
    id manager = shared_instance_named("HSWiFiManager", "sharedWiFiManager");
    if (!ICBABI(manager, "isWiFiEnabled", "B16@0:8")
        || !ICBABI(manager, "isWiFiAssociated", "B16@0:8")) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    BOOL enabled = ((BoolGetter)objc_msgSend)(manager, sel_registerName("isWiFiEnabled"));
    BOOL associated = ((BoolGetter)objc_msgSend)(manager, sel_registerName("isWiFiAssociated"));
    *value = enabled ? 1 : 0;
    snprintf(detail, detail_size, "enabled=%d associated=%d", enabled ? 1 : 0, associated ? 1 : 0);
    return true;
}

static bool execute_bluetooth_get(char *detail, size_t detail_size, int *value) {
    static void *handle = NULL;
    static id manager = nil;
    if (!handle) handle = dlopen("/System/Library/PrivateFrameworks/BluetoothManager.framework/BluetoothManager",
                                RTLD_LAZY | RTLD_LOCAL);
    if (!handle) {
        snprintf(detail, detail_size, "framework_unavailable");
        return false;
    }
    Class cls = objc_getClass("BluetoothManager");
    if (!cls) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    if (!manager) {
        manager = ((id (*)(id, SEL))objc_msgSend)((id)cls, sel_registerName("alloc"));
        manager = ((id (*)(id, SEL))objc_msgSend)(manager, sel_registerName("init"));
    }
    if (!manager) {
        snprintf(detail, detail_size, "init_failed");
        return false;
    }
    if (!ICBABI(manager, "enabled", "B16@0:8")) {
        snprintf(detail, detail_size, "abi_mismatch"); return false;
    }
    BOOL enabled = ((BoolGetter)objc_msgSend)(manager, sel_registerName("enabled"));
    *value = enabled ? 1 : 0;
    snprintf(detail, detail_size, "enabled=%d", enabled ? 1 : 0);
    return true;
}


static bool execute_airplane_get(char *detail, size_t detail_size, int *value) {
    static id preferences = nil;
    Class cls = objc_getClass("RadiosPreferences");
    if (!cls) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    if (!preferences) {
        preferences = ((id (*)(id, SEL))objc_msgSend)((id)cls, sel_registerName("alloc"));
        preferences = ((id (*)(id, SEL))objc_msgSend)(preferences, sel_registerName("init"));
    }
    if (!preferences) {
        snprintf(detail, detail_size, "init_failed");
        return false;
    }
    if (!ICBABI(preferences, "airplaneMode", "B16@0:8")) {
        snprintf(detail, detail_size, "abi_mismatch"); return false;
    }
    BOOL enabled = ((BoolGetter)objc_msgSend)(preferences, sel_registerName("airplaneMode"));
    *value = enabled ? 1 : 0;
    snprintf(detail, detail_size, "airplaneMode=%d", enabled ? 1 : 0);
    return true;
}

static void execute(Command *command) {
    char detail[128] = {0};
    int readback = -1;
    bool ok = false;
    if (strcmp(command->action, "get_low_power") == 0) {
        ok = execute_low_power_get(detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "set_low_power") == 0) {
        ok = execute_low_power_set(command, detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "get_orientation_lock") == 0) {
        ok = execute_orientation_get(detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "set_orientation_lock") == 0) {
        ok = execute_orientation_set(command, detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "get_wifi") == 0) {
        ok = execute_wifi_get(detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "get_airplane") == 0) {
        ok = execute_airplane_get(detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "get_bluetooth") == 0) {
        ok = execute_bluetooth_get(detail, sizeof(detail), &readback);
    } else {
        snprintf(command->status, sizeof(command->status), "error");
        snprintf(command->detail, sizeof(command->detail), "unsupported_action");
        return;
    }
    snprintf(command->status, sizeof(command->status), "%s", ok ? "ok" : "unavailable");
    command->readback = readback;
    snprintf(command->detail, sizeof(command->detail), "%s", detail);
}

static void *bridge_thread(void *argument) {
    (void)argument;
    sleep(5);
    icb_serve();
    return NULL;
}

__attribute__((constructor)) static void initialize_bridge(void) {
    /*
     * Only C code and pthread_create run here. Objective-C messaging is done on
     * the main queue after SpringBoard has finished launching; calling
     * Foundation from the injected constructor itself can crash SpringBoard.
     */
    pthread_t thread;
    if (pthread_create(&thread, NULL, bridge_thread, NULL) == 0) {
        pthread_detach(thread);
    }
}
