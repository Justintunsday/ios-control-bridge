#import <Foundation/Foundation.h>
id _Nullable ICBCreateActivityCenter(void);
id _Nullable ICBReadActivityCenterBridge(id _Nonnull center);
id _Nullable ICBObserveActivities(id _Nonnull center, void (^_Nonnull callback)(void));
id _Nonnull ICBDescribeObject(id _Nonnull object);
BOOL ICBInvalidateObserver(id _Nonnull token);
id _Nonnull ICBQueryActivityOutput(id _Nonnull connection, NSString * _Nonnull activityID, BOOL includePayloads);
