#define _GNU_SOURCE
#include <err.h>
#include <errno.h>
#include <fcntl.h>
#include <seccomp.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/utsname.h>
#include <unistd.h>

void export_filter(int fd) {
	scmp_filter_ctx seccomp_ctx = seccomp_init(SCMP_ACT_ALLOW);
	if (!seccomp_ctx) {
		err(1, "seccomp_init failed");
		goto falure;
	}

	if (seccomp_rule_add_exact(seccomp_ctx, SCMP_ACT_ERRNO(EPERM),
	                           SCMP_SYS(ioctl), 1,
	                           SCMP_A1(SCMP_CMP_EQ, TIOCSTI)))
	{
		perror("seccomp_rule_add_exact failed");
		goto falure;
	}

	int rc = seccomp_export_bpf(seccomp_ctx, fd);
	if (rc < 0) {
		perror("failed to export bpf");
		goto falure;
	}

	seccomp_release(seccomp_ctx);
	return;

falure:
	close(fd);
	exit(1);
}

void pysetvar(const char *name, const char *value, size_t size) {
	printf("%s = b'", name);
	for (size_t i = 0; i < size; i++) {
		unsigned char c = (unsigned char)value[i];
		// Print each byte as a two-digit hexadecimal value
		printf("\\x%02x", c);
	}
	printf("'\n");
}

int main(void) {

	int fd = memfd_create("seccomp_filter", 0);
	if (fd == -1) {
		perror("memfd_create");
		exit(1);
	}

	export_filter(fd);

	off_t bpf_len = lseek(fd, 0, SEEK_END);
	lseek(fd, 0, SEEK_SET);

	char *bpf = malloc(bpf_len);
	if (bpf == NULL) {
		perror("malloc");
		close(fd);
		exit(1);
	}

	read(fd, bpf, bpf_len);

	close(fd);

	pysetvar("SECCOMP_FILTER", bpf, bpf_len);

	return 0;
}
