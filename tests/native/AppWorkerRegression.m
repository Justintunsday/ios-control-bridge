#include <stdio.h>
#include <time.h>
#include <unistd.h>

/* No private frameworks or app writes. Exercises lease inheritance and ACK
 * delivery while the native process remains alive for device authentication. */
int main(void) {
    double now = (double)time(NULL);
    printf("{\"schema\":\"ios-control-bridge.apps.v1\",\"source\":\"LaunchServices+StoreServices\","
           "\"command\":\"store_download\",\"status\":\"partial\",\"submitted\":true,"
           "\"bundle_id\":\"dev.ioscontrol.appsfixture\",\"app_id\":\"1\","
           "\"observed_at_unix\":%.0f,\"worker_pid\":%d,\"worker_expires_at_unix\":%.0f}\n", now, getpid(), now+10);
    fflush(stdout);
    sleep(2);
    return 2;
}
