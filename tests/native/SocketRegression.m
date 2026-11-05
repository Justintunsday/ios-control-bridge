#import <Foundation/Foundation.h>
#include <dispatch/dispatch.h>
#include <unistd.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include "../../native/ellekit/SocketServer.h"
static int calls, setting;
static void execute(Command *command) {
    if (!strcmp(command->action, "set_low_power")) { calls++; setting = command->value; }
    command->readback = !strcmp(command->action, "get_orientation_lock") ? calls : setting;
    snprintf(command->status, sizeof(command->status), "ok");
    snprintf(command->detail, sizeof(command->detail), "fixture");
}
static void *serve(void *unused) { (void)unused; @autoreleasepool { icb_serve(); } return NULL; }
int main(int argc, char **argv) {
    pthread_t thread; pthread_create(&thread, NULL, serve, NULL); pthread_detach(thread);
    if (argc > 1 && !strcmp(argv[1], "delay")) usleep(500000);
    dispatch_main();
}
