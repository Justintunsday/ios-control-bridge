#import <Foundation/Foundation.h>
#import <dlfcn.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/*
 * Device-side system Clock alarm adapter using the private MobileTimer framework.
 *
 * Fixed commands only:
 *   icb-alarms list
 *   icb-alarms create <hour> <minute> <title>
 *   icb-alarms update <alarm-id> <hour> <minute> <title>
 *   icb-alarms set_enabled <alarm-id> <0|1>
 *   icb-alarms delete <alarm-id>
 *
 * The helper is signed with the mobiletimerd client entitlement; without that
 * entitlement MTAlarmManager cannot reach the MobileTimer service.
 */

static NSString *const ALARMS_SCHEMA = @"ios-control-bridge.alarms.v1";
static NSString *const ALARMS_SOURCE = @"MobileTimer.MTAlarmManager";

typedef long long (*ULLGetter)(id, SEL);
typedef BOOL (*BoolGetter)(id, SEL);
typedef id (*IdGetter)(id, SEL);
typedef id (*ObjectGetter)(id, SEL, id);
typedef void (*VoidSetterULL)(id, SEL, unsigned long long);
typedef void (*VoidSetterBool)(id, SEL, BOOL);
typedef void (*VoidSetterObject)(id, SEL, id);
typedef void (*VoidCallObject)(id, SEL, id);

static id manager = nil;

static int emit(NSDictionary *payload) {
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:&error];
    if (!data) {
        fprintf(stdout, "{\"schema\":\"%s\",\"status\":\"error\",\"reason\":\"json_encoding_failed\"}\n",
                [ALARMS_SCHEMA UTF8String]);
        return 4;
    }
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
    fflush(stdout);
    NSString *status = payload[@"status"];
    if ([status isEqualToString:@"verified"]) return 0;
    if ([status isEqualToString:@"partial"]) return 2;
    if ([status isEqualToString:@"unavailable"]) return 3;
    return 4;
}

static NSDictionary *response(NSString *status, NSDictionary *details) {
    NSMutableDictionary *payload = [NSMutableDictionary dictionary];
    payload[@"schema"] = ALARMS_SCHEMA;
    payload[@"status"] = status;
    payload[@"source"] = ALARMS_SOURCE;
    payload[@"observed_at_unix"] = @((double)time(NULL));
    if (details) [payload addEntriesFromDictionary:details];
    return payload;
}

static NSDictionary *error_response(NSString *reason) {
    return response(@"error", @{@"reason": reason});
}

static id load_manager(void) {
    if (manager) return manager;
    void *handle = dlopen("/System/Library/PrivateFrameworks/MobileTimer.framework/MobileTimer",
                          RTLD_LAZY | RTLD_LOCAL);
    if (!handle) return nil;
    Class cls = NSClassFromString(@"MTAlarmManager");
    if (!cls) return nil;
    manager = ((id (*)(id, SEL))objc_msgSend)((id)[cls alloc], sel_registerName("init"));
    return manager;
}

static NSArray *alarms(void) {
    if (!load_manager()) return nil;
    id value = ((id (*)(id, SEL))objc_msgSend)(manager, sel_registerName("alarmsSync"));
    return [value isKindOfClass:[NSArray class]] ? value : nil;
}

static NSString *alarm_id(id alarm) {
    id identifier = ((id (*)(id, SEL))objc_msgSend)(alarm, sel_registerName("alarmID"));
    return identifier ? [[identifier description] uppercaseString] : nil;
}

