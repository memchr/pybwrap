#include <errno.h>
#include <linux/audit.h>
#include <linux/bpf.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <termios.h>
#include <unistd.h>

#define NR_ioctl_x86_64 16
#define NR_ioctl_i386   54

struct sock_filter filter[] = {
    /* Load architecture, x86_64 or i386 */
    BPF_STMT(BPF_LD | BPF_W | BPF_ABS, (offsetof(struct seccomp_data, arch))),
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 2, 0),
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_I386, 4, 0),
    /* If neither, kill the process */
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL),

    /* x86_64 Check if it's ioctl */
    BPF_STMT(BPF_LD | BPF_W | BPF_ABS, (offsetof(struct seccomp_data, nr))),
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, NR_ioctl_x86_64, 4, 0),
    /* if not ioctl, ret allow */
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),

    /* i386 Check if it's ioctl */
    BPF_STMT(BPF_LD | BPF_W | BPF_ABS, (offsetof(struct seccomp_data, nr))),
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, NR_ioctl_i386, 1, 0),
    /* if not ioctl, ret allow */
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),

    /* Load ioctl cmd argument */
    BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
             (offsetof(struct seccomp_data, args[1]))),

    /*  Check if it's TIOCSTI */
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, TIOCSTI, 1, 0),
    /* if not TIOSCTI, ret allow */
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),

    /* Block TIOCSTI */
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | (EPERM & SECCOMP_RET_DATA))};

/* Create the filter program structure */
struct sock_fprog prog = {
    .len = sizeof(filter) / sizeof(filter[0]),
    .filter = filter,
};

void pysetvar(const char *name, unsigned char *value, size_t size) {
	printf("%s = b'", name);
	for (size_t i = 0; i < size; i++) {
		// Print each byte as a two-digit hexadecimal value
		printf("\\x%02x", value[i]);
	}
	printf("'\n");
}

int main(void) {
	pysetvar("SECCOMP_BLOCK_TIOCSTI", (unsigned char *)filter, sizeof(filter));
	return 0;
}
