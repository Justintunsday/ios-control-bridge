#import <Foundation/Foundation.h>
#import <dlfcn.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/*
 * Fixed-purpose ReminderKit adapter.
 *
 * Commands:
 *   icb-reminders lists
 *   icb-reminders list <list-id>
 *   icb-reminders create <list-id> <title>
 *   icb-reminders update <reminder-id> <title>
 *   icb-reminders complete <reminder-id>
 *   icb-reminders delete <reminder-id>
 *
 * ReminderKit is the private framework behind Reminders; EventKit reported zero
 * reminder lists on this device, while REMStore correctly exposes the account
 * and the user's "Reminders" list.
 */

static NSString *const REMINDERS_SCHEMA = @"ios-control-bridge.reminders.v1";
static NSString *const REMINDERS_SOURCE = @"ReminderKit.REMStore";

static int emit(NSDictionary *payload) {
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:&error];
    if (!data) {
        fprintf(stdout, "{\"schema\":\"%s\",\"status\":\"error\",\"reason\":\"json_encoding_failed\"}\n",
                [REMINDERS_SCHEMA UTF8String]);
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
    payload[@"schema"] = REMINDERS_SCHEMA;
    payload[@"status"] = status;
    payload[@"source"] = REMINDERS_SOURCE;
    payload[@"observed_at_unix"] = @((double)time(NULL));
    if (details) [payload addEntriesFromDictionary:details];
    return payload;
}

static NSDictionary *error_response(NSString *reason) {
    return response(@"error", @{@"reason": reason});
}

static id rem_store(void) {
    static id store = nil;
    if (store) return store;
    dlopen("/System/Library/PrivateFrameworks/ReminderKit.framework/ReminderKit", RTLD_LAZY | RTLD_LOCAL);
    Class cls = NSClassFromString(@"REMStore");
    if (!cls) return nil;
    store = ((id (*)(id, SEL))objc_msgSend)((id)[cls alloc], sel_registerName("init"));
    return store;
}

static NSString *object_uuid(id object_id) {
    NSString *description = object_id ? [object_id description] : @"";
    NSRange range = [description rangeOfString:@"/" options:NSBackwardsSearch];
    if (range.location != NSNotFound && range.location + 1 < description.length) {
        NSString *tail = [description substringFromIndex:range.location + 1];
        NSRange close = [tail rangeOfString:@">"];
        if (close.location != NSNotFound) tail = [tail substringToIndex:close.location];
        return [tail uppercaseString];
    }
    NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:
                               @"0123456789ABCDEFabcdef-"];
    NSMutableString *value = [NSMutableString string];
    for (NSUInteger index = 0; index < description.length; index++) {
        unichar c = [description characterAtIndex:index];
        if ([allowed characterIsMember:c]) [value appendFormat:@"%C", c];
    }
    return [value uppercaseString];
}

static NSString *string_value(id object, const char *selector) {
    SEL sel = sel_registerName(selector);
    if (![object respondsToSelector:sel]) return @"";
    id value = ((id (*)(id, SEL))objc_msgSend)(object, sel);
    return [value isKindOfClass:[NSString class]] ? value : (value ? [value description] : @"");
}

static BOOL bool_value(id object, const char *selector, BOOL fallback) {
    SEL sel = sel_registerName(selector);
    if (![object respondsToSelector:sel]) return fallback;
    return ((BOOL (*)(id, SEL))objc_msgSend)(object, sel);
}

static id kvc_value(id object, NSString *key) {
    @try {
        return [object valueForKey:key];
    } @catch (__unused NSException *exception) {
        return nil;
    }
}

static NSArray *lists(void) {
    id store = rem_store();
    if (!store) return nil;
    NSError *error = nil;
    id value = ((id (*)(id, SEL, NSError **))objc_msgSend)(
        store, sel_registerName("fetchListsForEventKitBridgingWithError:"), &error);
    return [value isKindOfClass:[NSArray class]] ? value : nil;
}

static id find_list(NSString *identifier) {
    for (id list in lists()) {
        if ([object_uuid(((id (*)(id, SEL))objc_msgSend)(list, sel_registerName("objectID")))
             isEqualToString:identifier]) {
            return list;
        }
    }
    return nil;
}

