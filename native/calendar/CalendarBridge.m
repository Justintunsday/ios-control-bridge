#import <Foundation/Foundation.h>
#import <EventKit/EventKit.h>
#import <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/*
 * Fixed-purpose EventKit calendar adapter.
 *
 * Commands:
 *   icb-calendar list
 *   icb-calendar create <title> [source-id]
 *   icb-calendar delete <calendar-id>
 *
 * The helper is signed with the CalendarDaemon TCC allow entitlement; without
 * it EventKit authorization is denied and no calendar is readable.
 */

static NSString *const CALENDAR_SCHEMA = @"ios-control-bridge.calendar.v1";
static NSString *const CALENDAR_SOURCE = @"EventKit.EKEventStore";

static int emit(NSDictionary *payload) {
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:&error];
    if (!data) {
        fprintf(stdout, "{\"schema\":\"%s\",\"status\":\"error\",\"reason\":\"json_encoding_failed\"}\n",
                [CALENDAR_SCHEMA UTF8String]);
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
    payload[@"schema"] = CALENDAR_SCHEMA;
    payload[@"status"] = status;
    payload[@"source"] = CALENDAR_SOURCE;
    payload[@"observed_at_unix"] = @((double)time(NULL));
    if (details) [payload addEntriesFromDictionary:details];
    return payload;
}

static NSDictionary *error_response(NSString *reason) {
    return response(@"error", @{@"reason": reason});
}

static NSDate *parse_date(NSString *text) {
    if (!text) return nil;
    NSISO8601DateFormatter *formatter = [[NSISO8601DateFormatter alloc] init];
    formatter.formatOptions = NSISO8601DateFormatWithInternetDateTime;
    NSDate *date = [formatter dateFromString:text];
    if (date) return date;
    formatter.formatOptions = NSISO8601DateFormatWithInternetDateTime |
                               NSISO8601DateFormatWithFractionalSeconds;
    return [formatter dateFromString:text];
}

static NSDictionary *event_description(EKEvent *event) {
    return @{
        @"id": event.eventIdentifier ?: @"",
        @"title": event.title ?: @"",
        @"calendar_id": event.calendar.calendarIdentifier ?: @"",
        @"start": event.startDate ? @([event.startDate timeIntervalSince1970]) : [NSNull null],
        @"end": event.endDate ? @([event.endDate timeIntervalSince1970]) : [NSNull null],
        @"all_day": @(event.isAllDay),
    };
}

static NSDictionary *calendar_description(EKCalendar *calendar) {
    return @{
        @"id": calendar.calendarIdentifier ?: @"",
        @"title": calendar.title ?: @"",
        @"source": calendar.source.title ?: @"",
        @"source_id": calendar.source.sourceIdentifier ?: @"",
        @"allows_modifications": @(calendar.allowsContentModifications),
    };
}

static EKEventStore *make_store(void) {
    EKAuthorizationStatus status = [EKEventStore authorizationStatusForEntityType:EKEntityTypeEvent];
    if (status != EKAuthorizationStatusAuthorized) return nil;
    return [[EKEventStore alloc] init];
}

static NSArray *event_calendars(EKEventStore *store) {
    return [store calendarsForEntityType:EKEntityTypeEvent];
}

