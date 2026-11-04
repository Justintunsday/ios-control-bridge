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

#define COMMAND_PATH "/var/jb/var/lib/icb/spring.cmd"
#define RESULT_PATH "/var/jb/var/lib/icb/spring.result"
#define RESULT_TMP "/var/jb/var/lib/icb/spring.result.tmp"

typedef long long (*LongGetter)(id, SEL);
typedef BOOL (*BoolGetter)(id, SEL);
typedef void (*VoidCall)(id, SEL);
typedef BOOL (*BoolSetter)(id, SEL, long long, id);
typedef BOOL (*BoolSetterSimple)(id, SEL, BOOL);

typedef struct {
    char id[128];
    char action[64];
    int value;
} Command;

static char last_id[128] = {0};

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
    if (!class_respondsToSelector(object_getClass(cls), selector)) {
        return nil;
    }
    return ((id (*)(id, SEL))objc_msgSend)((id)cls, selector);
}

static bool execute_low_power_get(char *detail, size_t detail_size, int *value) {
    id manager = shared_instance_named("_PMLowPowerMode", "sharedInstance");
    if (!manager) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    long long mode = ((LongGetter)objc_msgSend)(manager, sel_registerName("getPowerMode"));
    *value = mode != 0 ? 1 : 0;
    snprintf(detail, detail_size, "power_mode=%lld", mode);
    return true;
}

static bool execute_low_power_set(int value, char *detail, size_t detail_size, int *readback) {
    id manager = shared_instance_named("_PMLowPowerMode", "sharedInstance");
    if (!manager) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    id source = string_with_utf8("ios-control-bridge");
    ((BoolSetter)objc_msgSend)(manager, sel_registerName("setPowerMode:fromSource:"),
                               (long long)(value ? 1 : 0), source);
    usleep(300000);
    long long mode = ((LongGetter)objc_msgSend)(manager, sel_registerName("getPowerMode"));
    *readback = mode != 0 ? 1 : 0;
    snprintf(detail, detail_size, "power_mode=%lld", mode);
    return true;
}

static bool execute_orientation_get(char *detail, size_t detail_size, int *value) {
    id manager = shared_instance_named("SBOrientationLockManager", "sharedInstance");
    if (!manager) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    BOOL locked = ((BoolGetter)objc_msgSend)(manager, sel_registerName("isUserLocked"));
    *value = locked ? 1 : 0;
    snprintf(detail, detail_size, "isUserLocked=%d", locked ? 1 : 0);
    return true;
}

static bool execute_orientation_set(int value, char *detail, size_t detail_size, int *readback) {
    id manager = shared_instance_named("SBOrientationLockManager", "sharedInstance");
    if (!manager) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    if (value) {
        ((VoidCall)objc_msgSend)(manager, sel_registerName("lock"));
    } else {
        ((VoidCall)objc_msgSend)(manager, sel_registerName("unlock"));
    }
    usleep(300000);
    BOOL locked = ((BoolGetter)objc_msgSend)(manager, sel_registerName("isUserLocked"));
    *readback = locked ? 1 : 0;
    snprintf(detail, detail_size, "isUserLocked=%d", locked ? 1 : 0);
    return true;
}