static NSArray *reminders_in_list(id list) {
    NSError *error = nil;
    id value = ((id (*)(id, SEL, NSError **))objc_msgSend)(
        list, sel_registerName("fetchRemindersWithError:"), &error);
    return [value isKindOfClass:[NSArray class]] ? value : nil;
}

static id find_reminder(NSString *identifier, id *out_list) {
    for (id list in lists()) {
        for (id reminder in reminders_in_list(list)) {
            id object_id = ((id (*)(id, SEL))objc_msgSend)(reminder, sel_registerName("objectID"));
            if ([object_uuid(object_id) isEqualToString:identifier]) {
                if (out_list) *out_list = list;
                return reminder;
            }
        }
    }
    return nil;
}

static NSDictionary *list_description(id list) {
    return @{
        @"id": object_uuid(((id (*)(id, SEL))objc_msgSend)(list, sel_registerName("objectID"))),
        @"name": string_value(list, "name"),
        @"reminder_count": @([reminders_in_list(list) count]),
    };
}

static NSDictionary *reminder_description(id reminder, id list) {
    NSNumber *completed = nil;
    id value = kvc_value(reminder, @"completed");
    if ([value isKindOfClass:[NSNumber class]]) completed = value;
    if (!completed) completed = @(bool_value(reminder, "isCompleted", NO));
    id due = kvc_value(reminder, @"dueDate");
    return @{
        @"id": object_uuid(((id (*)(id, SEL))objc_msgSend)(reminder, sel_registerName("objectID"))),
        @"title": string_value(reminder, "titleAsString"),
        @"completed": completed,
        @"due_at_unix": [due isKindOfClass:[NSDate class]] ? @([(NSDate *)due timeIntervalSince1970])
                                                          : (id)[NSNull null],
        @"list_id": list ? object_uuid(((id (*)(id, SEL))objc_msgSend)(list, sel_registerName("objectID"))) : @"",
    };
}

static BOOL save_request(id request, NSError **error) {
    return ((BOOL (*)(id, SEL, NSError **))objc_msgSend)(
        request, sel_registerName("saveSynchronouslyWithError:"), error);
}

static void set_value(id object, NSString *key, id value) {
    @try {
        [object setValue:value forKey:key];
    } @catch (__unused NSException *exception) {
    }
}