static EKSource *choose_source(EKEventStore *store, NSString *identifier) {
    NSArray<EKSource *> *sources = [store sources];
    if (identifier.length) {
        for (EKSource *source in sources) {
            if ([source.sourceIdentifier isEqualToString:identifier]) return source;
        }
        return nil;
    }
    for (EKSource *source in sources) {
        if (source.sourceType == EKSourceTypeCalDAV || source.sourceType == EKSourceTypeExchange) {
            return source;
        }
    }
    return sources.firstObject;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc < 2) return emit(error_response(@"usage"));
        EKEventStore *store = make_store();
        if (!store) return emit(response(@"unavailable", @{@"reason": @"calendar_access_denied"}));
        NSString *command = [NSString stringWithUTF8String:argv[1]];
        if ([command isEqualToString:@"list"]) {
            NSMutableArray *rows = [NSMutableArray array];
            for (EKCalendar *calendar in event_calendars(store)) {
                [rows addObject:calendar_description(calendar)];
            }
            NSMutableArray *sources = [NSMutableArray array];
            for (EKSource *source in [store sources]) {
                [sources addObject:@{@"id": source.sourceIdentifier ?: @"",
                                     @"title": source.title ?: @"",
                                     @"type": @(source.sourceType)}];
            }
            return emit(response(@"verified", @{@"calendars": rows, @"count": @(rows.count),
                                                @"sources": sources}));
        }
        if ([command isEqualToString:@"create"]) {
            if (argc < 3) return emit(error_response(@"missing_title"));
            NSString *title = [NSString stringWithUTF8String:argv[2]];
            if (title.length == 0 || title.length > 64) return emit(error_response(@"invalid_title"));
            NSString *source_id = argc >= 4 ? [NSString stringWithUTF8String:argv[3]] : nil;
            EKSource *source = choose_source(store, source_id);
            if (!source) return emit(error_response(@"source_not_found"));
            EKCalendar *calendar = [EKCalendar calendarForEntityType:EKEntityTypeEvent eventStore:store];
            calendar.title = title;
            calendar.source = source;
            NSError *error = nil;
            BOOL saved = [store saveCalendar:calendar commit:YES error:&error];
            if (!saved) {
                return emit(error_response(error.localizedDescription ?: @"save_failed"));
            }
            EKCalendar *saved_calendar = nil;
            for (EKCalendar *candidate in event_calendars(store)) {
                if ([candidate.calendarIdentifier isEqualToString:calendar.calendarIdentifier] ||
                    [candidate.title isEqualToString:title]) {
                    saved_calendar = candidate;
                    break;
                }
            }
            if (!saved_calendar) return emit(response(@"partial", @{@"reason": @"create_not_confirmed"}));
            return emit(response(@"verified", @{@"calendar": calendar_description(saved_calendar)}));
        }
        if ([command isEqualToString:@"events"]) {
            if (argc < 5) return emit(error_response(@"invalid_arguments"));
            NSString *calendar_id = [NSString stringWithUTF8String:argv[2]];
            NSDate *start = parse_date([NSString stringWithUTF8String:argv[3]]);
            NSDate *end = parse_date([NSString stringWithUTF8String:argv[4]]);
            if (!start || !end || [end compare:start] == NSOrderedAscending)
                return emit(error_response(@"invalid_date_range"));
            EKCalendar *calendar = [store calendarWithIdentifier:calendar_id];
            if (!calendar) return emit(error_response(@"calendar_not_found"));
            NSPredicate *predicate = [store predicateForEventsWithStartDate:start endDate:end
                                                                    calendars:@[calendar]];
            NSArray<EKEvent *> *events = [store eventsMatchingPredicate:predicate];
            NSMutableArray *rows = [NSMutableArray array];
            for (EKEvent *event in events) {
                if (rows.count >= 100) break;
                [rows addObject:event_description(event)];
            }
            return emit(response(@"verified", @{@"events": rows, @"count": @(rows.count)}));
        }
        if ([command isEqualToString:@"event_create"]) {
            if (argc < 6) return emit(error_response(@"invalid_arguments"));
            NSString *calendar_id = [NSString stringWithUTF8String:argv[2]];
            NSString *title = [NSString stringWithUTF8String:argv[3]];
            NSDate *start = parse_date([NSString stringWithUTF8String:argv[4]]);
            NSDate *end = parse_date([NSString stringWithUTF8String:argv[5]]);
            NSString *notes = argc >= 7 ? [NSString stringWithUTF8String:argv[6]] : @"";
            if (title.length == 0 || title.length > 128) return emit(error_response(@"invalid_title"));
            if (!start || !end || [end compare:start] == NSOrderedAscending)
                return emit(error_response(@"invalid_date_range"));
            EKCalendar *calendar = [store calendarWithIdentifier:calendar_id];
            if (!calendar) return emit(error_response(@"calendar_not_found"));
            EKEvent *event = [EKEvent eventWithEventStore:store];
            event.calendar = calendar;
            event.title = title;
            event.startDate = start;
            event.endDate = end;
            if (notes.length) event.notes = notes;
            NSError *error = nil;
            BOOL saved = [store saveEvent:event span:EKSpanThisEvent commit:YES error:&error];
            if (!saved) return emit(error_response(error.localizedDescription ?: @"save_failed"));
            EKEvent *verified = event.eventIdentifier ? [store eventWithIdentifier:event.eventIdentifier] : nil;
            if (!verified) return emit(response(@"partial", @{@"reason": @"create_not_confirmed"}));
            return emit(response(@"verified", @{@"event": event_description(verified)}));
        }
        if ([command isEqualToString:@"event_delete"]) {
            if (argc < 3) return emit(error_response(@"invalid_arguments"));
            NSString *event_id = [NSString stringWithUTF8String:argv[2]];
            EKEvent *event = [store eventWithIdentifier:event_id];
            if (!event) return emit(error_response(@"event_not_found"));
            NSError *error = nil;
            BOOL removed = [store removeEvent:event span:EKSpanThisEvent commit:YES error:&error];
            if (!removed) return emit(error_response(error.localizedDescription ?: @"remove_failed"));
            if ([store eventWithIdentifier:event_id]) {
                return emit(response(@"partial", @{@"reason": @"delete_not_confirmed"}));
            }
            return emit(response(@"verified", @{@"deleted": @YES, @"event_id": event_id}));
        }
        if ([command isEqualToString:@"delete"]) {
            if (argc < 3) return emit(error_response(@"missing_calendar_id"));
            NSString *identifier = [NSString stringWithUTF8String:argv[2]];
            EKCalendar *calendar = [store calendarWithIdentifier:identifier];
            if (!calendar) return emit(error_response(@"calendar_not_found"));
            NSError *error = nil;
            BOOL removed = [store removeCalendar:calendar commit:YES error:&error];
            if (!removed) return emit(error_response(error.localizedDescription ?: @"remove_failed"));
            if ([store calendarWithIdentifier:identifier]) {
                return emit(response(@"partial", @{@"reason": @"delete_not_confirmed"}));
            }
            return emit(response(@"verified", @{@"deleted": @YES, @"calendar_id": identifier}));
        }
        return emit(error_response(@"unsupported_command"));
    }
}