static bool execute_wifi_get(char *detail, size_t detail_size, int *value) {
    id manager = shared_instance_named("HSWiFiManager", "sharedWiFiManager");
    if (!manager) {
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
    void *handle = dlopen("/System/Library/PrivateFrameworks/BluetoothManager.framework/BluetoothManager",
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
    id manager = ((id (*)(id, SEL))objc_msgSend)((id)cls, sel_registerName("alloc"));
    manager = ((id (*)(id, SEL))objc_msgSend)(manager, sel_registerName("init"));
    if (!manager) {
        snprintf(detail, detail_size, "init_failed");
        return false;
    }
    BOOL enabled = ((BoolGetter)objc_msgSend)(manager, sel_registerName("enabled"));
    *value = enabled ? 1 : 0;
    snprintf(detail, detail_size, "enabled=%d", enabled ? 1 : 0);
    return true;
}

static bool execute_bluetooth_set(int value, char *detail, size_t detail_size, int *readback) {
    void *handle = dlopen("/System/Library/PrivateFrameworks/BluetoothManager.framework/BluetoothManager",
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
    id manager = ((id (*)(id, SEL))objc_msgSend)((id)cls, sel_registerName("alloc"));
    manager = ((id (*)(id, SEL))objc_msgSend)(manager, sel_registerName("init"));
    if (!manager) {
        snprintf(detail, detail_size, "init_failed");
        return false;
    }
    BOOL accepted = ((BoolSetterSimple)objc_msgSend)(manager, sel_registerName("setEnabled:"), value ? YES : NO);
    usleep(800000);
    BOOL enabled = ((BoolGetter)objc_msgSend)(manager, sel_registerName("enabled"));
    *readback = enabled ? 1 : 0;
    snprintf(detail, detail_size, "accepted=%d enabled=%d", accepted ? 1 : 0, enabled ? 1 : 0);
    return true;
}

static bool execute_airplane_get(char *detail, size_t detail_size, int *value) {
    Class cls = objc_getClass("RadiosPreferences");
    if (!cls) {
        snprintf(detail, detail_size, "class_unavailable");
        return false;
    }
    id preferences = ((id (*)(id, SEL))objc_msgSend)((id)cls, sel_registerName("alloc"));
    preferences = ((id (*)(id, SEL))objc_msgSend)(preferences, sel_registerName("init"));
    if (!preferences) {
        snprintf(detail, detail_size, "init_failed");
        return false;
    }
    BOOL enabled = ((BoolGetter)objc_msgSend)(preferences, sel_registerName("airplaneMode"));
    *value = enabled ? 1 : 0;
    snprintf(detail, detail_size, "airplaneMode=%d", enabled ? 1 : 0);
    return true;
}

static void write_result(const char *id, const char *status, int value, const char *detail) {
    FILE *file = fopen(RESULT_TMP, "w");
    if (!file) {
        return;
    }
    fprintf(file, "%s\n%s\n%d\n%s\n", id, status, value, detail);
    fclose(file);
    rename(RESULT_TMP, RESULT_PATH);
}

static void execute(Command *command) {
    char detail[128] = {0};
    int readback = -1;
    bool ok = false;
    if (strcmp(command->action, "get_low_power") == 0) {
        ok = execute_low_power_get(detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "set_low_power") == 0) {
        ok = execute_low_power_set(command->value, detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "get_orientation_lock") == 0) {
        ok = execute_orientation_get(detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "set_orientation_lock") == 0) {
        ok = execute_orientation_set(command->value, detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "get_wifi") == 0) {
        ok = execute_wifi_get(detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "get_airplane") == 0) {
        ok = execute_airplane_get(detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "get_bluetooth") == 0) {
        ok = execute_bluetooth_get(detail, sizeof(detail), &readback);
    } else if (strcmp(command->action, "set_bluetooth") == 0) {
        ok = execute_bluetooth_set(command->value, detail, sizeof(detail), &readback);
    } else {
        write_result(command->id, "error", -1, "unsupported_action");
        return;
    }
    write_result(command->id, ok ? "ok" : "unavailable", readback, detail);
}

static void execute_on_main(void *context) {
    Command *command = (Command *)context;
    @autoreleasepool {
        execute(command);
    }
    free(command);
}

static void process_command(void) {
    FILE *file = fopen(COMMAND_PATH, "r");
    if (!file) {
        return;
    }
    char id[128] = {0};
    char action[64] = {0};
    char value_text[32] = {0};
    if (!fgets(id, sizeof(id), file) || !fgets(action, sizeof(action), file) ||
        !fgets(value_text, sizeof(value_text), file)) {
        fclose(file);
        return;
    }
    fclose(file);
    id[strcspn(id, "\r\n")] = 0;
    action[strcspn(action, "\r\n")] = 0;
    if (id[0] == 0 || action[0] == 0 || strcmp(id, last_id) == 0) {
        return;
    }
    snprintf(last_id, sizeof(last_id), "%s", id);
    Command *command = (Command *)calloc(1, sizeof(Command));
    if (!command) {
        return;
    }
    snprintf(command->id, sizeof(command->id), "%s", id);
    snprintf(command->action, sizeof(command->action), "%s", action);
    command->value = atoi(value_text);
    dispatch_async_f(dispatch_get_main_queue(), command, execute_on_main);
}

static void *bridge_thread(void *argument) {
    (void)argument;
    sleep(5);
    for (;;) {
        process_command();
        usleep(100000);
    }
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
