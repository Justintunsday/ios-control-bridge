#import <Foundation/Foundation.h>
static NSString *mode;
static BOOL saved;
static NSMutableArray *items;
static NSString *const OLD_ID = @"00000000-0000-4000-8000-000000000001";
static NSString *const NEW_ID = @"00000000-0000-4000-8000-000000000002";
static NSString *const LIST_ID = @"00000000-0000-4000-8000-000000000003";
@interface ICBFakeObjectID : NSObject
@property(nonatomic, strong) NSUUID *uuid;
@end
@implementation ICBFakeObjectID @end
static id identifier(NSString *text) {
    ICBFakeObjectID *value = [ICBFakeObjectID new];
    value.uuid = [[NSUUID alloc] initWithUUIDString:text]; return value;
}
@interface ICBFakeReminder : NSObject
@property(nonatomic, strong) id objectID;
- (id)titleAsString;
- (BOOL)isCompleted;
@end
@implementation ICBFakeReminder
- (id)titleAsString { return @"Repeated title"; }
- (BOOL)isCompleted { return NO; }
@end
@interface ICBFakeList : NSObject
- (id)objectID;
- (id)fetchRemindersWithError:(NSError **)error;
@end
@implementation ICBFakeList
- (id)objectID { return identifier(LIST_ID); }
- (id)fetchRemindersWithError:(NSError **)error {
    if (saved && [mode isEqual:@"failure"]) {
        if (error) *error = [NSError errorWithDomain:@"fixture" code:1 userInfo:nil];
        return nil;
    }
    return items;
}
@end
@interface ICBFakeReminderStore : NSObject
- (id)fetchListsForEventKitBridgingWithError:(NSError **)error;
@end
@implementation ICBFakeReminderStore
- (id)fetchListsForEventKitBridgingWithError:(NSError **)error { (void)error; return @[[ICBFakeList new]]; }
@end
@interface ICBFakeChange : NSObject
- (id)objectID;
- (void)removeFromList;
@end
@implementation ICBFakeChange
- (id)objectID { return [mode isEqual:@"missing_id"] ? nil : identifier(NEW_ID); }
- (void)removeFromList { if ([mode isEqual:@"absent"]) [items removeAllObjects]; }
@end
/* Production rem_store() is replaced by the local object before any dlopen. */
@interface REMSaveRequest : NSObject
- (id)initWithStore:(id)store;
- (id)updateList:(id)list;
- (id)updateReminder:(id)reminder;
- (id)addReminderWithTitle:(id)title toListChangeItem:(id)list;
- (BOOL)saveSynchronouslyWithError:(NSError **)error;
@end
@implementation REMSaveRequest
- (id)initWithStore:(id)store { (void)store; return [super init]; }
- (id)updateList:(id)list { return list; }
- (id)updateReminder:(id)reminder { (void)reminder; return [ICBFakeChange new]; }
- (id)addReminderWithTitle:(id)title toListChangeItem:(id)list { (void)title; (void)list; return [ICBFakeChange new]; }
- (BOOL)saveSynchronouslyWithError:(NSError **)error {
    (void)error; saved = YES;
    if ([mode isEqual:@"duplicate"]) {
        ICBFakeReminder *value = [ICBFakeReminder new]; value.objectID = identifier(NEW_ID); [items addObject:value];
    }
    return YES;
}
@end
#define main icb_reminder_main
#include "../../native/reminders/RemindersBridge.m"
#undef main
int main(int argc, char **argv) { @autoreleasepool {
    mode = argc > 1 ? @(argv[1]) : @"failure";
    reminder_store = [ICBFakeReminderStore new];
    ICBFakeReminder *old = [ICBFakeReminder new]; old.objectID = identifier(OLD_ID);
    items = [NSMutableArray arrayWithObject:old];
    if ([mode isEqual:@"duplicate"] || [mode isEqual:@"missing_id"]) {
        char *args[] = {"fixture", "create", (char *)LIST_ID.UTF8String, "Repeated title"};
        return icb_reminder_main(4, args);
    }
    char *args[] = {"fixture", "delete", (char *)OLD_ID.UTF8String};
    return icb_reminder_main(3, args);
}}