static NSDictionary *alarm_description(id alarm) {
    unsigned long long hour = ((ULLGetter)objc_msgSend)(alarm, sel_registerName("hour"));
    unsigned long long minute = ((ULLGetter)objc_msgSend)(alarm, sel_registerName("minute"));
    BOOL enabled = ((BoolGetter)objc_msgSend)(alarm, sel_registerName("isEnabled"));
    BOOL sleep = ((BoolGetter)objc_msgSend)(alarm, sel_registerName("isSleepAlarm"));
    id title = ((id (*)(id, SEL))objc_msgSend)(alarm, sel_registerName("displayTitle"));
    id next = ((id (*)(id, SEL))objc_msgSend)(alarm, sel_registerName("nextFireDate"));
    unsigned long long repeat = ((ULLGetter)objc_msgSend)(alarm, sel_registerName("repeatSchedule"));
    return @{
        @"id": alarm_id(alarm) ?: @"",
        @"hour": @(hour),
        @"minute": @(minute),
        @"enabled": @(enabled),
        @"sleep_alarm": @(sleep),
        @"title": [title isKindOfClass:[NSString class]] ? title : @"",
        @"repeat_schedule": @(repeat),
        @"next_fire_at_unix": [next isKindOfClass:[NSDate class]]
            ? @([(NSDate *)next timeIntervalSince1970]) : [NSNull null]
    };
}

static NSArray *visible_alarms(void) {
    NSArray *all = alarms();
    if (!all) return nil;
    NSMutableArray *rows = [NSMutableArray array];
    for (id alarm in all) {
        BOOL sleep = ((BoolGetter)objc_msgSend)(alarm, sel_registerName("isSleepAlarm"));
        if (!sleep) [rows addObject:alarm_description(alarm)];
    }
    return rows;
}

static id find_alarm(NSString *identifier) {
    NSArray *all = alarms();
    if (!all) return nil;
    for (id alarm in all) {
        if ([alarm_id(alarm) isEqualToString:identifier]) return alarm;
    }
    return nil;
}

static id create_alarm(unsigned long long hour, unsigned long long minute, NSString *title) {
    Class cls = NSClassFromString(@"MTAlarm");
    if (!cls) return nil;
    id alarm = ((id (*)(id, SEL, unsigned long long, unsigned long long))objc_msgSend)(
        (id)[cls alloc], sel_registerName("initWithHour:minute:"), hour, minute);
    ((VoidSetterObject)objc_msgSend)(alarm, sel_registerName("setTitle:"), title);
    ((VoidSetterBool)objc_msgSend)(alarm, sel_registerName("setEnabled:"), YES);
    ((VoidSetterULL)objc_msgSend)(alarm, sel_registerName("setRepeatSchedule:"), 0);
    ((VoidSetterBool)objc_msgSend)(alarm, sel_registerName("setAllowsSnooze:"), YES);
    ((VoidCallObject)objc_msgSend)(manager, sel_registerName("addAlarm:"), alarm);
    return alarm;
}

static BOOL parse_time(const char *hour_text, const char *minute_text,
                       unsigned long long *hour, unsigned long long *minute) {
    char *end = NULL;
    long h = strtol(hour_text, &end, 10);
    if (!hour_text[0] || (end && *end) || h < 0 || h > 23) return NO;
    long m = strtol(minute_text, &end, 10);
    if (!minute_text[0] || (end && *end) || m < 0 || m > 59) return NO;
    *hour = (unsigned long long)h;
    *minute = (unsigned long long)m;
    return YES;
}

