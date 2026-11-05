#import <Foundation/Foundation.h>
#import <EventKit/EventKit.h>
static NSString *mode;
static NSMutableArray *fixture_calendars, *fixture_events;
static NSString *const CAL_ID = @"00000000-0000-4000-8000-000000000001";
static NSString *const NEW_CAL_ID = @"00000000-0000-4000-8000-000000000002";
@interface ICBFakeSource : NSObject
@property(nonatomic, strong) NSString *title, *sourceIdentifier;
@property(nonatomic) EKSourceType sourceType;
@end
@implementation ICBFakeSource @end
static ICBFakeSource *fixture_source;
@interface ICBFakeCalendar : NSObject
@property(nonatomic, strong) NSString *calendarIdentifier, *title;
@property(nonatomic, strong) ICBFakeSource *source;
@property(nonatomic) BOOL allowsContentModifications;
+ (id)calendarForEntityType:(EKEntityType)type eventStore:(id)store;
@end
@implementation ICBFakeCalendar
+ (id)calendarForEntityType:(EKEntityType)type eventStore:(id)store { (void)type; (void)store; return [self new]; }
@end
@interface ICBFakeEvent : NSObject
@property(nonatomic, strong) NSString *eventIdentifier, *title, *notes;
@property(nonatomic, strong) NSDate *startDate, *endDate;
@property(nonatomic, strong) ICBFakeCalendar *calendar;
@property(nonatomic, getter=isAllDay) BOOL allDay;
+ (id)eventWithEventStore:(id)store;
@end
@implementation ICBFakeEvent
+ (id)eventWithEventStore:(id)store { (void)store; return [self new]; }
@end
@interface ICBFakeEventStore : NSObject
+ (EKAuthorizationStatus)authorizationStatusForEntityType:(EKEntityType)type;
- (id)calendarsForEntityType:(EKEntityType)type;
- (id)sources;
- (BOOL)saveCalendar:(ICBFakeCalendar *)calendar commit:(BOOL)commit error:(NSError **)error;
- (id)calendarWithIdentifier:(NSString *)identifier;
- (BOOL)removeCalendar:(id)calendar commit:(BOOL)commit error:(NSError **)error;
- (id)predicateForEventsWithStartDate:(NSDate *)start endDate:(NSDate *)end calendars:(id)calendars;
- (id)eventsMatchingPredicate:(id)predicate;
- (BOOL)saveEvent:(ICBFakeEvent *)event span:(EKSpan)span commit:(BOOL)commit error:(NSError **)error;
- (id)eventWithIdentifier:(NSString *)identifier;
- (BOOL)removeEvent:(id)event span:(EKSpan)span commit:(BOOL)commit error:(NSError **)error;
@end
@implementation ICBFakeEventStore
+ (EKAuthorizationStatus)authorizationStatusForEntityType:(EKEntityType)type { (void)type; return EKAuthorizationStatusAuthorized; }
- (id)calendarsForEntityType:(EKEntityType)type { (void)type; return fixture_calendars; }
- (id)sources { return @[fixture_source]; }
- (BOOL)saveCalendar:(ICBFakeCalendar *)calendar commit:(BOOL)commit error:(NSError **)error {
    (void)commit; (void)error; calendar.calendarIdentifier = NEW_CAL_ID; [fixture_calendars addObject:calendar]; return YES;
}
- (id)calendarWithIdentifier:(NSString *)identifier {
    for (ICBFakeCalendar *calendar in fixture_calendars) if ([calendar.calendarIdentifier isEqual:identifier]) return calendar;
    return nil;
}
- (BOOL)removeCalendar:(id)calendar commit:(BOOL)commit error:(NSError **)error {
    (void)commit; (void)error; [fixture_calendars removeObject:calendar]; return YES;
}
- (id)predicateForEventsWithStartDate:(NSDate *)start endDate:(NSDate *)end calendars:(id)calendars {
    (void)start; (void)end; (void)calendars; return [NSPredicate predicateWithValue:YES];
}
- (id)eventsMatchingPredicate:(id)predicate { (void)predicate; return fixture_events; }
- (BOOL)saveEvent:(ICBFakeEvent *)event span:(EKSpan)span commit:(BOOL)commit error:(NSError **)error {
    (void)span; (void)commit; (void)error; event.eventIdentifier = @"new-event";
    if ([mode isEqual:@"wrong_time"]) event.startDate = [NSDate dateWithTimeIntervalSince1970:0];
    [fixture_events addObject:event]; return YES;
}
- (id)eventWithIdentifier:(NSString *)identifier {
    for (ICBFakeEvent *event in fixture_events) if ([event.eventIdentifier isEqual:identifier]) return event;
    return nil;
}
- (BOOL)removeEvent:(id)event span:(EKSpan)span commit:(BOOL)commit error:(NSError **)error {
    (void)span; (void)commit; (void)error; [fixture_events removeObject:event]; return YES;
}
@end
#define EKEventStore ICBFakeEventStore
#define EKCalendar ICBFakeCalendar
#define EKEvent ICBFakeEvent
#define EKSource ICBFakeSource
#define main icb_calendar_main
#include "../../native/calendar/CalendarBridge.m"
#undef main
int main(int argc, char **argv) { @autoreleasepool {
    mode = argc > 1 ? @(argv[1]) : @"duplicate";
    fixture_source = [ICBFakeSource new]; fixture_source.sourceIdentifier = @"source";
    fixture_source.title = @"Fixture"; fixture_source.sourceType = EKSourceTypeLocal;
    ICBFakeCalendar *old = [ICBFakeCalendar new]; old.calendarIdentifier = CAL_ID;
    old.title = @"Repeated title"; old.source = fixture_source;
    fixture_calendars = [NSMutableArray arrayWithObject:old]; fixture_events = [NSMutableArray array];
    if ([mode isEqual:@"duplicate"]) {
        char *args[] = {"fixture", "create", "Repeated title", "source"}; return icb_calendar_main(4, args);
    }
    if ([mode hasPrefix:@"page"]) {
        for (int index = 0; index < 101; index++) {
            ICBFakeEvent *event = [ICBFakeEvent new]; event.eventIdentifier = [NSString stringWithFormat:@"event-%03d", index];
            event.title = @"Fixture"; event.calendar = old;
            event.startDate = [NSDate dateWithTimeIntervalSince1970:index]; event.endDate = [NSDate dateWithTimeIntervalSince1970:index + 1];
            [fixture_events addObject:event];
        }
        char *args[] = {"fixture", "events", (char *)CAL_ID.UTF8String,
            "2026-11-05T10:00:00Z", "2026-11-05T11:00:00Z", "100", [mode isEqual:@"page2"] ? "100" : "0"};
        return icb_calendar_main(7, args);
    }
    char *args[] = {"fixture", "event_create", (char *)CAL_ID.UTF8String, "Fixture",
        "2026-11-05T10:00:00Z", "2026-11-05T11:00:00Z", "fixture notes"};
    return icb_calendar_main(7, args);
}}