static NSString *argument(int argc, char **argv, int index) {
    return index < argc ? [NSString stringWithUTF8String:argv[index]] : nil;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (!rem_store()) return emit(response(@"unavailable", @{@"reason": @"reminderkit_unavailable"}));
        if (argc < 2) return emit(error_response(@"usage"));
        NSString *command = argument(argc, argv, 1);
        if ([command isEqualToString:@"lists"]) {
            NSArray *items = lists();
            if (!items) return emit(response(@"unavailable", @{@"reason": @"reminder_lists_unavailable"}));
            NSMutableArray *rows = [NSMutableArray array];
            for (id list in items) [rows addObject:list_description(list)];
            return emit(response(@"verified", @{@"lists": rows, @"count": @(rows.count)}));
        }
        if ([command isEqualToString:@"list"]) {
            if (argc < 3) return emit(error_response(@"invalid_arguments"));
            NSString *identifier = [argument(argc, argv, 2) uppercaseString];
            id list = find_list(identifier);
            if (!list) return emit(error_response(@"list_not_found"));
            NSArray *items = reminders_in_list(list);
            if (!items) return emit(response(@"unavailable", @{@"reason": @"reminders_unavailable"}));
            NSMutableArray *rows = [NSMutableArray array];
            for (id reminder in items) [rows addObject:reminder_description(reminder, list)];
            return emit(response(@"verified", @{@"reminders": rows, @"count": @(rows.count)}));
        }
        if ([command isEqualToString:@"create"]) {
            if (argc < 4) return emit(error_response(@"invalid_arguments"));
            NSString *list_id = [argument(argc, argv, 2) uppercaseString];
            NSString *title = argument(argc, argv, 3);
            if (title.length == 0 || title.length > 128) return emit(error_response(@"invalid_title"));
            id list = find_list(list_id);
            if (!list) return emit(error_response(@"list_not_found"));
            id request = ((id (*)(id, SEL, id))objc_msgSend)(
                ((id (*)(id, SEL))objc_msgSend)(NSClassFromString(@"REMSaveRequest"), sel_registerName("alloc")),
                sel_registerName("initWithStore:"), rem_store());
            id list_change = ((id (*)(id, SEL, id))objc_msgSend)(
                request, sel_registerName("updateList:"), list);
            ((id (*)(id, SEL, id, id))objc_msgSend)(
                request, sel_registerName("addReminderWithTitle:toListChangeItem:"), title, list_change);
            NSError *error = nil;
            if (!save_request(request, &error))
                return emit(error_response(error.localizedDescription ?: @"save_failed"));
            NSArray *after = reminders_in_list(list);
            NSDictionary *found = nil;
            for (id reminder in after) {
                if ([string_value(reminder, "titleAsString") isEqualToString:title]) {
                    found = reminder_description(reminder, list);
                    break;
                }
            }
            if (!found) return emit(response(@"partial", @{@"reason": @"create_not_confirmed"}));
            return emit(response(@"verified", @{@"reminder": found}));
        }
        if ([command isEqualToString:@"update"] || [command isEqualToString:@"complete"] ||
            [command isEqualToString:@"delete"]) {
            if (argc < 3) return emit(error_response(@"invalid_arguments"));
            NSString *identifier = [argument(argc, argv, 2) uppercaseString];
            id list = nil;
            id reminder = find_reminder(identifier, &list);
            if (!reminder) return emit(error_response(@"reminder_not_found"));
            id request = ((id (*)(id, SEL, id))objc_msgSend)(
                ((id (*)(id, SEL))objc_msgSend)(NSClassFromString(@"REMSaveRequest"), sel_registerName("alloc")),
                sel_registerName("initWithStore:"), rem_store());
            id change = ((id (*)(id, SEL, id))objc_msgSend)(
                request, sel_registerName("updateReminder:"), reminder);
            if ([command isEqualToString:@"update"]) {
                if (argc < 4) return emit(error_response(@"invalid_arguments"));
                NSString *title = argument(argc, argv, 3);
                if (title.length == 0 || title.length > 128) return emit(error_response(@"invalid_title"));
                if ([change respondsToSelector:sel_registerName("setTitleAsString:")]) {
                    ((void (*)(id, SEL, id))objc_msgSend)(change, sel_registerName("setTitleAsString:"), title);
                } else if ([change respondsToSelector:sel_registerName("setTitle:")]) {
                    ((void (*)(id, SEL, id))objc_msgSend)(change, sel_registerName("setTitle:"), title);
                } else {
                    set_value(change, @"title", title);
                }
            } else if ([command isEqualToString:@"complete"]) {
                if ([change respondsToSelector:sel_registerName("setCompleted:")]) {
                    ((void (*)(id, SEL, BOOL))objc_msgSend)(change, sel_registerName("setCompleted:"), YES);
                } else {
                    set_value(change, @"completed", @YES);
                }
            } else {
                if ([change respondsToSelector:sel_registerName("removeFromList")]) {
                    ((void (*)(id, SEL))objc_msgSend)(change, sel_registerName("removeFromList"));
                } else if ([change respondsToSelector:sel_registerName("removeFromListAllowingUndo")]) {
                    ((void (*)(id, SEL))objc_msgSend)(change, sel_registerName("removeFromListAllowingUndo"));
                } else {
                    set_value(change, @"markedForRemoval", @YES);
                }
            }
            NSError *error = nil;
            if (!save_request(request, &error))
                return emit(error_response(error.localizedDescription ?: @"save_failed"));
            if ([command isEqualToString:@"delete"]) {
                id still = find_reminder(identifier, NULL);
                if (still) return emit(response(@"partial", @{@"reason": @"delete_not_confirmed"}));
                return emit(response(@"verified", @{@"deleted": @YES, @"reminder_id": identifier}));
            }
            id still = find_reminder(identifier, NULL);
            if (!still) return emit(response(@"partial", @{@"reason": @"update_not_confirmed"}));
            return emit(response(@"verified", @{@"reminder": reminder_description(still, list)}));
        }
        return emit(error_response(@"unsupported_command"));
    }
}
