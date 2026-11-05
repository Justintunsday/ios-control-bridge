#import <Foundation/Foundation.h>
static NSString *mode;
static BOOL removed;
@interface ICBFakeAlarm : NSObject
- (id)alarmID;
@end
@implementation ICBFakeAlarm
- (id)alarmID { return [[NSUUID alloc] initWithUUIDString:@"00000000-0000-4000-8000-000000000001"]; }
@end
@interface ICBFakeAlarmManager : NSObject
- (id)alarmsSync;
- (void)removeAlarm:(id)alarm;
@end
@implementation ICBFakeAlarmManager
- (id)alarmsSync {
    if (removed && [mode isEqual:@"failure"]) return nil;
    if (removed && [mode isEqual:@"absent"]) return @[];
    return @[[ICBFakeAlarm new]];
}
- (void)removeAlarm:(id)alarm { (void)alarm; removed = YES; }
@end
#define main icb_alarm_main
#include "../../native/alarms/AlarmsBridge.m"
#undef main
int main(int argc, char **argv) { @autoreleasepool {
    mode = argc > 1 ? @(argv[1]) : @"failure";
    manager = [ICBFakeAlarmManager new];
    char *args[] = {"fixture", "delete", "00000000-0000-4000-8000-000000000001"};
    return icb_alarm_main(3, args);
}}
