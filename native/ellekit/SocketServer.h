#ifndef ICB_SPRING_SOCKET_SERVER_H
#define ICB_SPRING_SOCKET_SERVER_H
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/time.h>
#include <sys/sysctl.h>
#include <fcntl.h>
#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <dispatch/dispatch.h>

#ifndef ICB_DIRECTORY
#define ICB_DIRECTORY "/var/jb/var/run/ios-control-bridge"
#endif
#define ICB_SOCKET ICB_DIRECTORY "/spring.sock"
#define ICB_LOCK ICB_DIRECTORY "/server.lock"
#define ICB_PROTOCOL "ios-control-bridge.spring.v2"

typedef struct {
    char id[33], action[64], status[24], detail[128];
    int value, socket_fd, readback;
    long long deadline_ms;
    bool execution_started;
} Command;
typedef struct { char id[33]; long long deadline_ms; } ICBSeen;
static void execute(Command *command);

static long long icb_now_ms(void) {
    struct timeval now; gettimeofday(&now, NULL);
    return (long long)now.tv_sec * 1000 + now.tv_usec / 1000;
}
static bool icb_connected(int fd) {
    char byte; ssize_t size = recv(fd, &byte, 1, MSG_PEEK | MSG_DONTWAIT);
    return size > 0 || (size < 0 && (errno == EAGAIN || errno == EWOULDBLOCK));
}
static void execute_on_main(void *context) {
    Command *command = context;
    @autoreleasepool {
        if (icb_now_ms() >= command->deadline_ms || !icb_connected(command->socket_fd)) {
            snprintf(command->status, sizeof(command->status), "unavailable");
            snprintf(command->detail, sizeof(command->detail), "request_expired_or_disconnected");
        } else {
            command->execution_started = true;
            @try { execute(command); }
            @catch (__unused NSException *exception) {
                snprintf(command->status, sizeof(command->status), "unavailable");
                snprintf(command->detail, sizeof(command->detail), "private_call_exception");
            }
        }
    }
}
static bool icb_send(int fd, const char *line) {
    size_t left = strlen(line);
    while (left) {
        ssize_t written = send(fd, line, left, 0);
        if (written <= 0) return false;
        line += written; left -= (size_t)written;
    }
    return true;
}
static bool icb_read(int fd, char *bytes, size_t capacity) {
    size_t used = 0;
    while (used + 1 < capacity) {
        char byte;
        if (recv(fd, &byte, 1, 0) != 1 || byte == 0) return false;
        if (byte == '\n') { bytes[used] = 0; return true; }
        bytes[used++] = byte;
    }
    return false;
}
static bool icb_hex_id(const char *value) {
    return value && strlen(value) == 32 && strspn(value, "0123456789abcdef") == 32;
}
static void icb_reply(int fd, const char *generation, const char *identifier,
                      const char *status, int value, bool unknown, const char *detail) {
    static const char digits[] = "0123456789abcdef";
    char hex[257] = {0}, line[512];
    size_t length = strnlen(detail, 127);
    for (size_t i = 0; i < length; i++) {
        unsigned char c = (unsigned char)detail[i]; hex[i*2] = digits[c>>4]; hex[i*2+1] = digits[c&15];
    }
    snprintf(line, sizeof(line), "%s %s %s %d %d %s\n", generation,
             icb_hex_id(identifier) ? identifier : "-", status, value, unknown ? 1 : 0, length ? hex : "-");
    icb_send(fd, line);
}
static bool icb_allowed(const char *action) {
    const char *actions[] = {"get_low_power", "set_low_power", "get_orientation_lock",
        "set_orientation_lock", "get_wifi", "get_airplane", "get_bluetooth"};
    for (size_t i = 0; i < sizeof(actions)/sizeof(actions[0]); i++)
        if (!strcmp(action, actions[i])) return true;
    return false;
}
/* Fixed ASCII framing avoids Foundation constant objects in this arm64e shim. */
static void icb_handle(int fd, const char *generation, ICBSeen seen[128]) {
    char line[1024]; snprintf(line, sizeof(line), "%s %s\n", ICB_PROTOCOL, generation);
    if (!icb_send(fd, line) || !icb_read(fd, line, sizeof(line))) return;
    char *fields[6] = {0}, *cursor = NULL;
    int count = 0;
    for (char *part = strtok_r(line, " ", &cursor); part && count < 6; part = strtok_r(NULL, " ", &cursor)) fields[count++] = part;
    long long now = icb_now_ms(), deadline = 0; char *end = NULL;
    if (count == 5) { errno = 0; deadline = strtoll(fields[2], &end, 10); }
    bool valid = count == 5 && icb_hex_id(fields[0]) && !strcmp(fields[0], generation)
        && icb_hex_id(fields[1]) && fields[2][0] && end && !*end && errno != ERANGE
        && deadline > now && deadline <= now + 6001 && icb_allowed(fields[3])
        && (!strcmp(fields[4], "0") || !strcmp(fields[4], "1"));
    const char *detail = "invalid_or_expired_request";
    int free_slot = -1;
    if (valid) {
        for (int i = 0; i < 128; i++) {
            if (seen[i].deadline_ms < now) seen[i].id[0] = 0;
            if (seen[i].id[0] && !strcmp(seen[i].id, fields[1])) { valid = false; detail = "duplicate_request"; break; }
            if (!seen[i].id[0] && free_slot < 0) free_slot = i;
        }
        if (valid && free_slot < 0) { valid = false; detail = "bridge_busy"; }
    }
    if (!valid) {
        icb_reply(fd, generation, count > 1 ? fields[1] : NULL, "unavailable", -1, false, detail); return;
    }
    snprintf(seen[free_slot].id, sizeof(seen[free_slot].id), "%s", fields[1]);
    seen[free_slot].deadline_ms = deadline;
    Command command = {0};
    snprintf(command.id, sizeof(command.id), "%s", fields[1]);
    snprintf(command.action, sizeof(command.action), "%s", fields[3]);
    command.value = fields[4][0] == '1'; command.socket_fd = fd; command.readback = -1; command.deadline_ms = deadline;
    dispatch_sync_f(dispatch_get_main_queue(), &command, execute_on_main);
    bool unknown = command.execution_started && !strncmp(command.action, "set_", 4) && strcmp(command.status, "ok") != 0;
    icb_reply(fd, generation, command.id, command.status, command.readback, unknown, command.detail);
}
static void icb_serve(void) {
    char build[64] = {0}; size_t build_size = sizeof(build);
    if (sysctlbyname("kern.osversion", build, &build_size, NULL, 0) || strcmp(build, "20B101")) return;
    struct stat info;
    if (lstat(ICB_DIRECTORY, &info) || !S_ISDIR(info.st_mode) || info.st_uid != geteuid() || (info.st_mode & 0777) != 0700) return;
    int lock_fd = open(ICB_LOCK, O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (lock_fd < 0) return;
    if (fstat(lock_fd, &info) || !S_ISREG(info.st_mode) || info.st_uid != geteuid()
        || info.st_nlink != 1 || (info.st_mode & 0777) != 0600 || flock(lock_fd, LOCK_EX | LOCK_NB)) { close(lock_fd); return; }
    if (!lstat(ICB_SOCKET, &info)) {
        if (!S_ISSOCK(info.st_mode) || info.st_uid != geteuid() || unlink(ICB_SOCKET)) { close(lock_fd); return; }
    } else if (errno != ENOENT) { close(lock_fd); return; }
    int server = socket(AF_UNIX, SOCK_STREAM, 0);
    if (server < 0) { close(lock_fd); return; }
    struct sockaddr_un address = {0}; address.sun_family = AF_UNIX; address.sun_len = sizeof(address);
    snprintf(address.sun_path, sizeof(address.sun_path), "%s", ICB_SOCKET);
    if (bind(server, (struct sockaddr *)&address, sizeof(address)) || chmod(ICB_SOCKET, 0600) || listen(server, 16)) { close(server); close(lock_fd); return; }
    unsigned char random[16]; char generation[33] = {0};
    arc4random_buf(random, sizeof(random));
    for (int i = 0; i < 16; i++) snprintf(generation+i*2, 3, "%02x", random[i]);
    ICBSeen seen[128] = {0};
    for (;;) {
        int fd = accept(server, NULL, NULL);
        if (fd < 0) { if (errno == EINTR) continue; break; }
        uid_t user; gid_t group;
        if (getpeereid(fd, &user, &group) || (user != 0 && user != geteuid())) { close(fd); continue; }
        int yes = 1; struct timeval timeout = {1, 0};
        setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &yes, sizeof(yes));
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        icb_handle(fd, generation, seen); close(fd);
    }
    close(server); close(lock_fd);
}
#endif