static NSString *argument(int argc, char **argv, int index) {
    return index < argc ? [NSString stringWithUTF8String:argv[index]] : nil;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc < 2) return emit(error_response(@"usage"));
        if (!load_manager()) return emit(response(@"unavailable", @{@"reason": @"framework_unavailable"}));
        NSString *command = argument(argc, argv, 1);
        if ([command isEqualToString:@"list"]) {
            NSArray *rows = visible_alarms();
            if (!rows) return emit(response(@"unavailable", @{@"reason": @"alarms_unavailable"}));
            return emit(response(@"verified", @{@"alarms": rows, @"count": @(rows.count)}));
        }
        if ([command isEqualToString:@"create"]) {
            unsigned long long hour = 0, minute = 0;
            if (argc < 5 || !parse_time(argv[2], argv[3], &hour, &minute))
                return emit(error_response(@"invalid_time"));
            NSString *title = argument(argc, argv, 4);
            if (title.length == 0 || title.length > 64) return emit(error_response(@"invalid_title"));
            NSArray *before = visible_alarms();
            create_alarm(hour, minute, title);
            usleep(400000);
            NSArray *after = visible_alarms();
            if (!after) return emit(response(@"partial", @{@"reason": @"readback_unavailable"}));
            NSDictionary *found = nil;
            for (NSDictionary *row in after) {
                if ([row[@"title"] isEqualToString:title] &&
                    [row[@"hour"] unsignedLongLongValue] == hour &&
                    [row[@"minute"] unsignedLongLongValue] == minute &&
                    ![before containsObject:row]) {
                    found = row;
                    break;
                }
            }
            if (!found) return emit(response(@"partial", @{@"reason": @"create_not_confirmed",
                                                          @"alarms": after}));
            return emit(response(@"verified", @{@"alarm": found}));
        }
        if ([command isEqualToString:@"update"]) {
            if (argc < 6) return emit(error_response(@"invalid_arguments"));
            NSString *identifier = [argument(argc, argv, 2) uppercaseString];
            unsigned long long hour = 0, minute = 0;
            if (!parse_time(argv[3], argv[4], &hour, &minute))
                return emit(error_response(@"invalid_time"));
            NSString *title = argument(argc, argv, 5);
            if (title.length == 0 || title.length > 64) return emit(error_response(@"invalid_title"));
            id alarm = find_alarm(identifier);
            if (!alarm) return emit(error_response(@"alarm_not_found"));
            id mutable = ((id (*)(id, SEL))objc_msgSend)(alarm, sel_registerName("mutableCopy"));
            ((VoidSetterULL)objc_msgSend)(mutable, sel_registerName("setHour:"), hour);
            ((VoidSetterULL)objc_msgSend)(mutable, sel_registerName("setMinute:"), minute);
            ((VoidSetterObject)objc_msgSend)(mutable, sel_registerName("setTitle:"), title);
            ((VoidCallObject)objc_msgSend)(manager, sel_registerName("updateAlarm:"), mutable);
            usleep(400000);
            id updated = find_alarm(identifier);
            if (!updated) return emit(response(@"partial", @{@"reason": @"update_not_confirmed"}));
            return emit(response(@"verified", @{@"alarm": alarm_description(updated)}));
        }
        if ([command isEqualToString:@"set_enabled"]) {
            if (argc < 4) return emit(error_response(@"invalid_arguments"));
            NSString *identifier = [argument(argc, argv, 2) uppercaseString];
            BOOL enabled = strcmp(argv[3], "1") == 0;
            id alarm = find_alarm(identifier);
            if (!alarm) return emit(error_response(@"alarm_not_found"));
            id mutable = ((id (*)(id, SEL))objc_msgSend)(alarm, sel_registerName("mutableCopy"));
            ((VoidSetterBool)objc_msgSend)(mutable, sel_registerName("setEnabled:"), enabled);
            ((VoidCallObject)objc_msgSend)(manager, sel_registerName("updateAlarm:"), mutable);
            usleep(400000);
            id updated = find_alarm(identifier);
            if (!updated) return emit(response(@"partial", @{@"reason": @"update_not_confirmed"}));
            NSDictionary *row = alarm_description(updated);
            if ([row[@"enabled"] boolValue] != enabled)
                return emit(response(@"partial", @{@"reason": @"readback_mismatch", @"alarm": row}));
            return emit(response(@"verified", @{@"alarm": row}));
        }
        if ([command isEqualToString:@"delete"]) {
            if (argc < 3) return emit(error_response(@"invalid_arguments"));
            NSString *identifier = [argument(argc, argv, 2) uppercaseString];
            id alarm = find_alarm(identifier);
            if (!alarm) return emit(error_response(@"alarm_not_found"));
            ((VoidCallObject)objc_msgSend)(manager, sel_registerName("removeAlarm:"), alarm);
            usleep(400000);
            if (find_alarm(identifier)) return emit(response(@"partial", @{@"reason": @"delete_not_confirmed"}));
            return emit(response(@"verified", @{@"deleted": @YES, @"alarm_id": identifier}));
        }
        return emit(error_response(@"unsupported_command"));
    }
}
